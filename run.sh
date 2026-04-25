#!/bin/bash
# Whisper Local - Start Web UI
# Usage: ./run.sh [port]

PORT=${1:-8080}

echo "🎙️ Starting Whisper Local..."

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install dependencies if needed
pip install -q flask

# Check Ollama
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "⚠️ Ollama not running. Starting..."
    brew services start ollama 2>/dev/null || echo "Please run: brew services start ollama"
fi

# Check whisper.cpp model
if [ ! -f "whisper.cpp/models/ggml-small.bin" ]; then
    echo "Downloading whisper small model..."
    cd whisper.cpp
    bash ./models/download-ggml-model.sh small
    cd ..
fi

echo "🚀 Starting web interface on port $PORT..."
python src/webui.py $PORT 2>&1 | head -20