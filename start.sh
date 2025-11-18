#!/bin/bash

echo "=========================================="
echo "Starting LINE Plant Disease Detection Bot"
echo "=========================================="

# Download E5 model on first run (if not cached)
echo "Checking E5 model..."
python -c "from sentence_transformers import SentenceTransformer; print('Loading E5 model...'); model = SentenceTransformer('intfloat/multilingual-e5-base'); print('E5 model ready!')"

echo ""
echo "Starting FastAPI server..."
echo "=========================================="

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
