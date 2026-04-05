# Tsushin Backend

FastAPI backend for the Tsushin multi-tenant agentic messaging framework.

## Requirements Files

The backend splits its Python dependencies into tiered files:

| File | Purpose | Installed in Docker? |
|------|---------|---------------------|
| `requirements-base.txt` | Core framework (FastAPI, SQLAlchemy, Pydantic, security) | Yes (always) |
| `requirements-app.txt` | AI providers, channel integrations, Playwright, docker SDK | Yes (always) |
| `requirements-optional.txt` | Kubernetes client, GCP secret manager, optional vector DB clients | Yes (if `INSTALL_OPTIONAL_DEPS=true`) |
| `requirements-phase4.txt` | `chromadb`, `sentence-transformers` (CPU torch installed separately) | Yes (always) |
| **`requirements-dev.txt`** | **`pytest`, `pytest-asyncio`, `pytest-cov` — NOT installed in production image** | **No** |

### Local development

Install app + dev dependencies on the host:

```bash
python -m venv venv && source venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch
pip install -r backend/requirements-base.txt \
            -r backend/requirements-app.txt \
            -r backend/requirements-phase4.txt \
            -r backend/requirements-dev.txt

# Run tests
pytest backend/tests -q
```

> **Note:** Tests run on the host (or in a purpose-built dev container). `docker exec tsushin-backend pytest` will fail because `requirements-dev.txt` is intentionally NOT installed in the production image.

## Docker Build Flags

The backend Dockerfile exposes three ARG flags to control image size:

| ARG | Default | What it gates | Size impact |
|-----|---------|--------------|-------------|
| `INSTALL_OPTIONAL_DEPS` | `true` | `requirements-optional.txt` (k8s, GCP, vector DBs) | ~100-200 MB |
| `INSTALL_PLAYWRIGHT` | `true` | Chromium binary + system libs (`libnss3`, `libatk*`, etc.) | ~1.1 GB + ~120 MB |
| `INSTALL_FFMPEG` | `true` | `ffmpeg` binary (required by Kokoro TTS for WAV→Opus) | ~250 MB |

### Default build (backwards-compatible, full featured)

```bash
cd /path/to/tsushin
docker-compose build --no-cache backend
docker-compose up -d backend
```

### Lean build (no browser automation, no TTS)

Produces a ~2.79 GB image (vs ~4.84 GB default) by skipping Playwright/Chromium and ffmpeg. Suitable for deployments that don't use browser-automation skills or Kokoro TTS.

```bash
docker build \
  --build-arg INSTALL_PLAYWRIGHT=false \
  --build-arg INSTALL_FFMPEG=false \
  -t tsushin-backend:lean \
  backend/
```

Lean-image caveats:
- `/tool browse ...` and any Playwright-backed skill will fail at runtime with `browser not installed`.
- Kokoro TTS provider will raise on WAV→Opus conversion (OpenAI TTS and ElevenLabs are unaffected).

## CPU-only PyTorch

`sentence-transformers` pulls `torch` as a dependency. The default PyPI `torch` wheel bundles ~4.3 GB of NVIDIA/CUDA/triton binaries — unused here because all embeddings run on CPU via `asyncio.to_thread()`.

The Dockerfile installs the CPU-only wheel **before** `requirements-phase4.txt` to skip the CUDA cascade:

```dockerfile
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch
RUN pip install -r requirements-phase4.txt
```

Verify with:

```bash
docker exec tsushin-backend pip list | grep -iE "nvidia|cuda|torch"
# Expected: torch  2.11.0+cpu  (no nvidia-* packages)
```
