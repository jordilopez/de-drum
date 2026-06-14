"""Audio analysis: BPM, musical key, and spectral density section map."""

import re
from pathlib import Path

import librosa
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Krumhansl-Schmuckler key profiles
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
_NOTE_NAMES = [
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
]


def _parse_tempo(tempo_result) -> float:
    """Extract a scalar BPM from librosa's beat_track return value.

    librosa may return a float, a 0-d array, a 1-element array, or 0.0
    when no beats are found.
    """
    if hasattr(tempo_result, "item"):
        # ndarray → scalar
        return float(tempo_result.item())
    return float(tempo_result)


def detect_bpm(audio_path: str) -> float | None:
    """Detect the tempo (BPM) of an audio file.

    Args:
        audio_path: Path to an audio file.

    Returns:
        BPM as a float, or None if detection failed.
    """
    try:
        y, sr = librosa.load(audio_path, sr=None, duration=60)
        if len(y) < sr:  # Less than 1 second
            return None
        tempo_arr, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = _parse_tempo(tempo_arr)
        return round(bpm, 1) if bpm > 0 else None
    except Exception:
        return None


def detect_key(audio_path: str) -> str | None:
    """Detect the most likely musical key of an audio file.

    Uses the Krumhansl-Schmuckler key-finding algorithm on chroma
    features.

    Args:
        audio_path: Path to an audio file.

    Returns:
        Key name like ``"F minor"`` or ``"C major"``, or None if
        detection failed.
    """
    try:
        y, sr = librosa.load(audio_path, sr=None, duration=60)
        if len(y) < sr:
            return None

        # Chromagram averaged over time
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)

        # Correlate with all 12 rotations of each profile
        corr_major = np.array(
            [np.correlate(chroma_mean, np.roll(_MAJOR_PROFILE, i)) for i in range(12)]
        )
        corr_minor = np.array(
            [np.correlate(chroma_mean, np.roll(_MINOR_PROFILE, i)) for i in range(12)]
        )

        best_idx = int(np.argmax(np.concatenate([corr_major, corr_minor])))
        if best_idx < 12:
            return f"{_NOTE_NAMES[best_idx]} major"
        else:
            return f"{_NOTE_NAMES[best_idx - 12]} minor"
    except Exception:
        return None


def detect_time_signature(audio_path: str, bpm: float | None = None) -> str | None:
    """Detect the time signature (3/4, 4/4) from audio.

    Uses onset-strength autocorrelation at beat positions to find
    whether the accent pattern repeats every 3 beats (3/4) or every
    4 beats (4/4). If neither is clearly dominant, returns ``None``.

    Args:
        audio_path: Path to an audio file.
        bpm: Pre-detected BPM (optional, saves recomputation).

    Returns:
        ``"3/4"``, ``"4/4"``, or ``None`` if detection is unreliable.
    """
    try:
        y, sr = librosa.load(audio_path, sr=None, duration=60)
        if len(y) < sr * 10:  # need at least 10 seconds
            return None

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)

        if bpm is None:
            tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            bpm = _parse_tempo(tempo)

        if bpm is None or bpm <= 0:
            return None

        _, beats = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sr, units="frames"
        )
        if len(beats) < 16:
            return None

        # Onset strength at each beat position, normalised 0-1
        onset_b = onset_env[beats].astype(np.float64)
        mn, mx = onset_b.min(), onset_b.max()
        if mx - mn < 1e-10:
            return None
        onset_b = (onset_b - mn) / (mx - mn)

        # Remove DC for correlation
        x = onset_b - onset_b.mean()
        n = len(x)

        # Autocorrelation at lags 1-8
        ac = np.full(9, np.nan)
        for lag in range(3, 7):
            if lag < n:
                denom = np.std(x[:-lag]) * np.std(x[lag:])
                if denom > 1e-10:
                    ac[lag] = np.corrcoef(x[:-lag], x[lag:])[0, 1]

        if np.isnan(ac[3]) or np.isnan(ac[4]):
            return None

        # Strong periodicity at lag 3 → likely 3/4, at lag 4 → 4/4
        # Apply a small bias toward 4/4 (more common)
        if ac[3] > ac[4] + 0.08:
            return "3/4"
        elif ac[4] > ac[3] + 0.08:
            return "4/4"

        # Ambiguous via autocorrelation — try pattern-matching
        # with multiple phase offsets
        def _score_meter(onset: np.ndarray, meter: int) -> float:
            """Score how well onset array matches a meter.

            Tries every phase offset 0..meter-1 and returns the best
            score.  Higher score = better fit.
            """
            best = -np.inf
            for shift in range(meter):
                usable = (len(onset) - shift) // meter
                if usable < 3:
                    continue
                # Unfold into bars
                bars = onset[shift : shift + usable * meter].reshape(usable, meter)
                avg_bar = bars.mean(axis=0)
                # Ideal: downbeat (idx 0) is strongest
                downbeat_prominence = avg_bar[0] - avg_bar[1:].mean()
                within_bar_var = avg_bar[1:].std()  # smaller = more uniform
                score = downbeat_prominence - 0.3 * within_bar_var
                if score > best:
                    best = score
            return best

        score_3 = _score_meter(onset_b, 3)
        score_4 = _score_meter(onset_b, 4)

        if score_3 > score_4 + 0.05:
            return "3/4"
        elif score_4 > score_3 + 0.05:
            return "4/4"

        return None  # truly ambiguous
    except Exception:
        return None


