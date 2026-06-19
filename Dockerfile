FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema (áudio, crypto)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Código do backend
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY .env.example ./.env.example

# Criar dirs de dados
RUN mkdir -p backend/data/tts backend/data/chroma backend/logs backend/memory

# Variáveis de ambiente padrão (sobrescritas pelo docker-compose ou .env)
ENV JARVIS_HOST=0.0.0.0
ENV JARVIS_PORT=8000
ENV JARVIS_LOG_LEVEL=INFO
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:8000/ping || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
