"""
DigiPhenoMS FHIR Mapper — Configuration-driven CSV-to-FHIR R4 Transformation
=============================================================================

This module provides a loosely coupled, configuration-driven mapping engine
that transforms CSV data (conforming to the DigiPhenoMS data schemas) into
FHIR R4 resources. It is designed to be embedded as a step in a Python-based
data pipeline.

Architecture:
    - MappingConfig: Loads and validates YAML mapping configurations
    - ResourceBuilder: Constructs FHIR R4 resources from CSV rows + config
    - FHIRMapper: Orchestrates the mapping for a single CSV source
    - Pipeline: Executes all mapping steps in dependency order

Dependencies:
    pip install pyyaml fhir.resources pandas

Usage as pipeline step:
    from fhir_mapper import Pipeline
    pipeline = Pipeline(config_dir="config/")
    bundles = pipeline.run(data_dir="data/", output_dir="output/")

Usage standalone:
    python fhir_mapper.py --config config/ --data data/ --output output/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("digiphenoms.fhir_mapper")


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

        # Resource ID
        resource["id"] = self._interpolate(
            target.get("id_template", ""), row, extra_context
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
                    "reference": self._interpolate(ref, row, extra_context),
                }
                for ref in target["result_references"]
            ]

        return resource

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
                if "linkId_source" in items_cfg:
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

        return resource

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

    def _build_static(self, key: str, value: Any) -> Any:
        """Build a static field value (handles nested dicts for CodeableConcept etc.)."""
        if isinstance(value, dict) and "system" in value and "code" in value:
            return {"coding": [value], "text": value.get("display", "")}
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
            self._set_nested(resource, target, {"reference": f"{ref_type}/{ref_id}"})

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
    """Wrap a list of FHIR resources into a FHIR Bundle."""
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

    return {
        "resourceType": "Bundle",
        "type": bundle_type,
        "entry": entries,
    }


def _deterministic_uuid(resource: dict) -> str:
    """Generate a deterministic UUID from resource type + id."""
    key = f"{resource.get('resourceType', '')}:{resource.get('id', '')}"
    return hashlib.md5(key.encode()).hexdigest()


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

    def run(
        self,
        data_dir: str | Path,
        output_dir: str | Path | None = None,
    ) -> dict[str, list[dict]]:
        """
        Execute all enabled pipeline steps.

        Args:
            data_dir: Directory containing source CSV files
            output_dir: Directory for output FHIR bundles (None = no file output)

        Returns:
            Dict mapping step names to lists of generated FHIR resources
        """
        data_dir = Path(data_dir)
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, list[dict]] = {}
        steps = self._resolve_execution_order()

        for step in steps:
            if not step.get("enabled", True):
                logger.info(f"Skipping disabled step: {step['name']}")
                continue

            logger.info(f"=== Step: {step['name']} — {step.get('description', '')} ===")

            # Load mapping config
            mapping_path = self.config_dir / step["mapping_config"]
            if not mapping_path.exists():
                logger.warning(f"  Mapping config not found: {mapping_path}")
                continue

            mapping_cfg = MappingConfig.from_yaml(mapping_path)
            mapper = FHIRMapper(mapping_cfg, self.builder)

            # Find matching CSV files
            pattern = step.get("file_pattern", "*.csv")
            csv_files = list(data_dir.glob(pattern))
            if not csv_files:
                # Try with .csv extension
                csv_files = list(data_dir.glob(pattern + ".csv"))
            if not csv_files:
                logger.warning(f"  No files matching '{pattern}' in {data_dir}")
                continue

            # Map all matching files
            step_resources = []
            for csv_file in csv_files:
                resources = mapper.map_file(csv_file)
                step_resources.extend(resources)

            results[step["name"]] = step_resources

            # Write output bundle
            if output_dir and step_resources:
                bundle = build_bundle(
                    step_resources,
                    bundle_type=self.pipeline_cfg.output_cfg.get(
                        "bundle_type", "transaction"
                    ),
                )
                out_path = output_dir / f"{step['name']}_bundle.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(
                        bundle,
                        f,
                        indent=2 if self.pipeline_cfg.output_cfg.get("pretty_print") else None,
                        ensure_ascii=False,
                        default=str,
                    )
                logger.info(
                    f"  Wrote {len(step_resources)} resources to {out_path}"
                )

        # Summary
        total = sum(len(v) for v in results.values())
        logger.info(f"\n=== Pipeline complete: {total} resources generated ===")
        for step_name, res in results.items():
            logger.info(f"  {step_name}: {len(res)} resources")

        return results

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

    results = pipeline.run(data_dir=args.data, output_dir=args.output)

    # Print summary
    total = sum(len(v) for v in results.values())
    print(f"\nDone. {total} FHIR resources generated in {args.output}")


if __name__ == "__main__":
    main()
