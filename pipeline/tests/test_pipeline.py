"""Tests for the Pipeline and FHIRMapper — end-to-end mapping from CSV to FHIR bundles."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from digiphenoms_fhir.mapper import (
    CohortSubmitClient,
    CohortSubmitError,
    FHIRMapper,
    MappingConfig,
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
        # 3 rows × 5 targets = 15 resources
        types = [r["resourceType"] for r in resources]
        assert types.count("DiagnosticReport") == 3
        assert types.count("Observation") == 12  # 4 per row

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


class TestResourceIdentifiers:
    """Test that resources contain identifier arrays for conditional operations."""

    def test_patient_has_identifier(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "patient_profile.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(
            fixtures_dir / "patient-profile-overview_training.csv"
        )
        patients = [r for r in resources if r["resourceType"] == "Patient"]
        for pat in patients:
            assert "identifier" in pat, "Patient must have identifier array"
            assert len(pat["identifier"]) >= 1
            ident = pat["identifier"][0]
            assert ident["system"] == (
                "urn:oid:2.16.840.1.113883.3.digiphenoms.patient"
            )
            assert ident["value"], "Identifier value must be non-empty"

    def test_observation_has_identifier(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "lclat_summary.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(fixtures_dir / "lclat-summary_training.csv")
        for obs in resources:
            assert "identifier" in obs
            assert obs["identifier"][0]["system"] == (
                "urn:oid:2.16.840.1.113883.3.digiphenoms.module"
            )

    def test_encounter_has_identifier(self, builder, config_dir, fixtures_dir):
        mapping = MappingConfig.from_yaml(
            config_dir / "mapping" / "wrapper_overview.mapping.yaml"
        )
        mapper = FHIRMapper(mapping, builder)
        resources = mapper.map_file(
            fixtures_dir / "wrapper-overview_training.csv"
        )
        encounters = [r for r in resources if r["resourceType"] == "Encounter"]
        for enc in encounters:
            assert "identifier" in enc
            assert enc["identifier"][0]["system"] == (
                "urn:oid:2.16.840.1.113883.3.digiphenoms.assessment"
            )


class TestCohortSubmitClient:
    """Test the $cohort-submit client with mocked HTTP responses."""

    @pytest.fixture
    def sample_resources(self):
        return [
            {"resourceType": "Patient", "id": "pat-1"},
            {"resourceType": "Observation", "id": "obs-1"},
        ]

    @pytest.fixture
    def success_response(self):
        return {
            "resourceType": "Parameters",
            "parameter": [
                {
                    "name": "outcome",
                    "resource": {
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {
                                "severity": "information",
                                "code": "informational",
                                "diagnostics": "Import completed successfully.",
                            }
                        ],
                    },
                },
                {
                    "name": "importGroup",
                    "valueReference": {
                        "reference": "Group/import-2026-04-11-001"
                    },
                },
                {
                    "name": "statistics",
                    "part": [
                        {"name": "resourcesCreated", "valueInteger": 2},
                        {"name": "resourcesUpdated", "valueInteger": 0},
                        {"name": "resourcesSkipped", "valueInteger": 0},
                        {"name": "patientsInBatch", "valueInteger": 1},
                        {"name": "patientsInCohort", "valueInteger": 1},
                    ],
                },
            ],
        }

    def test_submit_success(self, sample_resources, success_response):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = success_response

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            mock_httpx.ConnectError = Exception
            mock_httpx.TimeoutException = Exception

            client = CohortSubmitClient("http://localhost:8080/fhir")
            result = client.submit(sample_resources, mode="merge")

        assert result["resourceType"] == "Parameters"
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args
        body = call_kwargs.kwargs["json"] if "json" in call_kwargs.kwargs else call_kwargs[1]["json"]
        assert body["resourceType"] == "Parameters"
        params = {p["name"]: p for p in body["parameter"]}
        assert params["mode"]["valueCode"] == "merge"
        assert params["inputBundle"]["resource"]["type"] == "collection"

    def test_submit_parameters_structure(self, sample_resources):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"resourceType": "Parameters", "parameter": []}

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            mock_httpx.ConnectError = Exception
            mock_httpx.TimeoutException = Exception

            client = CohortSubmitClient("http://localhost:8080/fhir")
            client.submit(
                sample_resources,
                mode="distinct",
                cohort_id="test-cohort",
                batch_label="Test Import",
            )

        call_kwargs = mock_httpx.post.call_args
        body = call_kwargs.kwargs["json"] if "json" in call_kwargs.kwargs else call_kwargs[1]["json"]
        params = {p["name"]: p for p in body["parameter"]}
        assert params["mode"]["valueCode"] == "distinct"
        assert params["cohortId"]["valueString"] == "test-cohort"
        assert params["batchLabel"]["valueString"] == "Test Import"

    def test_submit_http_400(self, sample_resources):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": "invalid",
                    "diagnostics": "Input bundle must contain at least one Patient.",
                }
            ],
        }

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            mock_httpx.ConnectError = Exception
            mock_httpx.TimeoutException = Exception

            client = CohortSubmitClient("http://localhost:8080/fhir")
            with pytest.raises(CohortSubmitError) as exc_info:
                client.submit(sample_resources)

        assert exc_info.value.status_code == 400
        assert "Invalid request" in str(exc_info.value)
        assert "at least one Patient" in str(exc_info.value)
        assert exc_info.value.operation_outcome is not None

    def test_submit_http_422(self, sample_resources):
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": "processing",
                    "diagnostics": "Identifier system missing on Patient/pat-1.",
                }
            ],
        }

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            mock_httpx.ConnectError = Exception
            mock_httpx.TimeoutException = Exception

            client = CohortSubmitClient("http://localhost:8080/fhir")
            with pytest.raises(CohortSubmitError) as exc_info:
                client.submit(sample_resources)

        assert exc_info.value.status_code == 422
        assert "Validation failed" in str(exc_info.value)

    def test_submit_http_500(self, sample_resources):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {}

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            mock_httpx.ConnectError = Exception
            mock_httpx.TimeoutException = Exception

            client = CohortSubmitClient("http://localhost:8080/fhir")
            with pytest.raises(CohortSubmitError) as exc_info:
                client.submit(sample_resources)

        assert exc_info.value.status_code == 500
        assert "Server error" in str(exc_info.value)

    def test_submit_connection_error(self, sample_resources):
        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            conn_err = type("ConnectError", (Exception,), {})
            mock_httpx.ConnectError = conn_err
            mock_httpx.TimeoutException = type("TimeoutException", (Exception,), {})
            mock_httpx.post.side_effect = conn_err("Connection refused")

            client = CohortSubmitClient("http://localhost:8080/fhir")
            with pytest.raises(CohortSubmitError) as exc_info:
                client.submit(sample_resources)

        assert "Connection" in str(exc_info.value)

    def test_submit_timeout(self, sample_resources):
        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            timeout_err = type("TimeoutException", (Exception,), {})
            mock_httpx.ConnectError = type("ConnectError", (Exception,), {})
            mock_httpx.TimeoutException = timeout_err
            mock_httpx.post.side_effect = timeout_err("Read timed out")

            client = CohortSubmitClient("http://localhost:8080/fhir", timeout=10)
            with pytest.raises(CohortSubmitError) as exc_info:
                client.submit(sample_resources)

        assert "timed out" in str(exc_info.value)

    def test_collection_bundle_type(self, sample_resources):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"resourceType": "Parameters", "parameter": []}

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            mock_httpx.ConnectError = Exception
            mock_httpx.TimeoutException = Exception

            client = CohortSubmitClient("http://localhost:8080/fhir")
            client.submit(sample_resources)

        body = mock_httpx.post.call_args.kwargs["json"]
        bundle = body["parameter"][3]["resource"]
        assert bundle["type"] == "collection"
        for entry in bundle["entry"]:
            assert "request" not in entry


class TestPipelineSubmitIntegration:
    """Test Pipeline integration with $cohort-submit."""

    def test_pipeline_no_submit_by_default(self, pipeline, fixtures_dir):
        pipeline.run(data_dir=fixtures_dir)
        assert pipeline.last_submit_result is None

    def test_pipeline_submit_when_enabled(self, pipeline, fixtures_dir):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resourceType": "Parameters",
            "parameter": [],
        }

        pipeline.pipeline_cfg.cohort_submit = {
            "enabled": True,
            "endpoint": "http://localhost:8080/fhir",
            "mode": "merge",
            "cohort_id": "test-cohort",
            "timeout": 30,
        }

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            mock_httpx.ConnectError = Exception
            mock_httpx.TimeoutException = Exception

            results = pipeline.run(data_dir=fixtures_dir)

        assert pipeline.last_submit_result is not None
        assert mock_httpx.post.call_count == 1
        body = mock_httpx.post.call_args.kwargs["json"]
        bundle = body["parameter"][3]["resource"]
        total_resources = sum(len(v) for v in results.values())
        assert len(bundle["entry"]) == total_resources

    def test_pipeline_submit_error_propagates(self, pipeline, fixtures_dir):
        pipeline.pipeline_cfg.cohort_submit = {
            "enabled": True,
            "endpoint": "http://localhost:8080/fhir",
            "mode": "merge",
        }

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            conn_err = type("ConnectError", (Exception,), {})
            mock_httpx.ConnectError = conn_err
            mock_httpx.TimeoutException = type("TimeoutException", (Exception,), {})
            mock_httpx.post.side_effect = conn_err("Connection refused")

            with pytest.raises(CohortSubmitError):
                pipeline.run(data_dir=fixtures_dir)
