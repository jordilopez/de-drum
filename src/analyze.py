"""Audio analysis: detect BPM (tempo) and musical key."""

import librosa
import numpy as np

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


def analyze(audio_path: str) -> dict:
    """Run all audio analysis and return a dict of results.

    Args:
        audio_path: Path to an audio file.

    Returns:
        Dict with keys ``bpm`` (float | None) and ``key`` (str | None).
    """
    return {
        "bpm": detect_bpm(audio_path),
        "key": detect_key(audio_path),
    }
