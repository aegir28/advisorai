# AdvisorAI backend image (Render free web service, or any container host). Synthetic data only.
#
#   docker build -f backend/Dockerfile -t advisorai-backend .          (context: the repository root)
#   docker run --rm -p 8000:8000 --env-file backend/.env advisorai-backend
#
# The context is the repository root because the image also carries the versioned workflow definitions
# (workflows/) and the model/agent registries (registry/). Secrets are never baked in: they arrive as environment variables at run time.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# Dependencies first (cached until the lockfile changes). EXACTLY what uv.lock pins; no dev tools.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/app ./app
RUN uv sync --locked --no-dev

FROM python:3.12-slim
RUN useradd --system --uid 10001 --no-create-home advisorai
WORKDIR /app
COPY --from=build /app /app
COPY workflows /workflows
COPY registry /registry
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ADVISORAI_WORKFLOWS_DIR=/workflows \
    ADVISORAI_AI_MODELS_FILE=/registry/models.yaml
USER advisorai
EXPOSE 8000
# Liveness only (no database call): a sleeping free-tier host should not be restarted by it.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"
# --proxy-headers so the audit log hashes the real client IP behind the host's proxy. Set
# FORWARDED_ALLOW_IPS to the proxy's address range, never "*" on an open network.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
