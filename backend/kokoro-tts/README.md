# Kokoro TTS Service (Kokoro-FastAPI)

**Production-ready Text-to-Speech using Kokoro-82M model via Kokoro-FastAPI**

This directory contains Docker Compose configuration for running the [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) service, which provides an **OpenAI-compatible API** for the Kokoro TTS model.

## Why Kokoro-FastAPI?

- **OpenAI-Compatible**: Drop-in replacement for OpenAI TTS API
- **Pre-built Images**: No build required, instant deployment
- **Auto-downloads Models**: ~100MB models downloaded on first run
- **Zero Cost**: Completely free, no API keys needed
- **High Performance**: 35x-100x realtime on GPU, 2-3x on CPU
- **Advanced Features**: Voice mixing, streaming, word-level timestamps
- **Production Ready**: Health checks, monitoring endpoints, active development

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
cd backend/kokoro-tts

# Pull the latest image (optional, will pull on first up)
sudo docker pull ghcr.io/remsky/kokoro-fastapi-cpu:latest

# Start the service
sudo docker compose up -d

# View logs (first run downloads models, takes ~30-60s)
sudo docker compose logs -f kokoro-tts

# Stop the service
sudo docker compose down
```

### Option 2: Docker Run

```bash
# CPU version (no GPU required)
sudo docker run -d \
  --name kokoro-tts \
  -p 8880:8880 \
  -e API_LOG_LEVEL=INFO \
  --restart unless-stopped \
  ghcr.io/remsky/kokoro-fastapi-cpu:latest

# GPU version (requires NVIDIA Docker)
sudo docker run -d \
  --name kokoro-tts \
  --gpus all \
  -p 8880:8880 \
  -e API_LOG_LEVEL=INFO \
  --restart unless-stopped \
  ghcr.io/remsky/kokoro-fastapi-gpu:latest
```

## Verify Service is Running

```bash
# Check health
curl http://localhost:8880/docs

# You should see OpenAPI documentation page

# Check available voices
curl http://localhost:8880/v1/audio/voices

# Test TTS generation
curl -X POST http://localhost:8880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kokoro",
    "input": "Olá, tudo bem? Eu sou a Kokoro.",
    "voice": "af_bella",
    "response_format": "opus",
    "speed": 1.0
  }' \
  --output test.ogg

# Play the audio
ffplay test.ogg  # or vlc test.ogg
```

## API Endpoints

### `/v1/audio/speech` (OpenAI-Compatible TTS)

**Request:**
```json
{
  "model": "kokoro",
  "input": "Text to synthesize",
  "voice": "af_bella",
  "response_format": "opus",
  "speed": 1.0
}
```

**Response:** Audio bytes (direct stream)

**Supported Formats:**
- `opus` - WhatsApp-compatible (recommended)
- `mp3` - Universal compatibility
- `wav` - Uncompressed
- `flac` - Lossless
- `m4a` - Apple preferred
- `pcm` - Raw audio

### `/v1/audio/voices` (List Voices)

Returns all available voice profiles.

### `/web` (Web UI)

Interactive web interface for testing TTS at `http://localhost:8880/web`

### `/docs` (API Documentation)

OpenAPI documentation at `http://localhost:8880/docs`

## Available Voices

### Brazilian Portuguese (PT-BR) Voices 🇧🇷
- `pf_dora` - Female, warm and natural (recommended for PT-BR)
- `pm_alex` - Male, professional
- `pm_santa` - Male, alternative voice

### American English Voices
- `af_bella` - Female, warm and conversational
- `af_sarah` - Female, professional and clear
- `af_nicole` - Female, bright and energetic
- `af_sky` - Female, calm and soothing
- `am_adam` - Male, deep and authoritative
- `am_michael` - Male, friendly and casual

### British English Voices
- `bf_emma` - Female, warm
- `bf_isabella` - Female, professional
- `bm_george` - Male, deep
- `bm_lewis` - Male, professional

### Voice Mixing (Advanced)

Blend multiple voices with weights:
```json
{
  "voice": "af_bella(2)+af_sky(1)"  // 67% bella, 33% sky
}
```

## Advanced Features

### Streaming TTS

