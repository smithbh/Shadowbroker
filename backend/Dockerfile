FROM python:3.10-slim-bookworm

WORKDIR /app

# Install Node.js (for AIS WebSocket proxy) and curl (for network fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install UV for Python dependency management
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"
# Set environment variable for UV to install dependencies in the system Python environment
# By default UV creates a new venv and installs dependencies there
ENV UV_PROJECT_ENVIRONMENT=/usr/local

# Copy pyproject.toml from root for dependency management
COPY pyproject.toml .
# Copy lock file for reproducible builds
COPY uv.lock .
# Install Python dependencies using UV (this will use the lock file for reproducibility)
RUN uv sync --frozen
RUN uv run playwright install --with-deps chromium

# Install Node.js dependencies (ws module for AIS WebSocket proxy)
# Copy manifests first so this layer is cached unless deps change
COPY backend/package*.json ./
RUN npm ci --omit=dev

# Copy source code
COPY backend/ .
# Create a non-root user for security
# Grant write access to /app so the auto-updater can extract files
RUN adduser --system --uid 1001 backenduser \
    && chown -R backenduser /app \
    && chmod -R u+w /app

# Switch to the non-root user
USER backenduser

# Expose port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
