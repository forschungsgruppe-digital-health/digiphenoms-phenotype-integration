"""
Tests for the ML server client (synthetic data job API).

All HTTP traffic is mocked following the same pattern as the
$cohort-submit client tests (patching the module-level httpx).
"""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from digiphenoms_fhir.ml_client import (
    DEFAULT_BASE_URL,
    MLServerClient,
    MLServerError,
    main as ml_main,
)


class FakeConnectError(Exception):
    pass


class FakeTimeout(Exception):
    pass


def make_client(**kwargs) -> MLServerClient:
    kwargs.setdefault("base_url", "http://ml.test")
    kwargs.setdefault("token", "test-token")
    return MLServerClient(**kwargs)


def make_response(status_code=200, json_data=None, content=b"", text=""):
    response = MagicMock()
    response.status_code = status_code
    if json_data is not None:
        response.json.return_value = json_data
        response.text = json.dumps(json_data)
    else:
        response.json.side_effect = ValueError("not json")
        response.text = text
    response.content = content
    return response


def zip_bytes(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class TestClientConfiguration:
    def test_token_from_environment(self, monkeypatch):
        monkeypatch.setenv("API_AUTH_TOKEN", "env-token")
        client = MLServerClient(base_url="http://ml.test")
        assert client.token == "env-token"

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
        with pytest.raises(MLServerError, match="API_AUTH_TOKEN"):
            MLServerClient(base_url="http://ml.test")

    def test_base_url_from_environment(self, monkeypatch):
        monkeypatch.setenv("ML_SERVER_URL", "http://tunnel:9000")
        client = MLServerClient(token="t")
        assert client.base_url == "http://tunnel:9000"

    def test_default_base_url(self, monkeypatch):
        monkeypatch.delenv("ML_SERVER_URL", raising=False)
        client = MLServerClient(token="t")
        assert client.base_url == DEFAULT_BASE_URL

    def test_trailing_slash_stripped(self):
        client = make_client(base_url="http://ml.test/")
        assert client.base_url == "http://ml.test"

    def test_timeout_from_environment(self, monkeypatch):
        monkeypatch.setenv("ML_SERVER_TIMEOUT", "120")
        client = make_client()
        assert client.timeout == 120.0

    def test_timeout_param_beats_environment(self, monkeypatch):
        monkeypatch.setenv("ML_SERVER_TIMEOUT", "120")
        client = make_client(timeout=5.0)
        assert client.timeout == 5.0

    def test_invalid_timeout_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("ML_SERVER_TIMEOUT", "not-a-number")
        client = make_client()
        assert client.timeout == 60.0


# ---------------------------------------------------------------------------
# Job management
# ---------------------------------------------------------------------------
class TestJobManagement:
    def _request(self, client_call, json_data=None):
        """Run a client call with mocked httpx; return (result, request call)."""
        with patch("digiphenoms_fhir.ml_client.httpx") as mock_httpx:
            mock_httpx.request.return_value = make_response(
                json_data=json_data if json_data is not None else {"job_id": "j1"}
            )
            mock_httpx.ConnectError = FakeConnectError
            mock_httpx.TimeoutException = FakeTimeout
            result = client_call(make_client())
            return result, mock_httpx.request.call_args

    def test_start_training_posts_job_type(self):
        result, call = self._request(lambda c: c.start_training())
        method, url = call.args
        assert method == "POST"
        assert url == "http://ml.test/jobs"
        assert call.kwargs["json"] == {"job_type": "training"}
        assert result == {"job_id": "j1"}

    def test_bearer_token_sent(self):
        _, call = self._request(lambda c: c.start_training())
        assert call.kwargs["headers"]["Authorization"] == "Bearer test-token"

    def test_start_synthesis_payload(self):
        _, call = self._request(
            lambda c: c.start_synthesis("train-1", scale_factor=2.5)
        )
        assert call.kwargs["json"] == {
            "job_type": "synthesis",
            "scale_factor": 2.5,
            "training_job_id": "train-1",
        }

    def test_start_evaluation_payload(self):
        _, call = self._request(lambda c: c.start_evaluation("syn-1"))
        assert call.kwargs["json"] == {
            "job_type": "evaluation",
            "synthesis_job_id": "syn-1",
        }

    def test_create_job_omits_none_params(self):
        _, call = self._request(
            lambda c: c.create_job("training", scale_factor=None)
        )
        assert call.kwargs["json"] == {"job_type": "training"}

    def test_create_job_rejects_unknown_type(self):
        with pytest.raises(MLServerError, match="job_type"):
            make_client().create_job("mystery")

    def test_get_job_uses_job_path(self):
        result, call = self._request(
            lambda c: c.get_job("j-9"), json_data={"job_id": "j-9", "status": "running"}
        )
        method, url = call.args
        assert method == "GET"
        assert url == "http://ml.test/jobs/j-9"
        assert result["status"] == "running"

    def test_fetch_openapi(self):
        result, call = self._request(
            lambda c: c.fetch_openapi(), json_data={"openapi": "3.1.0"}
        )
        _, url = call.args
        assert url == "http://ml.test/openapi.json"
        assert result["openapi"] == "3.1.0"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
class TestErrorHandling:
    def _failing_request(self, response=None, side_effect=None):
        with patch("digiphenoms_fhir.ml_client.httpx") as mock_httpx:
            mock_httpx.ConnectError = FakeConnectError
            mock_httpx.TimeoutException = FakeTimeout
            if side_effect is not None:
                mock_httpx.request.side_effect = side_effect
            else:
                mock_httpx.request.return_value = response
            with pytest.raises(MLServerError) as exc_info:
                make_client().start_training()
            return exc_info.value

    def test_http_401_mentions_token(self):
        err = self._failing_request(
            make_response(401, json_data={"detail": "bad token"})
        )
        assert err.status_code == 401
        assert "API_AUTH_TOKEN" in str(err)

    def test_http_404(self):
        err = self._failing_request(make_response(404, text="not found"))
        assert err.status_code == 404

    def test_http_422_includes_detail(self):
        err = self._failing_request(
            make_response(422, json_data={"detail": "training_job_id required"})
        )
        assert "training_job_id required" in str(err)

    def test_http_500(self):
        err = self._failing_request(make_response(500, text="boom"))
        assert err.status_code == 500

    def test_connect_error_mentions_tunnel(self):
        err = self._failing_request(side_effect=FakeConnectError("refused"))
        assert "SSH port forwarding" in str(err)

    def test_timeout_error(self):
        err = self._failing_request(side_effect=FakeTimeout("slow"))
        assert "timed out" in str(err)


# ---------------------------------------------------------------------------
# Job polling
# ---------------------------------------------------------------------------
class TestWaitForJob:
    def _wait(self, job_sequence, **wait_kwargs):
        with patch("digiphenoms_fhir.ml_client.httpx") as mock_httpx, patch(
            "digiphenoms_fhir.ml_client.time.sleep"
        ):
            mock_httpx.ConnectError = FakeConnectError
            mock_httpx.TimeoutException = FakeTimeout
            mock_httpx.request.side_effect = [
                make_response(json_data=job) for job in job_sequence
            ]
            wait_kwargs.setdefault("poll_interval", 0.01)
            return make_client().wait_for_job("j1", **wait_kwargs)

    def test_polls_until_completed(self):
        job = self._wait(
            [
                {"job_id": "j1", "status": "queued"},
                {"job_id": "j1", "status": "running"},
                {"job_id": "j1", "status": "completed"},
            ]
        )
        assert job["status"] == "completed"

    def test_alternative_state_key(self):
        job = self._wait([{"job_id": "j1", "state": "finished"}])
        assert job["state"] == "finished"

    def test_failure_status_raises(self):
        with pytest.raises(MLServerError, match="failed"):
            self._wait([{"job_id": "j1", "status": "failed"}])

    def test_no_status_field_returns_immediately(self):
        job = self._wait([{"job_id": "j1"}])
        assert job == {"job_id": "j1"}

    def test_timeout_raises(self):
        with pytest.raises(MLServerError, match="Timed out"):
            self._wait(
                [{"status": "running"}, {"status": "running"}],
                timeout=0.0,
            )


# ---------------------------------------------------------------------------
# Artifact downloads
# ---------------------------------------------------------------------------
class TestDownloads:
    def _download(self, content, tmp_path, method="download_dataset"):
        with patch("digiphenoms_fhir.ml_client.httpx") as mock_httpx:
            mock_httpx.ConnectError = FakeConnectError
            mock_httpx.TimeoutException = FakeTimeout
            mock_httpx.request.return_value = make_response(content=content)
            client = make_client()
            files = getattr(client, method)("job-1", tmp_path)
            return files, mock_httpx.request.call_args

    def test_dataset_extracts_csv_files(self, tmp_path):
        content = zip_bytes(
            {"patients.csv": "a,b\n1,2", "mrt.csv": "c,d\n3,4"}
        )
        files, call = self._download(content, tmp_path)
        _, url = call.args
        assert url == "http://ml.test/jobs/job-1/dataset"
        assert sorted(f.name for f in files) == ["mrt.csv", "patients.csv"]
        assert (tmp_path / "patients.csv").read_text() == "a,b\n1,2"

    def test_nested_members_are_flattened(self, tmp_path):
        content = zip_bytes({"export/tables/wst.csv": "x\n1"})
        files, _ = self._download(content, tmp_path)
        assert [f.name for f in files] == ["wst.csv"]
        assert (tmp_path / "wst.csv").exists()

    def test_basename_collision_uses_full_path(self, tmp_path):
        content = zip_bytes({"a/data.csv": "1", "b/data.csv": "2"})
        files, _ = self._download(content, tmp_path)
        names = sorted(f.name for f in files)
        assert "data.csv" in names
        assert "b_data.csv" in names

    def test_traversal_members_are_skipped(self, tmp_path):
        content = zip_bytes({"../evil.csv": "x", "ok.csv": "y"})
        files, _ = self._download(content, tmp_path)
        assert [f.name for f in files] == ["ok.csv"]
        assert not (tmp_path.parent / "evil.csv").exists()

    def test_invalid_zip_raises(self, tmp_path):
        with pytest.raises(MLServerError, match="ZIP"):
            self._download(b"this is not a zip", tmp_path)

    def test_empty_zip_returns_no_files(self, tmp_path):
        files, _ = self._download(zip_bytes({}), tmp_path)
        assert files == []

    def test_report_uses_report_path(self, tmp_path):
        content = zip_bytes({"report.html": "<html></html>"})
        files, call = self._download(content, tmp_path, method="download_report")
        _, url = call.args
        assert url == "http://ml.test/jobs/job-1/report"
        assert [f.name for f in files] == ["report.html"]


# ---------------------------------------------------------------------------
# CLI (digiphenoms-ml)
# ---------------------------------------------------------------------------
class TestMlCli:
    def test_train_prints_job(self, capsys):
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.start_training.return_value = {
                "job_id": "j1",
                "status": "queued",
            }
            exit_code = ml_main(["train"])
        assert exit_code == 0
        assert "j1" in capsys.readouterr().out

    def test_synthesize_forwards_arguments(self):
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.start_synthesis.return_value = {"job_id": "s1"}
            exit_code = ml_main(
                ["synthesize", "--training-job", "t1", "--scale-factor", "2.0"]
            )
        assert exit_code == 0
        mock_cls.return_value.start_synthesis.assert_called_once_with(
            "t1", scale_factor=2.0
        )

    def test_status_wait_polls(self):
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.wait_for_job.return_value = {"status": "completed"}
            exit_code = ml_main(["status", "j1", "--wait"])
        assert exit_code == 0
        mock_cls.return_value.wait_for_job.assert_called_once()

    def test_download_dataset_lists_files(self, tmp_path, capsys):
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.download_dataset.return_value = [
                tmp_path / "patients.csv"
            ]
            exit_code = ml_main(
                ["download-dataset", "syn-1", "--output", str(tmp_path)]
            )
        assert exit_code == 0
        assert "patients.csv" in capsys.readouterr().out

    def test_openapi_written_to_file(self, tmp_path):
        target = tmp_path / "openapi.json"
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.fetch_openapi.return_value = {"openapi": "3.1.0"}
            exit_code = ml_main(["openapi", "--output", str(target)])
        assert exit_code == 0
        assert json.loads(target.read_text())["openapi"] == "3.1.0"

    def test_ml_server_error_returns_nonzero(self):
        with patch("digiphenoms_fhir.ml_client.MLServerClient") as mock_cls:
            mock_cls.return_value.start_training.side_effect = MLServerError("down")
            exit_code = ml_main(["train"])
        assert exit_code == 1
