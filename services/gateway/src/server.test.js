/**
 * Tests for the de-drum API Gateway.
 *
 * Builds the Fastify app once (top-level await in ESM) and uses
 * ``inject()`` to simulate HTTP requests without opening a port.
 */
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import Fastify from "fastify";
import cors from "@fastify/cors";
import multipart from "@fastify/multipart";
import { describeSections } from "./describer.js";

/**
 * Build a minimal gateway app with routes for testing.
 *
 * Does NOT register @fastify/rate-limit to avoid test complexity.
 */
async function buildApp() {
  const app = Fastify({ logger: false });

  await app.register(cors, { origin: true });
  await app.register(multipart, {
    limits: { fileSize: 200 * 1024 * 1024 },
  });

  // Health
  app.get("/api/health", async () => {
    return { status: "ok", service: "gateway" };
  });

  // Separate URL (proxy stub)
  app.post("/api/separate/url", async (request, reply) => {
    const { url, model } = request.body || {};
    if (!url) {
      return reply.status(422).send({ error: "URL is required" });
    }
    return reply.status(200).send({ job_id: "mock-job-id-123" });
  });

  // File upload (tested via inject with minimal body)
  app.post("/api/separate/file", async (request, reply) => {
    const data = await request.file().catch(() => null);
    if (!data) {
      return reply.status(422).send({ error: "File is required" });
    }
    return reply.status(200).send({ job_id: "mock-job-id-456" });
  });

  // Describe sections
  app.post("/api/describe", async (request, reply) => {
    const analysis = request.body;
    if (!analysis?.sections?.length) {
      return reply.status(422).send({ error: "Analysis data with sections[] is required" });
    }
    try {
      const description = await describeSections(analysis);
      return reply.send({ description, bpm: analysis.bpm, key: analysis.key });
    } catch (err) {
      return reply.status(502).send({ error: "LLM service unavailable", detail: err.message });
    }
  });

  // Job status
  app.get("/api/jobs/:id", async (request, reply) => {
    const { id } = request.params;
    if (id === "not-found") {
      return reply.status(404).send({ detail: "Job not found" });
    }
    return reply.status(200).send({
      id,
      status: "done",
      type: "url",
      model: "htdemucs",
      files: { "song_drums.mp3": "/output/song/song_drums.mp3" },
    });
  });

  return app;
}

// Build app once (top-level await is valid in ESM)
const app = await buildApp();

// ─── Tests ─────────────────────────────────────────────────────────

describe("Gateway API", () => {
  it("GET /api/health returns 200", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/health",
    });
    assert.equal(res.statusCode, 200);
    assert.deepEqual(res.json(), { status: "ok", service: "gateway" });
  });

  it("POST /api/separate/url rejects empty body", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/separate/url",
      payload: {},
    });
    assert.equal(res.statusCode, 422);
    assert(res.json().error);
  });

  it("POST /api/separate/url rejects missing URL", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/separate/url",
      payload: { model: "htdemucs" },
    });
    assert.equal(res.statusCode, 422);
  });

  it("POST /api/separate/url accepts valid payload", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/separate/url",
      payload: { url: "https://youtube.com/watch?v=test", model: "htdemucs_ft" },
    });
    assert.equal(res.statusCode, 200);
    const body = res.json();
    assert.equal(body.job_id, "mock-job-id-123");
  });

  it("GET /api/jobs/:id returns job object", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/jobs/abc123",
    });
    assert.equal(res.statusCode, 200);
    const body = res.json();
    assert.equal(body.id, "abc123");
    assert.equal(body.status, "done");
  });

  it("GET /api/jobs/:id returns 404 for unknown job", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/jobs/not-found",
    });
    assert.equal(res.statusCode, 404);
  });

  it("POST /api/separate/file rejects non-multipart content type", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/separate/file",
      payload: "",
      headers: { "content-type": "text/plain" },
    });
    assert.equal(res.statusCode, 422);
  });

  // ── Describe endpoint ───────────────────────────────────────────

  it("POST /api/describe rejects missing sections", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/describe",
      payload: { bpm: 120, key: "C major" },
    });
    assert.equal(res.statusCode, 422);
  });

  it("POST /api/describe works with valid analysis", async () => {
    const analysis = {
      bpm: 120,
      key: "C major",
      duration_sec: 240,
      sections: [
        { loudness: 0.2, bands: [0.3, 0.2, 0.1, 0.4, 0.5, 0.3, 0.1] },
        { loudness: 0.8, bands: [0.9, 0.7, 0.6, 0.8, 0.7, 0.5, 0.3] },
      ],
    };
    const res = await app.inject({
      method: "POST",
      url: "/api/describe",
      payload: analysis,
    });
    assert.equal(res.statusCode, 200);
    const body = res.json();
    // Without OPENROUTER_API_KEY → null; with key → a string
    if (process.env.OPENROUTER_API_KEY) {
      assert(typeof body.description === "string" && body.description.length > 0);
    } else {
      assert.equal(body.description, null);
    }
    assert.equal(body.bpm, 120);
    assert.equal(body.key, "C major");
  });

  // ── Describer module unit tests ─────────────────────────────────

  it("describeSections returns description or null depending on API key", async () => {
    const result = await describeSections({
      bpm: 128,
      key: "A minor",
      sections: [{ loudness: 0.5, bands: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7] }],
    });
    if (process.env.OPENROUTER_API_KEY) {
      assert(typeof result === "string" && result.length > 0);
    } else {
      assert.equal(result, null);
    }
  });

  it("describeSections returns null for empty sections", async () => {
    const result = await describeSections({ bpm: 120, sections: [] });
    assert.equal(result, null);
  });
});
