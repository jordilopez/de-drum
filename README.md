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

## Usage

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

[**Demucs**](https://github.com/facebookresearch/demucs) is a state-of-the-art deep learning model by Meta for music source separation. On Apple Silicon it runs on the GPU via **MPS**; on NVIDIA GPUs via **CUDA**.

---

## Project structure

```
de-drum/
├── package.json        # npm scripts
├── scripts/
│   ├── setup.mjs       # Cross-platform postinstall
│   └── run.mjs         # Cross-platform Python runner
├── src/
│   └── separate.py     # Main separation script
├── .venv/              # Python virtual environment (auto-created)
├── output/             # Results go here (gitignored)
├── tests/              # CLI tests
├── .editorconfig
├── .prettierrc
├── pyproject.toml       # Ruff + pytest config
├── requirements.txt
├── .gitignore
├── .nvmrc
└── README.md
```

---

## Links

- [Demucs (Meta)](https://github.com/facebookresearch/demucs)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [PyTorch MPS](https://pytorch.org/docs/stable/notes/mps.html)