For real-time audio playback:
```python
import httpx

with httpx.stream(
    "POST",
    "http://localhost:8880/v1/audio/speech",
    json={"model": "kokoro", "input": text, "voice": "af_bella"}
) as response:
    for chunk in response.iter_bytes():
        # Play audio chunk in real-time
        pass
```

### Word-Level Timestamps

For accessibility features:
```bash
curl -X POST http://localhost:8880/dev/captioned_speech \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "voice": "af_bella"
  }'
```

Returns audio + JSON with word timestamps.

### Monitoring Endpoints

- `/debug/system` - CPU/Memory/GPU usage
- `/debug/threads` - Thread monitoring
- `/debug/storage` - Disk usage

## Integration with Tsushin

The Kokoro-FastAPI service is integrated into Tsushin via the `AudioTTSSkill`:

```python
# backend/agent/skills/audio_tts_skill.py
# Automatically uses Kokoro-FastAPI when provider="kokoro"

# For Brazilian Portuguese (PT-BR)
config = {
    "provider": "kokoro",
    "voice": "pf_dora",  # PT-BR female voice
    "speed": 1.0,
    "response_format": "opus"
}

# For English
config = {
    "provider": "kokoro",
    "voice": "af_bella",  # American English female voice
    "speed": 1.0,
    "response_format": "opus"
}
```

**Note:** Language is determined by voice selection (voice name prefix). The model uses the appropriate phonemization for each language automatically.

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo docker logs kokoro-tts

# Common issues:
# - Port 8880 already in use: Change port in docker-compose.yml
# - Models downloading: Wait 30-60s on first run
# - Permission denied: Ensure you're using sudo
```

### Audio Generation Fails

```bash
# Check service health
curl http://localhost:8880/docs

# Verify connectivity
curl -I http://localhost:8880/v1/audio/voices

# Check backend logs
tail -f ../../logs/tsushin.log | grep -E "(Kokoro|audio_tts)"
```

### Voice Not Available

```bash
# List all voices
curl http://localhost:8880/v1/audio/voices | jq .
```

### Slow Performance

**CPU Version:**
- Expected: 2-3x realtime (1s to generate 3s audio)
- Models loaded on first request (adds ~5s initial latency)

**GPU Version:**
- Expected: 35-100x realtime on RTX 4060Ti
- Requires NVIDIA Docker and GPU support

## Performance

| Hardware | Speed | Latency |
|----------|-------|---------|
| **CPU** (Intel i7) | 2-3x realtime | ~2-3s |
| **GPU** (RTX 4060Ti) | 35-100x realtime | ~0.5s |

**Memory Usage:**
- CPU version: ~500MB
- GPU version: ~2GB (includes model on GPU)

## Configuration

Environment variables (docker-compose.yml):

```yaml
environment:
  # Logging level
  - API_LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

  # Token chunking (advanced, optional)
  - TARGET_MIN_TOKENS=175
  - TARGET_MAX_TOKENS=250
  - ABSOLUTE_MAX_TOKENS=450
```

## Updates

To update to the latest version:

```bash
cd backend/kokoro-tts

# Pull latest image
sudo docker pull ghcr.io/remsky/kokoro-fastapi-cpu:latest

# Restart service
sudo docker compose down
sudo docker compose up -d
```

## Cost Comparison

| Provider | Cost per 1M chars | Quality | Deployment |
|----------|------------------|---------|------------|
| OpenAI tts-1 | $15 | Excellent | SaaS |
| OpenAI tts-1-hd | $30 | Excellent | SaaS |
| **Kokoro-FastAPI** | **$0 (FREE)** | **Very Good** | **Self-hosted** |

## Resources

- **Repository**: https://github.com/remsky/Kokoro-FastAPI
- **Docker Hub**: `ghcr.io/remsky/kokoro-fastapi-cpu:latest`
- **Kokoro Model**: https://github.com/hexgrad/Kokoro-82M
- **OpenAPI Docs**: http://localhost:8880/docs
- **Web UI**: http://localhost:8880/web

## License

Kokoro TTS is open source. See the [Kokoro-FastAPI repository](https://github.com/remsky/Kokoro-FastAPI) for license details.
