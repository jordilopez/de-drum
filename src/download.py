#!/usr/bin/env python3
"""Download YouTube audio as an MP3 file."""

import argparse
import subprocess
from pathlib import Path

from rich.console import Console

from separate import clean_youtube_url

console = Console()


def download_audio(url: str, output_dir: str = "output") -> Path:
    """Download YouTube audio and convert it to MP3 with yt-dlp.

    Args:
        url: YouTube video URL.
        output_dir: Directory where the MP3 is saved.

    Returns:
        Path to the downloaded MP3.

    Raises:
        RuntimeError: If yt-dlp fails or produces no output path.
    """
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    cleaned_url = clean_youtube_url(url)
    template = str(destination / "%(title)s.%(ext)s")
    command = [
        "yt-dlp",
        "--no-playlist",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--output",
        template,
        "--print",
        "after_move:filepath",
        cleaned_url,
    ]

    console.print(f"Downloading MP3 from [cyan]{cleaned_url}[/cyan]...")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "yt-dlp not found — install it with `brew install yt-dlp`."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = f":\n{exc.stderr}" if exc.stderr else ""
        raise RuntimeError(
            f"yt-dlp failed with exit code {exc.returncode}{detail}"
        ) from exc

    lines = result.stdout.strip().splitlines()
    downloaded = Path(lines[-1]) if lines else None
    if downloaded is None or not downloaded.exists():
        raise RuntimeError("yt-dlp did not report a valid MP3 output path")

    console.print(f"[green]✓[/green] Saved [bold]{downloaded}[/bold]")
    return downloaded


def main() -> int:
    """Parse arguments and download the requested audio."""
    parser = argparse.ArgumentParser(description="Download YouTube audio as MP3.")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--output", default="output", help="Output directory (default: output/)"
    )
    args = parser.parse_args()

    try:
        download_audio(args.url, args.output)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
