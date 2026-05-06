"""Smoke tests for the API surface. Demo-only — no network calls."""

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    # `with` is required so the FastAPI lifespan + Starlette portal stay open
    # for the duration of the test, allowing the analyze endpoint's
    # background task to actually progress between subsequent requests.
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_sources_lists_demo(client: TestClient) -> None:
    r = client.get("/api/sources")
    assert r.status_code == 200
    body = r.json()
    ids = [s["id"] for s in body["sources"]]
    assert "demo" in ids
    demo = next(s for s in body["sources"] if s["id"] == "demo")
    assert demo["status"] == "available"
    assert demo["requires_internet"] is False


def test_analyze_rejects_unavailable_source(client: TestClient) -> None:
    r = client.post(
        "/api/analyze",
        json={
            "source_ids": ["nmdb"],
            "start": "2025-09-01",
            "end": "2025-09-08",
        },
    )
    assert r.status_code == 400
    assert "not available" in r.json()["detail"]


def test_analyze_rejects_bad_date_range(client: TestClient) -> None:
    r = client.post(
        "/api/analyze",
        json={
            "source_ids": ["demo"],
            "start": "2025-09-08",
            "end": "2025-09-01",
        },
    )
    assert r.status_code == 400


def test_analyze_demo_end_to_end(client: TestClient) -> None:
    r = client.post(
        "/api/analyze",
        json={
            "source_ids": ["demo"],
            "start": "2025-09-01",
            "end": "2025-09-02",
            "settings": {"null_shifts_count": 10},
        },
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    body: dict | None = None
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        time.sleep(0.5)
        resp = client.get(f"/api/analysis/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("succeeded", "failed"):
            break
    else:
        raise AssertionError("Demo job did not finish in 60s")

    assert body is not None
    assert body["status"] == "succeeded", body.get("error")
    assert "result" in body
    summary = body["result"]["summary"]
    assert summary["sources_count"] >= 1
    assert summary["duration_seconds"] >= 0
