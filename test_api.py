"""
Test suite — runs fully on CPU with mocked GPU/FFmpeg.
`pytest tests/ -v`
"""

from __future__ import annotations

import asyncio
import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# ── App bootstrap ─────────────────────────────────────────────────────────────
# Patch GPU init before importing the app so tests don't need real weights
with patch("app.core.gpu.initialize_gpu", new_callable=AsyncMock), \
     patch("app.services.job_manager.job_manager.start", new_callable=AsyncMock), \
     patch("app.services.job_manager.job_manager.stop", new_callable=AsyncMock):
    from app.main import app
    from app.models.job import JobState, JobStatus
    from app.services.job_manager import job_manager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tiny_mp4() -> bytes:
    """Minimal valid-ish MP4 byte payload for upload tests."""
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2"


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Job status — unknown ID ────────────────────────────────────────────────────

def test_get_unknown_job(client):
    r = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert r.status_code == 404


# ── Enhance endpoint — unsupported MIME ───────────────────────────────────────

def test_enhance_rejects_non_video(client):
    r = client.post(
        "/api/v1/enhance",
        files={"file": ("photo.jpg", b"fake", "image/jpeg")},
    )
    assert r.status_code == 415


# ── Enhance endpoint — happy path (queue only, pipeline mocked) ───────────────

def test_enhance_queues_job(client, tiny_mp4, tmp_path):
    with patch("app.api.routes._enqueue", new_callable=AsyncMock), \
         patch("app.core.config.settings.UPLOAD_DIR", str(tmp_path)), \
         patch("app.core.config.settings.OUTPUT_DIR", str(tmp_path)):

        r = client.post(
            "/api/v1/enhance",
            files={"file": ("sample.mp4", tiny_mp4, "video/mp4")},
            data={"scale": "4"},
        )

    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["status"] == JobStatus.QUEUED


# ── Job status transitions ────────────────────────────────────────────────────

def test_job_progress_tracking(client):
    job_id = uuid.uuid4()
    state = JobState(
        job_id=job_id,
        status=JobStatus.ENHANCING,
        total_frames=100,
        processed_frames=42,
    )
    job_manager.put(state)

    r = client.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == JobStatus.ENHANCING
    assert data["progress_pct"] == 42.0
    assert data["total_frames"] == 100


def test_job_done_returns_download_url(client):
    job_id = uuid.uuid4()
    out = f"storage/outputs/video_4k_{job_id}.mp4"
    state = JobState(
        job_id=job_id,
        status=JobStatus.DONE,
        total_frames=50,
        processed_frames=50,
        output_path=out,
    )
    job_manager.put(state)

    r = client.get(f"/api/v1/jobs/{job_id}")
    data = r.json()
    assert data["status"] == JobStatus.DONE
    assert data["download_url"] is not None
    assert "video_4k" in data["download_url"]


# ── Delete job ────────────────────────────────────────────────────────────────

def test_delete_job(client):
    job_id = uuid.uuid4()
    job_manager.put(JobState(job_id=job_id, status=JobStatus.QUEUED))

    r = client.delete(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 204

    r2 = client.get(f"/api/v1/jobs/{job_id}")
    assert r2.status_code == 404


# ── JobState progress calculation ────────────────────────────────────────────

def test_job_state_progress_zero_division():
    state = JobState(job_id=uuid.uuid4(), total_frames=0, processed_frames=0)
    assert state.progress_pct == 0.0


def test_job_state_progress_complete():
    state = JobState(job_id=uuid.uuid4(), total_frames=200, processed_frames=200)
    assert state.progress_pct == 100.0
