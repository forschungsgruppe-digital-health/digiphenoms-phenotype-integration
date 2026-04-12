"""Tests for ResourceBuilder — verifies FHIR resource construction from CSV rows."""

import pandas as pd
import pytest

from digiphenoms_fhir.mapper import MappingConfig


# ---------------------------------------------------------------------------
# Patient mapping
# ---------------------------------------------------------------------------
class TestPatientMapping:
    """Test patient_profile.mapping.yaml → Patient + Condition."""

    @pytest.fixture
    def mapping(self, config_dir):
        return MappingConfig.from_yaml(
            config_dir / "mapping" / "patient_profile.mapping.yaml"
        )

    @pytest.fixture
    def sample_row(self):
        return pd.Series(
            {
                "Patient UUID": "abc-1001",
                "Organization": "Dresden Carus",
                "DOB": "01-06-1985",
                "Gender": "female",
                "Handedness": "right",
                "Preferred Language": "de",
                "Date of Diagnosis": "15-03-2018",
                "Comorbidities": "depression#high_blood_pressure",
                "Created At": "Mon 10 Jan 2022 09:00:00 +0000",
            }
        )

    def test_patient_resource_type(self, builder, mapping, sample_row):
        target = mapping.targets[0]  # Patient target
        resource = builder.build(sample_row, target)
        assert resource is not None
        assert resource["resourceType"] == "Patient"

    def test_patient_id(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert resource["id"] == "pat-abc-1001"

    def test_patient_gender(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert resource["gender"] == "female"

    def test_patient_birthdate(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert str(resource["birthDate"]) == "1985-06-01"

    def test_ms_condition_resource(self, builder, mapping, sample_row):
        target = mapping.targets[1]  # Condition (MS) target
        resource = builder.build(sample_row, target)
        assert resource is not None
        assert resource["resourceType"] == "Condition"
        assert resource["id"] == "cond-ms-abc-1001"

    def test_ms_condition_snomed_code(self, builder, mapping, sample_row):
        target = mapping.targets[1]
        resource = builder.build(sample_row, target)
        code = resource["code"]
        assert code["coding"][0]["code"] == "24700007"
        assert code["coding"][0]["system"] == "http://snomed.info/sct"

    def test_ms_condition_onset(self, builder, mapping, sample_row):
        target = mapping.targets[1]
        resource = builder.build(sample_row, target)
        assert str(resource["onsetDateTime"]) == "2018-03-15"


# ---------------------------------------------------------------------------
# LCLA mapping
# ---------------------------------------------------------------------------
class TestLCLAMapping:
    """Test lclat_summary.mapping.yaml → Observation."""

    @pytest.fixture
    def mapping(self, config_dir):
        return MappingConfig.from_yaml(
            config_dir / "mapping" / "lclat_summary.mapping.yaml"
        )

    @pytest.fixture
    def sample_row(self):
        return pd.Series(
            {
                "Assessment UUID": "assess-2001",
                "Patient UUID": "abc-1001",
                "Assessor UUID": "assessor-01",
                "Module UUID": "mod-lcla-001",
                "Module Started At": "Mon, 14 Mar 2022 08:05:00 +0000",
                "Canceled": "False",
                "Cancel Reason": "",
                "Version": "0.0.45",
                "Total Number Correct": 78.0,
                "Total Number Correct at 100%": 52.0,
                "Total Number Correct at 2.5%": 26.0,
                "Total Number Correct at 10%": float("nan"),
                "Total Number Correct at 5%": float("nan"),
                "Total Number Correct at 1.25%": float("nan"),
                "Module Duration": 900,
            }
        )

    def test_observation_type(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert resource["resourceType"] == "Observation"

    def test_status_mapping_final(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert resource["status"] == "final"

    def test_status_mapping_cancelled(self, builder, mapping):
        row = pd.Series(
            {
                "Assessment UUID": "assess-2003",
                "Patient UUID": "abc-1003",
                "Assessor UUID": "assessor-01",
                "Module UUID": "mod-lcla-003",
                "Module Started At": "Wed, 16 Mar 2022 14:05:00 +0000",
                "Canceled": "True",
                "Cancel Reason": "incomplete-unable-to-complete",
                "Version": "0.0.45",
                "Total Number Correct": float("nan"),
                "Total Number Correct at 100%": float("nan"),
                "Total Number Correct at 2.5%": float("nan"),
                "Total Number Correct at 10%": float("nan"),
                "Total Number Correct at 5%": float("nan"),
                "Total Number Correct at 1.25%": float("nan"),
                "Module Duration": 300,
            }
        )
        target = mapping.targets[0]
        resource = builder.build(row, target)
        assert resource["status"] == "cancelled"

    def test_subject_reference(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert resource["subject"]["reference"] == "Patient/pat-abc-1001"

    def test_encounter_reference(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert resource["encounter"]["reference"] == "Encounter/enc-assess-2001"

    def test_components_present(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert "component" in resource
        # Should have total, 100%, 2.5%, and duration (NaN values are skipped)
        codes = [c["code"]["coding"][0]["code"] for c in resource["component"]]
        assert "lclat-total-correct" in codes
        assert "lclat-correct-100pct" in codes
        assert "lclat-correct-2.5pct" in codes
        assert "module-duration" in codes

    def test_nan_components_skipped(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        codes = [c["code"]["coding"][0]["code"] for c in resource["component"]]
        # 10%, 5%, 1.25% are NaN and should not appear
        assert "lclat-correct-10pct" not in codes
        assert "lclat-correct-5pct" not in codes
        assert "lclat-correct-1.25pct" not in codes

    def test_component_value_quantity(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        total_comp = [
            c
            for c in resource["component"]
            if c["code"]["coding"][0]["code"] == "lclat-total-correct"
        ][0]
        assert total_comp["valueQuantity"]["value"] == 78.0
        assert total_comp["valueQuantity"]["unit"] == "{score}"


# ---------------------------------------------------------------------------
# T25FW mapping
# ---------------------------------------------------------------------------
class TestT25FWMapping:
    """Test wst_summary.mapping.yaml → Observation."""

    @pytest.fixture
    def mapping(self, config_dir):
        return MappingConfig.from_yaml(
            config_dir / "mapping" / "wst_summary.mapping.yaml"
        )

    @pytest.fixture
    def sample_row(self):
        return pd.Series(
            {
                "Assessment UUID": "assess-2002",
                "Patient UUID": "abc-1002",
                "Module UUID": "mod-wst-002",
                "Module Started At": "Tue, 15 Mar 2022 10:55:00 +0000",
                "Canceled": "False",
                "Walk Duration": 8.3,
                "Z-Score": -1.5,
                "Walking Aid Used": "True",
                "Walking Aid Choice": "cane",
                "AFO Used": "True",
                "AFO Choice": "rechts",
                "Successful Trials": 2,
                "Unsuccessful Trials": 1,
            }
        )

    def test_primary_value(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert resource["valueQuantity"]["value"] == 8.3
        assert resource["valueQuantity"]["unit"] == "s"

    def test_walking_aid_boolean(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        aid_comps = [
            c
            for c in resource["component"]
            if c["code"]["coding"][0]["code"] == "walking-aid-used"
        ]
        assert len(aid_comps) == 1
        assert aid_comps[0]["valueBoolean"] is True

    def test_z_score_component(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        z_comps = [
            c
            for c in resource["component"]
            if c["code"]["coding"][0]["code"] == "t25fw-zscore"
        ]
        assert len(z_comps) == 1
        assert z_comps[0]["valueQuantity"]["value"] == -1.5


# ---------------------------------------------------------------------------
# 9HPT mapping
# ---------------------------------------------------------------------------
class TestNineHPTMapping:
    """Test mdt_summary.mapping.yaml → Observation."""

    @pytest.fixture
    def mapping(self, config_dir):
        return MappingConfig.from_yaml(
            config_dir / "mapping" / "mdt_summary.mapping.yaml"
        )

    @pytest.fixture
    def sample_row(self):
        return pd.Series(
            {
                "Assessment UUID": "assess-2001",
                "Patient UUID": "abc-1001",
                "Module UUID": "mod-mdt-001",
                "Module Started At": "Mon, 14 Mar 2022 08:25:00 +0000",
                "Canceled": "False",
                "Cancel Reason": "",
                "Z-Score Dominant": -0.5,
                "Z-Score Nondominant": 0.3,
                "Left Hand Time": 22.4,
                "Right Hand Time": 19.8,
                "Dominant Hand": "right",
                "Pegs Dropped": 0,
                "Trial Duration": 19.8,
            }
        )

    def test_loinc_code(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        code = resource["code"]
        assert code["coding"][0]["code"] == "83141-2"
        assert code["coding"][0]["system"] == "http://loinc.org"

    def test_hand_times(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        left = [
            c
            for c in resource["component"]
            if c["code"]["coding"][0]["code"] == "9hpt-left-hand-time"
        ]
        right = [
            c
            for c in resource["component"]
            if c["code"]["coding"][0]["code"] == "9hpt-right-hand-time"
        ]
        assert left[0]["valueQuantity"]["value"] == 22.4
        assert right[0]["valueQuantity"]["value"] == 19.8


# ---------------------------------------------------------------------------
# MRI mapping
# ---------------------------------------------------------------------------
class TestMRIMapping:
    """Test mrt.mapping.yaml → DiagnosticReport + Observations."""

    @pytest.fixture
    def mapping(self, config_dir):
        return MappingConfig.from_yaml(
            config_dir / "mapping" / "mrt.mapping.yaml"
        )

    @pytest.fixture
    def sample_row(self):
        return pd.Series(
            {
                "unnamed__0": 0,
                "patientalias": "abc-1001",
                "sty_date": "2022-03-01",
                "bpf": 0.78,
                "bpf_chg": -0.01,
                "t2lesvol": 4.2,
                "t2overbv": 0.0035,
                "nt2lescn": 2,
                "nt2lesvo": 0.8,
                "t2voljux": 1.1,
                "t2volprv": 2.3,
                "t2volinf": 0.8,
                "gmf": 0.45,
                "wmf": 0.33,
                "cgmvol": 520.3,
                "dgmvol": 48.7,
                "cgmf": 0.38,
                "dgmf": 0.036,
                "thalvol": 12.4,
                "thalf": 0.0092,
                "segvisqc": "passed",
                "segcomm": "",
            }
        )

    def test_diagnostic_report(self, builder, mapping, sample_row):
        target = mapping.targets[0]  # DiagnosticReport
        resource = builder.build(sample_row, target)
        assert resource["resourceType"] == "DiagnosticReport"
        assert resource["status"] == "final"

    def test_diagnostic_report_result_refs(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert len(resource["result"]) == 4
        refs = [r["reference"] for r in resource["result"]]
        assert "obs-mri-atrophy-abc-1001-2022-03-01" in refs[0]

    def test_atrophy_observation(self, builder, mapping, sample_row):
        target = mapping.targets[1]  # Atrophy
        resource = builder.build(sample_row, target)
        assert resource["resourceType"] == "Observation"
        bpf = [
            c
            for c in resource["component"]
            if c["code"]["coding"][0]["code"] == "bpf"
        ]
        assert len(bpf) == 1
        assert bpf[0]["valueQuantity"]["value"] == 0.78

    def test_lesion_observation(self, builder, mapping, sample_row):
        target = mapping.targets[2]  # Lesions
        resource = builder.build(sample_row, target)
        codes = [c["code"]["coding"][0]["code"] for c in resource["component"]]
        assert "t2-lesion-volume" in codes
        assert "new-t2-lesion-count" in codes

    def test_thalamus_observation(self, builder, mapping, sample_row):
        target = mapping.targets[4]  # Thalamus
        resource = builder.build(sample_row, target)
        vol = [
            c
            for c in resource["component"]
            if c["code"]["coding"][0]["code"] == "thalamus-volume"
        ]
        assert vol[0]["valueQuantity"]["value"] == 12.4
        assert vol[0]["valueQuantity"]["unit"] == "mL"


# ---------------------------------------------------------------------------
# SDMT mapping
# ---------------------------------------------------------------------------
class TestSDMTMapping:
    """Test npst_summary.mapping.yaml → Observation."""

    @pytest.fixture
    def mapping(self, config_dir):
        return MappingConfig.from_yaml(
            config_dir / "mapping" / "npst_summary.mapping.yaml"
        )

    @pytest.fixture
    def sample_row(self):
        return pd.Series(
            {
                "Assessment UUID": "assess-2001",
                "Patient UUID": "abc-1001",
                "Module UUID": "mod-npst-001",
                "Module Started At": "Mon, 14 Mar 2022 08:45:00 +0000",
                "Canceled": "False",
                "Total Number Correct": 48,
                "Total Number Incorrect": 7,
                "Z-Score": 0.2,
            }
        )

    def test_primary_value(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        assert resource["valueQuantity"]["value"] == 48.0
        assert resource["valueQuantity"]["unit"] == "{score}"

    def test_snomed_additional_coding(self, builder, mapping, sample_row):
        target = mapping.targets[0]
        resource = builder.build(sample_row, target)
        code = resource["code"]
        # Should have primary custom code + additional SNOMED coding in static_fields
        assert code["coding"][0]["code"] == "sdmt-test"
