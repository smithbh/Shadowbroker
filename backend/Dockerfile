FROM python:3.11-slim-bookworm

WORKDIR /app

# Install Node.js (for AIS WebSocket proxy) and curl (for network fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install UV for fast, reproducible Python dependency management
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"
# Install into system Python (no venv needed inside container)
ENV UV_PROJECT_ENVIRONMENT=/usr/local

# Copy workspace root files for UV resolution (build context is repo root)
COPY pyproject.toml /workspace/pyproject.toml
COPY uv.lock /workspace/uv.lock
COPY backend/pyproject.toml /workspace/backend/pyproject.toml

# Install Python dependencies using the lockfile
RUN cd /workspace/backend && uv sync --frozen --no-dev \
    && playwright install --with-deps chromium

# Copy backend source code
COPY backend/ .

# Install Node.js dependencies (ws module for AIS WebSocket proxy)
COPY backend/package*.json ./
RUN npm ci --omit=dev

# Clean up workspace scaffold
RUN rm -rf /workspace


# Create a non-root user for security
# Grant write access to /app so the auto-updater can extract files
# Pre-create /app/data so mounted volumes inherit correct ownership
RUN adduser --system --uid 1001 backenduser \
    && mkdir -p /app/data \
    && chown -R backenduser /app \
    && chmod -R u+w /app

# Switch to the non-root user
USER backenduser

# Expose port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "120"]
