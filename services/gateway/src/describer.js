/**
 * de-drum Section Describer — LLM-powered song structure analysis.
 *
 * Calls DeepSeek via OpenRouter to describe each section of a song
 * based on per-section energy data (loudness + 7 frequency bands).
 *
 * This is a direct port of ``src/section_describer.py`` to JavaScript,
 * allowing the gateway (and future Cloudflare Workers) to enrich
 * analysis data without round-tripping through the Python backend.
 *
 * @module describer
 */

// ─── Constants ────────────────────────────────────────────────────

/** OpenRouter API endpoint. */
const API_URL = "https://openrouter.ai/api/v1/chat/completions";

/** Cheap & capable model for section description. */
const MODEL = "deepseek/deepseek-chat";

/**
 * Request timeout in milliseconds.
 * OpenRouter usually responds within 5-10 s for this small prompt.
 */
const TIMEOUT_MS = 30_000;

// ─── Helpers ──────────────────────────────────────────────────────

/**
 * Format seconds to a ``M:SS`` timestamp string.
 *
 * @param {number} totalSeconds
 * @returns {string} e.g. ``"3:45"``
 */
function fmtTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

// ─── Prompt builder ──────────────────────────────────────────────

/**
 * Build the prompt sent to the LLM from per-section analysis data.
 *
 * @param {Object} analysis — dict with ``bpm``, ``key``,
 *   ``duration_sec``, and ``sections[]`` (each section has
 *   ``loudness`` and ``bands[7]``).
 * @returns {string} The formatted prompt.
 */
function buildPrompt(analysis) {
  const bpm = analysis.bpm ?? "—";
  const key = analysis.key ?? "—";
  const duration = analysis.duration_sec ?? 0;
  const sections = analysis.sections ?? [];

  const lines = [
    "You are a music producer analysing a song arrangement.",
    "Below is the per-section energy analysis.",
    "Describe the likely structure section by section (e.g. intro, verse,",
    "chorus, bridge, solo, outro) and what each section adds or removes.",
    "Be concise — one short line per section.",
    "If a section has low energy in all bands, call it 'quiet / breakdown'.",
    "If all bands are high, call it 'full / climax'.",
    "",
    `BPM: ${bpm}`,
    `Key: ${key}`,
    `Duration: ${fmtTime(duration)}`,
    `Sections: ${sections.length}`,
    "",
    "Columns: loudness(0-1) | Sub | Bass | Low-Mid | Mid | High-Mid | Presence | Air",
    "",
  ];

  for (let i = 0; i < sections.length; i++) {
    const s = sections[i];
    const loudness = s.loudness ?? 0;
    const bands = s.bands ?? [];
    const bandStr = bands.map((b) => b.toFixed(2)).join(" ");
    lines.push(`  Section ${i + 1}: loudness=${loudness.toFixed(2)} | ${bandStr}`);
  }

  lines.push(
    "",
    'Now describe each section briefly. Format as:',
    '0:00-0:12 | Intro | Drum groove, low energy',
    '0:12-0:45 | Verse | Vocals enter, bass drops in',
    "...",
  );

  return lines.join("\n");
}

// ─── API call ─────────────────────────────────────────────────────

/**
 * Call OpenRouter's chat-completion endpoint and return the assistant's
 * reply text.
 *
 * @param {string} prompt — The formatted prompt from {@link buildPrompt}.
 * @returns {Promise<string|null>} The generated description, or ``null``
 *   if the API key is missing or the request fails.
 */
async function callAPI(prompt) {
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return null;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        messages: [{ role: "user", content: prompt }],
        max_tokens: 1024,
        temperature: 0.3,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    return data.choices?.[0]?.message?.content ?? null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Public API ───────────────────────────────────────────────────

/**
 * Analyse per-section energy data with DeepSeek and return a
 * section-by-section description of the song.
 *
 * @param {Object} analysis — analysis data from the backend
 *   (expects ``bpm``, ``key``, ``duration_sec``, ``sections[]``).
 * @returns {Promise<string|null>} Multi-line description string, or
 *   ``null`` if the API key is not set, the analysis has no section
 *   data, or the API call fails.
 */
export async function describeSections(analysis) {
  if (!process.env.OPENROUTER_API_KEY) {
    return null;
  }

  if (!analysis?.sections?.length) {
    return null;
  }

  const prompt = buildPrompt(analysis);
  return callAPI(prompt);
}
