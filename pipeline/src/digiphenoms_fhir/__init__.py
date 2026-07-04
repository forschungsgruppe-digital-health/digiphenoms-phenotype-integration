"""
DigiPhenoMS FHIR Integration — CSV-to-FHIR R4 Mapping and Import.

This package provides a configuration-driven integration engine that transforms
CSV data (conforming to the DigiPhenoMS data schemas) into FHIR R4 resources
and optionally submits them to a HAPI FHIR server via ``$cohort-submit``.
"""

from digiphenoms_fhir.mapper import (
    CohortSubmitClient,
    CohortSubmitError,
    FHIRMapper,
    MappingConfig,
    Pipeline,
    PipelineConfig,
    ResourceBuilder,
    TerminologyMap,
    build_bundle,
)
from digiphenoms_fhir.ml_client import (
    MLServerClient,
    MLServerError,
)

__version__ = "1.0.0"  # x-release-please-version

__all__ = [
    "CohortSubmitClient",
    "CohortSubmitError",
    "FHIRMapper",
    "MLServerClient",
    "MLServerError",
    "MappingConfig",
    "Pipeline",
    "PipelineConfig",
    "ResourceBuilder",
    "TerminologyMap",
    "build_bundle",
]
