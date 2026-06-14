# AGENTS.md — Instructions for AI agents

## Project: de-drum 🥁

Local drum track separation from audio using Demucs + yt-dlp.

---

## Tech stack

- **Python 3.14+** — core logic (Demucs, yt-dlp wrapper)
- **Node.js 24** — npm scripts and possible auxiliary tools
- **Demucs (Meta)** — instrument separation model (htdemucs)
- **PyTorch** with **MPS** — GPU execution on Apple Silicon
- **yt-dlp** — audio download from YouTube
- **ffmpeg** — audio conversion

## Project structure

```
de-drum/
├── README.md                 # Main documentation
├── AGENTS.md                 # This file
├── PLAN.md                   # Roadmap and tasks
├── .gitignore
├── requirements.txt          # Python dependencies
├── package.json              # npm scripts
├── .venv/                    # Virtual environment (not in git)
├── src/                      # Core Python code (shared)
│   ├── separate.py           # Separation + CLI
│   ├── analyze.py            # BPM, key, spectral map
│   ├── section_describer.py  # LLM section descriptions
│   └── ui.py                 # Gradio UI (legacy)
├── services/
│   ├── gateway/              # API Gateway (Node.js / Fastify)
│   │   ├── package.json
│   │   ├── src/server.js
│   │   └── Dockerfile
│   └── backend/              # Backend service (Python / FastAPI)
│       └── main.py
├── output/                   # Results (not in git)
└── input/                    # Uploaded files (not in git)
```

## Code conventions

### Python (`src/` and `services/backend/`)

- **Shebang**: `#!/usr/bin/env python3`
- **Typing**: Use type hints on all functions
- **Docstrings**: Google-style
- **Errors**: Use `log` with `logging` or `rich` instead of `print`
- **Line length**: 88 characters (Ruff-compatible)
- **File handling**: Prefer `pathlib`
- **Backend service** (`services/backend/main.py`): FastAPI app wrapping `src/`
  - Never call `sys.exit()` inside the service — raise exceptions
  - Background threads for async jobs
  - Job status tracked in-memory (`_jobs` dict)

### Node.js (`services/gateway/`)

- **ESM** (`"type": "module"`)
- **Fastify v5** with plugins: `@fastify/cors`, `@fastify/multipart`, `@fastify/rate-limit`
- **Endpoints**:
  - `POST /api/describe` — LLM section description (local, no backend)
  - `POST /api/separate/url` — forward to backend
  - `POST /api/separate/file` — multipart → backend
  - `GET /api/jobs/:id` — status proxy
  - `GET /api/jobs/:id/download/:filename` — stream file from backend
- **Section describer** (`src/describer.js`): port of Python `section_describer.py`
  - Calls DeepSeek via OpenRouter directly from the gateway
  - Avoids round-trip to the Python backend for LLM enrichment
  - Same signature: `describeSections(analysis)` → description string or null
- **Error handling**: Return 502 if backend is unavailable

### Bash / Scripts

- Use `set -euo pipefail` in bash scripts (if any)

## Dependencies

### Python (requirements.txt)

```
torch>=2.4.0
demucs>=4.0.0
torchcodec>=0.14.0
ffmpeg-python>=0.2.0
rich>=13.0.0
ruff>=0.11.0    # linter + formatter
pytest>=8.0.0   # tests
```

### Node (devDependencies)

```
prettier  # formatting for JSON, Markdown, YAML
```

### System (already installed)

- `yt-dlp` (managed via Homebrew)
- `ffmpeg` (managed via Homebrew)

## Data flow

### CLI mode

1. **Input**: YouTube URL or local audio file
2. **Process**:
   - `yt-dlp` → temporary `.mp3`
   - `demucs` → `drums.wav` + `no_drums.wav`
3. **Output**: `output/<song>/`

### API Gateway mode

1. **Frontend** sends request to **Gateway** (`POST /api/separate/url` or `/file`)
2. **Gateway** forwards to **Backend** (`POST /backend/separate/url` or `/file`)
3. **Backend** creates a job, returns `job_id`, starts background processing
4. **Frontend** polls `GET /api/jobs/:id` for status (`pending → processing → done`)
5. When done, **Frontend** downloads via `GET /api/jobs/:id/download/:filename`

## ⚠️ Critical rules

- **No auto-commits** — Never commit changes on my behalf. I decide when and what to commit.
- **No auto-push** — Never push to remote. I handle pushes manually.
- **No download tests** — Never run `npm run separate` or `yt-dlp` tests against real URLs. I test through the Gradio UI myself.

## Notes for agents

- **Do not commit** large or binary files to the repository
- MPS GPU is the main acceleration path; always verify availability
- Demucs loads ~2 GB model into RAM; ensure enough memory is free
- The `output/` directory must be gitignored
- If adding Python dependencies, update `requirements.txt`

## Useful commands

```bash
# Install everything (creates venv + installs Python deps)
npm install

# Run separation
npm run separate -- "https://youtube.com/watch?v=..."

# Check GPU
npm run check

# Lint Python code
npm run lint

# Format all files (Python via Ruff, others via Prettier)
npm run format

# Run tests
npm run test

# For development (activate venv manually)
source .venv/bin/activate
pip install -r requirements.txt
python3 src/separate.py --check

# Docker: start gateway + backend
npm run docker:up

# Docker: start just backend (FastAPI)
npm run docker:backend

# Docker: start just gateway (Fastify, needs backend running)
npm run docker:gateway

# Docker: legacy Gradio UI
npm run docker:ui

# Gateway local dev (Node.js, needs backend running)
npm run gateway:install
npm run gateway:dev
```

## Tooling

- **EditorConfig** (`.editorconfig`) — universal indentation/encoding settings
- **Prettier** (`.prettierrc`) — formats JSON, Markdown, YAML; run via `npx prettier --write .`
- **Ruff** (`pyproject.toml`) — Python linter + formatter (replaces flake8 + isort + black)
- **pytest** (`pyproject.toml`) — test runner; tests live in `tests/`
