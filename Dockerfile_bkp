FROM python:3.11-slim AS base

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application code
COPY healthcare_platform/ ./healthcare_platform/

# Health check endpoint (workers expose /health on port 8000)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Create non-root user and switch to it
RUN useradd -m -u 1000 worker && chown -R worker:worker /app
USER worker

# Run worker runner with domain filter via CMD
# Usage:
#   docker build -t maestro-worker .
#   docker run maestro-worker --domain revenue_cycle
#   docker run maestro-worker --topics billing-calculate-charges,identify-glosa
#   docker run maestro-worker --all
ENTRYPOINT ["python", "-m", "healthcare_platform.shared.runtime.worker_runner"]
CMD ["--all"]
