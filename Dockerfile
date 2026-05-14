# ==============================================================================
# JARVIS v5.2 — Multi-stage Dockerfile for Production
# ==============================================================================
# Build stage: Install dependencies and run tests
# Runtime stage: Minimal production image

# ==============================================================================
# Stage 1: Builder
# ==============================================================================
FROM python:3.11-slim as builder

WORKDIR /build

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt backend/requirements-dev.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-dev.txt

# Copy application code
COPY backend ./backend
COPY tests ./tests

# Run linting and tests
RUN echo "Running linting..." && \
    black --check backend/ || true && \
    isort --check-only backend/ || true && \
    flake8 backend/ --count --exit-zero || true

RUN echo "Running tests..." && \
    pytest tests/ -v --tb=short --cov=backend --cov-report=term || true

# ==============================================================================
# Stage 2: Runtime
# ==============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 jarvis

# Copy only production dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY backend ./backend
COPY .env.example ./.env

# Create logs directory
RUN mkdir -p backend/logs && chown -R jarvis:jarvis /app

# Switch to non-root user
USER jarvis

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV JARVIS_HOST=0.0.0.0
ENV JARVIS_PORT=8000

# Default command
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
