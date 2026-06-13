#!/usr/bin/env python3
"""Separate drums from audio using Demucs with MPS acceleration."""

import argparse
import logging
import shutil
import subprocess
import sys
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

    # List output
    if final_out.exists():
        files = list(final_out.iterdir())
        console.print(
            f"\n[green]✓[/green] Done — [bold]{len(files)}[/bold] file(s) in [bold]{final_out}[/bold]:"
        )
        for f in files:
            size = f.stat().st_size / 1024 / 1024
            console.print(f"  [bold]{f.name}[/bold] ({size:.1f} MB)")
    else:
        console.print(
            f"\n[green]✓[/green] Separation complete — check [bold]{output_dir}[/bold]"
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
        console.print(f"Downloading audio from [cyan]{source}[/cyan]...")
        # TODO: Phase 3 — yt-dlp integration
        console.print(
            "[yellow]YouTube download not yet implemented — coming in Phase 3.[/yellow]"
        )
        sys.exit(1)

    separate(source, args.output, args.model)


if __name__ == "__main__":
    main()
