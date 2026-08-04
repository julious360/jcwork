FROM python:3.12-slim

# ffmpeg is required by the video stitcher; without it longer-form video ads
# cannot be assembled from vendor segments.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency layer first so code changes do not invalidate the install cache.
COPY pyproject.toml README.md ./
COPY agent/ ./agent/
RUN pip install --upgrade pip && pip install .

COPY migrations/ ./migrations/

# Never run as root.
RUN useradd --create-home --uid 10001 adagent && chown -R adagent:adagent /app
USER adagent

# Default to the worker; railway.json overrides this for the scheduler service.
CMD ["adagent", "worker"]
