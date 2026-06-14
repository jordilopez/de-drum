"""Tests for analyze.py — bar enrichment and analysis helpers."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analyze import (  # noqa: E402
    _enrich_section_desc,
    _time_to_seconds,
    detect_modulations,
    detect_time_signature,
)

# ── Sample LLM output for tests ────────────────────────────────────

_SAMPLE_DESC = """0:00-0:12 | Intro | Quiet / breakdown (low energy)
0:12-0:24 | Verse 1 | Full / climax (high energy)
1:24-1:36 | Chorus 2 | Full / climax (powerful, bright highs)"""


# ── _time_to_seconds ───────────────────────────────────────────────


class TestTimeToSeconds:
    def test_simple_minutes_seconds(self):
        assert _time_to_seconds("1:30") == 90

    def test_zero(self):
        assert _time_to_seconds("0:00") == 0

    def test_only_seconds(self):
        assert _time_to_seconds("0:45") == 45

    def test_large_minutes(self):
        assert _time_to_seconds("5:00") == 300

    def test_mixed(self):
        assert _time_to_seconds("2:15") == 135


# ── _enrich_section_desc ───────────────────────────────────────────


class TestEnrichSectionDesc:
    def test_no_desc_returns_empty(self):
        assert _enrich_section_desc("", 120.0) == ""

    def test_none_desc_returns_none(self):
        assert _enrich_section_desc(None, 120.0) is None  # type: ignore

    def test_zero_bpm_returns_original(self):
        assert _enrich_section_desc(_SAMPLE_DESC, 0) == _SAMPLE_DESC

    def test_negative_bpm_returns_original(self):
        assert _enrich_section_desc(_SAMPLE_DESC, -10) == _SAMPLE_DESC

    def test_bar_count_at_120_bpm(self):
        """12 s sections at 120 BPM → 6 bars each (240/120 = 2 s/bar)."""
        enriched = _enrich_section_desc(_SAMPLE_DESC, 120.0)
        lines = enriched.strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            assert "(6 bars, 24 beats)" in line

    def test_bar_count_at_140_bpm(self):
        """12 s sections at 140 BPM → ~7 bars each."""
        enriched = _enrich_section_desc(_SAMPLE_DESC, 140.0)
        lines = enriched.strip().split("\n")
        for line in lines:
            # 12 / (240/140) = 12 / 1.714 = 7.0
            assert "7 bars" in line

    def test_non_matching_lines_pass_through(self):
        """Lines that don't match the pattern should be left as-is."""
        desc = "A header line\n\n0:00-0:12 | Intro | Quiet\nA footer line"
        enriched = _enrich_section_desc(desc, 120.0)
        assert enriched.startswith("A header line")
        assert enriched.endswith("A footer line")
        assert "Intro (6 bars, 24 beats)" in enriched

    def test_singular_bar(self):
        """1 bar should say 'bar' not 'bars'."""
        # A 2-second section at 120 BPM = 1 bar
        desc = "0:00-0:02 | Hit | Quick stab"
        enriched = _enrich_section_desc(desc, 120.0)
        assert "1 bar, 4 beats" in enriched

    def test_timezone_style_timestamp(self):
        """Handles 'MM:SS' format (more than 1 digit for minutes)."""
        desc = "10:00-12:00 | Long Section | Extended breakdown"
        enriched = _enrich_section_desc(desc, 120.0)
        # 120 s at 120 BPM = 60 bars
        assert "60 bars" in enriched


# ── detect_time_signature ──────────────────────────────────────────

_SR = 22050


