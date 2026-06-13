# de-drum 🥁

**Separate drums from any song — 100% local, zero cost.**

de-drum downloads audio from YouTube with `yt-dlp` and separates the drum track using **Demucs** with GPU acceleration on Apple Silicon (MPS).

> Everything runs on your Mac — no external APIs, no subscriptions, no cloud costs.

---

## Requirements

- **macOS** with **Apple Silicon** (M1/M2/M3/M4)
- **Python 3.10+**
- **Node.js 20+**
- **ffmpeg** (via Homebrew: `brew install ffmpeg`)
- **yt-dlp** (via Homebrew: `brew install yt-dlp`)
- ~8 GB of free RAM for long songs

---

## Installation

**One command is all you need:**

```bash
npm install
```

That's it. `npm install` will:

1. ✅ Create a Python virtual environment (`.venv/`)
2. ✅ Install PyTorch with MPS support
3. ✅ Install Demucs and all Python dependencies

### Verify everything works

```bash
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

---

## Usage

### From a YouTube link

```bash
npm run separate -- "https://youtube.com/watch?v=..."
```

This will:

1. Download the audio with `yt-dlp`
2. Separate drums from the rest using Demucs on the GPU
3. Save the results to `output/<song-title>/`

### From a local audio file

```bash
npm run separate -- path/to/audio.mp3
```

### Output

```
output/
└── <song-name>/
    ├── drums.wav       🥁 Drums only
    ├── no_drums.wav    🎵 Everything else
    └── original.mp3    📥 Original audio
```

### Options

| Option            | Description                                                                     |
| ----------------- | ------------------------------------------------------------------------------- |
| `--model`         | Demucs model: `htdemucs` (default), `htdemucs_ft`, `htdemucs_6s`, `hdemucs_mmi` |
| `--output`        | Output directory (default: `output/`)                                           |
| `--keep-original` | Keep the original downloaded file                                               |
| `--check`         | Verify the environment only                                                     |

Examples:

```bash
# Use a more accurate model
npm run separate -- "https://..." --model htdemucs_ft

# Save to a custom directory
npm run separate -- "https://..." --output ~/Desktop

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
        ▼ [Demucs with MPS (GPU)]
    ┌──────────────┐
    │  drums.wav   │
    │ no_drums.wav │
    └──────────────┘
```

[**Demucs**](https://github.com/facebookresearch/demucs) is a state-of-the-art deep learning model by Meta for music source separation. On Apple Silicon, it runs on the GPU via **MPS** (Metal Performance Shaders), reaching speeds comparable to an NVIDIA T4.

---

## Project structure

```
de-drum/
├── package.json        # npm scripts (install, check, separate)
├── .venv/              # Python virtual environment (auto-created)
├── src/
│   └── separate.py     # Separation script
├── output/             # Results go here
├── .gitignore
├── requirements.txt
├── README.md
├── AGENTS.md
└── PLAN.md
```

---

## Links

- [Demucs (Meta)](https://github.com/facebookresearch/demucs)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [PyTorch MPS](https://pytorch.org/docs/stable/notes/mps.html)
