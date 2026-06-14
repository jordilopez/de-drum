# de-drum 🥁 — Docker image
#
# Build:   docker build -t de-drum .
# Run:     docker run --rm -p 7860:7860 -v ./output:/app/output -v ./cache:/cache de-drum
# GPU:     docker run --rm --gpus all -p 7860:7860 -v ./output:/app/output -v ./cache:/cache de-drum

FROM python:3.13-slim-bookworm AS builder

# Keep package lists small
RUN rm -f /etc/apt/apt.conf.d/docker-clean; echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    yt-dlp \
    && apt-get clean

# ── Runtime stage ──────────────────────────────────────────────────
FROM python:3.13-slim-bookworm

# Copy ffmpeg & yt-dlp from builder (avoids keeping apt cache in final image)
COPY --from=builder /usr/bin/ffmpeg /usr/bin/ffmpeg
COPY --from=builder /usr/bin/ffprobe /usr/bin/ffprobe
COPY --from=builder /usr/bin/yt-dlp /usr/bin/yt-dlp

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY pyproject.toml .

# Optional: OpenRouter API key (mount at runtime via -e or .env)
ENV OPENROUTER_API_KEY=""

# Model cache directories — mount a volume at /cache to persist
ENV TORCH_HOME=/cache/torch
ENV DEMUCS_CACHE=/cache/demucs
ENV XDG_CACHE_HOME=/cache/xdg

# Create cache directory for non-root users
RUN mkdir -p /cache && chmod 777 /cache

# Gradio default port
EXPOSE 7860

# Health check — Gradio serves a /healthz endpoint on 7860
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/healthz')" || exit 1

ENTRYPOINT ["python3", "src/ui.py"]
