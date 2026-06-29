FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim 

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

COPY job_agent ./job_agent/

ENTRYPOINT ["uv","run","job-agent"]    