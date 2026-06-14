"""Audio analysis: BPM, musical key, and spectral density section map."""

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
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
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
        corr_major = np.array([
            np.correlate(chroma_mean, np.roll(_MAJOR_PROFILE, i))
            for i in range(12)
        ])
        corr_minor = np.array([
            np.correlate(chroma_mean, np.roll(_MINOR_PROFILE, i))
            for i in range(12)
        ])

        best_idx = int(np.argmax(np.concatenate([corr_major, corr_minor])))
        if best_idx < 12:
            return f"{_NOTE_NAMES[best_idx]} major"
        else:
            return f"{_NOTE_NAMES[best_idx - 12]} minor"
    except Exception:
        return None


# ── Frequency bands (Hz) that musicians care about ─────────────────
_BAND_DEFS = [
    ("Sub",      20,   60),
    ("Bass",     60,  250),
    ("Low-Mid", 250,  500),
    ("Mid",     500, 2000),
    ("High-Mid",2000, 4000),
    ("Presence",4000, 8000),
    ("Air",    8000, 16000),
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
        _im = ax1.imshow(band_norm, aspect="auto", cmap="magma", interpolation="nearest")
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
    result: dict = {
        "bpm": detect_bpm(audio_path),
        "key": detect_key(audio_path),
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
            result["section_desc"] = desc
    except Exception:
        pass

    return result
