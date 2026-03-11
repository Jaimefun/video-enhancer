# 4K Video Enhancer

[![CI](https://github.com/YOUR_USERNAME/video-enhancer/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/video-enhancer/actions/workflows/ci.yml)
[![Docker](https://github.com/YOUR_USERNAME/video-enhancer/actions/workflows/cd.yml/badge.svg)](https://github.com/YOUR_USERNAME/video-enhancer/actions/workflows/cd.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> GPU-accelerated video upscaling API powered by **Real-ESRGAN** and **FFmpeg**,
> served via **FastAPI**.  Architecture mirrors Topaz Video AI's processing pipeline.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FastAPI Server                            │
│                                                                     │
│  POST /enhance ──► Job Queue ──► Worker Pool (asyncio)             │
│  GET  /jobs/{id}◄─────────────────────────────────────────────────  │
│  GET  /downloads/{file} (static)                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────▼────────────────┐
              │        Processing Pipeline     │
              │                                │
              │  1. FFmpeg — probe metadata    │
              │  2. FFmpeg — extract frames    │  PNG sequence
              │  3. FFmpeg — extract audio     │  AAC track
              │  4. Real-ESRGAN — GPU enhance  │  batched, tiled
              │  5. FFmpeg — reassemble video  │  H.265 MP4
              └────────────────────────────────┘
```

---

## Folder structure

```
video_enhancer/
├── app/
│   ├── main.py                  # FastAPI app + lifespan (GPU init)
│   ├── api/
│   │   └── routes.py            # POST /enhance · GET /jobs/{id} · DELETE
│   ├── core/
│   │   ├── config.py            # Pydantic settings (env-driven)
│   │   └── gpu.py               # Real-ESRGAN model loader
│   ├── models/
│   │   └── job.py               # JobState · JobStatus · API schemas
│   ├── services/
│   │   ├── ffmpeg_service.py    # probe · extract_frames · reassemble
│   │   ├── enhancer_service.py  # Real-ESRGAN batch processor
│   │   ├── pipeline.py          # end-to-end orchestration
│   │   └── job_manager.py       # async queue + worker pool
│   └── utils/
├── storage/
│   ├── uploads/                 # incoming video files
│   ├── jobs/{job_id}/
│   │   ├── frames/              # raw extracted PNGs
│   │   ├── enhanced/            # upscaled PNGs (deleted after encode)
│   │   └── audio.aac
│   └── outputs/                 # finished 4K MP4s (served as downloads)
├── weights/
│   └── RealESRGAN_x4plus.pth   # model weights (download_weights.py)
├── scripts/
│   └── download_weights.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Quick start (Docker — recommended)

```bash
# 1. Clone & enter project
git clone <repo> && cd video_enhancer

# 2. Start (weights are downloaded at build time)
docker compose up --build

# 3. Enhance a video
curl -X POST http://localhost:8000/api/v1/enhance \
  -F "file=@my_video.mp4" \
  -F "scale=4" \
  -F "output_crf=18"

# 4. Poll progress
curl http://localhost:8000/api/v1/jobs/<job_id>

# 5. Download when status == "done"
curl -O http://localhost:8000/downloads/my_video_4k_<job_id>.mp4
```

---

## Local development (no Docker)

```bash
# Prerequisites: Python 3.11, FFmpeg, CUDA 12.1 + cuDNN 8

python -m venv .venv && source .venv/bin/activate

# PyTorch with CUDA
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Rest of deps
pip install -r requirements.txt

# Download model weights
python scripts/download_weights.py

# Copy and edit env
cp .env.example .env

# Start server
uvicorn app.main:app --reload --port 8000
```

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/enhance` | Upload video, returns `job_id` |
| `GET` | `/api/v1/jobs/{job_id}` | Poll status & get download URL |
| `DELETE` | `/api/v1/jobs/{job_id}` | Cancel job & delete files |
| `GET` | `/api/v1/health` | Liveness check |
| `GET` | `/downloads/{filename}` | Download enhanced video |

### POST /enhance — form fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | file | required | Source video |
| `scale` | int | `4` | Upscale factor (2 or 4) |
| `output_crf` | int | `18` | H.265 CRF quality (0–51) |
| `output_codec` | str | `libx265` | FFmpeg codec |

### GET /jobs/{id} — response

```json
{
  "job_id": "...",
  "status": "enhancing_frames",
  "progress_pct": 42.0,
  "total_frames": 1800,
  "processed_frames": 756,
  "error": null,
  "download_url": null
}
```

---

## Deploying via GitHub

### 1 — Push to GitHub

```bash
git init
git remote add origin https://github.com/YOUR_USERNAME/video-enhancer.git
git add .
git commit -m "feat: initial commit"
git push -u origin main
```

> `weights/*.pth` and `storage/` are in `.gitignore` — large files are never committed.

### 2 — CI runs automatically

Every push to `main` or `develop` triggers `.github/workflows/ci.yml`:

- ✅ Ruff lint + Mypy type check
- ✅ Pytest suite (CPU, mock GPU)
- ✅ Docker build smoke test

### 3 — Publish a Docker image to GitHub Container Registry

```bash
# Create a release tag — triggers cd.yml automatically
git tag v1.0.0 && git push --tags
```

The CD workflow pushes to `ghcr.io/YOUR_USERNAME/video-enhancer:1.0.0`.  No extra secrets needed — `GITHUB_TOKEN` is automatically available.

### 4 — Pull and run on your GPU server

```bash
docker pull ghcr.io/YOUR_USERNAME/video-enhancer:latest

docker run -d \
  --gpus all \
  -p 8000:8000 \
  -v $(pwd)/storage:/app/storage \
  -v $(pwd)/weights:/app/weights \
  -e DOWNLOAD_BASE_URL=https://yourdomain.com/downloads \
  ghcr.io/YOUR_USERNAME/video-enhancer:latest
```

---

## Performance tips

| Setting | Recommendation |
|---------|----------------|
| `FRAME_BATCH_SIZE` | 4–8 for 8 GB VRAM, 16+ for 24 GB |
| `TILE_SIZE` | 512 standard; 256 for < 8 GB VRAM |
| `OUTPUT_PRESET` | `fast` for speed, `slow` for size/quality |
| `MAX_CONCURRENT_JOBS` | 1 per GPU; 2+ only with multiple GPUs |

---

## Production considerations

- Replace in-memory `JobManager` with **Redis + Celery** for multi-process/multi-node deployments.
- Add **S3 / object storage** for uploads and outputs instead of local disk.
- Implement **authentication** (OAuth2 / API keys) on the `/enhance` endpoint.
- Set up **Prometheus metrics** via `prometheus-fastapi-instrumentator`.
