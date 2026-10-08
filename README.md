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

### Quick install (recommended)

```bash
# 1. Install system dependencies (if you don't have them)
brew install ffmpeg yt-dlp

# 2. Install de-drum (creates .venv/, installs Python deps)
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

### Interactive installer

For a guided setup that checks versions and prompts before installing:

```bash
npm run install:interactive
```

Or run directly:

```bash
python3 scripts/install.py
```

Options:

- `--yes` / `-y` — assume yes to all prompts
- `--skip-system` — skip system dependency installation
- `--skip-venv` — skip venv creation (use existing)

---

## Usage

### From a YouTube URL (video workflow)

Downloads the video, removes the drums from the audio, and muxes the result into a de-drummed MP4:

```bash
npm run dedrum -- "https://youtube.com/watch?v=..."
```

Extra query parameters in the URL (e.g. `list`, `radio`, `si`, `t`) are stripped
automatically — only the `v` (watch id) parameter is kept, so playlist or radio
links can't alter the download.

### Extracting individual stems (drums + bass)

To only extract specific stems (no de-drummed video muxing):

```bash
npm run dedrum -- "https://youtube.com/watch?v=..." --stems drums,bass
npm run dedrum -- path/to/song.mp3 --stems drums,bass
```

Comma-separated stem names from the full `htdemucs` separation: `drums`,
`bass`, `other`, `vocals`. Everything not requested is discarded.

### Comparing engines: Demucs vs Open-Unmix

Two separation engines are available. Demucs is the default. Open-Unmix
supports the `umxhq` and `umxl` models and can also be selected for YouTube
URLs or local files:

```bash
# Demucs (default)
npm run dedrum -- path/to/song.mp3 --stems drums,bass

# Open-Unmix with its default model (umxhq)
npm run dedrum -- path/to/song.mp3 --stems drums,bass --engine openunmix

# Open-Unmix with the larger umxl model
npm run dedrum -- "https://youtube.com/watch?v=..." --stems drums,bass --engine openunmix --model umxl
```

Open-Unmix uses `niter=0` for faster processing without iterative
refinement. Check the upstream model and weight licenses before using either
engine in a commercial service.

### From a local audio file

Separates the stems without muxing (no video involved):

```bash
npm run dedrum -- path/to/song.mp3
```

### Options

```bash
npm run dedrum -- --help
```

| Flag                 | Description                                                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `--model <name>`     | Model for the selected engine: Demucs `htdemucs` (default), `htdemucs_ft`, `htdemucs_6s`, `hdemucs_mmi`; Open-Unmix `umxhq` or `umxl` |
| `--engine <name>`    | Stem-separation engine: `demucs` (default) or `openunmix`; use with `--stems`                                                         |
| `--stems <list>`     | Extract individual stems (e.g. `drums,bass`) instead of de-drumming; skips video muxing                                               |
| `--drums-format <f>` | Output format for extracted stems: `mp3` (default) or `wav`                                                                           |
| `--output <dir>`     | Output directory (default: `output/`)                                                                                                 |
| `--check`            | Verify the environment and exit                                                                                                       |
| `-v, --verbose`      | Show debug logs                                                                                                                       |

### Output

For YouTube URLs, the de-drummed video and the isolated drums are saved to `output/`:

```
output/
├── Bohemian Rhapsody_no_drums.mp4
└── Bohemian Rhapsody_drums.mp3
```

For stem extraction (`--stems`), the requested stems are saved to
`output/<title>/`:

```
output/
└── Bohemian Rhapsody/
    ├── Bohemian Rhapsody_drums.mp3
    └── Bohemian Rhapsody_bass.mp3
```

The isolated drums are saved as MP3 by default. Use `--drums-format wav` to keep Demucs' WAV output as-is (no re-encoding):

For local audio files, the stems are saved to `output/<song>/`:

```
output/
└── Bohemian Rhapsody/
    ├── Bohemian Rhapsody_drums.mp3
    └── Bohemian Rhapsody_no_drums.mp3
```

---

## How it works

1. **Input**: a YouTube URL (video workflow) or a local audio file. Unwanted query parameters are stripped from the URL, keeping only the watch id (`v`)
2. **Download** (URL only): `yt-dlp` fetches the video and audio as a single merged file (MP4), and `ffmpeg` extracts the audio (MP3) into a temporary directory
3. **Separation**: Demucs (`htdemucs`) splits the audio into `drums` and `no_drums` stems, using the Metal GPU (MPS) when available
4. **Muxing**: `ffmpeg` copies the original video stream and combines it with the `no_drums` audio (AAC) into `<title>_no_drums.mp4`
5. **Drums**: the isolated `drums` stem is kept as `output/<title>_drums.mp3` (or `<title>_drums.wav` with `--drums-format wav`)
6. **Output**: `output/<title>_no_drums.mp4` — temporary files are cleaned up automatically

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
