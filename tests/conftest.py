import json
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_catalog_path():
    return FIXTURES_DIR / "sample_catalog.json"


@pytest.fixture
def sample_catalog_data(sample_catalog_path):
    return json.loads(sample_catalog_path.read_text())
