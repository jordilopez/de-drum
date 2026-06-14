"""Gradio web UI for de-drum — separate drums from audio in your browser."""
# ruff: noqa: I001 — sys.path.insert breaks standard import ordering

import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import gradio as gr

# Import core logic from the CLI module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from separate import download_audio, separate as _separate  # noqa: E402

# Suppress noisy TorchCodec warnings
warnings.filterwarnings("ignore", message=".*not fully supported by TorchCodec.*")
warnings.filterwarnings("ignore", message=".*not directly supported by TorchCodec.*")

OUTPUT_DIR = Path("output")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_output_files(song_stem: str) -> tuple[str, str]:
    """Return paths to drums and no_drums mp3, or empty strings if missing."""
    song_dir = OUTPUT_DIR / song_stem
    drums = song_dir / f"{song_stem}_drums.mp3"
    no_drums = song_dir / f"{song_stem}_no_drums.mp3"
    return (str(drums) if drums.exists() else "", str(no_drums) if no_drums.exists() else "")


def _as_file_update(path: str) -> dict:
    """Return a gr.File update — visible with value if path exists, hidden otherwise."""
    return gr.update(visible=bool(path), value=path if path else None)


# ---------------------------------------------------------------------------
# Processing functions
# ---------------------------------------------------------------------------


def process_url(url: str, model: str, keep_original: bool) -> tuple:
    """Process a YouTube URL.

    Returns (status_markdown, button_update, drums_file_update, no_drums_file_update).
    """
    if not url.strip():
        return "⚠️ Please enter a YouTube URL.", gr.update(interactive=True, value="🥁 Separate Drums"), gr.update(visible=False), gr.update(visible=False)

    tmp_dir = Path(tempfile.mkdtemp(prefix="dedrum_"))
    try:
        audio_path = download_audio(url, str(tmp_dir))
        _separate(str(audio_path), str(OUTPUT_DIR), model)

        drums_path, no_drums_path = _get_output_files(audio_path.stem)

        if keep_original:
            song_dir = OUTPUT_DIR / audio_path.stem
            song_dir.mkdir(parents=True, exist_ok=True)
            dst = song_dir / audio_path.name
            shutil.move(str(audio_path), str(dst))

        shutil.rmtree(tmp_dir, ignore_errors=True)
        return (
            "✅ **Done!** Click the files below to download.",
            gr.update(interactive=True, value="🥁 Separate Drums"),
            _as_file_update(drums_path),
            _as_file_update(no_drums_path),
        )
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return (
            f"❌ **Error:** {e}",
            gr.update(interactive=True, value="🥁 Separate Drums"),
            gr.update(visible=False),
            gr.update(visible=False),
        )


def process_file(file: Path, model: str) -> tuple:
    """Process a local audio file.

    Returns (status_markdown, button_update, drums_file_update, no_drums_file_update).
    """
    if file is None:
        return "⚠️ Please upload an audio file.", gr.update(interactive=True, value="🥁 Separate Drums"), gr.update(visible=False), gr.update(visible=False)

    file_path = Path(file)
    try:
        _separate(str(file_path), str(OUTPUT_DIR), model)
        drums_path, no_drums_path = _get_output_files(file_path.stem)

        return (
            "✅ **Done!** Click the files below to download.",
            gr.update(interactive=True, value="🥁 Separate Drums"),
            _as_file_update(drums_path),
            _as_file_update(no_drums_path),
        )
    except Exception as e:
        return (
            f"❌ **Error:** {e}",
            gr.update(interactive=True, value="🥁 Separate Drums"),
            gr.update(visible=False),
            gr.update(visible=False),
        )


# ---------------------------------------------------------------------------
# UI definition
# ---------------------------------------------------------------------------

MODEL_CHOICES = [
    "htdemucs",
    "htdemucs_ft",
    "htdemucs_6s",
    "hdemucs_mmi",
]

with gr.Blocks(title="de-drum 🥁") as demo:
    gr.Markdown("# 🥁 de-drum")
    gr.Markdown("Separate drums from any song — 100% local, zero cost.")

    # ── YouTube URL tab ──────────────────────────────────────────────

    with gr.Tab("🎬 YouTube URL"):
        url_input = gr.Textbox(
            label="YouTube URL",
            placeholder="https://youtube.com/watch?v=...",
        )
        with gr.Row():
            url_model = gr.Dropdown(
                choices=MODEL_CHOICES,
                value="htdemucs",
                label="Model",
            )
            url_keep = gr.Checkbox(
                label="Keep original audio",
                value=False,
            )
        url_btn = gr.Button("🥁 Separate Drums", variant="primary", size="lg")
        url_status = gr.Markdown("")
        with gr.Row():
            url_drums = gr.File(label="🥁 Drums", visible=False)
            url_no_drums = gr.File(label="🎵 No Drums", visible=False)

    # ── Upload File tab ──────────────────────────────────────────────

    with gr.Tab("📁 Upload File"):
        file_input = gr.File(
            label="Audio file",
            file_types=[".mp3", ".wav", ".flac", ".m4a", ".ogg"],
        )
        file_model = gr.Dropdown(
            choices=MODEL_CHOICES,
            value="htdemucs",
            label="Model",
        )
        file_btn = gr.Button("🥁 Separate Drums", variant="primary", size="lg")
        file_status = gr.Markdown("")
        with gr.Row():
            file_drums = gr.File(label="🥁 Drums", visible=False)
            file_no_drums = gr.File(label="🎵 No Drums", visible=False)

    # ── Event wiring ─────────────────────────────────────────────────

    def _start_processing(btn_label: str = "⏳ Processing...") -> dict:
        """Disable the button and show a spinner status."""
        return {
            url_btn: gr.update(interactive=False, value=btn_label),
            url_status: "⏳ **Processing…** this may take a while.",
            url_drums: gr.update(visible=False),
            url_no_drums: gr.update(visible=False),
        }

    def _start_file_processing() -> dict:
        return {
            file_btn: gr.update(interactive=False, value="⏳ Processing..."),
            file_status: "⏳ **Processing…** this may take a while.",
            file_drums: gr.update(visible=False),
            file_no_drums: gr.update(visible=False),
        }

    # URL tab chain: start → process → done (button state is handled inside process)
    url_btn.click(
        fn=_start_processing,
        outputs=[url_btn, url_status, url_drums, url_no_drums],
    ).then(
        fn=process_url,
        inputs=[url_input, url_model, url_keep],
        outputs=[url_status, url_btn, url_drums, url_no_drums],
        api_name="separate_url",
    )

    # File tab chain
    file_btn.click(
        fn=_start_file_processing,
        outputs=[file_btn, file_status, file_drums, file_no_drums],
    ).then(
        fn=process_file,
        inputs=[file_input, file_model],
        outputs=[file_status, file_btn, file_drums, file_no_drums],
        api_name="separate_file",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    demo.launch()
