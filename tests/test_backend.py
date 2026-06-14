"""Tests for the de-drum FastAPI backend service."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path for imports from services/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from services.backend.main import app, _get_job, _new_job, _update_job

client = TestClient(app)


# ── Job store unit tests ───────────────────────────────────────────


def test_new_job_creates_unique_id() -> None:
    """Each call to _new_job returns a different job ID."""
    id1 = _new_job("url", "htdemucs")
    id2 = _new_job("file", "htdemucs_ft")
    assert id1 != id2
    assert len(id1) == 12
    assert len(id2) == 12


def test_new_job_sets_initial_state() -> None:
    """A freshly created job starts as 'pending' with the given fields."""
    job_id = _new_job("url", "htdemucs", url="https://example.com/song")
    job = _get_job(job_id)
    assert job is not None
    assert job["status"] == "pending"
    assert job["type"] == "url"
    assert job["model"] == "htdemucs"
    assert job["url"] == "https://example.com/song"
    assert job["error"] is None
    assert job["files"] == {}


def test_update_job_modifies_fields() -> None:
    """_update_job should merge the given fields into the existing job."""
    job_id = _new_job("file", "htdemucs")
    _update_job(job_id, status="processing")
    job = _get_job(job_id)
    assert job["status"] == "processing"
    assert job["model"] == "htdemucs"  # original field preserved
    _update_job(job_id, status="done", files={"drums.mp3": "/path/to/drums.mp3"})
    job = _get_job(job_id)
    assert job["status"] == "done"
    assert "drums.mp3" in job["files"]


def test_update_job_ignores_nonexistent() -> None:
    """Updating a job that does not exist should not raise."""
    _update_job("nonexistent", status="done")  # should not throw


def test_get_job_returns_none_for_missing() -> None:
    """Asking for a job that does not exist returns None."""
    assert _get_job("no-such-job") is None


# ── Health endpoint ────────────────────────────────────────────────


def test_health_endpoint() -> None:
    """GET /backend/health returns 200 with status ok."""
    response = client.get("/backend/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_job_endpoint_not_found() -> None:
    """GET /backend/jobs/:id on a missing job returns 404."""
    response = client.get("/backend/jobs/does-not-exist")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_job_endpoint_found() -> None:
    """GET /backend/jobs/:id returns the job object."""
    job_id = _new_job("url", "htdemucs")
    response = client.get(f"/backend/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["status"] == "pending"
    assert data["type"] == "url"


def test_separate_url_rejects_empty() -> None:
    """POST /backend/separate/url without a URL returns 422."""
    response = client.post("/backend/separate/url", data={"url": "", "model": "htdemucs"})
    assert response.status_code == 422


def test_separate_url_returns_job_id() -> None:
    """A valid URL submission returns 200 with a job_id."""
    response = client.post(
        "/backend/separate/url",
        data={"url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "model": "htdemucs"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 12
