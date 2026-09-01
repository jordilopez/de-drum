#!/usr/bin/env python3
"""Separate drums from a video: download, demucs, and mux the de-drummed video.

The main workflow takes a YouTube URL, downloads the video and audio streams,
separates the drum track from the audio with Demucs (MPS accelerated when
available), and muxes the original video with the ``no_drums`` audio back into
a single MP4.
"""

import argparse
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import torch
from rich.console import Console
from rich.logging import RichHandler

# Suppress noisy TorchCodec warnings about encoding/bits_per_sample
warnings.filterwarnings("ignore", message=".*not fully supported by TorchCodec.*")
warnings.filterwarnings("ignore", message=".*not directly supported by TorchCodec.*")

log = logging.getLogger("de-drum")
console = Console()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_environment() -> bool:
    """Verify that PyTorch and required system tools are available.

    MPS availability is informational only — Demucs transparently falls back
    to CPU when the Metal GPU is not available (slower, but functional).

    Returns:
        True when the environment is ready.

    Raises:
        RuntimeError: If a required tool (ffmpeg, yt-dlp) is missing.
    """
    console.print(f"[bold]PyTorch[/bold] {torch.__version__}")

    if torch.backends.mps.is_available():
        console.print("[green]✓[/green] MPS (Metal GPU) is available")
    else:
        console.print(
            "[yellow]⚠[/yellow] MPS not available — using CPU (slower but functional)"
        )

    if torch.backends.mps.is_built():
        console.print("[green]✓[/green] PyTorch built with MPS support")
    else:
        console.print(
            "[yellow]⚠[/yellow] PyTorch not built with MPS support — CPU will be used"
        )

    required_tools = (
        ("ffmpeg", "-version", "muxing and audio conversion"),
        ("yt-dlp", "--version", "YouTube downloads"),
    )
    for tool, version_flag, purpose in required_tools:
        try:
            subprocess.run([tool, version_flag], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(
                f"{tool} not found — required for {purpose}. "
                f"Install it with `brew install {tool}`."
            ) from exc
        console.print(f"[green]✓[/green] {tool} found")

    return True


# ---------------------------------------------------------------------------
# yt-dlp downloads
# ---------------------------------------------------------------------------


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters that are problematic in filenames."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip(". ")


def _run_yt_dlp(cmd: list[str], url: str) -> Path:
    """Run a yt-dlp command and return the downloaded file path.

    Args:
        cmd: Full yt-dlp command (must include ``--print after_move:filepath``).
        url: Source URL, used for error messages only.

    Returns:
        Path to the downloaded file.

    Raises:
        RuntimeError: If yt-dlp fails or the output path cannot be determined.
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "yt-dlp failed: executable `yt-dlp` not found — "
            "is it installed and on PATH? (brew install yt-dlp)"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"yt-dlp failed with exit code {exc.returncode} for {url}"
            + (f":\n{exc.stderr}" if exc.stderr else "")
        ) from exc

    # yt-dlp --print filename outputs the final file path
    downloaded = result.stdout.strip().splitlines()[-1] if result.stdout else None

    if not downloaded or not Path(downloaded).exists():
        raise RuntimeError(f"Could not determine downloaded file path for {url}")

    return Path(downloaded)


def _run_command(cmd: list[str], label: str) -> None:
    """Run a subprocess, normalizing all failures into RuntimeError.

    Args:
        cmd: Command to run (captured output).
        label: Human-readable step name for error messages.

    Raises:
        RuntimeError: If the executable is missing or exits non-zero.
    """
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"{label}: executable `{cmd[0]}` not found — is it installed and on PATH?"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"{label} failed with exit code {exc.returncode}"
            + (f":\n{exc.stderr}" if exc.stderr else "")
        ) from exc


def download_video(url: str, output_dir: str) -> Path:
    """Download the video-only stream from a YouTube URL using yt-dlp.

    Prefers a video-only MP4 (best quality available); the audio track is
    discarded since the de-drummed audio is muxed back in later.

    Args:
        url: YouTube URL.
        output_dir: Directory where the video file will be saved.

    Returns:
        Path to the downloaded video file.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # yt-dlp template: save as <output_dir>/<title>.<ext>
    template = str(out_dir / "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bestvideo[ext=mp4]/bestvideo*",
        "--output",
        template,
        "--print",
        "after_move:filepath",
        url,
    ]

    console.print(f"Downloading video from [cyan]{url}[/cyan]...")
    video_path = _run_yt_dlp(cmd, url)
    console.print(f"[green]✓[/green] Downloaded [bold]{video_path.name}[/bold]")
    return video_path


def download_audio(url: str, output_dir: str) -> Path:
    """Download audio from a YouTube URL using yt-dlp.

    Args:
        url: YouTube URL.
        output_dir: Directory where the audio file will be saved.

    Returns:
        Path to the downloaded audio file.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # yt-dlp template: save as <output_dir>/<title>.mp3
    template = str(out_dir / "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--output",
        template,
        "--no-playlist",
        "--print",
        "after_move:filepath",
        url,
    ]

    console.print(f"Downloading audio from [cyan]{url}[/cyan]...")
    audio_path = _run_yt_dlp(cmd, url)
    console.print(f"[green]✓[/green] Downloaded [bold]{audio_path.name}[/bold]")
    return audio_path


# ---------------------------------------------------------------------------
# Separation
# ---------------------------------------------------------------------------


def separate(
    source: str,
    output_dir: str,
    model: str = "htdemucs",
    convert_mp3: bool = True,
) -> Path:
    """Run Demucs separation on a local audio file.

    Demucs saves to ``<output_dir>/<model>/<stem>/`` by default. After
    separation we move the files up one level so the final structure is
    ``<output_dir>/<stem>/`` (cleaner for users).

    Args:
        source: Path to an audio file.
        output_dir: Directory to save the results.
        model: Demucs model name (default: htdemucs).
        convert_mp3: Convert the WAV stems to MP3 and delete the WAVs.
            When False, the WAVs are kept untouched (needed for muxing).

    Returns:
        Path to the ``no_drums`` stem: ``no_drums.wav`` when ``convert_mp3``
        is False, otherwise the converted ``<song>_no_drums.mp3``.

    Raises:
        RuntimeError: If the source file is missing or Demucs fails.
    """
    source_path = Path(source)

    if not source_path.exists():
        raise RuntimeError(f"File not found: {source}")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    console.print(
        f"Separating [bold]{source_path.name}[/bold] "
        f"using [cyan]{model}[/cyan] on [bright_blue]{device}[/bright_blue]..."
    )

    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems",
        "drums",
        "-o",
        str(Path(output_dir).resolve()),
        "--device",
        device,
        "-n",
        model,
        str(source_path.resolve()),
    ]

    with console.status("[bold green]Processing...") as _:
        _run_command(cmd, "Demucs")

    # Demucs saves to <output_dir>/<model>/<stem>/ — move files to <output_dir>/<stem>/
    demucs_out = Path(output_dir) / model / source_path.stem
    final_out = Path(output_dir) / source_path.stem

    if demucs_out.exists():
        if final_out.exists():
            shutil.rmtree(final_out)
        demucs_out.rename(final_out)

        # Remove empty model directory if no other tracks are left
        model_dir = Path(output_dir) / model
        if model_dir.exists() and not any(model_dir.iterdir()):
            model_dir.rmdir()
    else:
        # If the model subdirectory doesn't exist, Demucs may have saved directly
        final_out = demucs_out

    no_drums_wav = final_out / "no_drums.wav"

    if not convert_mp3:
        if not no_drums_wav.exists():
            raise RuntimeError(f"Separation produced no no_drums.wav in {final_out}")
        return no_drums_wav

    # Convert WAV outputs to MP3 with prefix naming
    if final_out.exists():
        wav_files = list(final_out.glob("*.wav"))
        for wav in wav_files:
            stem = wav.stem  # e.g. "drums" or "no_drums"
            mp3_name = f"{source_path.stem}_{stem}.mp3"
            mp3_path = final_out / mp3_name
            _run_command(
                [
                    "ffmpeg",
                    "-i",
                    str(wav),
                    "-codec:a",
                    "libmp3lame",
                    "-qscale:a",
                    "0",
                    "-y",
                    str(mp3_path),
                ],
                "ffmpeg MP3 conversion",
            )
            wav.unlink()  # remove the original WAV

    no_drums_mp3 = final_out / f"{source_path.stem}_no_drums.mp3"
    if not no_drums_mp3.exists():
        raise RuntimeError(f"Separation produced no output in {final_out}")

    # List output
    files = list(final_out.iterdir())
    console.print(
        f"[green]✓[/green] [bold]{len(files)}[/bold] file(s) in [bold]{final_out}[/bold]:"
    )
    for f in sorted(files):
        size = f.stat().st_size / 1024 / 1024
        console.print(f"  [bold]{f.name}[/bold] ({size:.1f} MB)")
    console.print()

    return no_drums_mp3


# ---------------------------------------------------------------------------
# Muxing
# ---------------------------------------------------------------------------


def mux_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Mux a video stream together with a replacement audio track using ffmpeg.

    The video stream is copied untouched; the audio is re-encoded to AAC.

    Args:
        video_path: Path to the source video (video stream is copied).
        audio_path: Path to the replacement audio (e.g. ``no_drums.wav``).
        output_path: Path of the resulting MP4 file.

    Raises:
        RuntimeError: If ffmpeg fails to mux the streams.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]

    console.print(
        f"Muxing [bold]{video_path.name}[/bold] with [bold]{audio_path.name}[/bold]..."
    )

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg muxing failed: executable `ffmpeg` not found — "
            "is it installed and on PATH?"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg muxing failed with exit code {exc.returncode}"
            + (f":\n{exc.stderr}" if exc.stderr else "")
        ) from exc

    # Artifact validation: ffmpeg must have produced a non-empty file
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg muxing produced no output at {output_path}")

    console.print(f"[green]✓[/green] Muxed [bold]{output_path.name}[/bold]")


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def run_dedrum_workflow(url: str, output_dir: str, model: str = "htdemucs") -> Path:
    """Run the full de-drum workflow for a YouTube URL.

    Steps: verify the environment, download the video and audio streams into
    temporary directories, separate the audio with Demucs, mux the original
    video with the ``no_drums`` audio, and clean up the temporary files.

    Args:
        url: YouTube URL.
        output_dir: Directory where the final MP4 will be saved.
        model: Demucs model name (default: htdemucs).

    Returns:
        Path to the final de-drummed video: ``<output_dir>/<title>_no_drums.mp4``.

    Raises:
        RuntimeError: If any step (download, separation, muxing) fails.
    """
    if not check_environment():
        raise RuntimeError(
            "Environment check failed — run `npm run check` for details."
        )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with (
        tempfile.TemporaryDirectory(prefix="dedrum_video_") as tmp_video,
        tempfile.TemporaryDirectory(prefix="dedrum_audio_") as tmp_audio,
        tempfile.TemporaryDirectory(prefix="dedrum_stems_") as tmp_stems,
    ):
        # 1. Download the video (video-only stream) and audio streams
        video_path = download_video(url, tmp_video)
        audio_path = download_audio(url, tmp_audio)

        # 2. Separate the drums from the audio (keep the WAV for muxing)
        no_drums_wav = separate(audio_path, tmp_stems, model, convert_mp3=False)

        # 3. Mux the original video with the de-drummed audio
        safe_title = _sanitize_filename(video_path.stem)
        output_path = out_dir / f"{safe_title}_no_drums.mp4"
        mux_video_audio(video_path, no_drums_wav, output_path)

        # Final artifact validation before cleanup
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"Workflow produced no output video at {output_path}")

    console.print()
    console.print(
        f"[bold green]🎵 Done![/bold green] De-drummed video at "
        f"[bold]{output_path.resolve()}[/bold]"
    )
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and run the appropriate command."""
    parser = argparse.ArgumentParser(
        description="Remove drums from a YouTube video (download + Demucs + mux).",
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="YouTube URL (video workflow) or path to a local audio file.",
    )
    parser.add_argument(
        "--model",
        default="htdemucs",
        choices=["htdemucs", "htdemucs_ft", "htdemucs_6s", "hdemucs_mmi"],
        help="Demucs model to use (default: htdemucs).",
    )
    parser.add_argument(
        "--output",
        default="output",
        help="Output directory (default: output/).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify the environment and exit.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show debug logs.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )

    if args.check:
        try:
            check_environment()
            sys.exit(0)
        except RuntimeError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            sys.exit(1)

    if not args.source:
        console.print(
            "[red]Error:[/red] Provide a YouTube URL or path to a local audio file."
        )
        console.print(
            "Use [bold]--check[/bold] to verify the environment, or [bold]--help[/bold] for usage."
        )
        sys.exit(1)

    source = args.source
    is_url = source.startswith(
        ("http://", "https://", "www.", "youtube.com", "youtu.be")
    )

    try:
        if is_url:
            run_dedrum_workflow(source, args.output, args.model)
        else:
            no_drums = separate(source, args.output, args.model)
            console.print()
            console.print(
                f"[bold green]🎵 Done![/bold green] De-drummed audio at "
                f"[bold]{no_drums.resolve()}[/bold]"
            )
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
