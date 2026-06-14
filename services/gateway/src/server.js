/**
 * de-drum API Gateway — Fastify proxy between frontend and backend.
 *
 * Routes:
 *   POST  /api/separate/url        →  backend POST /backend/separate/url
 *   POST  /api/separate/file       →  backend POST /backend/separate/file
 *   GET   /api/jobs/:id             →  backend GET  /backend/jobs/:id
 *   GET   /api/jobs/:id/download/:filename → stream from backend
 */

import Fastify from "fastify";
import cors from "@fastify/cors";
import multipart from "@fastify/multipart";
import rateLimit from "@fastify/rate-limit";
import { Readable } from "node:stream";

// ─── Config ────────────────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || "3000", 10);
const HOST = process.env.HOST || "0.0.0.0";
const BACKEND_URL = process.env.BACKEND_URL || "http://backend:8000";

// ─── Server ────────────────────────────────────────────────────────

const app = Fastify({ logger: true });

// ─── Plugins ───────────────────────────────────────────────────────

await app.register(cors, { origin: true });
await app.register(multipart, {
  limits: {
    fileSize: 200 * 1024 * 1024, // 200 MB
  },
});
await app.register(rateLimit, {
  max: 30, // requests per minute per IP
  timeWindow: "1 minute",
});

// TODO(future): Throttling per endpoint
//   - /api/separate/*  → quota baixa (cada request triga minuts, pocs users)
//   - /api/jobs/*      → quota alta (polling, necessari per UX)
//   - Afegir cua de jobs amb 429 Retry-After quan el backend estigui saturation
//   - Quota per IP o per API key si es vol multi-tenant
//
// TODO(future): Cloudflare Workers migration
//   - Gateway stateless → fàcil de portar a Worker
//   - Problema: límit de payload (100 MB Free, 500 MB Paid)
//   - Solució: upload directe a R2 amb presigned URL, Worker només
//     notifica al backend amb l'object key

// ─── Routes ────────────────────────────────────────────────────────

// ── Health ─────────────────────────────────────────────────────────

/**
 * Health-check endpoint.
 *
 * @returns {{ status: string, service: string }} Always returns a 200
 *   with ``{ status: "ok", service: "gateway" }``.
 */
app.get("/api/health", async (request, reply) => {
  return { status: "ok", service: "gateway" };
});

// ── Separate from URL ──────────────────────────────────────────────

/**
 * Submit a YouTube URL for separation.
 *
 * Accepts a JSON body with ``url`` and optional ``model``. Converts
 * the request to FormData and proxies it to the backend service.
 *
 * @param {string} request.body.url - YouTube URL to download and separate.
 * @param {string} [request.body.model=htdemucs] - Demucs model name.
 * @returns {{ job_id: string }} The created job identifier.
 * @throws {502} If the backend service is unreachable.
 */
