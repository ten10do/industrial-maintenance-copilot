# 工业设备运维工单 Copilot - 后端 API Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/

# Environment
ENV PYTHONPATH=/app
ENV APP_ENV=production
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV SEED_ON_STARTUP=false

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
