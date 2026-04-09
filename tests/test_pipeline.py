"""Tests for the Pipeline and FHIRMapper — end-to-end mapping from CSV to FHIR bundles."""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from digiphenoms_fhir.mapper import (
    FHIRMapper,
    MappingConfig,
    Pipeline,
    build_bundle,
)


class TestFHIRMapperFile:
    """Test FHIRMapper.map_file() for each CSV type."""

    def test_map_patient_profile(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "patient_profile.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(
            fixtures_dir / "patient-profile-overview_training.csv"
        )
        # 3 patients → 3 Patient + 2 MS Condition (patient 3 has no comorbidities)
        # + comorbidities: patient 1 has 2, patient 2 has 1
        patients = [r for r in resources if r["resourceType"] == "Patient"]
        conditions = [r for r in resources if r["resourceType"] == "Condition"]
        assert len(patients) == 3
        # MS conditions: 3 (all have Date of Diagnosis... wait, patient 3 has empty)
        ms_conds = [c for c in conditions if c["id"].startswith("cond-ms-")]
        comorbid_conds = [
            c for c in conditions if c["id"].startswith("cond-comorbid-")
        ]
        assert len(ms_conds) >= 2  # Patients 1 and 2 have diagnosis dates
        assert len(comorbid_conds) >= 2  # Patient 1: depression + high_blood_pressure

    def test_map_lclat_summary(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "lclat_summary.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(fixtures_dir / "lclat-summary_training.csv")
        assert len(resources) == 3
        final = [r for r in resources if r.get("status") == "final"]
        cancelled = [r for r in resources if r.get("status") == "cancelled"]
        assert len(final) == 2
        assert len(cancelled) == 1

    def test_map_mdt_summary(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "mdt_summary.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(fixtures_dir / "mdt-summary_training.csv")
        assert len(resources) == 2
        for r in resources:
            assert r["resourceType"] == "Observation"
            assert "component" in r

    def test_map_npst_summary(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "npst_summary.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(fixtures_dir / "npst-summary_training.csv")
        assert len(resources) == 2
        for r in resources:
            assert "valueQuantity" in r  # Primary value

    def test_map_wst_summary(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "wst_summary.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(fixtures_dir / "wst-summary_training.csv")
        assert len(resources) == 2
        for r in resources:
            assert "valueQuantity" in r
            assert r["valueQuantity"]["unit"] == "s"

    def test_map_mrt(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "mrt.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(fixtures_dir / "mrt_training.csv")
        # 2 rows × 5 targets = 10 resources
        types = [r["resourceType"] for r in resources]
        assert types.count("DiagnosticReport") == 2
        assert types.count("Observation") == 8  # 4 per row

    def test_map_wrapper_overview(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "wrapper_overview.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(
            fixtures_dir / "wrapper-overview_training.csv"
        )
        encounters = [r for r in resources if r["resourceType"] == "Encounter"]
        devices = [r for r in resources if r["resourceType"] == "Device"]
        assert len(encounters) == 3
        assert len(devices) >= 2  # Deduplicated by Vendor Identifier


class TestBundleBuilder:
    """Test FHIR Bundle creation."""

    def test_transaction_bundle(self):
        resources = [
            {"resourceType": "Patient", "id": "pat-1"},
            {"resourceType": "Observation", "id": "obs-1"},
        ]
        bundle = build_bundle(resources, bundle_type="transaction")
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "transaction"
        assert len(bundle["entry"]) == 2
        for entry in bundle["entry"]:
            assert "request" in entry
            assert entry["request"]["method"] == "PUT"
            assert "fullUrl" in entry

    def test_collection_bundle(self):
        resources = [{"resourceType": "Patient", "id": "pat-1"}]
        bundle = build_bundle(resources, bundle_type="collection")
        assert bundle["type"] == "collection"
        assert "request" not in bundle["entry"][0]

    def test_bundle_json_serializable(self):
        resources = [
            {"resourceType": "Patient", "id": "pat-1", "birthDate": "1985-06-01"},
        ]
        bundle = build_bundle(resources)
        # Should not raise
        json_str = json.dumps(bundle, default=str)
        assert "pat-1" in json_str


class TestPipelineIntegration:
    """Integration test: run the full pipeline against fixture data."""

    def test_pipeline_runs_without_error(self, pipeline, fixtures_dir):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = pipeline.run(data_dir=fixtures_dir, output_dir=tmpdir)
            assert isinstance(results, dict)
            # At least some steps should have produced resources
            total = sum(len(v) for v in results.values())
            assert total > 0

    def test_pipeline_output_files(self, pipeline, fixtures_dir):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline.run(data_dir=fixtures_dir, output_dir=tmpdir)
            output_files = list(Path(tmpdir).glob("*_bundle.json"))
            assert len(output_files) > 0
            # Each output file should be valid JSON
            for f in output_files:
                data = json.loads(f.read_text())
                assert data["resourceType"] == "Bundle"

    def test_pipeline_patient_step(self, pipeline, fixtures_dir):
        results = pipeline.run(data_dir=fixtures_dir)
        assert "patient_profile" in results
        patients = [
            r for r in results["patient_profile"] if r["resourceType"] == "Patient"
        ]
        assert len(patients) == 3

    def test_pipeline_resource_references(self, pipeline, fixtures_dir):
        """Verify referential integrity: Observations reference existing Patients."""
        results = pipeline.run(data_dir=fixtures_dir)
        patient_ids = {
            r["id"]
            for r in results.get("patient_profile", [])
            if r["resourceType"] == "Patient"
        }
        # Check LCLA observations reference known patients
        for obs in results.get("lclat_summary", []):
            if "subject" in obs:
                ref_id = obs["subject"]["reference"].split("/")[-1]
                assert ref_id in patient_ids, (
                    f"Observation references unknown patient: {ref_id}"
                )


class TestTerminologyMap:
    """Test terminology/concept map loading and translation."""

    def test_walking_aids_map(self, config_dir):
        from digiphenoms_fhir.mapper import TerminologyMap

        tmap = TerminologyMap.from_yaml(
            config_dir / "terminology" / "walking_aids_conceptmap.yaml"
        )
        result = tmap.translate("cane")
        assert result["code"] == "360006004"
        assert result["system"] == "http://snomed.info/sct"

    def test_handedness_map(self, config_dir):
        from digiphenoms_fhir.mapper import TerminologyMap

        tmap = TerminologyMap.from_yaml(
            config_dir / "terminology" / "handedness_conceptmap.yaml"
        )
        result = tmap.translate("right")
        assert result["code"] == "46669005"

    def test_comorbidity_map_default(self, config_dir):
        from digiphenoms_fhir.mapper import TerminologyMap

        tmap = TerminologyMap.from_yaml(
            config_dir / "terminology" / "comorbidity_conceptmap.yaml"
        )
        result = tmap.translate("unknown_condition")
        # Should fall back to _default
        assert result["code"] == "64572001"  # Disease (generic)

    def test_neuroqol_domains_map(self, config_dir):
        from digiphenoms_fhir.mapper import TerminologyMap

        tmap = TerminologyMap.from_yaml(
            config_dir / "terminology" / "neuroqol_domains_conceptmap.yaml"
        )
        result = tmap.translate("anxiety")
        # NeuroQoL map uses loinc_code/loinc_display (not snomed_code)
        assert result["code"] == "67903-5"
        assert result["display"] == "Neuro-Qol short form - anxiety - version 1.0"
        assert result["system"] == "http://loinc.org"

    def test_neuroqol_domains_map_fatigue(self, config_dir):
        from digiphenoms_fhir.mapper import TerminologyMap

        tmap = TerminologyMap.from_yaml(
            config_dir / "terminology" / "neuroqol_domains_conceptmap.yaml"
        )
        result = tmap.translate("fatigue")
        assert result["code"] == "67905-0"
        assert result["system"] == "http://loinc.org"
