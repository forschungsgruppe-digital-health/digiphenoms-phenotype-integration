"""
DigiPhenoMS ML-Server Client — Synthetic Data Job API
======================================================

Client for the DigiPhenoMS ML server that generates synthetic assessment
data (tables: Patienten, MRT, LCLAT, WST). The server exposes a job-based
REST API (see ``docs/ml_server_api.md``):

    POST /jobs                    start a training / synthesis / evaluation job
    GET  /jobs/{id}               query job status
    GET  /jobs/{id}/dataset       download synthetic dataset (ZIP of CSVs)
    GET  /jobs/{id}/report        download evaluation report (ZIP)
    GET  /openapi.json            OpenAPI specification

The ML server sits behind a restrictive proxy; requests are made against a
local SSH port forwarding (default ``http://localhost:8000``). Host and
credentials are provided by the ML team (see docs/ml_server_api.md):

    ssh -L 8000:localhost:8000 "$ML_SERVER_SSH_USER@$ML_SERVER_SSH_HOST" -N

Every request requires a Bearer token, taken from the ``API_AUTH_TOKEN``
environment variable (or passed explicitly).

Usage as library:
    from digiphenoms_fhir.ml_client import MLServerClient
    client = MLServerClient()                       # token from API_AUTH_TOKEN
    job = client.start_synthesis("ee81f8cd-...", scale_factor=1.0)
    client.wait_for_job(job["job_id"])
    files = client.download_dataset(job["job_id"], "data/")

Usage standalone:
    digiphenoms-ml train
    digiphenoms-ml synthesize --training-job <id> --scale-factor 1.0
    digiphenoms-ml evaluate --synthesis-job <id>
    digiphenoms-ml status <job-id> [--wait]
    digiphenoms-ml download-dataset <job-id> --output data/
    digiphenoms-ml download-report <job-id> --output reports/
    digiphenoms-ml openapi --output openapi.json
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger("digiphenoms.ml_client")

DEFAULT_BASE_URL = "http://localhost:8000"
TOKEN_ENV_VAR = "API_AUTH_TOKEN"
BASE_URL_ENV_VAR = "ML_SERVER_URL"

JOB_TYPES = ("training", "synthesis", "evaluation")

# Job status vocabularies — the OpenAPI spec is only reachable through the
# SSH tunnel, so status parsing is deliberately tolerant.
_SUCCESS_STATUSES = {"completed", "succeeded", "success", "finished", "done"}
_FAILURE_STATUSES = {"failed", "error", "errored", "cancelled", "canceled", "aborted"}
_ID_KEYS = ("job_id", "id", "jobId", "uuid")
_STATUS_KEYS = ("status", "state", "job_status")


class MLServerError(Exception):
    """Raised when a request to the ML server fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class MLServerClient:
    """HTTP client for the DigiPhenoMS ML server job API.

    Requires the ``httpx`` package (``pip install httpx``).

    Args:
        base_url: Server base URL. Defaults to ``$ML_SERVER_URL`` or
            ``http://localhost:8000`` (the SSH port forwarding target).
        token: Bearer token. Defaults to ``$API_AUTH_TOKEN``.
        timeout: Per-request timeout in seconds.
        verify_ssl: Verify TLS certificates.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 60.0,
        verify_ssl: bool = True,
    ):
        if httpx is None:
            raise ImportError(
                "httpx is required for the ML server client. "
                "Install it with: pip install httpx"
            )
        self.base_url = (
            base_url or os.environ.get(BASE_URL_ENV_VAR) or DEFAULT_BASE_URL
        ).rstrip("/")
        self.token = token or os.environ.get(TOKEN_ENV_VAR)
        if not self.token:
            raise MLServerError(
                "ML server API token missing — set the "
                f"{TOKEN_ENV_VAR} environment variable or pass token=..."
            )
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    # -- job management -------------------------------------------------------

    def create_job(self, job_type: str, **params: Any) -> dict:
        """Start a job (``POST /jobs``).

        Args:
            job_type: One of ``training``, ``synthesis``, ``evaluation``.
            **params: Additional job parameters (e.g. ``scale_factor``,
                ``training_job_id``, ``synthesis_job_id``). ``None`` values
                are omitted.
        """
        if job_type not in JOB_TYPES:
            raise MLServerError(
                f"Unknown job_type {job_type!r} — expected one of {JOB_TYPES}"
            )
        payload = {"job_type": job_type}
        payload.update({k: v for k, v in params.items() if v is not None})
        response = self._request("POST", "/jobs", json=payload)
        return self._parse_json(response)

    def start_training(self) -> dict:
        """Start a training job on the ML server."""
        return self.create_job("training")

    def start_synthesis(self, training_job_id: str, scale_factor: float = 1.0) -> dict:
        """Start a synthesis job based on a completed training job."""
        return self.create_job(
            "synthesis",
            scale_factor=scale_factor,
            training_job_id=training_job_id,
        )

    def start_evaluation(self, synthesis_job_id: str) -> dict:
        """Start an evaluation job based on a completed synthesis job."""
        return self.create_job("evaluation", synthesis_job_id=synthesis_job_id)

    def get_job(self, job_id: str) -> dict:
        """Fetch job details/status (``GET /jobs/{id}``)."""
        response = self._request("GET", f"/jobs/{job_id}")
        return self._parse_json(response)

    def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 10.0,
        timeout: float = 3600.0,
    ) -> dict:
        """Poll a job until it reaches a terminal status.

        Returns the final job dict on success. If the job document exposes
        no recognizable status field, it is returned as-is after the first
        poll (nothing to wait on).

        Raises:
            MLServerError: If the job fails or ``timeout`` is exceeded.
        """
        deadline = time.monotonic() + timeout
        while True:
            job = self.get_job(job_id)
            status = self.job_status(job)
            if status is None:
                logger.warning(
                    "Job %s exposes no status field — not waiting", job_id
                )
                return job
            normalized = status.lower()
            if normalized in _SUCCESS_STATUSES:
                logger.info("Job %s finished with status %r", job_id, status)
                return job
            if normalized in _FAILURE_STATUSES:
                raise MLServerError(f"Job {job_id} failed with status {status!r}")
            if time.monotonic() >= deadline:
                raise MLServerError(
                    f"Timed out after {timeout}s waiting for job {job_id} "
                    f"(last status: {status!r})"
                )
            logger.info("Job %s status %r — polling again in %ss", job_id, status, poll_interval)
            time.sleep(poll_interval)

    @staticmethod
    def job_status(job: dict) -> str | None:
        """Extract the status field from a job dict (tolerant of key naming)."""
        for key in _STATUS_KEYS:
            val = job.get(key)
            if isinstance(val, str) and val:
                return val
        return None

    @staticmethod
    def job_id(job: dict) -> str | None:
        """Extract the job id from a job dict (tolerant of key naming)."""
        for key in _ID_KEYS:
            val = job.get(key)
            if isinstance(val, (str, int)) and str(val):
                return str(val)
        return None

    # -- artifact download ----------------------------------------------------

    def download_dataset(self, synthesis_job_id: str, target_dir: str | Path) -> list[Path]:
        """Download and extract the synthetic dataset of a synthesis job.

        The dataset ZIP is extracted flat into ``target_dir`` (the mapping
        pipeline searches its data directory non-recursively).

        Returns the list of extracted file paths.
        """
        return self._download_zip(f"/jobs/{synthesis_job_id}/dataset", target_dir)

    def download_report(self, evaluation_job_id: str, target_dir: str | Path) -> list[Path]:
        """Download and extract the evaluation report of an evaluation job."""
        return self._download_zip(f"/jobs/{evaluation_job_id}/report", target_dir)

    def fetch_openapi(self) -> dict:
        """Fetch the OpenAPI specification (``GET /openapi.json``)."""
        response = self._request("GET", "/openapi.json")
        return self._parse_json(response)

    # -- internals -------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any):
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", f"Bearer {self.token}")
        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
                **kwargs,
            )
        except httpx.ConnectError as exc:
            raise MLServerError(
                f"Connection to {self.base_url} failed: {exc}. "
                "Is the SSH port forwarding to the ML server running? "
                "(ssh -L 8000:localhost:8000 <user>@<ml-server-host> -N, "
                "see docs/ml_server_api.md)"
            ) from exc
        except httpx.TimeoutException as exc:
            raise MLServerError(
                f"Request to {url} timed out after {self.timeout}s"
            ) from exc

        if response.status_code >= 400:
            raise MLServerError(
                self._error_message(response), response.status_code
            )
        return response

    @staticmethod
    def _error_message(response) -> str:
        messages = {
            401: "Authentication failed — check API_AUTH_TOKEN",
            403: "Insufficient permissions — check API_AUTH_TOKEN",
            404: "Not found — check the job id and its job type",
            422: "Invalid request payload",
        }
        msg = messages.get(
            response.status_code,
            f"ML server error (HTTP {response.status_code})",
        )
        detail = ""
        try:
            body = response.json()
            detail = body.get("detail") or body.get("message") or ""
            if isinstance(detail, (list, dict)):
                detail = json.dumps(detail, ensure_ascii=False)
        except Exception:
            detail = response.text[:200] if response.text else ""
        return f"{msg}: {detail}" if detail else f"{msg} (HTTP {response.status_code})"

    @staticmethod
    def _parse_json(response) -> dict:
        try:
            return response.json()
        except Exception as exc:
            raise MLServerError(
                f"ML server returned invalid JSON: {exc}"
            ) from exc

    def _download_zip(self, path: str, target_dir: str | Path) -> list[Path]:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        response = self._request("GET", path)

        try:
            archive = zipfile.ZipFile(io.BytesIO(response.content))
        except zipfile.BadZipFile as exc:
            raise MLServerError(
                f"Response from {path} is not a valid ZIP archive"
            ) from exc

        extracted: list[Path] = []
        seen_names: set[str] = set()
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = self._safe_member_name(member.filename, seen_names)
            if name is None:
                logger.warning("Skipping unsafe ZIP member: %r", member.filename)
                continue
            seen_names.add(name)
            out_path = target / name
            with archive.open(member) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
            extracted.append(out_path)
            logger.info("Extracted %s", out_path)

        if not extracted:
            logger.warning("ZIP archive from %s contained no files", path)
        return extracted

    @staticmethod
    def _safe_member_name(member_name: str, seen: set[str]) -> str | None:
        """Flatten a ZIP member to a safe file name inside the target dir.

        Members are extracted flat (basename only) so the pipeline's
        non-recursive glob finds them; on basename collision the full
        sanitized path is used instead. Absolute paths and traversal
        segments are rejected.
        """
        pure = PurePosixPath(member_name.replace("\\", "/"))
        parts = [p for p in pure.parts if p not in ("", ".")]
        if not parts or pure.is_absolute() or ".." in parts:
            return None
        name = parts[-1]
        if name in seen:
            name = "_".join(re.sub(r"[^\w.\-]", "_", p) for p in parts)
        return name


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help=f"ML server base URL (default: ${BASE_URL_ENV_VAR} or {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="digiphenoms-ml",
        description=(
            "DigiPhenoMS ML server client — manage synthetic data jobs. "
            f"The API token is read from ${TOKEN_ENV_VAR}."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_train = sub.add_parser("train", help="Start a training job")
    _add_common_args(p_train)

    p_synth = sub.add_parser("synthesize", help="Start a synthesis job")
    p_synth.add_argument("--training-job", required=True, help="Training job id the model was built by")
    p_synth.add_argument("--scale-factor", type=float, default=1.0)
    _add_common_args(p_synth)

    p_eval = sub.add_parser("evaluate", help="Start an evaluation job")
    p_eval.add_argument("--synthesis-job", required=True, help="Synthesis job id to evaluate")
    _add_common_args(p_eval)

    p_status = sub.add_parser("status", help="Show job status")
    p_status.add_argument("job_id")
    p_status.add_argument("--wait", action="store_true", help="Poll until the job finishes")
    p_status.add_argument("--poll-interval", type=float, default=10.0)
    p_status.add_argument("--wait-timeout", type=float, default=3600.0)
    _add_common_args(p_status)

    p_data = sub.add_parser("download-dataset", help="Download a synthetic dataset (ZIP → CSVs)")
    p_data.add_argument("job_id", help="Synthesis job id")
    p_data.add_argument("--output", type=str, default="data/", help="Target directory (default: data/)")
    _add_common_args(p_data)

    p_report = sub.add_parser("download-report", help="Download an evaluation report")
    p_report.add_argument("job_id", help="Evaluation job id")
    p_report.add_argument("--output", type=str, default="reports/", help="Target directory (default: reports/)")
    _add_common_args(p_report)

    p_openapi = sub.add_parser("openapi", help="Fetch the OpenAPI specification")
    p_openapi.add_argument("--output", type=str, default=None, help="Write spec to this file instead of stdout")
    _add_common_args(p_openapi)

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        client = MLServerClient(
            base_url=args.base_url,
            timeout=args.timeout,
            verify_ssl=not args.insecure,
        )

        if args.command == "train":
            job = client.start_training()
        elif args.command == "synthesize":
            job = client.start_synthesis(args.training_job, scale_factor=args.scale_factor)
        elif args.command == "evaluate":
            job = client.start_evaluation(args.synthesis_job)
        elif args.command == "status":
            if args.wait:
                job = client.wait_for_job(
                    args.job_id,
                    poll_interval=args.poll_interval,
                    timeout=args.wait_timeout,
                )
            else:
                job = client.get_job(args.job_id)
        elif args.command == "download-dataset":
            files = client.download_dataset(args.job_id, args.output)
            print(f"Downloaded {len(files)} file(s) to {args.output}:")
            for f in files:
                print(f"  {f}")
            return 0
        elif args.command == "download-report":
            files = client.download_report(args.job_id, args.output)
            print(f"Downloaded {len(files)} file(s) to {args.output}:")
            for f in files:
                print(f"  {f}")
            return 0
        elif args.command == "openapi":
            spec = client.fetch_openapi()
            text = json.dumps(spec, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(text, encoding="utf-8")
                print(f"OpenAPI specification written to {args.output}")
            else:
                print(text)
            return 0
        else:  # pragma: no cover — argparse enforces the command set
            parser.error(f"Unknown command: {args.command}")

        print(json.dumps(job, indent=2, ensure_ascii=False))
        return 0

    except MLServerError as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
