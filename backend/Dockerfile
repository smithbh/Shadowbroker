FROM python:3.10-slim

WORKDIR /app

# Install Node.js (for AIS WebSocket proxy) and curl (for network fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

# Install Node.js dependencies (ws module for AIS WebSocket proxy)
# Copy manifests first so this layer is cached unless deps change
COPY package*.json ./
RUN npm ci --omit=dev

# Copy source code
COPY . .

# Create a non-root user for security
RUN adduser --system --uid 1001 backenduser \
    && chown -R backenduser /app

# Switch to the non-root user
USER backenduser

# Expose port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
