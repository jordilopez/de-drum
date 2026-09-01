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

### 2018 MacBook Pro and other Intel Macs

This project should also run on a 2018 Intel MacBook Pro, provided that the
required Python, Node.js, `ffmpeg`, and `yt-dlp` versions can be installed on
the Mac's version of macOS. However, Intel Macs cannot use PyTorch's MPS
(Metal) acceleration. Demucs will therefore fall back to the CPU, which can be
considerably slower than running on Apple Silicon.

For a more reliable experience, use a model with **16 GB of RAM or more**, keep
it connected to power, and close other memory-intensive applications. An 8 GB
Mac may work for shorter files but can become slow or run out of memory when
processing longer songs. Run `npm run check` after installation to confirm
that the environment is ready; an Intel Mac is expected to report that MPS is
unavailable and that CPU processing will be used.

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

## Experimental status

This project is an experiment in running local drum separation with Demucs. It
is provided as-is, without guarantees about separation quality, performance,
compatibility, or uninterrupted operation. It is not affiliated with Demucs,
YouTube, or any other service used by the project.

## Legal and responsible use

This project uses [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) to retrieve media
from third-party platforms. It is intended for content that you own or are
authorized to download and process. Before downloading anything, make sure
your use complies with applicable copyright law, the rights holder's
permissions, and the terms of service of the source platform. Do not use this
project to infringe copyright or bypass access controls.

The upstream software licenses cover the software, not the media it retrieves
or the outputs it creates: [`yt-dlp` is released under the Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE),
while [Demucs is released under the MIT license](https://github.com/facebookresearch/demucs/blob/main/LICENSE).
Neither license grants permission to download or redistribute copyrighted
media.

This project does not grant permission to download any content, and this
notice cannot make an otherwise unlawful download lawful. You are solely
responsible for how you use the software and for any content you download or
create with it. This is a general project notice, not legal advice.

## Notes

- The first run downloads the ~2 GB `htdemucs` model into memory — make sure enough RAM is free.
- MPS (Metal GPU) is the main acceleration path on Apple Silicon; on machines without MPS, Demucs falls back to CPU (slower).
- `output/` and `input/` are gitignored.
