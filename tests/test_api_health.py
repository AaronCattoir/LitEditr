"""FastAPI smoke tests (optional [api] extra)."""

import pytest
from fastapi.testclient import TestClient

from narrative_dag.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_ready(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
