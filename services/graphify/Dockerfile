FROM python:3.12-slim

WORKDIR /app

# git: clone target repos. ffmpeg: faster-whisper audio/video extraction.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY app/ app/

# Pre-bake the Whisper model into the image: the dev VM has no public IP and
# cannot reach HuggingFace at runtime. Pin the model so first video extraction
# does not attempt a (failing) network download. faster-whisper caches under
# HF_HOME; we set it to a baked-in path.
ENV HF_HOME=/opt/whisper-cache
ENV GRAPHIFY_OUT_DIR=/graphify-out

EXPOSE 8012

# Default command runs the API. The worker compose service overrides this with
# `python -m app.worker`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012"]
