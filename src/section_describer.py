"""Describe song sections using an LLM via OpenRouter (DeepSeek).

Optional feature — only works if the ``OPENROUTER_API_KEY`` environment
variable is set. If missing, all functions gracefully return ``None``.
"""

import json
import os
from typing import Any
from urllib import request

_API_KEY_ENV = "OPENROUTER_API_KEY"
_MODEL = "deepseek/deepseek-chat"  # cheap & capable on OpenRouter
_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(analysis: dict[str, Any]) -> str:
    """Build a prompt from the per-section analysis data."""
    bpm = analysis.get("bpm", "—")
    key = analysis.get("key", "—")
    duration = analysis.get("duration_sec", 0)
    n_sections = len(analysis.get("sections", []))

    lines = [
        "You are a music producer analysing a song arrangement.",
        "Below is the per-section energy analysis.",
        "Describe the likely structure section by section (e.g. intro, verse,",
        "chorus, bridge, solo, outro) and what each section adds or removes.",
        "Be concise — one short line per section.",
        "If a section has low energy in all bands, call it 'quiet / breakdown'.",
        "If all bands are high, call it 'full / climax'.",
        "",
        f"BPM: {bpm}",
        f"Key: {key}",
        f"Duration: {duration // 60}:{duration % 60:02d}",
        f"Sections: {n_sections}",
        "",
        "Columns: loudness(0-1) | Sub | Bass | Low-Mid | Mid | High-Mid | Presence | Air",
        "",
    ]

    for i, sec in enumerate(analysis.get("sections", [])):
        loudness_val = sec.get("loudness", 0)
        bands = sec.get("bands", [])
        band_str = " ".join(f"{b:.2f}" for b in bands)
        lines.append(f"  Section {i + 1}: loudness={loudness_val:.2f} | {band_str}")

    lines.append(
        "\nNow describe each section briefly. Format as:\n"
        "0:00-0:12 | Intro | Drum groove, low energy\n"
        "0:12-0:45 | Verse | Vocals enter, bass drops in\n"
        "..."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------


def _call_api(prompt: str) -> str | None:
    """Call OpenRouter / DeepSeek and return the response text."""
    api_key = os.environ.get(_API_KEY_ENV)
    if not api_key:
        return None

    payload = json.dumps({
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.3,
    }).encode()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        req = request.Request(_URL, data=payload, headers=headers, method="POST")
        with request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def describe_sections(analysis: dict[str, Any]) -> str | None:
    """Analyse per-section energy data with DeepSeek and return a description.

    Args:
        analysis: Dict as returned by ``analyze()`` with section data.

    Returns:
        Multi-line string describing the song structure, or ``None`` if
        unavailable (no API key, network error, …).
    """
    if not os.environ.get(_API_KEY_ENV):
        return None

    if not analysis.get("sections"):
        return None

    prompt = _build_prompt(analysis)
    return _call_api(prompt)
