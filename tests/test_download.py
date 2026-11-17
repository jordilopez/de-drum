"""Tests for the audio-only YouTube downloader."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))
import download  # noqa: E402


def test_download_audio_builds_mp3_command(monkeypatch, tmp_path):
    """The downloader should request audio extraction and MP3 conversion."""
    output = tmp_path / "Song.mp3"
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        output.write_bytes(b"mp3")
        return SimpleNamespace(stdout=f"{output}\n")

    monkeypatch.setattr(download.subprocess, "run", fake_run)

    result = download.download_audio(
        "https://www.youtube.com/watch?v=abc&list=ignored", str(tmp_path)
    )

    command = commands[0]
    assert command[0] == "yt-dlp"
    assert "--no-playlist" in command
    assert "--extract-audio" in command
    assert command[command.index("--audio-format") + 1] == "mp3"
    assert command[-1] == "https://www.youtube.com/watch?v=abc"
    assert result == output


def test_download_audio_failure_raises(monkeypatch, tmp_path):
    """yt-dlp failures should become clear RuntimeErrors."""
    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command[0], stderr="boom")

    monkeypatch.setattr(download.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="yt-dlp failed"):
        download.download_audio("https://youtu.be/abc", str(tmp_path))


def test_download_audio_requires_reported_file(monkeypatch, tmp_path):
    """A missing post-processing path should fail instead of claiming success."""
    monkeypatch.setattr(
        download.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(stdout=""),
    )

    with pytest.raises(RuntimeError, match="valid MP3 output path"):
        download.download_audio("https://youtu.be/abc", str(tmp_path))
