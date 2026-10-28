# Runs the journal's MCP server (stdio). Used by Glama to check that the server
# starts and lists its tools; MT5 sync is a no-op inside the container.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    TZ=UTC \
    TJ_DATA_DIR=/app/data

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-sync", "tj", "mcp"]
