"""Tests for de-drum separation script."""

import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
PYTHON = sys.executable  # use the venv Python that's running the tests


def _run(*args: str) -> subprocess.CompletedProcess:
    """Run separate.py with the given arguments."""
    return subprocess.run(
        [PYTHON, str(SRC_DIR / "separate.py"), *args],
        capture_output=True,
        text=True,
    )


def test_check_pass() -> None:
    """The --check flag should exit successfully on this machine."""
    result = _run("--check")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "MPS" in result.stdout


def test_missing_file_shows_error() -> None:
    """Running on a non-existent file should exit with code 1."""
    result = _run("/does/not/exist.mp3")
    assert result.returncode == 1
    assert "not found" in result.stdout.lower()


def test_no_args_shows_usage() -> None:
    """Running without arguments should show an error message."""
    result = _run()
    assert result.returncode == 1


def test_help_flag() -> None:
    """--help should display usage information and exit 0."""
    result = _run("--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
