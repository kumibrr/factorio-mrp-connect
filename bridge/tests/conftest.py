"""Shared fixtures for bridge tests; every caller receives an independent payload."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def pumpworks_payload():
    path = Path(__file__).resolve().parents[2] / "contracts/fixtures/pumpworks-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))
