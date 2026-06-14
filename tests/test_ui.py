"""Tests for de-drum UI helpers."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from ui import _fmt_section_desc  # noqa: E402


# ---------------------------------------------------------------------------
# _fmt_section_desc
# ---------------------------------------------------------------------------


class TestFmtSectionDesc:
    """Tests for ``_fmt_section_desc`` — formatting the LLM section
    description into Markdown for the Gradio UI."""

    def test_none_returns_empty(self) -> None:
        """``None`` input produces an empty string."""
        assert _fmt_section_desc(None) == ""

    def test_empty_string_returns_empty(self) -> None:
        """Empty string input produces an empty string."""
        assert _fmt_section_desc("") == ""

    def test_whitespace_only_returns_empty(self) -> None:
        """Whitespace-only input is stripped to empty."""
        assert _fmt_section_desc("   \n  \n  ") == ""

    def test_single_section_line(self) -> None:
        """A single section line gets a header prepended."""
        raw = "0:00-0:12 | Intro | Drum groove"
        result = _fmt_section_desc(raw)
        assert result.startswith("💬 **Section description**")
        assert "0:00-0:12 | Intro | Drum groove" in result

    def test_multi_line_without_header(self) -> None:
        """Multiple section lines without a preceding header get a header."""
        raw = (
            "0:00-0:12 | Intro | Quiet\n"
            "0:12-0:24 | Verse | Vocal enters"
        )
        result = _fmt_section_desc(raw)
        assert result.startswith("💬 **Section description**")
        assert "0:00-0:12 | Intro | Quiet" in result
        assert "0:12-0:24 | Verse | Vocal enters" in result

    def test_multi_line_with_existing_header(self) -> None:
        """When the LLM provides its own intro text, it is preserved
        after the UI header."""
        raw = (
            "Here's the likely structure:\n\n"
            "**0:00-0:12** | **Intro** | Quiet"
        )
        result = _fmt_section_desc(raw)
        assert result.startswith("💬 **Section description**")
        assert "likely structure" in result
        assert "0:00-0:12" in result

    def test_trailing_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace is removed from the input."""
        result = _fmt_section_desc("  line one\n  line two  ")
        assert result == "💬 **Section description**\n\nline one\n  line two"

    def test_survives_bold_markdown(self) -> None:
        """Bold markdown syntax in the LLM output is preserved."""
        raw = "**0:00-0:12** | **Intro** | Quiet / breakdown"
        result = _fmt_section_desc(raw)
        assert "**0:00-0:12**" in result
        assert "**Intro**" in result
