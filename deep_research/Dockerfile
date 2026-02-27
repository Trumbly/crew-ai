FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (without the project itself, for caching)
RUN uv sync --frozen --no-install-project

# Copy the rest of the project
COPY . .

# Install the project in editable mode
RUN uv sync --frozen

# Create output directory
RUN mkdir -p output

# orchestrate.py lives at project root and is imported by api.py
ENV PYTHONPATH=/app

EXPOSE ${PORT}

CMD ["sh", "-c", "uv run uvicorn deep_research.api:app --host 0.0.0.0 --port ${PORT}"]
