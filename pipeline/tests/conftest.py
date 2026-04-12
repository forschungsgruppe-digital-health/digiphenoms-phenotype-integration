"""Shared fixtures for DigiPhenoMS FHIR Mapper tests."""

from pathlib import Path

import pytest

from digiphenoms_fhir.mapper import (
    Pipeline,
    PipelineConfig,
    ResourceBuilder,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIG_DIR = Path(__file__).parent.parent / "config"


@pytest.fixture
def fixtures_dir():
    """Path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def config_dir():
    """Path to the mapping configuration directory."""
    return CONFIG_DIR


@pytest.fixture
def pipeline_cfg(config_dir):
    """Loaded PipelineConfig."""
    return PipelineConfig.from_yaml(config_dir / "pipeline.yaml")


@pytest.fixture
def builder(pipeline_cfg, config_dir):
    """ResourceBuilder instance for test use."""
    return ResourceBuilder(pipeline_cfg, config_dir)


@pytest.fixture
def pipeline(config_dir):
    """Pipeline instance pointing to the project config."""
    return Pipeline(config_dir=config_dir)