app.post("/api/separate/url", async (request, reply) => {
  const { url, model } = request.body || {};

  if (!url) {
    return reply.status(422).send({ error: "URL is required" });
  }

  const backendUrl = `${BACKEND_URL}/backend/separate/url`;
  const formData = new FormData();
  formData.append("url", url);
  formData.append("model", model || "htdemucs");

  try {
    const response = await fetch(backendUrl, {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    return reply.status(response.status).send(data);
  } catch (err) {
    request.log.error({ err, backendUrl }, "Backend proxy failed");
    return reply.status(502).send({ error: "Backend unavailable", detail: err.message });
  }
});

// ── Separate from file upload ──────────────────────────────────────

/**
 * Upload an audio file for separation.
 *
 * Accepts a multipart/form-data request with a ``file`` field and
 * an optional ``model`` field. Streams the file to the backend
 * service for processing.
 *
 * @param {Object} request.file - Parsed multipart file (via @fastify/multipart).
 * @param {string} request.file.filename - Original uploaded filename.
 * @param {string} request.file.mimetype - MIME type of the uploaded file.
 * @param {import('stream').Readable} request.file.file - Readable stream of the file.
 * @param {Object} request.file.fields - Other form fields (e.g. ``model``).
 * @returns {{ job_id: string }} The created job identifier.
 * @throws {502} If the backend service is unreachable.
 */
app.post("/api/separate/file", async (request, reply) => {
  const data = await request.file();

  if (!data) {
    return reply.status(422).send({ error: "File is required" });
  }

  // Read the file stream into a buffer
  const chunks = [];
  for await (const chunk of data.file) {
    chunks.push(chunk);
  }
  const buffer = Buffer.concat(chunks);
  const filename = data.filename;
  const model = (data.fields.model?.value) || "htdemucs";

  // Forward to backend as multipart
  const backendUrl = `${BACKEND_URL}/backend/separate/file`;
  const formData = new FormData();
  const blob = new Blob([buffer], { type: data.mimetype || "audio/mpeg" });
  formData.append("file", blob, filename);
  formData.append("model", model);

  try {
    const response = await fetch(backendUrl, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    return reply.status(response.status).send(result);
  } catch (err) {
    request.log.error({ err, backendUrl }, "Backend proxy failed");
    return reply.status(502).send({ error: "Backend unavailable", detail: err.message });
  }
});

// ── Get job status ────────────────────────────────────────────────

/**
 * Poll the status of a separation job.
 *
 * Proxies the request to the backend. Returns the full job object
 * including status (``pending``, ``processing``, ``done``, ``error``),
 * model, and output file listing when complete.
 *
 * @param {string} request.params.id - Job identifier (12-char hex).
 * @returns {Object} The job object from the backend.
 * @throws {404} If the job does not exist.
 * @throws {502} If the backend service is unreachable.
 */
app.get("/api/jobs/:id", async (request, reply) => {
  const { id } = request.params;
  const backendUrl = `${BACKEND_URL}/backend/jobs/${id}`;

  try {
    const response = await fetch(backendUrl);
    const data = await response.json();
    return reply.status(response.status).send(data);
  } catch (err) {
    request.log.error({ err, backendUrl }, "Backend proxy failed");
    return reply.status(502).send({ error: "Backend unavailable", detail: err.message });
  }
});

// ── Download result file ──────────────────────────────────────────

/**
 * Download a result file from a completed job.
 *
 * Streams the file directly from the backend. The filename typically
 * follows the pattern ``<song>_drums.mp3`` or ``<song>_no_drums.mp3``.
 *
 * @param {string} request.params.id - Job identifier.
 * @param {string} request.params.filename - Name of the result file to download.
 * @returns {import('stream').Readable} The file content streamed from backend.
 * @throws {404} If the job or file does not exist.
 * @throws {400} If the job is not yet completed.
 * @throws {502} If the backend service is unreachable.
 */
app.get("/api/jobs/:id/download/:filename", async (request, reply) => {
  const { id, filename } = request.params;
  const backendUrl = `${BACKEND_URL}/backend/jobs/${id}/download/${filename}`;

  try {
    const response = await fetch(backendUrl);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return reply.status(response.status).send(errorData);
    }

    // Stream the file response back
    const contentType = response.headers.get("content-type") || "application/octet-stream";
    const contentDisposition = response.headers.get("content-disposition") || `attachment; filename="${filename}"`;

    reply.header("Content-Type", contentType);
    reply.header("Content-Disposition", contentDisposition);

    // Node 24+ fetch response.body is a Web ReadableStream
    const webStream = response.body;
    const nodeStream = Readable.fromWeb(webStream);
    return reply.send(nodeStream);
  } catch (err) {
    request.log.error({ err, backendUrl }, "Backend proxy failed");
    return reply.status(502).send({ error: "Backend unavailable", detail: err.message });
  }
});

// ── Start ──────────────────────────────────────────────────────────

/**
 * Start the Fastify server.
 *
 * Listens on the configured port and host. Terminates the process
 * with exit code 1 if the server fails to start.
 */
const start = async () => {
  try {
    await app.listen({ port: PORT, host: HOST });
    app.log.info(`Gateway listening on http://${HOST}:${PORT}`);
    app.log.info(`Backend URL: ${BACKEND_URL}`);
  } catch (err) {
    app.log.fatal(err);
    process.exit(1);
  }
};

start();
