# Kokoro TTS Service Dockerfile
# Builds a lightweight container for running Kokoro TTS HTTP service

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create models directory
RUN mkdir -p /app/models

# Download Kokoro models (v0.19)
# Note: You may need to manually download these files if the URLs change
RUN wget -O /app/models/kokoro-v0_19.onnx \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx || \
    echo "WARNING: Could not download ONNX model. Please manually place kokoro-v0_19.onnx in /app/models/"

RUN wget -O /app/models/voices.bin \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin || \
    echo "WARNING: Could not download voices file. Please manually place voices.bin in /app/models/"

# Copy service code
COPY kokoro_service.py .

# Create temp directory for audio files
RUN mkdir -p /tmp/kokoro-audio

# Expose port
EXPOSE 8089

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8089/health')" || exit 1

# Run the service
CMD ["python", "-m", "uvicorn", "kokoro_service:app", "--host", "0.0.0.0", "--port", "8089"]
