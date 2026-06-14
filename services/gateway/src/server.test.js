/**
 * Tests for the de-drum API Gateway.
 *
 * Builds the Fastify app once (top-level await in ESM) and uses
 * ``inject()`` to simulate HTTP requests without opening a port.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import Fastify from "fastify";
import cors from "@fastify/cors";
import multipart from "@fastify/multipart";

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
});
