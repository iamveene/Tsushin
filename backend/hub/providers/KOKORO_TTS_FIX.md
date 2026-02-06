# Kokoro TTS Audio Truncation Fix

## Problem
Kokoro TTS audio responses were being cut off before the end of the message. Users reported audio stopping mid-sentence, losing the final portion of spoken content.

## Root Cause
**Kokoro-FastAPI has a bug in its OGG Opus encoder** where audio data is truncated. The issue is NOT just a missing End-Of-Stream (EOS) marker - actual audio frames are lost during encoding.

### Evidence
Testing the same text with different formats revealed:
- **OGG Opus (direct from Kokoro)**: 3.00 seconds, ~37% audio missing
- **WAV (from Kokoro)**: 4.77 seconds, complete audio
- **MP3 (from Kokoro)**: 4.83 seconds, complete audio

The bug is in Kokoro-FastAPI's `StreamingAudioWriter` class where `output_buffer.getvalue()` is called BEFORE `container.close()`, causing the final audio frames to be lost.

## Solution
Instead of requesting OGG Opus directly from Kokoro (which is truncated), we:
1. Request **WAV format** from Kokoro (which works correctly)
2. Convert WAV → OGG Opus locally using **ffmpeg**
3. Delete the temporary WAV file

This produces complete, properly-formatted OGG Opus files that work correctly with WhatsApp.

## Changes Made

### 1. Backend Dockerfile
Added `ffmpeg` to runtime dependencies:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    ...
    ffmpeg \
    ...
```

### 2. Kokoro TTS Provider (`kokoro_tts_provider.py`)
- Added `needs_conversion` flag when opus format is requested
- Request WAV from Kokoro instead of opus
- Added `_convert_wav_to_opus()` method using ffmpeg
- Conversion uses optimal settings for voice: `-c:a libopus -b:a 48k -vbr on -application voip`

## Testing
Verified fix with Whisper transcription:
- **Before fix**: Audio transcribed as incomplete, missing final words
- **After fix**: Audio transcribed as complete, all words present

## WhatsApp Compatibility
The fix maintains WhatsApp compatibility:
- Output format remains OGG Opus (required for inline audio playback)
- Files include proper EOS markers
- Audio quality preserved with 48kbps VBR encoding

## Date
December 31, 2025
