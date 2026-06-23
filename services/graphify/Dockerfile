FROM python:3.12-slim

WORKDIR /app

# git: clone target repos. ffmpeg: faster-whisper audio/video extraction.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Whisper model name + cache location. The dev VM has no public-IP egress to
# HuggingFace, so we bake the weights into the image at build time (CI runners
# do have egress). Pin the model name so the baked weights match what graphify
# requests at runtime (graphify reads GRAPHIFY_WHISPER_MODEL, default "base").
ENV HF_HOME=/opt/whisper-cache
ENV GRAPHIFY_WHISPER_MODEL=base
ENV GRAPHIFY_OUT_DIR=/graphify-out

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Pre-download the Whisper "base" weights into HF_HOME so the first video/audio
# extraction on the no-egress VM does not attempt a (failing) network fetch.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

COPY app/ app/

EXPOSE 8012

# Default command runs the API. The worker compose service overrides this with
# `python -m app.worker`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012"]
