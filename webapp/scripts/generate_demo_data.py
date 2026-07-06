#!/usr/bin/env python3
"""Generate the demonstrator's synthetic demo dataset.

Runs the DigiPhenoMS mapping pipeline over the synthetic test fixtures
(pipeline/tests/fixtures) and writes all resulting FHIR resources as one
collection Bundle to webapp/public/demo-data/demo-bundle.json.

The fixtures are synthetic by construction — no real patient data is
involved at any point.

Usage (from the repository root, pipeline installed in the environment):
    python webapp/scripts/generate_demo_data.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pipeline" / "src"))

from digiphenoms_fhir.mapper import Pipeline, build_bundle  # noqa: E402

OUTPUT = REPO_ROOT / "webapp" / "public" / "demo-data" / "demo-bundle.json"


def main() -> int:
    pipeline = Pipeline(config_dir=REPO_ROOT / "pipeline" / "config")
    results = pipeline.run(data_dir=REPO_ROOT / "pipeline" / "tests" / "fixtures")

    resources = [r for step in results.values() for r in step]
    bundle = build_bundle(resources, bundle_type="collection")
    bundle["meta"] = {
        "tag": [
            {
                "system": "https://digiphenoms.tu-dresden.de/fhir/CodeSystem/digiphenoms",
                "code": "synthetic-demo-data",
                "display": "Synthetische Demo-Daten — keine echten Patientendaten",
            }
        ]
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"{len(resources)} synthetic resources → {OUTPUT.relative_to(REPO_ROOT)}")
    print(f"generated: {date.today().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
