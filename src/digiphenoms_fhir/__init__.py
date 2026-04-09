"""
DigiPhenoMS FHIR Mapper — Configuration-driven CSV-to-FHIR R4 Transformation.

This package provides a mapping engine that transforms CSV data (conforming to
the DigiPhenoMS data schemas) into FHIR R4 resources using YAML-based
configuration files.
"""

from digiphenoms_fhir.mapper import (
    FHIRMapper,
    MappingConfig,
    Pipeline,
    PipelineConfig,
    ResourceBuilder,
    TerminologyMap,
    build_bundle,
)

__version__ = "1.0.0"

__all__ = [
    "FHIRMapper",
    "MappingConfig",
    "Pipeline",
    "PipelineConfig",
    "ResourceBuilder",
    "TerminologyMap",
    "build_bundle",
]
