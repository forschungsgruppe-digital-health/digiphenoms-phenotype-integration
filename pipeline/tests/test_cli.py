"""
Regression tests for the ``digiphenoms-fhir`` CLI entry point.

The CLI was previously untested; these tests cover argument handling,
step filtering, submit overrides, and the ML server dataset pre-fetch.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from digiphenoms_fhir.mapper import main as cli_main


def run_cli(monkeypatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["digiphenoms-fhir", *args])
    cli_main()


class TestCliMapping:
    def test_full_run_writes_bundles(self, monkeypatch, capsys, tmp_path, config_dir, fixtures_dir):
        out = tmp_path / "out"
        run_cli(
            monkeypatch,
            "--config", str(config_dir),
            "--data", str(fixtures_dir),
            "--output", str(out),
        )
        captured = capsys.readouterr()
        assert "FHIR resources generated" in captured.out
        bundles = sorted(p.name for p in out.glob("*_bundle.json"))
        assert "patient_profile_bundle.json" in bundles
        assert "mrt_bundle.json" in bundles
        # Bundles must be valid JSON with entries
        bundle = json.loads((out / "patient_profile_bundle.json").read_text())
        assert bundle["resourceType"] == "Bundle"
        assert len(bundle["entry"]) > 0

    def test_steps_filter_limits_output(self, monkeypatch, tmp_path, config_dir, fixtures_dir):
        out = tmp_path / "out"
        run_cli(
            monkeypatch,
            "--config", str(config_dir),
            "--data", str(fixtures_dir),
            "--output", str(out),
            "--steps", "patient_profile",
        )
        bundles = [p.name for p in out.glob("*_bundle.json")]
        assert bundles == ["patient_profile_bundle.json"]

    def test_submit_flag_posts_to_endpoint(self, monkeypatch, capsys, tmp_path, config_dir, fixtures_dir):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"resourceType": "Parameters", "parameter": []}

        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            mock_httpx.ConnectError = Exception
            mock_httpx.TimeoutException = Exception
            run_cli(
                monkeypatch,
                "--config", str(config_dir),
                "--data", str(fixtures_dir),
                "--output", str(tmp_path / "out"),
                "--submit",
                "--fhir-endpoint", "http://fhir.test/fhir",
            )
            mock_httpx.post.assert_called_once()
            url = mock_httpx.post.call_args.args[0]
        assert url == "http://fhir.test/fhir/$cohort-submit"
        assert "Cohort submit: OK" in capsys.readouterr().out

    def test_no_submit_overrides_config(self, monkeypatch, tmp_path, config_dir, fixtures_dir):
        with patch("digiphenoms_fhir.mapper.httpx") as mock_httpx:
            run_cli(
                monkeypatch,
                "--config", str(config_dir),
                "--data", str(fixtures_dir),
                "--output", str(tmp_path / "out"),
                "--no-submit",
                "--fhir-endpoint", "http://fhir.test/fhir",
            )
            mock_httpx.post.assert_not_called()


class TestCliMlIntegration:
    def test_ml_dataset_job_downloads_before_mapping(self, monkeypatch, tmp_path, config_dir):
        data_dir = tmp_path / "data"

        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.download_dataset.return_value = []
            run_cli(
                monkeypatch,
                "--config", str(config_dir),
                "--data", str(data_dir),
                "--output", str(tmp_path / "out"),
                "--ml-dataset-job", "syn-1",
            )
            mock_cls.return_value.download_dataset.assert_called_once_with(
                "syn-1", data_dir
            )
            mock_cls.return_value.wait_for_job.assert_not_called()
        # The data directory is created for the download
        assert data_dir.is_dir()

    def test_ml_wait_polls_before_download(self, monkeypatch, tmp_path, config_dir):
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.download_dataset.return_value = []
            run_cli(
                monkeypatch,
                "--config", str(config_dir),
                "--data", str(tmp_path / "data"),
                "--output", str(tmp_path / "out"),
                "--ml-dataset-job", "syn-1",
                "--ml-wait",
                "--ml-poll-interval", "5",
            )
            mock_cls.return_value.wait_for_job.assert_called_once()
            assert (
                mock_cls.return_value.wait_for_job.call_args.kwargs["poll_interval"]
                == 5.0
            )

    def test_ml_server_url_flag_wins(self, monkeypatch, tmp_path, config_dir):
        monkeypatch.setenv("ML_SERVER_URL", "http://env-url:8000")
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.download_dataset.return_value = []
            run_cli(
                monkeypatch,
                "--config", str(config_dir),
                "--data", str(tmp_path / "data"),
                "--output", str(tmp_path / "out"),
                "--ml-dataset-job", "syn-1",
                "--ml-server-url", "http://flag-url:8000",
            )
            assert mock_cls.call_args.kwargs["base_url"] == "http://flag-url:8000"

    def test_without_ml_flag_no_client_created(self, monkeypatch, tmp_path, config_dir, fixtures_dir):
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            run_cli(
                monkeypatch,
                "--config", str(config_dir),
                "--data", str(fixtures_dir),
                "--output", str(tmp_path / "out"),
            )
            mock_cls.assert_not_called()
