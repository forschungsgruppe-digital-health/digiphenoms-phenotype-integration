"""
DigiPhenoMS FHIR Integration — Configuration-driven CSV-to-FHIR R4 Pipeline
============================================================================

This module provides a loosely coupled, configuration-driven integration engine
that transforms CSV data (conforming to the DigiPhenoMS data schemas) into
FHIR R4 resources and optionally submits them to a HAPI FHIR server via the
custom ``$cohort-submit`` operation.

Architecture:
    - MappingConfig: Loads and validates YAML mapping configurations
    - ResourceBuilder: Constructs FHIR R4 resources from CSV rows + config
    - FHIRMapper: Orchestrates the mapping for a single CSV source
    - Pipeline: Executes all mapping steps in dependency order
    - CohortSubmitClient: Submits mapped resources to a HAPI FHIR server

Dependencies:
    pip install pyyaml pandas fhir.resources    # mapping only
    pip install pyyaml pandas fhir.resources httpx    # mapping + submit

Usage as pipeline step:
    from digiphenoms_fhir import Pipeline
    pipeline = Pipeline(config_dir="config/")
    results = pipeline.run(data_dir="data/", output_dir="output/")

Usage standalone:
    digiphenoms-fhir --config config/ --data data/ --output output/
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from fhir.resources.R4B.identifier import Identifier as FHIRIdentifier
from fhir.resources.R4B.operationoutcome import OperationOutcome as FHIROperationOutcome

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("digiphenoms.fhir_mapper")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESOURCE_IDENTIFIER_SYSTEMS: dict[str, str] = {
    "Patient": "patient_system",
    "Condition": "patient_system",
    "Encounter": "assessment_system",
    "Device": "module_system",
    "Observation": "module_system",
    "DiagnosticReport": "patient_system",
    "QuestionnaireResponse": "module_system",
}


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------
@dataclass
class MappingConfig:
    """Represents a parsed mapping YAML configuration."""

    source: dict
    targets: list[dict]
    raw: dict  # Full YAML for advanced access

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MappingConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls(
            source=raw.get("source", {}),
            targets=raw.get("targets", []),
            raw=raw,
        )


@dataclass
class PipelineConfig:
    """Represents the pipeline.yaml configuration."""

    namespaces: dict
    input_cfg: dict
    output_cfg: dict
    steps: list[dict]
    default_organization: dict
    cohort_submit: dict
    ml_server: dict
    data_quality: dict
    raw: dict

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PipelineConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls(
            namespaces=raw.get("namespaces", {}),
            input_cfg=raw.get("input", {}),
            output_cfg=raw.get("output", {}),
            steps=raw.get("pipeline", {}).get("steps", raw.get("steps", [])),
            default_organization=raw.get("default_organization", {}),
            cohort_submit=raw.get("cohort_submit", {}),
            ml_server=raw.get("ml_server", {}),
            data_quality=raw.get("data_quality", {}),
            raw=raw,
        )


@dataclass
class TerminologyMap:
    """Loads a terminology/concept map YAML for code translation."""

    mappings: dict
    source_system: str
    target_systems: dict

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TerminologyMap":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        cm = raw.get("concept_map", raw)
        return cls(
            mappings=cm.get("mappings", {}),
            source_system=cm.get("source_system", ""),
            target_systems=cm.get("target_systems", {}),
        )

    def translate(self, code: str) -> dict:
        """Translate a source code to target coding.

        Looks up the code in the mappings and returns a FHIR-compatible coding
        dict.  Supports different terminology key conventions (snomed_code,
        loinc_code, icd10_code) by probing common suffixes.
        """
        entry = self.mappings.get(code, self.mappings.get("_default", {}))
        resolved_code = code
        resolved_display = code
        for prefix in ("snomed", "loinc", "icd10"):
            if f"{prefix}_code" in entry:
                resolved_code = entry[f"{prefix}_code"]
                resolved_display = entry.get(f"{prefix}_display", resolved_code)
                break
        return {
            "system": self.target_systems.get("primary", ""),
            "code": resolved_code,
            "display": resolved_display,
        }


# ---------------------------------------------------------------------------
# Resource builder
# ---------------------------------------------------------------------------
class ResourceBuilder:
    """
    Builds FHIR R4 resource dicts from a CSV row and a target mapping config.

    This class intentionally produces plain dicts (not fhir.resources objects)
    for maximum flexibility.  A validation step can optionally parse them via
    fhir.resources for schema enforcement.
    """

    def __init__(
        self,
        pipeline_cfg: PipelineConfig,
        config_dir: Path,
    ):
        self.pipeline_cfg = pipeline_cfg
        self.config_dir = config_dir
        self._terminology_cache: dict[str, TerminologyMap] = {}
        self._fix_chronology = pipeline_cfg.data_quality.get("fix_chronology", True)

    # -- public API ----------------------------------------------------------

    def build(
        self,
        row: pd.Series,
        target: dict,
        extra_context: dict | None = None,
    ) -> dict | None:
        """Build a single FHIR resource dict from a CSV row + target config."""
        resource: dict[str, Any] = {
            "resourceType": target["resource_type"],
        }

        # Resource ID (sanitized to the FHIR id pattern [A-Za-z0-9\-.]{1,64})
        resource["id"] = self._sanitize_id(
            self._interpolate(target.get("id_template", ""), row, extra_context)
        )

        # Meta / profile
        if "profile" in target:
            resource["meta"] = {
                "profile": [target["profile"]],
            }

        # Static fields
        for key, value in target.get("static_fields", {}).items():
            resource[key] = self._build_static(key, value)

        # Status mapping
        if "status_mapping" in target:
            resource["status"] = self._map_status(row, target["status_mapping"])

        # Field mappings
        for fm in target.get("field_mappings", []):
            self._apply_field_mapping(resource, row, fm, extra_context)

        # Primary value
        if "primary_value" in target:
            pv = target["primary_value"]
            val = self._get_value(row, pv["source"])
            if val is not None:
                try:
                    resource["valueQuantity"] = {
                        "value": float(val),
                        "unit": pv.get("unit", ""),
                        "system": pv.get("unit_system", "http://unitsofmeasure.org"),
                    }
                except (ValueError, TypeError):
                    logger.warning("Cannot convert primary_value %r to float", val)

        # Components
        if "components" in target:
            components = []
            for comp_cfg in target["components"]:
                comp = self._build_component(row, comp_cfg)
                if comp is not None:
                    components.append(comp)
            if components:
                resource["component"] = components

        # Result references (for DiagnosticReport)
        if "result_references" in target:
            resource["result"] = [
                {
                    "reference": self._sanitize_reference(
                        self._interpolate(ref, row, extra_context)
                    ),
                }
                for ref in target["result_references"]
            ]

        # Identifier — ensure system is set for conditional create/update
        system_key = RESOURCE_IDENTIFIER_SYSTEMS.get(target["resource_type"])
        if system_key:
            system_uri = self.pipeline_cfg.namespaces.get(system_key, "")
            if system_uri:
                if "identifier" in resource and resource["identifier"]:
                    for ident in resource["identifier"]:
                        if isinstance(ident, dict) and "system" not in ident:
                            ident["system"] = system_uri
                elif resource.get("id"):
                    resource["identifier"] = [
                        FHIRIdentifier(
                            system=system_uri, value=resource["id"]
                        ).model_dump(exclude_none=True)
                    ]

        return self._validate_resource(resource)

    def build_grouped(
        self,
        group_df: pd.DataFrame,
        target: dict,
        group_keys: dict,
    ) -> dict | None:
        """Build a resource from a group of rows (e.g., QuestionnaireResponse)."""
        first_row = group_df.iloc[0]
        resource = self.build(first_row, target, extra_context=group_keys)
        if resource is None:
            return None

        # Build items from rows
        if "items_from_rows" in target:
            items_cfg = target["items_from_rows"]
            items = []
            for _, row in group_df.iterrows():
                # Apply filter if specified
                if "filter" in items_cfg:
                    flt = items_cfg["filter"]
                    if str(row.get(flt["column"], "")) != str(flt["value"]):
                        continue

                item = {}
                if "linkId_template" in items_cfg:
                    item["linkId"] = self._interpolate(
                        items_cfg["linkId_template"], row
                    )
                elif "linkId_source" in items_cfg:
                    item["linkId"] = str(row.get(items_cfg["linkId_source"], ""))
                if "text_source" in items_cfg:
                    text = row.get(items_cfg["text_source"])
                    if pd.notna(text):
                        item["text"] = str(text)

                answer_val = row.get(items_cfg.get("answer_source", ""))
                if pd.notna(answer_val):
                    answer = {}
                    atype = items_cfg.get("answer_type", "valueString")
                    if atype == "valueInteger":
                        try:
                            answer[atype] = int(float(answer_val))
                        except (ValueError, TypeError):
                            answer["valueString"] = str(answer_val)
                    else:
                        answer[atype] = str(answer_val)

                    # Add display if available
                    if "display_source" in items_cfg:
                        disp = row.get(items_cfg["display_source"])
                        if pd.notna(disp):
                            answer["_display"] = str(disp)

                    item["answer"] = [answer]

                if item:
                    items.append(item)

            if items:
                resource["item"] = items

        # Re-validate after adding grouped fields (items etc.)
        return self._validate_resource(resource) if resource else resource

    # -- internal helpers ----------------------------------------------------

    def _interpolate(
        self, template: str, row: pd.Series, extra: dict | None = None
    ) -> str:
        """Interpolate {column_name} placeholders from row data."""
        result = template
        # Replace from extra context first
        if extra:
            for k, v in extra.items():
                result = result.replace(f"{{{k}}}", str(v))
        # Replace from row
        for col in row.index:
            if f"{{{col}}}" in result:
                val = row[col]
                result = result.replace(
                    f"{{{col}}}", str(val) if pd.notna(val) else ""
                )
        return result

    def _get_value(self, row: pd.Series, col: str) -> Any:
        """Get a value from a row, returning None for missing/NaN."""
        val = row.get(col)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return val

    @staticmethod
    def _sanitize_id(value: str) -> str:
        """Normalize a string to a valid FHIR resource id.

        FHIR R4B ids must match ``[A-Za-z0-9\\-.]{1,64}`` — source values
        (e.g. Neuro-QoL subtest keys like ``upper_limbs`` or arbitrary
        patient UUIDs from synthetic datasets) may contain other characters,
        which HAPI rejects on import.
        """
        if not value:
            return value
        return re.sub(r"[^A-Za-z0-9\-.]", "-", str(value))[:64]

    @classmethod
    def _sanitize_reference(cls, reference: str) -> str:
        """Sanitize the id part of a ``ResourceType/id`` literal reference."""
        if "/" in reference:
            ref_type, ref_id = reference.split("/", 1)
            return f"{ref_type}/{cls._sanitize_id(ref_id)}"
        return reference

    def _build_static(self, key: str, value: Any) -> Any:
        """Build a static field value (handles nested dicts for CodeableConcept etc.)."""
        if isinstance(value, dict) and "system" in value and "code" in value:
            cc: dict[str, Any] = {"coding": [value]}
            display = value.get("display", "")
            if display:
                cc["text"] = display
            return cc
        if isinstance(value, list):
            return [self._build_static(key, v) for v in value]
        return value

    def _map_status(self, row: pd.Series, cfg: dict) -> str:
        """Map a CSV value to FHIR status."""
        source_val = str(row.get(cfg["source"], ""))
        mapping = cfg.get("mapping", {})
        return mapping.get(source_val, cfg.get("default", "unknown"))

    def _apply_field_mapping(
        self,
        resource: dict,
        row: pd.Series,
        fm: dict,
        extra: dict | None = None,
    ):
        """Apply a single field mapping to the resource dict."""
        val = self._get_value(row, fm["source"])

        # Check condition
        if "condition" in fm:
            cond = fm["condition"]
            if "is not empty" in cond and val is None:
                return
            if "is not empty" in cond and str(val).strip() == "":
                return

        if val is None:
            return

        target = fm["target"]
        ftype = fm.get("type", "string")

        if ftype == "reference":
            ref_type = fm["reference_type"]
            if "id_template" in fm:
                ref_id = fm["id_template"].replace("{value}", str(val))
            else:
                ref_id = str(val)
            self._set_nested(
                resource,
                target,
                {"reference": f"{ref_type}/{self._sanitize_id(ref_id)}"},
            )

        elif ftype == "datetime":
            fmt = fm.get("format")
            try:
                if fmt:
                    dt = datetime.strptime(str(val), fmt)
                    self._set_nested(resource, target, dt.isoformat())
                else:
                    self._set_nested(resource, target, str(val))
            except (ValueError, TypeError):
                self._set_nested(resource, target, str(val))

        elif ftype == "date":
            fmt = fm.get("format")
            target_fmt = fm.get("target_format", "%Y-%m-%d")
            try:
                dt = datetime.strptime(str(val), fmt)
                self._set_nested(resource, target, dt.strftime(target_fmt))
            except (ValueError, TypeError):
                self._set_nested(resource, target, str(val))

        elif ftype == "code":
            value_map = fm.get("value_map", {})
            mapped = value_map.get(str(val), str(val))
            if "code_system" in fm:
                self._set_nested(
                    resource,
                    target,
                    {"system": fm["code_system"], "code": mapped},
                )
            else:
                self._set_nested(resource, target, mapped)

        elif ftype == "extension":
            ext = {
                "url": fm["extension_url"],
                fm.get("value_type", "valueString"): val
                if fm.get("value_type") != "valueInteger"
                else int(float(val)),
            }
            self._set_nested(resource, target, ext)

        elif ftype == "coded":
            term_map_path = fm.get("terminology_map")
            if term_map_path:
                tmap = self._load_terminology(term_map_path)
                coding = tmap.translate(str(val))
                self._set_nested(resource, target, {"coding": [coding]})
            else:
                self._set_nested(resource, target, str(val))

        elif ftype == "string":
            prefix = fm.get("prefix", "")
            self._set_nested(resource, target, prefix + str(val))

        else:
            self._set_nested(resource, target, val)

    def _build_component(self, row: pd.Series, comp_cfg: dict) -> dict | None:
        """Build an Observation.component from a row and component config."""
        val = self._get_value(row, comp_cfg["source"])
        if val is None:
            return None

        component: dict[str, Any] = {
            "code": {"coding": [comp_cfg["code"]]},
        }

        vtype = comp_cfg.get("value_type", "valueQuantity")
        if vtype == "valueQuantity":
            try:
                component["valueQuantity"] = {
                    "value": float(val),
                    "unit": comp_cfg.get("unit", ""),
                    "system": comp_cfg.get(
                        "unit_system", "http://unitsofmeasure.org"
                    ),
                }
            except (ValueError, TypeError):
                return None
        elif vtype == "valueBoolean":
            component["valueBoolean"] = str(val).lower() in ("true", "1", "yes")
        elif vtype == "valueCodeableConcept":
            component["valueCodeableConcept"] = {
                "coding": [
                    {
                        "system": comp_cfg.get("code_system", ""),
                        "code": str(val),
                        "display": str(val),
                    }
                ]
            }
        elif vtype == "valueString":
            component["valueString"] = str(val)
        elif vtype == "valueInteger":
            try:
                component["valueInteger"] = int(float(val))
            except (ValueError, TypeError):
                return None

        return component

    def _set_nested(self, d: dict, path: str, value: Any):
        """
        Set a value in a nested dict using dot/bracket notation.
        E.g., 'identifier[0].value' → d['identifier'][0]['value'] = value
        """
        parts = path.split(".")
        current = d
        for i, part in enumerate(parts):
            # Handle array index
            match = re.match(r"(\w*)\[(\d+)\]", part)
            if match:
                key = match.group(1)
                idx = int(match.group(2))
                if key:
                    if key not in current:
                        current[key] = []
                    current = current[key]
                # Ensure list is long enough
                while len(current) <= idx:
                    current.append({})
                if i == len(parts) - 1:
                    current[idx] = value
                else:
                    if not isinstance(current[idx], dict):
                        current[idx] = {}
                    current = current[idx]
            else:
                if i == len(parts) - 1:
                    current[part] = value
                else:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

    def _validate_resource(self, resource_dict: dict) -> dict | None:
        """Validate and normalize a resource dict through its FHIR R4B model.

        Applies pre-validation cleanup (empty strings, structural fixes) before
        passing through the ``fhir.resources.R4B`` pydantic model.  Returns the
        validated dict, or the original dict with a warning on failure.

        The dump uses ``mode="json"`` so every value is JSON-native (datetimes
        as FHIR strings, decimals as numbers) — resources must survive
        ``json.dumps`` without custom encoders for bundle files and for the
        ``$cohort-submit`` HTTP body.
        """
        if self._fix_chronology:
            self._fix_period_chronology(resource_dict)
        self._cleanup_resource(resource_dict)
        resource_type = resource_dict.get("resourceType", "")
        try:
            mod = importlib.import_module(
                f"fhir.resources.R4B.{resource_type.lower()}"
            )
            model_cls = getattr(mod, resource_type)
            model = model_cls.model_validate(resource_dict)
            return model.model_dump(mode="json", exclude_none=True)
        except Exception as exc:
            logger.warning("FHIR model validation for %s: %s", resource_type, exc)
            return resource_dict

    @staticmethod
    def _fix_period_chronology(resource: dict) -> None:
        """Swap inverted ``start``/``end`` pairs in Period-like structures.

        The synthetic datasets from the ML server do not guarantee
        chronological timestamps (an assessment's end may precede its
        start). FHIR requires ``Period.start <= Period.end`` (invariant
        per-1), so inverted pairs are swapped in place. Controlled by
        ``data_quality.fix_chronology`` in pipeline.yaml (default: on).
        """

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                start, end = obj.get("start"), obj.get("end")
                if isinstance(start, str) and isinstance(end, str):
                    try:
                        if datetime.fromisoformat(end) < datetime.fromisoformat(start):
                            obj["start"], obj["end"] = end, start
                            logger.warning(
                                "Swapped inverted period (%s > %s) in %s/%s",
                                start,
                                end,
                                resource.get("resourceType", "?"),
                                resource.get("id", "?"),
                            )
                    except (ValueError, TypeError):
                        pass
                for v in obj.values():
                    _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(resource)

    @staticmethod
    def _cleanup_resource(resource: dict) -> None:
        """In-place pre-validation cleanup for common FHIR R4B issues.

        Fixes structural patterns that the YAML-driven builder produces but
        that do not pass strict R4B model validation:

        * Remove empty ``text`` fields from CodeableConcepts.
        * Wrap bare-dict ``category`` in a list.
        * Convert CodeableConcept-style ``class`` to Coding for Encounter.
        * Flatten ``additional_codings`` into the parent ``coding`` array.
        * Remove non-standard ``_display`` fields from answer dicts.
        * Fix ``meta.lastUpdated`` to ISO 8601 Instant format.
        * Normalise ``communication[].language.coding[].code`` to string.
        """
        # --- strip empty text from CodeableConcept-like dicts ---------------
        def _strip_empty_text(obj: Any) -> None:
            if isinstance(obj, dict):
                if "text" in obj and obj["text"] == "":
                    del obj["text"]
                for v in obj.values():
                    _strip_empty_text(v)
            elif isinstance(obj, list):
                for item in obj:
                    _strip_empty_text(item)

        _strip_empty_text(resource)

        # --- category: dict → [dict] (R4B expects a list) ------------------
        cat = resource.get("category")
        if isinstance(cat, dict):
            resource["category"] = [cat]

        # --- Encounter.class: CodeableConcept → Coding ----------------------
        if resource.get("resourceType") == "Encounter":
            cls = resource.get("class")
            if isinstance(cls, dict) and "coding" in cls:
                coding = cls["coding"][0] if cls["coding"] else {}
                resource["class"] = coding

        # --- flatten additional_codings into parent coding array ------------
        def _flatten_codings(obj: Any) -> None:
            if isinstance(obj, dict):
                if "coding" in obj and isinstance(obj["coding"], list):
                    flattened = []
                    for coding_entry in obj["coding"]:
                        if isinstance(coding_entry, dict):
                            extras = coding_entry.pop("additional_codings", None)
                            # Also handle nested 'coding' within a coding entry
                            nested = coding_entry.pop("coding", None)
                            if coding_entry:  # skip husks emptied by the pops
                                flattened.append(coding_entry)
                            if extras and isinstance(extras, list):
                                flattened.extend(extras)
                            if nested and isinstance(nested, list):
                                flattened.extend(nested)
                        else:
                            flattened.append(coding_entry)
                    obj["coding"] = flattened
                for v in obj.values():
                    _flatten_codings(v)
            elif isinstance(obj, list):
                for item in obj:
                    _flatten_codings(item)

        _flatten_codings(resource)

        # --- remove non-standard _display from answer dicts -----------------
        def _strip_display(obj: Any) -> None:
            if isinstance(obj, dict):
                obj.pop("_display", None)
                for v in obj.values():
                    _strip_display(v)
            elif isinstance(obj, list):
                for item in obj:
                    _strip_display(item)

        _strip_display(resource)

        # --- fix meta.lastUpdated to ISO 8601 Instant ----------------------
        meta = resource.get("meta")
        if isinstance(meta, dict) and "lastUpdated" in meta:
            raw = meta["lastUpdated"]
            if isinstance(raw, str) and not raw[:4].isdigit():
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(raw)
                    meta["lastUpdated"] = dt.isoformat()
                except Exception:
                    pass

        # --- fix DateTime fields missing timezone offset --------------------
        _datetime_fields = ("authored", "effectiveDateTime")
        for field_name in _datetime_fields:
            val = resource.get(field_name)
            if isinstance(val, str) and re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", val):
                resource[field_name] = val + "+00:00"

        # --- Device: drop entries whose mapped value was missing ------------
        # Static fields pre-seed deviceName[].type / property[].type (both
        # mandatory in R4B); if the CSV row had no name/value the husk entry
        # would fail validation.
        if resource.get("resourceType") == "Device":
            names = resource.get("deviceName")
            if isinstance(names, list):
                kept = [n for n in names if isinstance(n, dict) and n.get("name")]
                if kept:
                    resource["deviceName"] = kept
                else:
                    resource.pop("deviceName", None)
            props = resource.get("property")
            if isinstance(props, list):
                kept = [
                    p
                    for p in props
                    if isinstance(p, dict)
                    and p.get("type")
                    and (p.get("valueQuantity") or p.get("valueCode"))
                ]
                if kept:
                    resource["property"] = kept
                else:
                    resource.pop("property", None)

        # --- QuestionnaireResponse.identifier: list → single (R4B: 0..1) -----
        rt = resource.get("resourceType")
        if rt == "QuestionnaireResponse":
            ident = resource.get("identifier")
            if isinstance(ident, list) and len(ident) == 1:
                resource["identifier"] = ident[0]

        # --- communication[].language.coding[].code must be a string --------
        for comm in resource.get("communication", []):
            lang = comm.get("language", {})
            for coding in lang.get("coding", []):
                if isinstance(coding.get("code"), dict):
                    code_dict = coding["code"]
                    if "code" in code_dict:
                        coding["code"] = code_dict["code"]
                    if "system" not in coding and "system" in code_dict:
                        coding["system"] = code_dict["system"]

    def _load_terminology(self, rel_path: str) -> TerminologyMap:
        """Load and cache a terminology map."""
        if rel_path not in self._terminology_cache:
            full_path = self.config_dir / rel_path
            self._terminology_cache[rel_path] = TerminologyMap.from_yaml(full_path)
        return self._terminology_cache[rel_path]


# ---------------------------------------------------------------------------
# FHIR Mapper (single source type)
# ---------------------------------------------------------------------------
class FHIRMapper:
    """Maps a single CSV file to FHIR resources using a mapping config."""

    def __init__(
        self,
        mapping_config: MappingConfig,
        builder: ResourceBuilder,
    ):
        self.config = mapping_config
        self.builder = builder

    def map_file(self, csv_path: str | Path) -> list[dict]:
        """Map all rows in a CSV file to FHIR resources."""
        logger.info(f"Mapping file: {csv_path}")
        df = pd.read_csv(csv_path, encoding="utf-8", low_memory=False)
        logger.info(f"  Loaded {len(df)} rows")

        resources = []
        for target in self.config.targets:
            group_by = target.get("group_by") or self.config.source.get("group_by")

            if group_by:
                resources.extend(self._map_grouped(df, target, group_by))
            else:
                resources.extend(self._map_rows(df, target))

        logger.info(f"  Generated {len(resources)} resources")
        return resources

    def _map_rows(self, df: pd.DataFrame, target: dict) -> list[dict]:
        """Map individual rows to resources."""
        results = []
        seen_ids = set()

        for _, row in df.iterrows():
            # Deduplicate if configured
            dedup_key = target.get("deduplicate_by")
            if dedup_key:
                key_val = row.get(dedup_key)
                if pd.notna(key_val) and str(key_val) in seen_ids:
                    continue
                if pd.notna(key_val):
                    seen_ids.add(str(key_val))

            # Check condition
            if not self._check_condition(row, target.get("condition")):
                continue

            # Handle split sources (e.g., comorbidities)
            if "split_source" in target:
                results.extend(self._map_split(row, target))
            else:
                resource = self.builder.build(row, target)
                if resource:
                    results.append(resource)

        return results

    def _map_grouped(
        self, df: pd.DataFrame, target: dict, group_by: list[str]
    ) -> list[dict]:
        """Map groups of rows to resources."""
        results = []
        # Filter out rows where group_by columns are all NaN
        valid_cols = [c for c in group_by if c in df.columns]
        if not valid_cols:
            return results

        for keys, group_df in df.groupby(valid_cols, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            group_keys = dict(zip(valid_cols, [str(k) for k in keys]))

            resource = self.builder.build_grouped(group_df, target, group_keys)
            if resource:
                results.append(resource)

        return results

    def _map_split(self, row: pd.Series, target: dict) -> list[dict]:
        """Split a delimited field into multiple resources."""
        results = []
        source_col = target["split_source"]
        delimiter = target.get("split_delimiter", "#")
        raw_val = row.get(source_col)

        if pd.isna(raw_val) or str(raw_val).strip() == "":
            return results

        parts = str(raw_val).split(delimiter)
        for idx, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            # Create a modified row with split metadata
            split_row = row.copy()
            split_row["_split_value"] = part
            split_row["_split_index"] = str(idx)
            resource = self.builder.build(split_row, target)
            if resource:
                results.append(resource)

        return results

    @staticmethod
    def _check_condition(row: pd.Series, condition: str | None) -> bool:
        """Evaluate a simple condition string."""
        if condition is None:
            return True
        # Parse "ColumnName is not empty"
        match = re.match(r"(.+?)\s+is not empty", condition)
        if match:
            col = match.group(1).strip()
            val = row.get(col)
            return val is not None and pd.notna(val) and str(val).strip() != ""
        return True


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------
def build_bundle(
    resources: list[dict],
    bundle_type: str = "transaction",
) -> dict:
    """Wrap a list of FHIR resources into a FHIR Bundle.

    Resources are assumed to be pre-validated (via ``ResourceBuilder.build``).
    The Bundle wrapper itself is built as a plain dict to avoid deep
    re-validation of already-validated embedded resources.
    """
    entries = []
    for res in resources:
        entry: dict[str, Any] = {
            "resource": res,
            "fullUrl": f"urn:uuid:{_deterministic_uuid(res)}",
        }
        if bundle_type == "transaction":
            entry["request"] = {
                "method": "PUT",
                "url": f"{res['resourceType']}/{res.get('id', '')}",
            }
        entries.append(entry)

    return {"resourceType": "Bundle", "type": bundle_type, "entry": entries}


def _deterministic_uuid(resource: dict) -> str:
    """Generate a deterministic UUID from resource type + id."""
    key = f"{resource.get('resourceType', '')}:{resource.get('id', '')}"
    return hashlib.md5(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Cohort submit client
# ---------------------------------------------------------------------------
class CohortSubmitError(Exception):
    """Raised when the $cohort-submit operation fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        operation_outcome: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.operation_outcome = operation_outcome


