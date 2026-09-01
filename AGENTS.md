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
├── scripts/
│   ├── run.mjs               # npm runner (runs Python inside .venv)
│   └── setup.mjs             # venv + dependency setup (npm install)
├── .venv/                    # Virtual environment (not in git)
├── src/                      # Core Python code
│   └── separate.py           # Download + separation + CLI
├── tests/                    # pytest tests
├── output/                   # Results (not in git)
└── input/                    # Input files (not in git)
```

## Code conventions

### Python (`src/`)

- **Shebang**: `#!/usr/bin/env python3`
- **Typing**: Use type hints on all functions
- **Docstrings**: Google-style
- **Errors**: Use `log` with `logging` or `rich` instead of `print`
- **Line length**: 88 characters (Ruff-compatible)
- **File handling**: Prefer `pathlib`
- **CLI**: Never call `sys.exit()` outside CLI entry points

### Bash / Scripts

- Use `set -euo pipefail` in bash scripts (if any)

## Dependencies

### Python (requirements.txt)

```
torch>=2.4.0
demucs>=4.0.0
torchcodec>=0.14.0
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

1. **Input**: YouTube URL or local audio file
2. **Process**:
   - `yt-dlp` → temporary `.mp3` (for URLs)
   - `demucs --two-stems drums` → `drums.wav` + `no_drums.wav` (MPS if available)
   - `ffmpeg` → WAV converted to MP3 with `<song>_<stem>.mp3` naming
3. **Output**: `output/<song>/`

## ⚠️ Critical rules

- **No auto-commits** — Never commit changes on my behalf. I decide when and what to commit.
- **No auto-push** — Never push to remote. I handle pushes manually.
- **No download tests** — Never run separation against real URLs. I test it myself.

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
npm run dedrum -- "https://youtube.com/watch?v=..."
npm run dedrum -- path/to/song.mp3

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
```

## Tooling

- **EditorConfig** (`.editorconfig`) — universal indentation/encoding settings
- **Prettier** (`.prettierrc`) — formats JSON, Markdown, YAML; run via `npx prettier --write .`
- **Ruff** (`pyproject.toml`) — Python linter + formatter (replaces flake8 + isort + black)
- **pytest** (`pyproject.toml`) — test runner; tests live in `tests/`
