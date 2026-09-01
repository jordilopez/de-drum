# de-drum 🥁

**Separate drums from any song — 100% local, zero cost.**

de-drum downloads a video from YouTube with `yt-dlp`, separates the drum track from the audio using **Demucs** with GPU acceleration (MPS on Apple Silicon), and muxes everything back into a de-drummed MP4.

> Everything runs on your machine — no external APIs, no subscriptions, no cloud costs.

---

## Requirements

|             | Minimum                        |
| ----------- | ------------------------------ |
| **Python**  | 3.14+                          |
| **Node.js** | 24+                            |
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
PyTorch 2.x.x
✓ MPS (Metal GPU) is available
✓ PyTorch built with MPS support
✓ ffmpeg found
✓ yt-dlp found
```

`npm install` automatically creates a Python virtual environment (`.venv/`) and installs all dependencies — no manual `pip` steps needed.

---

## Usage

### From a YouTube URL (video workflow)

Downloads the video, removes the drums from the audio, and muxes the result into a de-drummed MP4:

```bash
npm run dedrum -- "https://youtube.com/watch?v=..."
```

### From a local audio file

Separates the stems without muxing (no video involved):

```bash
npm run dedrum -- path/to/song.mp3
```

### Options

```bash
npm run dedrum -- --help
```

| Flag             | Description                                            |
| ---------------- | ------------------------------------------------------ |
| `--model <name>` | Demucs model: `htdemucs` (default), `htdemucs_ft`, ... |
| `--output <dir>` | Output directory (default: `output/`)                  |
| `--check`        | Verify the environment and exit                        |
| `-v, --verbose`  | Show debug logs                                        |

### Output

For YouTube URLs, the final de-drummed video is saved as `output/<title>_no_drums.mp4`:

```
output/
└── Bohemian Rhapsody_no_drums.mp4
```

For local audio files, the stems are saved to `output/<song>/`:

```
output/
└── Bohemian Rhapsody/
    ├── Bohemian Rhapsody_drums.mp3
    └── Bohemian Rhapsody_no_drums.mp3
```

---

## How it works

1. **Input**: a YouTube URL (video workflow) or a local audio file
2. **Download** (URL only): `yt-dlp` fetches the video-only stream (MP4) and the audio (MP3) into temporary directories
3. **Separation**: Demucs (`htdemucs`) splits the audio into `drums` and `no_drums` stems, using the Metal GPU (MPS) when available
4. **Muxing**: `ffmpeg` copies the original video stream and combines it with the `no_drums` audio (AAC) into `<title>_no_drums.mp4`
5. **Output**: `output/<title>_no_drums.mp4` — temporary files are cleaned up automatically

---

## Development

```bash
npm run check   # verify PyTorch / MPS / ffmpeg / yt-dlp
npm run test    # run pytest
npm run lint    # ruff check
npm run format  # ruff format + prettier
```

### Project structure

```
de-drum/
├── README.md          # This file
├── AGENTS.md          # Instructions for AI agents
├── PLAN.md            # Roadmap
├── requirements.txt   # Python dependencies
├── package.json       # npm scripts
├── scripts/
│   ├── run.mjs        # npm runner (runs Python inside .venv)
│   └── setup.mjs      # venv + dependency setup
├── src/
│   └── separate.py    # Download + separation + CLI
├── tests/             # pytest tests
├── output/            # Results (gitignored)
└── input/             # Input files (gitignored)
```

---

## Notes

- The first run downloads the ~2 GB `htdemucs` model into memory — make sure enough RAM is free.
- MPS (Metal GPU) is the main acceleration path on Apple Silicon; on machines without MPS, Demucs falls back to CPU (slower).
- `output/` and `input/` are gitignored.