class CohortSubmitClient:
    """Client for the FHIR $cohort-submit operation.

    Collects mapped FHIR resources, wraps them in a FHIR Parameters resource,
    and POSTs to the ``$cohort-submit`` endpoint on a HAPI FHIR server.

    Requires the ``httpx`` package (``pip install httpx``).
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 300,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    def submit(
        self,
        resources: list[dict],
        mode: str = "merge",
        cohort_id: str = "digiphenoms-ms-cohort",
        batch_label: str | None = None,
    ) -> dict:
        """Submit resources to the HAPI FHIR server via ``$cohort-submit``.

        Args:
            resources: FHIR resource dicts produced by the mapping pipeline.
            mode: Import mode — ``"merge"`` (conditional PUT) or
                ``"distinct"`` (conditional POST).
            cohort_id: Identifier of the cohort root Group.
            batch_label: Human-readable label for this import batch.

        Returns:
            Parsed FHIR Parameters response from the server.

        Raises:
            CohortSubmitError: On HTTP errors or connectivity failures.
        """
        if httpx is None:
            raise ImportError(
                "httpx is required for cohort submission. "
                "Install it with: pip install httpx"
            )

        bundle = build_bundle(resources, bundle_type="collection")

        if batch_label is None:
            batch_label = f"DigiPhenoMS Pipeline {datetime.now().isoformat()}"

        parameters = {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "mode", "valueCode": mode},
                {"name": "cohortId", "valueString": cohort_id},
                {"name": "batchLabel", "valueString": batch_label},
                {"name": "inputBundle", "resource": bundle},
            ],
        }

        url = f"{self.base_url}/$cohort-submit"
        logger.info("Submitting %d resources to %s (mode=%s)", len(resources), url, mode)

        try:
            response = httpx.post(
                url,
                json=parameters,
                headers={"Content-Type": "application/fhir+json"},
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except httpx.ConnectError as exc:
            raise CohortSubmitError(
                f"Connection to {self.base_url} failed: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise CohortSubmitError(
                f"Request to {url} timed out after {self.timeout}s"
            ) from exc

        return self._handle_response(response)

    @staticmethod
    def _handle_response(response) -> dict:
        """Parse the server response or raise :class:`CohortSubmitError`."""
        if response.status_code in (200, 201):
            result = response.json()
            logger.info("Cohort submit succeeded (HTTP %d)", response.status_code)
            return result

        outcome_dict = None
        try:
            body = response.json()
            if body.get("resourceType") == "OperationOutcome":
                outcome_dict = body
        except Exception:
            pass

        messages = {
            400: "Invalid request",
            401: "Authentication required",
            403: "Insufficient permissions",
            404: "Endpoint not found",
            422: "Validation failed",
            504: "Server timeout",
        }
        msg = messages.get(
            response.status_code,
            f"Server error (HTTP {response.status_code})"
            if response.status_code >= 500
            else f"Unexpected response (HTTP {response.status_code})",
        )

        if outcome_dict:
            try:
                outcome = FHIROperationOutcome.model_validate(outcome_dict)
                diagnostics = "; ".join(
                    issue.diagnostics or (
                        issue.details.text if issue.details else ""
                    )
                    for issue in (outcome.issue or [])
                    if issue.diagnostics or (issue.details and issue.details.text)
                )
                if diagnostics:
                    msg = f"{msg}: {diagnostics}"
            except Exception:
                # Fall back to raw dict parsing if model validation fails
                if outcome_dict.get("issue"):
                    diagnostics = "; ".join(
                        issue.get("diagnostics", issue.get("details", {}).get("text", ""))
                        for issue in outcome_dict["issue"]
                        if issue.get("diagnostics") or issue.get("details", {}).get("text")
                    )
                    if diagnostics:
                        msg = f"{msg}: {diagnostics}"

        raise CohortSubmitError(msg, response.status_code, outcome_dict)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
class Pipeline:
    """
    Orchestrates the full CSV-to-FHIR mapping pipeline.

    Usage:
        pipeline = Pipeline(config_dir="config/")
        results = pipeline.run(data_dir="data/", output_dir="output/")
    """

    def __init__(self, config_dir: str | Path):
        self.config_dir = Path(config_dir)
        self.pipeline_cfg = PipelineConfig.from_yaml(
            self.config_dir / "pipeline.yaml"
        )
        self.builder = ResourceBuilder(self.pipeline_cfg, self.config_dir)
        self.last_submit_result: dict | None = None

    def run(
        self,
        data_dir: str | Path,
        output_dir: str | Path | None = None,
    ) -> dict[str, list[dict]]:
        """Execute all enabled pipeline steps.

        Args:
            data_dir: Directory containing source CSV files.
            output_dir: Directory for output FHIR bundles (None = no file output).

        Returns:
            Dict mapping step names to lists of generated FHIR resources.
        """
        data_dir = Path(data_dir)
        resolved_output = None
        if output_dir:
            resolved_output = Path(output_dir)
            resolved_output.mkdir(parents=True, exist_ok=True)

        results = self._run_mapping_steps(data_dir, resolved_output)

        total = sum(len(v) for v in results.values())
        logger.info(f"\n=== Pipeline complete: {total} resources generated ===")
        for step_name, res in results.items():
            logger.info(f"  {step_name}: {len(res)} resources")

        self.last_submit_result = None
        if self.pipeline_cfg.cohort_submit.get("enabled", False) and total > 0:
            self._submit_cohort(results)

        return results

    # -- pipeline phases -----------------------------------------------------

    def _run_mapping_steps(
        self,
        data_dir: Path,
        output_dir: Path | None,
    ) -> dict[str, list[dict]]:
        """Execute all mapping steps and optionally write bundle files."""
        results: dict[str, list[dict]] = {}

        for step in self._resolve_execution_order():
            if not step.get("enabled", True):
                logger.info(f"Skipping disabled step: {step['name']}")
                continue

            logger.info(f"=== Step: {step['name']} — {step.get('description', '')} ===")

            mapping_path = self.config_dir / step["mapping_config"]
            if not mapping_path.exists():
                logger.warning(f"  Mapping config not found: {mapping_path}")
                continue

            mapping_cfg = MappingConfig.from_yaml(mapping_path)
            mapper = FHIRMapper(mapping_cfg, self.builder)

            csv_files = self._find_csv_files(data_dir, step.get("file_pattern", "*.csv"))
            if not csv_files:
                logger.warning(f"  No files matching '{step.get('file_pattern')}' in {data_dir}")
                continue

            step_resources: list[dict] = []
            for csv_file in csv_files:
                step_resources.extend(mapper.map_file(csv_file))

            results[step["name"]] = step_resources

            if output_dir and step_resources:
                self._write_step_bundle(step["name"], step_resources, output_dir)

        return results

    def _write_step_bundle(
        self, step_name: str, resources: list[dict], output_dir: Path
    ) -> None:
        """Write a single step's resources as a FHIR Bundle JSON file."""
        bundle = build_bundle(
            resources,
            bundle_type=self.pipeline_cfg.output_cfg.get("bundle_type", "transaction"),
        )
        out_path = output_dir / f"{step_name}_bundle.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                bundle,
                f,
                indent=2 if self.pipeline_cfg.output_cfg.get("pretty_print") else None,
                ensure_ascii=False,
                default=str,
            )
        logger.info(f"  Wrote {len(resources)} resources to {out_path}")

    def _submit_cohort(self, results: dict[str, list[dict]]) -> None:
        """Submit all mapped resources to the HAPI FHIR server."""
        cfg = self.pipeline_cfg.cohort_submit

        all_resources: list[dict] = []
        for step_resources in results.values():
            all_resources.extend(step_resources)

        batch_label = (
            f"{cfg.get('batch_label_prefix', 'DigiPhenoMS Pipeline')} "
            f"{datetime.now().isoformat()}"
        )

        client = CohortSubmitClient(
            base_url=cfg["endpoint"],
            timeout=cfg.get("timeout", 300),
            verify_ssl=cfg.get("verify_ssl", True),
        )
        self.last_submit_result = client.submit(
            resources=all_resources,
            mode=cfg.get("mode", "merge"),
            cohort_id=cfg.get("cohort_id", "digiphenoms-ms-cohort"),
            batch_label=batch_label,
        )
        logger.info("=== Cohort submit complete ===")

    @staticmethod
    def _find_csv_files(data_dir: Path, pattern: str) -> list[Path]:
        """Find CSV files matching the given glob pattern."""
        csv_files = list(data_dir.glob(pattern))
        if not csv_files:
            csv_files = list(data_dir.glob(pattern + ".csv"))
        return csv_files

    def _resolve_execution_order(self) -> list[dict]:
        """Resolve step execution order based on dependencies (topological sort)."""
        steps_by_name = {s["name"]: s for s in self.pipeline_cfg.steps}
        executed = set()
        ordered = []

        def _visit(name: str):
            if name in executed:
                return
            step = steps_by_name.get(name)
            if step is None:
                return
            for dep in step.get("depends_on", []):
                _visit(dep)
            executed.add(name)
            ordered.append(step)

        for s in self.pipeline_cfg.steps:
            _visit(s["name"])

        return ordered


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="DigiPhenoMS FHIR Mapper — CSV to FHIR R4 transformation"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/",
        help="Path to configuration directory (default: config/)",
    )
    parser.add_argument(
        "--data",
        type=str,
        default="data/",
        help="Path to CSV data directory (default: data/)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/",
        help="Path to output directory (default: output/)",
    )
    parser.add_argument(
        "--steps",
        type=str,
        nargs="*",
        help="Run only specific steps (by name). Default: all enabled.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        default=None,
        help="Enable cohort submission to HAPI FHIR server",
    )
    parser.add_argument(
        "--no-submit",
        action="store_true",
        help="Disable cohort submission even if enabled in config",
    )
    parser.add_argument(
        "--fhir-endpoint",
        type=str,
        help="HAPI FHIR server base URL (overrides $FHIR_BASE_URL and config)",
    )
    parser.add_argument(
        "--import-mode",
        type=str,
        choices=["merge", "distinct"],
        help="Import mode for cohort submission (overrides config)",
    )
    parser.add_argument(
        "--ml-dataset-job",
        type=str,
        metavar="SYNTHESIS_JOB_ID",
        help=(
            "Download the synthetic dataset of this ML server synthesis job "
            "into the data directory before mapping (token: $API_AUTH_TOKEN)"
        ),
    )
    parser.add_argument(
        "--ml-server-url",
        type=str,
        help=(
            "ML server base URL (default: $ML_SERVER_URL, then "
            "pipeline.yaml ml_server.base_url, then http://localhost:8000)"
        ),
    )
    parser.add_argument(
        "--ml-wait",
        action="store_true",
        help="Wait for the ML synthesis job to finish before downloading",
    )
    parser.add_argument(
        "--ml-poll-interval",
        type=float,
        default=10.0,
        help="Polling interval in seconds for --ml-wait (default: 10)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    pipeline = Pipeline(config_dir=args.config)

    # Filter steps if specified
    if args.steps:
        for step in pipeline.pipeline_cfg.steps:
            step["enabled"] = step["name"] in args.steps

    # CLI overrides for cohort submit
    if args.submit:
        pipeline.pipeline_cfg.cohort_submit["enabled"] = True
    if args.no_submit:
        pipeline.pipeline_cfg.cohort_submit["enabled"] = False
    if args.fhir_endpoint:
        pipeline.pipeline_cfg.cohort_submit["endpoint"] = args.fhir_endpoint
        pipeline.pipeline_cfg.cohort_submit.setdefault("enabled", True)
    elif os.environ.get("FHIR_BASE_URL"):
        pipeline.pipeline_cfg.cohort_submit["endpoint"] = os.environ["FHIR_BASE_URL"]
    if args.import_mode:
        pipeline.pipeline_cfg.cohort_submit["mode"] = args.import_mode

    # Fetch synthetic dataset from the ML server before mapping
    if args.ml_dataset_job:
        from digiphenoms_fhir.ml_client import (
            BASE_URL_ENV_VAR,
            TIMEOUT_ENV_VAR,
            MLServerClient,
        )

        ml_cfg = pipeline.pipeline_cfg.ml_server
        client = MLServerClient(
            base_url=(
                args.ml_server_url
                or os.environ.get(BASE_URL_ENV_VAR)
                or ml_cfg.get("base_url")
            ),
            # env wins over pipeline.yaml; the client applies env/default when None
            timeout=(
                None if os.environ.get(TIMEOUT_ENV_VAR) else ml_cfg.get("timeout")
            ),
        )
        if args.ml_wait:
            client.wait_for_job(
                args.ml_dataset_job,
                poll_interval=args.ml_poll_interval,
                timeout=ml_cfg.get("wait_timeout", 3600.0),
            )
        data_path = Path(args.data)
        data_path.mkdir(parents=True, exist_ok=True)
        files = client.download_dataset(args.ml_dataset_job, data_path)
        logger.info(
            "Fetched %d dataset file(s) from ML server job %s",
            len(files),
            args.ml_dataset_job,
        )

    results = pipeline.run(data_dir=args.data, output_dir=args.output)

    # Print summary
    total = sum(len(v) for v in results.values())
    print(f"\nDone. {total} FHIR resources generated in {args.output}")

    if pipeline.last_submit_result:
        print("Cohort submit: OK")


if __name__ == "__main__":
    main()
