"""
Kokoro TTS Service
A FastAPI-based HTTP service for generating speech using Kokoro TTS.
Runs in Docker container, provides cost-free alternative to OpenAI TTS.
"""

import logging
import os
import tempfile
from typing import Optional, Literal
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import soundfile as sf
import numpy as np

# Import Kokoro TTS library
try:
    from kokoro_onnx import Kokoro
except ImportError:
    raise ImportError(
        "kokoro-onnx not installed. Install with: pip install kokoro-onnx"
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Kokoro TTS Service",
    description="Text-to-Speech service using Kokoro ONNX model",
    version="1.0.0"
)

# Global Kokoro instance (singleton)
kokoro_instance: Optional[Kokoro] = None

# Model paths
MODEL_DIR = Path("/app/models")
ONNX_MODEL_PATH = MODEL_DIR / "kokoro-v0_19.onnx"
VOICES_PATH = MODEL_DIR / "voices.bin"

# Supported voices
SUPPORTED_VOICES = {
    "af_bella", "af_sarah", "af_nicole", "af_sky",
    "am_adam", "am_michael", "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis"
}


class TTSRequest(BaseModel):
    """Request model for TTS generation"""
    text: str = Field(..., description="Text to synthesize", min_length=1, max_length=5000)
    voice: str = Field(default="af_bella", description="Voice profile to use")
    speed: float = Field(default=1.0, description="Speech speed", ge=0.5, le=2.0)
    language: str = Field(default="en", description="Language code (en, pt, es, ja)")
    format: Literal["wav", "ogg", "opus"] = Field(default="opus", description="Output format")


class TTSResponse(BaseModel):
    """Response model for TTS generation"""
    success: bool
    message: str
    audio_path: Optional[str] = None
    sample_rate: Optional[int] = None
    duration_seconds: Optional[float] = None
    character_count: int
    voice_used: str


def get_kokoro() -> Kokoro:
    """Get or initialize Kokoro TTS instance (singleton)"""
    global kokoro_instance

    if kokoro_instance is None:
        logger.info("Initializing Kokoro TTS model...")

        # Check if model files exist
        if not ONNX_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"ONNX model not found at {ONNX_MODEL_PATH}. "
                "Please download from Kokoro TTS repository."
            )

        if not VOICES_PATH.exists():
            raise FileNotFoundError(
                f"Voices file not found at {VOICES_PATH}. "
                "Please download from Kokoro TTS repository."
            )

        try:
            kokoro_instance = Kokoro(
                str(ONNX_MODEL_PATH),
                str(VOICES_PATH)
            )
            logger.info("Kokoro TTS initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kokoro: {e}")
            raise

    return kokoro_instance


@app.on_event("startup")
async def startup_event():
    """Initialize Kokoro on startup"""
    try:
        get_kokoro()
        logger.info("Kokoro TTS service started successfully")
    except Exception as e:
        logger.error(f"Failed to start Kokoro service: {e}")
        raise


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        kokoro = get_kokoro()
        return {
            "status": "healthy",
            "service": "kokoro-tts",
            "model_loaded": kokoro is not None
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.post("/tts", response_model=TTSResponse)
async def generate_tts(request: TTSRequest):
    """
    Generate speech from text using Kokoro TTS

    Args:
        request: TTSRequest with text, voice, speed, language, format

    Returns:
        TTSResponse with audio file path and metadata
    """
    try:
        logger.info(
            f"TTS request: {len(request.text)} chars, "
            f"voice={request.voice}, speed={request.speed}, lang={request.language}"
        )

        # Validate voice
        if request.voice not in SUPPORTED_VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voice '{request.voice}' not supported. "
                       f"Available: {sorted(SUPPORTED_VOICES)}"
            )

        # Get Kokoro instance
        kokoro = get_kokoro()

        # Generate audio
        logger.info(f"Generating audio with voice '{request.voice}'...")
        samples, sample_rate = kokoro.create(
            text=request.text,
            voice=request.voice,
            speed=request.speed,
            lang=request.language
        )

        # Convert to numpy array if needed
        if not isinstance(samples, np.ndarray):
            samples = np.array(samples, dtype=np.float32)

        # Calculate duration
        duration_seconds = len(samples) / sample_rate

        # Save to temporary file
        temp_dir = Path("/tmp/kokoro-audio")
        temp_dir.mkdir(exist_ok=True)

        # Determine output format
        if request.format == "opus" or request.format == "ogg":
            # Opus is the recommended format for WhatsApp
            audio_path = temp_dir / f"tts_{os.urandom(8).hex()}.ogg"
            # Save as OGG Opus (soundfile supports this)
            sf.write(
                str(audio_path),
                samples,
                sample_rate,
                format='OGG',
                subtype='OPUS'
            )
        else:
            # Default to WAV
            audio_path = temp_dir / f"tts_{os.urandom(8).hex()}.wav"
            sf.write(str(audio_path), samples, sample_rate)

        logger.info(
            f"Audio generated successfully: {audio_path} "
            f"({duration_seconds:.2f}s, {sample_rate}Hz)"
        )

        return TTSResponse(
            success=True,
            message="Audio generated successfully",
            audio_path=str(audio_path),
            sample_rate=sample_rate,
            duration_seconds=round(duration_seconds, 2),
            character_count=len(request.text),
            voice_used=request.voice
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"TTS generation failed: {str(e)}"
        )


@app.get("/voices")
async def list_voices():
    """List available voice profiles"""
    return {
        "voices": sorted(SUPPORTED_VOICES),
        "total": len(SUPPORTED_VOICES),
        "recommended": {
            "ptbr_female": "af_bella",
            "ptbr_male": "am_adam",
            "en_female": "af_sarah",
            "en_male": "am_michael"
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "kokoro_service:app",
        host="0.0.0.0",
        port=8089,
        log_level="info"
    )
