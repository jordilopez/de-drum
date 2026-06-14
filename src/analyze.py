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


def generate_spectral_map(
    audio_path: str,
    output_path: str,
    n_sections: int | None = None,
) -> str | None:
    """Generate a spectral density section map as a PNG image.

    The song is split into time sections (roughly one every 10 s).
    For each section the average mel spectrum is plotted, creating
    a grid whose columns are time and rows are frequency bands.

    Args:
        audio_path: Path to an audio file.
        output_path: Where to save the PNG.
        n_sections: Number of time sections (auto if None).

    Returns:
        Path to the saved PNG, or None on failure.
    """
    try:
        y, sr = librosa.load(audio_path, sr=None, duration=300)
        if len(y) < sr:
            return None

        duration_sec = len(y) / sr
        if n_sections is None:
            n_sections = max(8, min(48, int(duration_sec / 8)))

        # Mel spectrogram
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64, fmax=8000)
        mel_db = librosa.power_to_db(mel, ref=np.max)

        # Average into N time sections
        total_frames = mel_db.shape[1]
        frames_per_section = max(1, total_frames // n_sections)
        actual_n = min(n_sections, total_frames)

        sections = np.zeros((mel_db.shape[0], actual_n))
        for i in range(actual_n):
            start = i * frames_per_section
            end = start + frames_per_section if i < actual_n - 1 else total_frames
            sections[:, i] = np.mean(mel_db[:, start:end], axis=1)

        # Time labels
        sec_per_section = duration_sec / actual_n
        time_labels = [
            f"{int(i * sec_per_section // 60)}:{int(i * sec_per_section % 60):02d}"
            for i in range(0, actual_n, max(1, actual_n // 8))
        ]
        tick_positions = list(range(0, actual_n, max(1, actual_n // 8)))

        # Plot
        fig, ax = plt.subplots(figsize=(max(8, actual_n * 0.35), 5))
        img = ax.imshow(sections, aspect="auto", origin="lower", cmap="magma")
        ax.set_xlabel("Time section")
        ax.set_ylabel("Frequency band")
        ax.set_title("Spectral density per section")
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(time_labels, fontsize=8)
        cbar = plt.colorbar(img, ax=ax, label="dB")
        cbar.ax.tick_params(labelsize=8)

        fig.tight_layout()
        fig.savefig(output_path, dpi=100, bbox_inches="tight")
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
        Dict with keys ``bpm``, ``key``, and optionally ``spectral_map``.
    """
    result: dict = {
        "bpm": detect_bpm(audio_path),
        "key": detect_key(audio_path),
    }

    if output_dir:
        map_path = str(Path(output_dir) / f"{Path(audio_path).stem}_spectral_map.png")
        result["spectral_map"] = generate_spectral_map(audio_path, map_path)

    return result
