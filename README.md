# de-drum 🥁

**Separate drums from any song — 100% local, zero cost.**

de-drum downloads audio from YouTube with `yt-dlp` and separates the drum track using **Demucs** with GPU acceleration.

> Everything runs on your machine — no external APIs, no subscriptions, no cloud costs.

---

## Requirements

|             | Minimum                        |
| ----------- | ------------------------------ |
| **Python**  | 3.10+                          |
| **Node.js** | 20+                            |
| **ffmpeg**  | Required for audio conversion  |
| **yt-dlp**  | Required for YouTube downloads |
| **RAM**     | ~8 GB free for long songs      |

---

## Installation

### macOS (Apple Silicon) — recommended 🍎

```bash
# 1. Install system dependencies (if you don't have them)
brew install ffmpeg yt-dlp

# 2. Install de-drum
npm install

# 3. Verify GPU acceleration
npm run check
```

You should see:

```
PyTorch 2.12.0
✓ MPS (Metal GPU) is available
✓ PyTorch built with MPS support
✓ ffmpeg found
✓ yt-dlp found
```

### Linux 🐧

```bash
# 1. Install system dependencies
# Debian/Ubuntu:
sudo apt install ffmpeg yt-dlp python3 python3-venv

# Fedora:
sudo dnf install ffmpeg yt-dlp python3

# Arch:
sudo pacman -S ffmpeg yt-dlp python

# 2. Install de-drum
npm install

# 3. Verify the setup
npm run check
```

> **GPU acceleration**: Demucs will use CUDA if an NVIDIA GPU with PyTorch CUDA is available, otherwise it falls back to CPU.

### Windows 🪟

```powershell
# 1. Install system dependencies (using winget)
winget install ffmpeg
winget install yt-dlp
winget install Python.Python.3.14

# Or using Chocolatey:
# choco install ffmpeg yt-dlp python

# 2. Install de-drum
npm install

# 3. Verify the setup
npm run check
```

> **GPU acceleration**: On Windows, Demucs will use CUDA if available, otherwise CPU. No MPS support (Apple only).

---

## Docker 🐳

