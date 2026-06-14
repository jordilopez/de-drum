#!/usr/bin/env python3
"""Separate drums from audio using Demucs with MPS acceleration."""

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

from analyze import analyze as _analyze

# Suppress noisy TorchCodec warnings about encoding/bits_per_sample
warnings.filterwarnings("ignore", message=".*not fully supported by TorchCodec.*")
warnings.filterwarnings("ignore", message=".*not directly supported by TorchCodec.*")

log = logging.getLogger("de-drum")
console = Console()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_environment() -> bool:
    """Verify that PyTorch, MPS, and system dependencies are available."""
    ok = True

    console.print(f"[bold]PyTorch[/bold] {torch.__version__}")

    if torch.backends.mps.is_available():
        console.print("[green]✓[/green] MPS (Metal GPU) is available")
    else:
        console.print(
            "[red]✗[/red] MPS is [bold]NOT[/bold] available — falling back to CPU"
        )
        ok = False

    if torch.backends.mps.is_built():
        console.print("[green]✓[/green] PyTorch built with MPS support")
    else:
        console.print("[red]✗[/red] PyTorch was NOT built with MPS support")
        ok = False

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        console.print("[green]✓[/green] ffmpeg found")
    except FileNotFoundError, subprocess.CalledProcessError:
        console.print("[red]✗[/red] ffmpeg not found — required for audio conversion")
        ok = False

    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
        console.print("[green]✓[/green] yt-dlp found")
    except FileNotFoundError, subprocess.CalledProcessError:
        console.print("[yellow]⚠[/yellow] yt-dlp not found — YouTube URLs won't work")

    return ok


# ---------------------------------------------------------------------------
# YouTube download
# ---------------------------------------------------------------------------


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters that are problematic in filenames."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip(". ")


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

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        console.print(
            f"[red]Error:[/red] yt-dlp failed with exit code {exc.returncode}"
        )
        if exc.stderr:
            console.print(exc.stderr)
        sys.exit(1)

    # yt-dlp --print filename outputs the final file path
    downloaded = result.stdout.strip().splitlines()[-1] if result.stdout else None

    if not downloaded or not Path(downloaded).exists():
        console.print("[red]Error:[/red] Could not determine downloaded file path.")
        sys.exit(1)

    audio_path = Path(downloaded)
    console.print(f"[green]✓[/green] Downloaded [bold]{audio_path.name}[/bold]")
    return audio_path


# ---------------------------------------------------------------------------
# Separation
# ---------------------------------------------------------------------------