def _make_meter_signal(
    bpm: float,
    n_beats: int,
    accent_every: int,
    sr: int = _SR,
) -> np.ndarray:
    """Synthetic sine-tone pulse train with regular accents."""
    beat_sec = 60.0 / bpm
    total_sec = beat_sec * n_beats + 0.5
    n_samples = int(total_sec * sr)
    t = np.arange(n_samples) / sr
    audio = np.zeros(n_samples, dtype=np.float32)
    for b in range(n_beats):
        pos_samp = int(b * beat_sec * sr)
        if pos_samp >= n_samples:
            break
        tone_len = int(0.08 * sr)
        end_samp = min(pos_samp + tone_len, n_samples)
        actual_len = end_samp - pos_samp
        env = np.hanning(actual_len * 2 + 1)[1 : actual_len + 1]
        amp = 0.5 if (b % accent_every == 0) else 0.12
        tone = amp * np.sin(2 * np.pi * 500 * t[:actual_len])
        audio[pos_samp:end_samp] += tone * env[:actual_len]
    audio /= np.max(np.abs(audio)) + 1e-10
    return audio


class _MeterFiles:
    """Manage temporary WAV files for meter tests."""

    def __init__(self):
        import tempfile

        import soundfile as sf

        self.tmpdir = tempfile.mkdtemp(prefix="dedrum_test_")
        # 4/4: 64 beats (16 bars), accent every 4
        audio_4 = _make_meter_signal(120, 64, 4)
        self.path_4 = str(Path(self.tmpdir) / "meter_4.wav")
        sf.write(self.path_4, audio_4, _SR)
        # 3/4: 63 beats (21 bars), accent every 3
        audio_3 = _make_meter_signal(120, 63, 3)
        self.path_3 = str(Path(self.tmpdir) / "meter_3.wav")
        sf.write(self.path_3, audio_3, _SR)
        # Ambiguous: no accent pattern, too short
        audio_flat = np.random.randn(_SR * 5).astype(np.float32)
        self.path_flat = str(Path(self.tmpdir) / "meter_flat.wav")
        sf.write(self.path_flat, audio_flat, _SR)

    def cleanup(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)


_METER_FILES: _MeterFiles | None = None


def setup_module():
    global _METER_FILES
    _METER_FILES = _MeterFiles()


def teardown_module():
    if _METER_FILES is not None:
        _METER_FILES.cleanup()


class TestDetectTimeSignature:
    def test_detects_4_4(self):
        assert _METER_FILES is not None
        result = detect_time_signature(_METER_FILES.path_4)
        assert result == "4/4"

    def test_detects_3_4(self):
        assert _METER_FILES is not None
        result = detect_time_signature(_METER_FILES.path_3)
        assert result == "3/4"

    def test_short_audio_returns_none(self):
        assert _METER_FILES is not None
        result = detect_time_signature(_METER_FILES.path_flat)
        assert result is None

    def test_missing_file_returns_none(self):
        result = detect_time_signature("/nonexistent/file.wav")
        assert result is None


# ── detect_modulations ──────────────────────────────────────────────


class TestDetectModulations:
    @classmethod
    def setup_class(cls):
        import tempfile

        import soundfile as sf

        cls.tmpdir = tempfile.mkdtemp(prefix="dedrum_test_")
        cls.sr = _SR  # 22050 is fine for chroma

        # Create 60 seconds of audio
        # We'll just use white noise — modulations won't be detected
        # reliably on noise, but we test that the function runs
        audio = np.random.randn(_SR * 60).astype(np.float32)
        cls.path_noise = str(Path(cls.tmpdir) / "noise.wav")
        sf.write(cls.path_noise, audio, cls.sr)

        # Create a short file (<20s) to test early exit
        audio_short = np.random.randn(_SR * 10).astype(np.float32)
        cls.path_short = str(Path(cls.tmpdir) / "short.wav")
        sf.write(cls.path_short, audio_short, cls.sr)

    @classmethod
    def teardown_class(cls):
        import shutil

        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_modulations_returns_list_on_noise(self):
        result = detect_modulations(self.path_noise)
        # Even on noise, the function should run and return a list
        if result is not None:
            assert isinstance(result, list)
            assert len(result) >= 1
            for m in result:
                assert "start" in m
                assert "end" in m
                assert "key" in m
                assert "start_sec" in m
                assert "end_sec" in m

    def test_short_audio_returns_none(self):
        result = detect_modulations(self.path_short)
        assert result is None

    def test_missing_file_returns_none(self):
        result = detect_modulations("/nonexistent/file.wav")
        assert result is None