def detect_modulations(audio_path: str) -> list[dict] | None:
    """Detect key changes (modulations) across a song.

    Divides the audio into overlapping windows (30 s, 15 s hop),
    runs Krumhansl-Schmuckler key detection on each, and merges
    consecutive windows with the same key.

    Returns:
        List of dicts with keys ``start``, ``end``, ``start_sec``,
        ``end_sec``, ``key``, or ``None`` if detection fails.
    """
    try:
        y, sr = librosa.load(audio_path, sr=None, duration=300)
        if len(y) < sr * 20:
            return None

        # Compute chroma once for the full audio
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        hop_length = 512  # librosa default for chroma_cqt
        frames_total = chroma.shape[1]

        # Window in frames: 30 s → ~2646 frames at sr=44100, hop=512
        window_frames = int(30.0 * sr / hop_length)
        hop_frames = int(15.0 * sr / hop_length)

        n_windows = max(1, (frames_total - window_frames) // hop_frames + 1)

        raw: list[dict] = []
        for i in range(n_windows):
            start_f = i * hop_frames
            end_f = min(start_f + window_frames, frames_total)
            if end_f - start_f < 10:  # too few frames
                continue

            chroma_mean = np.mean(chroma[:, start_f:end_f], axis=1)

            corr_major = np.array(
                [
                    np.correlate(chroma_mean, np.roll(_MAJOR_PROFILE, i))
                    for i in range(12)
                ]
            )
            corr_minor = np.array(
                [
                    np.correlate(chroma_mean, np.roll(_MINOR_PROFILE, i))
                    for i in range(12)
                ]
            )

            best_idx = int(np.argmax(np.concatenate([corr_major, corr_minor])))
            if best_idx < 12:
                key = f"{_NOTE_NAMES[best_idx]} major"
            else:
                key = f"{_NOTE_NAMES[best_idx - 12]} minor"

            start_sec = start_f * hop_length / sr
            end_sec = end_f * hop_length / sr

            raw.append({"key": key, "start_sec": start_sec, "end_sec": end_sec})

        if not raw:
            return None

        # Merge consecutive same-key windows
        merged: list[dict] = []
        cur = dict(raw[0])
        for r in raw[1:]:
            if r["key"] == cur["key"]:
                cur["end_sec"] = r["end_sec"]
            else:
                merged.append(cur)
                cur = dict(r)
        merged.append(cur)

        # Format human-readable timestamps
        for m in merged:
            m["start"] = f"{int(m['start_sec'] // 60)}:{int(m['start_sec'] % 60):02d}"
            m["end"] = f"{int(m['end_sec'] // 60)}:{int(m['end_sec'] % 60):02d}"

        return merged
    except Exception:
        return None


# ── Section description enrichment (bar counts) ────────────────────


def _time_to_seconds(timestr: str) -> int:
    """Convert a ``'M:SS'`` timestamp to total seconds."""
    parts = timestr.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


def _enrich_section_desc(desc: str, bpm: float) -> str:
    """Add bar and beat counts to each section-description line.

    Parses lines in the format produced by
    :func:`section_describer.describe_sections`::

        0:00-0:12 | Intro | Quiet / breakdown...

    and enriches them::

        0:00-0:12 | Intro (4 bars, 16 beats) | Quiet / breakdown...

    Calculations assume 4/4 time: 1 bar = 4 beats = 240 / BPM seconds.

    Args:
        desc: Multi-line section description from the LLM.
        bpm: Beats per minute (must be > 0).

    Returns:
        Enhanced description string, or the original if parsing fails.
    """
    if not desc or not bpm or bpm <= 0:
        return desc

    sec_per_bar = 240.0 / bpm  # seconds per bar in 4/4
    lines = desc.strip().split("\n")
    new_lines: list[str] = []

    # Pattern: "M:SS-M:SS | Section Name | Description"
    pattern = re.compile(r"^(\d+:\d+)-(\d+:\d+) \| (.+?) \| (.+)$")

    for line in lines:
        m = pattern.match(line)
        if m:
            start_str, end_str, section_name, section_desc = m.groups()
            start_sec = _time_to_seconds(start_str)
            end_sec = _time_to_seconds(end_str)
            duration = end_sec - start_sec

            if duration > 0:
                bars = duration / sec_per_bar
                # Round to nearest half bar for musical readability
                bars_rounded = round(bars * 2) / 2
                beats = int(round(bars_rounded * 4))

                if bars_rounded == int(bars_rounded):
                    bars_str = str(int(bars_rounded))
                else:
                    bars_str = f"{bars_rounded:.1f}"

                bar_label = (
                    f"{bars_str} bar" if bars_rounded == 1 else f"{bars_str} bars"
                )
                new_lines.append(
                    f"{start_str}-{end_str} | {section_name} ({bar_label}, {beats} beats) | {section_desc}"
                )
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return "\n".join(new_lines)


def _parse_section_desc(desc: str) -> list[dict] | None:
    """Parse enriched section description lines into structured data.

    Expects the format produced by :func:`_enrich_section_desc`::

        0:00-0:12 | Intro (6 bars, 24 beats) | Quiet / breakdown...

    Returns:
        List of dicts with keys ``start``, ``end``, ``section``,
        ``bars``, ``beats``, ``desc``, or ``None`` if nothing to parse.
    """
    if not desc:
        return None

    # Pattern for enriched lines: Timestamp | Section (X bars, Y beats) | Desc
    pattern = re.compile(
        r"^(\d+:\d+)-(\d+:\d+) \| (.+?) \((\d+(?:\.\d+)?) bars?, (\d+) beats\) \| (.+)$"
    )
    sections: list[dict] = []
    for line in desc.strip().split("\n"):
        m = pattern.match(line)
        if m:
            start_str, end_str, section_name, bars_str, beats_str, section_desc = (
                m.groups()
            )
            sections.append(
                {
                    "start": start_str,
                    "end": end_str,
                    "section": section_name,
                    "bars": float(bars_str) if "." in bars_str else int(bars_str),
                    "beats": int(beats_str),
                    "desc": section_desc,
                }
            )
    return sections if sections else None


# ── Frequency bands (Hz) that musicians care about ─────────────────
_BAND_DEFS = [
    ("Sub", 20, 60),
    ("Bass", 60, 250),
    ("Low-Mid", 250, 500),
    ("Mid", 500, 2000),
    ("High-Mid", 2000, 4000),
    ("Presence", 4000, 8000),
    ("Air", 8000, 16000),
]
_BAND_NAMES = [b[0] for b in _BAND_DEFS]


def compute_section_data(audio_path: str, n_sections: int = 24) -> dict | None:
    """Compute per-section loudness and frequency-band energy.

    Returns a dict with keys ``duration_sec``, ``sections`` (list of
    per-section dicts with ``loudness`` and ``bands``).
    """
    try:
        y, sr = librosa.load(audio_path, sr=None, duration=300)
        if len(y) < sr:
            return None

        duration_sec = len(y) / sr
        stft = librosa.stft(y)
        mag = np.abs(stft) ** 2
        freqs = librosa.fft_frequencies(sr=sr)
        total_frames = mag.shape[1]

        frames_per_sec = max(1, total_frames // n_sections)
        actual_n = min(n_sections, total_frames)

        band_energy = np.zeros((len(_BAND_DEFS), actual_n))
        section_rms = np.zeros(actual_n)

        for sec_idx in range(actual_n):
            start = sec_idx * frames_per_sec
            end = start + frames_per_sec if sec_idx < actual_n - 1 else total_frames
            frame_slice = mag[:, start:end]

            section_rms[sec_idx] = np.sqrt(np.mean(frame_slice))
            for b_idx, (_, lo, hi) in enumerate(_BAND_DEFS):
                mask = (freqs >= lo) & (freqs < hi)
                if mask.any():
                    band_energy[b_idx, sec_idx] = np.mean(frame_slice[mask])

        # Convert to dB and normalise
        band_db = np.where(band_energy > 1e-10, 10 * np.log10(band_energy), 0)
        rms_db = np.where(section_rms > 1e-10, 20 * np.log10(section_rms), 0)

        # Normalise per band to 0-1
        for b_idx in range(len(_BAND_DEFS)):
            row = band_db[b_idx]
            mn, mx = row.min(), row.max()
            band_db[b_idx] = (row - mn) / (mx - mn + 1e-10)

        rng = rms_db.max() - rms_db.min()
        rms_norm = (rms_db - rms_db.min()) / (rng + 1e-10)

        sections = [
            {
                "loudness": float(rms_norm[i]),
                "bands": [float(band_db[b, i]) for b in range(len(_BAND_DEFS))],
            }
            for i in range(actual_n)
        ]

        return {
            "duration_sec": duration_sec,
            "sections": sections,
        }
    except Exception:
        return None


def generate_spectral_map(
    audio_path: str,
    output_path: str,
    n_sections: int = 24,
) -> str | None:
    """Generate a musician-friendly frequency energy timeline as a PNG.

    The song is divided into equal time sections (~2–4 s each). For
    each section we compute the RMS loudness and the energy in 7
    musically meaningful frequency bands:
    Sub (20–60 Hz), Bass (60–250 Hz), Low-Mid (250–500 Hz),
    Mid (500 Hz–2 kHz), High-Mid (2–4 kHz), Presence (4–8 kHz),
    Air (8–16 kHz).

    The resulting image shows:
    * **Top panel** — loudness contour (quieter → louder)
    * **Bottom panel** — frequency-band energy heatmap

    Args:
        audio_path: Path to an audio file.
        output_path: Where to save the PNG.
        n_sections: Number of time divisions (default 24).

    Returns:
        Path to the saved PNG, or None on failure.
    """
    try:
        dur_rms = compute_section_data(audio_path, n_sections)
        if dur_rms is None:
            return None

        duration_sec = dur_rms["duration_sec"]
        sections = dur_rms["sections"]
        actual_n = len(sections)

        # Build arrays for plotting
        rms_norm = np.array([s["loudness"] for s in sections])
        band_norm = np.array([s["bands"] for s in sections]).T  # bands × sections

        # ── Time axis labels ────────────────────────────────────────
        sec_dur = duration_sec / actual_n
        n_labels = min(10, actual_n)
        label_step = max(1, actual_n // n_labels)
        time_labels = [
            f"{int(i * sec_dur // 60)}:{int(i * sec_dur % 60):02d}"
            for i in range(0, actual_n, label_step)
        ]
        tick_pos = list(range(0, actual_n, label_step))

        # ── Build the figure ────────────────────────────────────────
        fig = plt.figure(figsize=(max(7, actual_n * 0.35), 4.5))
        gs = fig.add_gridspec(2, 1, height_ratios=[1, 2.5], hspace=0.08)

        # Top panel: loudness profile
        ax0 = fig.add_subplot(gs[0])
        colors = plt.cm.plasma(rms_norm)
        ax0.bar(range(actual_n), rms_norm, width=0.9, color=colors, edgecolor="none")
        ax0.set_ylabel("Loudness", fontsize=9)
        ax0.set_xticks([])
        ax0.set_xlim(-0.5, actual_n - 0.5)
        ax0.spines["top"].set_visible(False)
        ax0.spines["right"].set_visible(False)
        ax0.tick_params(labelsize=7)
        ax0.set_title("Loudness over time", fontsize=9, pad=2)

        # Bottom panel: frequency band heatmap
        ax1 = fig.add_subplot(gs[1])
        _im = ax1.imshow(
            band_norm, aspect="auto", cmap="magma", interpolation="nearest"
        )
        ax1.set_yticks(range(len(_BAND_NAMES)))
        ax1.set_yticklabels(_BAND_NAMES, fontsize=8)
        ax1.set_xticks(tick_pos)
        ax1.set_xticklabels(time_labels, fontsize=8)
        ax1.set_xlabel("Time")
        ax1.set_xlim(-0.5, actual_n - 0.5)
        ax1.set_title("Frequency energy by band", fontsize=9, pad=2)

        fig.suptitle("Song energy timeline", fontsize=12, fontweight="bold")
        fig.subplots_adjust(top=0.92)
        fig.savefig(output_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return output_path
    except Exception:
        return None


def analyze(audio_path: str, output_dir: str | None = None) -> dict:
    """Run all audio analysis and return a dict of results.

    Args:
        audio_path: Path to an audio file.
        output_dir: If set, also saves a spectral map PNG here.

    Returns:
        Dict with keys ``bpm``, ``key``, optionally ``spectral_map``,
        ``section_desc``, and raw per-section data.
    """
    bpm = detect_bpm(audio_path)
    result: dict = {
        "bpm": bpm,
        "key": detect_key(audio_path),
        "time_signature": detect_time_signature(audio_path, bpm),
        "modulations": detect_modulations(audio_path),
    }

    if output_dir:
        map_path = str(Path(output_dir) / f"{Path(audio_path).stem}_spectral_map.png")
        result["spectral_map"] = generate_spectral_map(audio_path, map_path)

    # Per-section data (used by LLM describer)
    section_data = compute_section_data(audio_path)
    if section_data:
        result.update(section_data)

    # LLM section description (if OPENROUTER_API_KEY is set)
    try:
        from section_describer import describe_sections  # noqa: F811

        desc = describe_sections(result)
        if desc:
            bpm = result.get("bpm")
            if bpm:
                desc = _enrich_section_desc(desc, bpm)
            result["section_desc"] = desc
            # Also store structured data for table rendering
            parsed = _parse_section_desc(desc)
            if parsed:
                # Enrich each section with key (from modulations) and time signature
                ts = result.get("time_signature")
                mods = result.get("modulations")
                for s in parsed:
                    s["time_signature"] = ts
                    s["key"] = None
                    if mods:
                        mid = (
                            _time_to_seconds(s["start"]) + _time_to_seconds(s["end"])
                        ) / 2
                        for m in mods:
                            if m["start_sec"] <= mid < m["end_sec"]:
                                s["key"] = m["key"]
                                break
                    if s["key"] is None:
                        s["key"] = result.get("key")
                result["sections_parsed"] = parsed
    except Exception:
        pass

    return result
