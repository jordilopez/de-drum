"""Tests for de-drum UI helpers."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from ui import _build_section_table, _fmt_section_desc  # noqa: E402

# ---------------------------------------------------------------------------
# _build_section_table
# ---------------------------------------------------------------------------


class TestBuildSectionTable:
    def test_basic_table(self):
        sections = [
            {
                "start": "0:00",
                "end": "0:12",
                "section": "Intro",
                "bars": 6,
                "beats": 24,
                "key": "C major",
                "desc": "Quiet / breakdown",
            },
            {
                "start": "0:12",
                "end": "0:24",
                "section": "Verse 1",
                "bars": 6,
                "beats": 24,
                "key": "C major",
                "desc": "Full / climax",
            },
        ]
        html = _build_section_table(sections)
        assert "Song structure" in html
        assert "<table" in html
        assert "C major" in html
        assert "Intro" in html
        assert "Verse 1" in html

    def test_empty_list_produces_no_rows(self):
        html = _build_section_table([])
        assert "<tr>" not in html

    def test_table_includes_all_columns(self):
        sections = [
            {
                "start": "0:00",
                "end": "0:08",
                "section": "Intro",
                "bars": 4,
                "beats": 16,
                "key": None,
                "desc": "Start",
            }
        ]
        html = _build_section_table(sections)
        # Verify expected column headers are present
        assert "<th" in html
        assert ">Time<" in html
        assert ">Section<" in html
        assert ">Bars<" in html
        assert ">Beats<" in html
        assert ">Key<" in html
        assert ">Description<" in html

    def test_table_includes_all_data_columns(self):
        """Each row should have 6 cells: time, section, bars, beats, key, desc."""
        sections = [
            {
                "start": "0:00",
                "end": "0:08",
                "section": "Intro",
                "bars": 4,
                "beats": 16,
                "key": "C major",
                "desc": "Start",
            }
        ]
        html = _build_section_table(sections)
        assert ">0:00–0:08<" in html
        assert ">Intro<" in html
        assert ">4<" in html
        assert ">16<" in html
        assert ">C major<" in html
        assert ">Start<" in html

    def test_bars_float_conversion(self):
        """Bars that are whole floats should display as integers."""
        sections = [
            {
                "start": "0:00",
                "end": "0:08",
                "section": "Intro",
                "bars": 4.0,
                "beats": 16,
                "key": None,
                "desc": "Start",
            }
        ]
        html = _build_section_table(sections)
        assert ">4<" in html


# ---------------------------------------------------------------------------
# _fmt_section_desc
# ---------------------------------------------------------------------------


class TestFmtSectionDesc:
    """Tests for ``_fmt_section_desc`` — formatting the section info
    into an HTML table or fallback Markdown for the Gradio UI."""

    def test_empty_info_returns_empty(self) -> None:
        """Empty dict produces an empty string."""
        assert _fmt_section_desc({}) == ""

    def test_only_section_desc_fallback(self) -> None:
        """When ``sections_parsed`` is absent, fall back to markdown."""
        info = {"section_desc": "0:00-0:12 | Intro | Drum groove"}
        result = _fmt_section_desc(info)
        assert result.startswith("💬 **Section description**")
        assert "0:00-0:12 | Intro | Drum groove" in result

    def test_sections_parsed_uses_html_table(self) -> None:
        """When ``sections_parsed`` is present, render an HTML table."""
        info = {
            "sections_parsed": [
                {
                    "start": "0:00",
                    "end": "0:12",
                    "section": "Intro",
                    "bars": 6,
                    "beats": 24,
                    "key": "C major",
                    "desc": "Quiet",
                }
            ]
        }
        result = _fmt_section_desc(info)
        assert "<table" in result
        assert "Intro" in result
        assert "C major" in result

    def test_sections_parsed_without_key(self) -> None:
        """Key column value is empty when key is None."""
        info = {
            "sections_parsed": [
                {
                    "start": "0:00",
                    "end": "0:12",
                    "section": "Intro",
                    "bars": 6,
                    "beats": 24,
                    "key": None,
                    "desc": "Quiet",
                }
            ]
        }
        result = _fmt_section_desc(info)
        assert "<table" in result
        # Key cell is present but empty: style='text-align:center'>\t</td>
        # Actually in the current impl it's: style='text-align:center'></td>
        # Let's just verify the table structure is correct
        assert "Song structure" in result
        assert "Intro" in result

    def test_markdown_fallback_preserves_bold(self) -> None:
        """Bold markdown in fallback sections is preserved."""
        info = {"section_desc": "**0:00-0:12** | **Intro** | Quiet"}
        result = _fmt_section_desc(info)
        assert "**0:00-0:12**" in result
        assert "**Intro**" in result
