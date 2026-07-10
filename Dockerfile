# sideOut — run the Jump Lab pipeline in one command, no local Python needed.
#
#   docker build -t sideout .
#   docker run --rm -v "$PWD/samples:/data" sideout jump analyze /data/demo.mov --out /data/runs
#
FROM python:3.11-slim

# mediapipe's native libraries + video I/O need these at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv provides the Python package manager (copied from its official image).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Pose model downloads on first run to this cache (mount a volume to persist it).
ENV SIDEOUT_MODEL_DIR=/app/.model-cache

ENTRYPOINT ["uv", "run", "--no-sync", "sideout"]
CMD ["--help"]