def separate(source: str, output_dir: str, model: str = "htdemucs") -> None:
    """Run Demucs separation on a local audio file.

    Demucs saves to ``<output_dir>/<model>/<stem>/`` by default. After
    separation we move the files up one level so the final structure is
    ``<output_dir>/<stem>/drums.wav`` (cleaner for users).

    Args:
        source: Path to an audio file.
        output_dir: Directory to save the results.
        model: Demucs model name (default: htdemucs).
    """
    source_path = Path(source)

    if not source_path.exists():
        console.print(f"[red]Error:[/red] File not found: {source}")
        sys.exit(1)

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
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            console.print(
                f"[red]Error:[/red] Demucs failed with exit code {exc.returncode}"
            )
            if exc.stderr:
                console.print(exc.stderr)
            sys.exit(1)

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

    # Convert WAV outputs to MP3 with prefix naming
    if final_out.exists():
        wav_files = list(final_out.glob("*.wav"))
        for wav in wav_files:
            stem = wav.stem  # e.g. "drums" or "no_drums"
            mp3_name = f"{source_path.stem}_{stem}.mp3"
            mp3_path = final_out / mp3_name
            subprocess.run(
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
                capture_output=True,
                check=True,
                text=True,
            )
            wav.unlink()  # remove the original WAV

    # Analyse original audio (BPM + key + spectral map)
    analysis = _analyze(str(source_path.resolve()), output_dir=str(final_out))

    # Show analysis
    bpm_str = f"{analysis['bpm']} BPM" if analysis["bpm"] else "—"
    key_str = analysis["key"] if analysis["key"] else "—"
    ts_str = analysis.get("time_signature") or "—"
    info_parts = [f"Tempo [cyan]{bpm_str}[/cyan]", f"Key [magenta]{key_str}[/magenta]"]
    if ts_str != "—":
        info_parts.append(f"Time [yellow]{ts_str}[/yellow]")
    console.print("\n🎵 [bold]Analysis:[/bold]  " + "  ·  ".join(info_parts))

    if analysis.get("spectral_map"):
        console.print(f"📊 Spectral map: [bold]{analysis['spectral_map']}[/bold]")
    sections_parsed = analysis.get("sections_parsed")
    if sections_parsed:
        from rich.table import Table

        table = Table(
            title="Song structure",
            title_style="bold",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Time", style="cyan", no_wrap=True)
        table.add_column("Section", style="bold white")
        table.add_column("Bars", justify="right")
        table.add_column("Beats", justify="right")
        table.add_column("Key", style="magenta")
        table.add_column("Description")
        for s in sections_parsed:
            bars_val = s["bars"]
            bars_label = (
                f"{int(bars_val)}"
                if isinstance(bars_val, int) or bars_val == int(bars_val)
                else f"{bars_val}"
            )
            key_display = s.get("key") or ""
            table.add_row(
                f"{s['start']}–{s['end']}",
                s["section"],
                bars_label,
                str(s["beats"]),
                key_display,
                s["desc"],
            )
        console.print()
        console.print(table)
    elif analysis.get("section_desc"):
        console.print("\n💬 [bold]Section description:[/bold]")
        for line in analysis["section_desc"].strip().split("\n"):
            console.print(f"  {line}")

    # List output
    if final_out.exists():
        files = list(final_out.iterdir())
        console.print(
            f"[green]✓[/green] [bold]{len(files)}[/bold] file(s) in [bold]{final_out}[/bold]:"
        )
        for f in sorted(files):
            size = f.stat().st_size / 1024 / 1024
            console.print(f"  [bold]{f.name}[/bold] ({size:.1f} MB)")
    else:
        console.print(
            f"[green]✓[/green] Separation complete — check [bold]{output_dir}[/bold]"
        )
    console.print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and run the appropriate command."""
    parser = argparse.ArgumentParser(
        description="Separate drums from audio using Demucs + MPS.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="YouTube URL or path to a local audio file.",
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
        "--keep-original",
        action="store_true",
        help="Keep the original downloaded file (only relevant for YouTube URLs).",
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
        ok = check_environment()
        sys.exit(0 if ok else 1)

    if not args.source:
        console.print(
            "[red]Error:[/red] Provide a YouTube URL or path to an audio file."
        )
        console.print(
            "Use [bold]--check[/bold] to verify the environment, or [bold]--help[/bold] for usage."
        )
        sys.exit(1)

    source = args.source
    is_url = source.startswith(
        ("http://", "https://", "www.", "youtube.com", "youtu.be")
    )

    if is_url:
        # Use a temp directory for the download
        tmp_dir = Path(tempfile.mkdtemp(prefix="dedrum_"))
        audio_path = download_audio(source, str(tmp_dir))
        separate(str(audio_path), args.output, args.model)
        # Cleanup
        if not args.keep_original:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            # Move downloaded file into the song output directory
            song_dir = Path(args.output) / audio_path.stem
            song_dir.mkdir(parents=True, exist_ok=True)
            dst = song_dir / audio_path.name
            shutil.move(str(audio_path), str(dst))
            shutil.rmtree(tmp_dir, ignore_errors=True)
            console.print(f"Original kept at [bold]{dst}[/bold]")
    else:
        separate(source, args.output, args.model)


if __name__ == "__main__":
    main()
