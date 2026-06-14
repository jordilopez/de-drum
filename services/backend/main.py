"""FastAPI backend service for de-drum — wraps separation + analysis as async jobs."""
# ruff: noqa: I001 — sys.path.insert breaks standard import ordering

import shutil
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

# ── Import core logic from the shared src/ directory ───────────────
SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))
from separate import download_audio, separate as _separate  # noqa: E402

app = FastAPI(
    title="de-drum Backend",
    version="1.0.0",
    description="Async audio separation service powered by Demucs.",
)

# -------------------------------------------------------------------
# Job store (in-memory — use Redis/DB in production)
# -------------------------------------------------------------------
_jobs: dict[str, dict] = {}
_lock = threading.Lock()

OUTPUT_DIR = Path("/app/output")  # Docker volume mount
INPUT_DIR = Path("/app/input")


def _new_job(job_type: str, model: str, **extra) -> str:
    """Create a new job and return its unique ID."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "type": job_type,  # "url" or "file"
            "model": model,
            "error": None,
            "files": {},
            **extra,
        }
    return job_id


def _update_job(job_id: str, **fields) -> None:
    """Atomically update fields on a job entry."""
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _get_job(job_id: str) -> dict | None:
    """Thread-safe read of a job."""
    with _lock:
        return _jobs.get(job_id)


# -------------------------------------------------------------------
# Background processing
# -------------------------------------------------------------------


def _run_separation(job_id: str, source_path: Path, model: str) -> None:
    """Run the Demucs separation in a background thread.

    Handles errors gracefully (no ``sys.exit``) and updates the job
    store on completion or failure.
    """
    try:
        _update_job(job_id, status="processing")

        job_output = OUTPUT_DIR / job_id
        job_output.mkdir(parents=True, exist_ok=True)

        # The existing `_separate()` may call sys.exit(1) on error.
        # Catch SystemExit so the background thread doesn't die.
        try:
            _separate(str(source_path), str(job_output), model)
        except SystemExit:
            # The existing `separate()` calls sys.exit(1) on failure.
            # Convert to a regular exception so the thread continues.
            raise RuntimeError("Separation failed (Demucs error)")

        # Collect output files
        song_dir = job_output / source_path.stem
        files: dict[str, str] = {}
        if song_dir.exists():
            for f in sorted(song_dir.iterdir()):
                if f.is_file():
                    files[f.name] = str(f)
        else:
            # Fallback: flat output
            for f in sorted(job_output.iterdir()):
                if f.is_file():
                    files[f.name] = str(f)

        _update_job(
            job_id,
            status="done",
            files=files,
            song_dir=str(song_dir if song_dir.exists() else job_output),
        )

    except RuntimeError as e:
        _update_job(job_id, status="error", error=str(e))
    except Exception as e:
        _update_job(job_id, status="error", error=str(e))


def _process_url_job(job_id: str, url: str, model: str) -> None:
    """Download audio from a YouTube URL, then separate."""
    try:
        _update_job(job_id, status="downloading")
        tmp_dir = Path(tempfile.mkdtemp(prefix="dedrum_"))
        audio_path = download_audio(url, str(tmp_dir))
        _run_separation(job_id, audio_path, model)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        _update_job(job_id, status="error", error=str(e))


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------


@app.post("/backend/separate/url")
async def separate_url(
    url: str = Form(..., description="YouTube URL to download and separate"),
    model: str = Form("htdemucs", description="Demucs model name"),
):
    """Submit a YouTube URL for separation (async, returns ``job_id``)."""
    if not url.strip():
        raise HTTPException(status_code=422, detail="URL is required")

    job_id = _new_job("url", model, url=url)
    thread = threading.Thread(
        target=_process_url_job,
        args=(job_id, url, model),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.post("/backend/separate/file")
async def separate_file(
    file: UploadFile = File(..., description="Audio file to separate"),
    model: str = Form("htdemucs", description="Demucs model name"),
):
    """Upload an audio file for separation (async, returns ``job_id``)."""
    if not file.filename:
        raise HTTPException(status_code=422, detail="File is required")

    job_id = _new_job("file", model, filename=file.filename)

    input_dir = INPUT_DIR / job_id
    input_dir.mkdir(parents=True, exist_ok=True)
    file_path = input_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    thread = threading.Thread(
        target=_run_separation,
        args=(job_id, file_path, model),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/backend/jobs/{job_id}")
async def get_job(job_id: str):
    """Get the current status and metadata of a separation job."""
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/backend/jobs/{job_id}/download/{filename:path}")
async def download_file(job_id: str, filename: str):
    """Download a result file from a completed job."""
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not completed yet")

    file_path = job.get("files", {}).get(filename)
    if not file_path or not Path(file_path).exists():
        # Try deriving from song_dir
        song_dir = job.get("song_dir")
        if song_dir:
            alt = Path(song_dir) / filename
            if alt.exists():
                file_path = str(alt)
            else:
                raise HTTPException(status_code=404, detail="File not found")
        else:
            raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, filename=filename)


@app.get("/backend/health")
async def health():
    """Health check."""
    return {"status": "ok"}


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
