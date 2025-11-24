# Use slim Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies (no cache)
RUN pip install --no-cache-dir -r requirements.txt

# Copy only necessary files
COPY app/ ./app/
COPY templates/ ./templates/

# Download E5 model during build
RUN python -c "from sentence_transformers import SentenceTransformer; \
    print('Downloading E5 model...'); \
    model = SentenceTransformer('intfloat/multilingual-e5-base'); \
    print('E5 model cached!')"

# Clean up to reduce image size
RUN find /usr/local/lib/python3.11 -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.11 -type f -name '*.pyc' -delete && \
    find /root/.cache -type f -delete 2>/dev/null || true && \
    apt-get purge -y gcc g++ && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Expose port
EXPOSE 8000

# Health check (use httpx instead of requests - already installed)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/', timeout=5)"

# Start command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
