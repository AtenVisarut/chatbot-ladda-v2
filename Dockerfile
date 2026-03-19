FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run the application with gunicorn (multi-worker for concurrency)
# WEB_CONCURRENCY env var controls workers (default 8, adjustable from Railway without redeploy)
CMD gunicorn app.main:app -w ${WEB_CONCURRENCY:-8} -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8080} --timeout 120 --graceful-timeout 30
