"""Tests for de-drum separation script.

Unit tests mock subprocess.run (no network, no Demucs, no real ffmpeg).
CLI tests run separate.py as a subprocess for flags only.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
PYTHON = sys.executable  # use the venv Python that's running the tests

sys.path.insert(0, str(SRC_DIR))
import separate as sep  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeRun:
    """Replace sep.subprocess.run: record commands, return canned results."""

    def __init__(self, stdout: str = "", fail: bool = False):
        self.commands: list[list[str]] = []
        self.stdout = stdout
        self.fail = fail

    def __call__(self, cmd, **kwargs):
        self.commands.append(list(cmd))
        if self.fail:
            raise subprocess.CalledProcessError(1, cmd[0], stderr="boom")
        return SimpleNamespace(stdout=self.stdout, returncode=0)


@pytest.fixture
def fake_file(tmp_path):
    """Create a dummy file and return its path."""
    f = tmp_path / "Song.mp4"
    f.write_bytes(b"fake")
    return f


# ---------------------------------------------------------------------------
# CLI smoke tests (subprocess, no mocking)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# download_video
# ---------------------------------------------------------------------------


def test_download_video_command(monkeypatch, tmp_path) -> None:
    """download_video must use yt-dlp with video-only MP4 format."""
    fake = FakeRun(stdout=str(tmp_path / "Video.mp4"))
    monkeypatch.setattr(sep.subprocess, "run", fake)
    (tmp_path / "Video.mp4").write_bytes(b"v")

    result = sep.download_video("https://youtu.be/abc", str(tmp_path))

    cmd = fake.commands[0]
    assert cmd[0] == "yt-dlp"
    assert "--no-playlist" in cmd
    assert "--print" in cmd and "after_move:filepath" in cmd
    fmt = cmd[cmd.index("-f") + 1]
    assert fmt == "bestvideo[ext=mp4]/bestvideo*"
    assert "https://youtu.be/abc" in cmd
    assert result == tmp_path / "Video.mp4"


def test_download_video_failure_raises(monkeypatch, tmp_path) -> None:
    """A yt-dlp failure must raise RuntimeError, not exit silently."""
    fake = FakeRun(fail=True)
    monkeypatch.setattr(sep.subprocess, "run", fake)

    with pytest.raises(RuntimeError, match="yt-dlp failed"):
        sep.download_video("https://youtu.be/abc", str(tmp_path))


# ---------------------------------------------------------------------------
# download_audio
# ---------------------------------------------------------------------------


def test_download_audio_command(monkeypatch, tmp_path) -> None:
    """download_audio must extract MP3 with --no-playlist."""
    fake = FakeRun(stdout=str(tmp_path / "Song.mp3"))
    monkeypatch.setattr(sep.subprocess, "run", fake)
    (tmp_path / "Song.mp3").write_bytes(b"a")

    result = sep.download_audio("https://youtu.be/abc", str(tmp_path))

    cmd = fake.commands[0]
    assert cmd[0] == "yt-dlp"
    assert "--extract-audio" in cmd
    assert "--audio-format" in cmd and "mp3" in cmd
    assert "--no-playlist" in cmd
    assert "--print" in cmd and "after_move:filepath" in cmd
    assert "https://youtu.be/abc" in cmd
    assert result == tmp_path / "Song.mp3"


def test_download_audio_failure_raises(monkeypatch, tmp_path) -> None:
    """A yt-dlp failure must raise RuntimeError."""
    fake = FakeRun(fail=True)
    monkeypatch.setattr(sep.subprocess, "run", fake)

    with pytest.raises(RuntimeError, match="yt-dlp failed"):
        sep.download_audio("https://youtu.be/abc", str(tmp_path))


# ---------------------------------------------------------------------------
# separate (Demucs)
# ---------------------------------------------------------------------------


def test_separate_demucs_command(monkeypatch, tmp_path, fake_file) -> None:
    """separate must invoke demucs with two-stems drums, device and model."""
    monkeypatch.setattr(
        sep.torch.backends.mps, "is_available", lambda: False
    )  # deterministic device
    fake = FakeRun()
    monkeypatch.setattr(sep.subprocess, "run", fake)
    # Simulate Demucs output: <output_dir>/<model>/<stem>/no_drums.wav
    demucs_dir = tmp_path / "htdemucs_ft" / fake_file.stem
    demucs_dir.mkdir(parents=True)
    (demucs_dir / "no_drums.wav").write_bytes(b"w")

    result = sep.separate(
        str(fake_file), str(tmp_path), "htdemucs_ft", convert_mp3=False
    )

    cmd = fake.commands[0]
    assert cmd[0] == sys.executable
    assert cmd[cmd.index("-m") + 1] == "demucs"
    assert cmd[cmd.index("--two-stems") + 1] == "drums"
    assert cmd[cmd.index("--device") + 1] == "cpu"
    assert cmd[cmd.index("-n") + 1] == "htdemucs_ft"
    assert str(fake_file.resolve()) in cmd
    assert result == tmp_path / fake_file.stem / "no_drums.wav"


def test_separate_cpu_fallback(monkeypatch, tmp_path, fake_file) -> None:
    """Without MPS, separate must pass device=cpu to Demucs (no failure)."""
    monkeypatch.setattr(sep.torch.backends.mps, "is_available", lambda: False)
    fake = FakeRun()
    monkeypatch.setattr(sep.subprocess, "run", fake)
    stem_dir = tmp_path / "htdemucs" / fake_file.stem
    stem_dir.mkdir(parents=True)
    (stem_dir / "no_drums.wav").write_bytes(b"w")

    sep.separate(str(fake_file), str(tmp_path), convert_mp3=False)

    cmd = fake.commands[0]
    assert cmd[cmd.index("--device") + 1] == "cpu"


def test_separate_missing_wav_raises(monkeypatch, tmp_path, fake_file) -> None:
    """If Demucs produced no no_drums.wav, separate must raise."""
    fake = FakeRun()
    monkeypatch.setattr(sep.subprocess, "run", fake)

    with pytest.raises(RuntimeError, match="no no_drums.wav"):
        sep.separate(str(fake_file), str(tmp_path), convert_mp3=False)


def test_separate_missing_executable_raises(monkeypatch, tmp_path, fake_file) -> None:
    """A missing executable must raise a RuntimeError with a clear message."""

    def missing(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(sep.subprocess, "run", missing)

    with pytest.raises(RuntimeError, match="not found"):
        sep.separate(str(fake_file), str(tmp_path), convert_mp3=False)


def test_separate_missing_file_raises(tmp_path) -> None:
    """A missing source file must raise RuntimeError."""
    with pytest.raises(RuntimeError, match="not found"):
        sep.separate("/does/not/exist.mp3", str(tmp_path))


def test_separate_demucs_failure_raises(monkeypatch, tmp_path, fake_file) -> None:
    """A Demucs failure must raise RuntimeError."""
    fake = FakeRun(fail=True)
    monkeypatch.setattr(sep.subprocess, "run", fake)

    with pytest.raises(RuntimeError, match="Demucs failed"):
        sep.separate(str(fake_file), str(tmp_path), convert_mp3=False)


# ---------------------------------------------------------------------------
# mux_video_audio
# ---------------------------------------------------------------------------


def test_mux_command(monkeypatch, tmp_path, fake_file) -> None:
    """mux_video_audio must map video from input 0, audio from input 1."""
    fake = FakeRun()
    monkeypatch.setattr(sep.subprocess, "run", fake)
    audio = tmp_path / "no_drums.wav"
    audio.write_bytes(b"w")
    out = tmp_path / "out.mp4"
    out.write_bytes(b"muxed")  # simulate successful ffmpeg output

    sep.mux_video_audio(fake_file, audio, out)

    cmd = fake.commands[0]
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert cmd.count("-i") == 2
    assert str(fake_file) in cmd and str(audio) in cmd
    assert cmd[cmd.index("-map") + 1] == "0:v:0"
    assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "1:a:0"
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert "-shortest" in cmd
    assert str(out) == cmd[-1]


def test_mux_failure_raises(monkeypatch, tmp_path, fake_file) -> None:
    """An ffmpeg muxing failure must raise RuntimeError."""
    fake = FakeRun(fail=True)
    monkeypatch.setattr(sep.subprocess, "run", fake)

    with pytest.raises(RuntimeError, match="muxing failed"):
        sep.mux_video_audio(fake_file, tmp_path / "no_drums.wav", tmp_path / "out.mp4")


def test_mux_artifact_validation(monkeypatch, tmp_path, fake_file) -> None:
    """mux_video_audio must verify the output exists and is non-empty."""
    fake = FakeRun()
    monkeypatch.setattr(sep.subprocess, "run", fake)
    audio = tmp_path / "no_drums.wav"
    audio.write_bytes(b"w")
    out = tmp_path / "out.mp4"

    # No output file at all → raise
    with pytest.raises(RuntimeError, match="no output"):
        sep.mux_video_audio(fake_file, audio, out)

    # Empty output file → raise
    out.write_bytes(b"")
    with pytest.raises(RuntimeError, match="no output"):
        sep.mux_video_audio(fake_file, audio, out)

    # Non-empty output file → OK
    out.write_bytes(b"muxed video data")
    sep.mux_video_audio(fake_file, audio, out)


# ---------------------------------------------------------------------------
# run_dedrum_workflow
# ---------------------------------------------------------------------------


def test_workflow_happy_path(monkeypatch, tmp_path, fake_file) -> None:
    """The full workflow must run every step in order and return the MP4."""
    calls: list[str] = []
    monkeypatch.setattr(sep, "check_environment", lambda: calls.append("env") or True)

    def fake_download_video(url, d):
        calls.append("video")
        fake_file.write_bytes(b"v")
        return fake_file

    def fake_download_audio(url, d):
        calls.append("audio")
        audio = Path(d) / "Song.mp3"
        audio.write_bytes(b"a")
        return audio

    def fake_separate(source, out, model, convert_mp3=False):
        calls.append("separate")
        assert convert_mp3 is False
        wav = Path(out) / "no_drums.wav"
        wav.write_bytes(b"w")
        return wav

    mux_args = {}

    def fake_mux(video, audio, output):
        calls.append("mux")
        mux_args.update(video=video, audio=audio, output=output)
        output.write_bytes(b"final")

    monkeypatch.setattr(sep, "download_video", fake_download_video)
    monkeypatch.setattr(sep, "download_audio", fake_download_audio)
    monkeypatch.setattr(sep, "separate", fake_separate)
    monkeypatch.setattr(sep, "mux_video_audio", fake_mux)

    out_dir = tmp_path / "output"
    result = sep.run_dedrum_workflow("https://youtu.be/abc", str(out_dir))

    assert calls == ["env", "video", "audio", "separate", "mux"]
    assert result == out_dir / "Song_no_drums.mp4"
    assert result.exists()
    assert mux_args["video"] == fake_file
    assert mux_args["audio"].name == "no_drums.wav"


def test_workflow_cleanup_on_success(monkeypatch, tmp_path, fake_file) -> None:
    """Temp directories must be cleaned up after a successful workflow."""
    created_dirs: list[Path] = []

    def fake_download_video(url, d):
        Path(d).mkdir(parents=True, exist_ok=True)
        created_dirs.append(Path(d))
        video = Path(d) / "Song.mp4"
        video.write_bytes(b"v")
        return video

    def fake_download_audio(url, d):
        Path(d).mkdir(parents=True, exist_ok=True)
        created_dirs.append(Path(d))
        audio = Path(d) / "Song.mp3"
        audio.write_bytes(b"a")
        return audio

    monkeypatch.setattr(sep, "check_environment", lambda: True)
    monkeypatch.setattr(sep, "download_video", fake_download_video)
    monkeypatch.setattr(sep, "download_audio", fake_download_audio)

    def fake_separate(source, out, model, convert_mp3=False):
        Path(out).mkdir(parents=True, exist_ok=True)
        created_dirs.append(Path(out))
        wav = Path(out) / "no_drums.wav"
        wav.write_bytes(b"w")
        return wav

    monkeypatch.setattr(sep, "separate", fake_separate)
    monkeypatch.setattr(
        sep,
        "mux_video_audio",
        lambda v, a, o: o.write_bytes(b"final"),
    )

    sep.run_dedrum_workflow("https://youtu.be/abc", str(tmp_path / "output"))

    assert len(created_dirs) == 3
    for d in created_dirs:
        assert not d.exists(), f"temp dir not cleaned up: {d}"


def test_workflow_output_naming(monkeypatch, tmp_path, fake_file) -> None:
    """The final MP4 must use the sanitized video title + _no_drums suffix."""
    monkeypatch.setattr(sep, "check_environment", lambda: True)
    monkeypatch.setattr(sep, "download_video", lambda url, d: fake_file)
    monkeypatch.setattr(sep, "download_audio", lambda url, d: tmp_path / "Song.mp3")
    monkeypatch.setattr(sep, "separate", lambda *a, **k: tmp_path / "no_drums.wav")
    muxed = {}
    monkeypatch.setattr(
        sep,
        "mux_video_audio",
        lambda v, a, o: (muxed.update(out=o), o.write_bytes(b"final")),
    )

    # Title with characters that need sanitizing (: ?) but are valid on disk
    weird = tmp_path / "My Song: Best Hits?.mp4"
    weird.write_bytes(b"v")
    monkeypatch.setattr(sep, "download_video", lambda url, d: weird)

    out_dir = tmp_path / "output"
    result = sep.run_dedrum_workflow("https://youtu.be/abc", str(out_dir))

    assert result == out_dir / "My Song_ Best Hits__no_drums.mp4"
    assert result.parent == out_dir
    assert muxed["out"] == result


def test_workflow_temp_cleanup_on_failure(monkeypatch, tmp_path) -> None:
    """Temp directories must be cleaned up even when a step fails."""
    before = {p.name for p in Path(tempfile.gettempdir()).glob("dedrum_*")}
    monkeypatch.setattr(sep, "check_environment", lambda: True)

    def fail_download(url, d):
        raise RuntimeError("yt-dlp failed")

    monkeypatch.setattr(sep, "download_video", fail_download)

    with pytest.raises(RuntimeError):
        sep.run_dedrum_workflow("https://youtu.be/abc", str(tmp_path / "out"))

    after = {p.name for p in Path(tempfile.gettempdir()).glob("dedrum_*")}
    assert not after - before  # no new dedrum_* temp dirs left behind


def test_workflow_env_check_failure(monkeypatch, tmp_path) -> None:
    """A failed environment check must abort the workflow."""
    monkeypatch.setattr(sep, "check_environment", lambda: False)

    with pytest.raises(RuntimeError, match="Environment check failed"):
        sep.run_dedrum_workflow("https://youtu.be/abc", str(tmp_path / "out"))


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------


def test_sanitize_filename() -> None:
    """Problematic characters must be replaced and dots/spaces stripped."""
    assert sep._sanitize_filename("My: Song?") == "My_ Song_"
    assert sep._sanitize_filename('a/b\\c"d|e*f<g>h') == "a_b_c_d_e_f_g_h"
    assert sep._sanitize_filename("  .title.  ") == "title"
    assert sep._sanitize_filename("clean-name") == "clean-name"