> **Note**: Inside Docker, Apple Silicon MPS acceleration is **not available**.
> For GPU acceleration on Linux, install the
> [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
> and uncomment the GPU section in `docker-compose.yml`.

```bash
# Build the image (first time only, takes ~10 min)
npm run docker:build

# Start the UI at http://localhost:7860
npm run docker:ui

# View logs
npm run docker:logs

# Run separation from the command line
npm run docker:separate -- "https://youtube.com/watch?v=..."

# Stop the container
npm run docker:stop
```

The model cache (~2 GB) is persisted in a Docker volume, so subsequent runs
are faster.

---

## API Gateway + Backend (new architecture)

Starting from Phase 6, de-drum has a **three-tier architecture** for production
deployments:

```
[Frontend · Svelte/React/Vanilla]
        ↕ HTTP (port 3000)
[API Gateway · Fastify (Node.js)]    ←  proxy / orchestrator
        ↕ HTTP (port 8000, internal)
[Backend · FastAPI (Python)]         ←  runs Demucs + analysis
```

### Docker compose (new stack)

```bash
# Build images (first time only, ~10 min)
npm run docker:build

# Start gateway + backend
npm run docker:up

# View logs
npm run docker:logs

# Stop the stack
npm run docker:down
```

The Gateway is exposed on **http://localhost:3000**.

### API Endpoints

| Method | Endpoint                                           | Description                        |
| ------ | -------------------------------------------------- | ---------------------------------- |
| `POST` | `/api/separate/url`                                | Submit YouTube URL for separation  |
| `POST` | `/api/separate/file`                               | Upload audio file for separation   |
| `GET`  | `/api/jobs/:id`                                    | Poll job status                    |
| `GET`  | `/api/jobs/:id/download/:filename`                 | Download result file               |

All endpoints return JSON. File uploads use **multipart/form-data** with fields
`file` (the audio) and `model` (optional, default `htdemucs`).

This lets you build any frontend (React, Svelte, vanilla JS, mobile app)
that talks to the Gateway — the backend is completely decoupled.

### Architecture diagram

```
You send a request ──▶  Gateway (port 3000)
                          │
                          ▼ (proxy)
                      Backend (port 8000, internal)
                          │
                    ┌─────┴─────┐
                    ▼           ▼
                 yt-dlp      Demucs
               (download)  (separation)
                    │           │
                    └─────┬─────┘
                          ▼
                     output/  ◀── results
```

### Local development (Node.js gateway)

```bash
# Install gateway deps
npm run gateway:install

# Run in dev mode (with auto-reload)
npm run gateway:dev
```

---

## Usage

### Web UI (no terminal needed) 🌐

```bash
npm run ui
```

Opens a browser interface at [http://127.0.0.1:7860](http://127.0.0.1:7860):

- Paste a YouTube URL or upload a local audio file
- Choose the Demucs model
- Download the separated MP3 files directly

### From a YouTube link

```bash
npm run separate -- "https://youtube.com/watch?v=..."
```

### From a local audio file

```bash
npm run separate -- path/to/audio.mp3
```

### Output

```
output/
└── <song-name>/
    ├── <song-name>_drums.mp3       🥁 Drums only
    └── <song-name>_no_drums.mp3    🎵 Everything else
```

### Options

| Option            | Description                                                                     |
| ----------------- | ------------------------------------------------------------------------------- |
| `--model`         | Demucs model: `htdemucs` (default), `htdemucs_ft`, `htdemucs_6s`, `hdemucs_mmi` |
| `--output`        | Output directory (default: `output/`)                                           |
| `--keep-original` | Keep the original YouTube audio file                                            |
| `--check`         | Verify the environment only                                                     |

Examples:

```bash
# Use a more accurate model
npm run separate -- "https://..." --model htdemucs_ft

# Save to a custom directory
npm run separate -- "https://..." --output ~/Desktop

# Keep the downloaded mp3
npm run separate -- "https://..." --keep-original

# Check environment
npm run check
```

---

## How it works

### CLI / local mode

```
YouTube URL / audio file
        │
        ▼ [yt-dlp]
      MP3
        │
        ▼ [Demucs — GPU accelerated]
    ┌──────────────┐
    │  _drums.mp3  │
    │ _no_drums.mp3│
    └──────────────┘
```

### Production mode (API Gateway)

```
[Frontend]  ──▶  [Gateway · Fastify]  ──▶  [Backend · FastAPI]
      POST /api/separate           POST /backend/separate
      GET  /api/jobs/:id            GET  /backend/jobs/:id
           │                              │
           └────── async job polling ─────┘
```

The Gateway handles routing, CORS, rate limiting, and file proxying.
The Backend runs the actual Demucs separation in background threads,
with per-job status tracking.

[**Demucs**](https://github.com/facebookresearch/demucs) is a state-of-the-art deep learning model by Meta for music source separation. On Apple Silicon it runs on the GPU via **MPS**; on NVIDIA GPUs via **CUDA**.

---

## Project structure

```
de-drum/
├── package.json              # npm scripts
├── scripts/
│   ├── setup.mjs             # Cross-platform postinstall
│   └── run.mjs               # Cross-platform Python runner
├── src/
│   ├── separate.py           # Core separation (CLI)
│   ├── analyze.py            # BPM, key, spectral map
│   ├── section_describer.py  # LLM section descriptions
│   └── ui.py                 # Gradio UI (legacy)
├── services/
│   ├── gateway/              # API Gateway (Node.js / Fastify)
│   │   ├── package.json
│   │   ├── src/
│   │   │   └── server.js
│   │   └── Dockerfile
│   └── backend/              # Backend service (Python / FastAPI)
│       └── main.py
├── .venv/                    # Python venv (auto-created)
├── output/                   # Results (gitignored)
├── input/                    # Uploaded files (gitignored)
├── tests/                    # CLI tests
├── .editorconfig
├── .prettierrc
├── pyproject.toml             # Ruff + pytest config
├── requirements.txt
├── .gitignore
├── .nvmrc
├── docker-compose.yml         # Backend + Gateway + UI services
├── Dockerfile                 # Python image (shared)
└── README.md
```

---

## Links

- [Demucs (Meta)](https://github.com/facebookresearch/demucs)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [PyTorch MPS](https://pytorch.org/docs/stable/notes/mps.html)
