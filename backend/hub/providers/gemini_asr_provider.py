"""
Gemini ASR provider.

Uses Google's Gemini multimodal models (gemini-3.5-flash and friends) to
transcribe audio. Unlike Whisper, the model accepts raw audio bytes inline
with a text prompt and returns the transcript as plain text — no separate
audio-input endpoint.

Inline upload caps at ~20 MB; larger files go through the Files API. The
returned `ASRResponse` matches the OpenAI provider's shape so the rest of
the agent pipeline does not need to know which backend produced the text.
"""

import asyncio
import mimetypes
from pathlib import Path
from typing import Any, Optional

from .asr_provider import ASRProvider, ASRRequest, ASRResponse
from services.provider_instance_service import ProviderInstanceService


_INLINE_AUDIO_LIMIT_BYTES = 20 * 1024 * 1024  # Gemini inline data cap
_RETRY_BACKOFFS_SEC = (1.0, 3.0, 7.0)
_TRANSIENT_KEYWORDS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "resourceexhausted",
    "serviceunavailable",
    "deadlineexceeded",
    "internal",
    "timeout",
)

_TRANSCRIBE_PROMPT_BASE = (
    "Transcribe this audio verbatim. "
    "Output only the transcription text, with no introduction, commentary, "
    "translations, or markup."
)

_AUDIO_MIME_FALLBACK = "audio/ogg"


def _is_transient_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(token in text for token in _TRANSIENT_KEYWORDS)


_CANONICAL_AUDIO_MIME = {
    "ogg": "audio/ogg",
    "oga": "audio/ogg",
    "opus": "audio/ogg",
    "mp3": "audio/mpeg",
    "mpeg": "audio/mpeg",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/mp4",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "webm": "audio/webm",
}


def _guess_audio_mime(path: str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    canonical = _CANONICAL_AUDIO_MIME.get(suffix)
    if canonical:
        return canonical
    guessed, _ = mimetypes.guess_type(path)
    if guessed and guessed.startswith("audio/"):
        return guessed
    return _AUDIO_MIME_FALLBACK


class GeminiASRProvider(ASRProvider):
    DEFAULT_MODEL = "gemini-3.5-flash"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key

    def get_provider_name(self) -> str:
        return "gemini"

    async def transcribe(self, request: ASRRequest) -> ASRResponse:
        api_key = self._api_key
        if not api_key and self.db is not None:
            api_key = ProviderInstanceService.resolve_default_api_key(
                "gemini", self.tenant_id, self.db
            )
        if not api_key:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error="missing_api_key",
            )

        # Releasing any pending DB txn mirrors the OpenAI provider — the
        # blocking Gemini call below runs in a thread and any held lock
        # would dead-end the worker session.
        if self.db is not None:
            try:
                self.db.rollback()
            except Exception as rollback_err:
                self.logger.warning(
                    "Failed to release DB transaction before Gemini ASR call: %s",
                    rollback_err,
                )

        audio_path = request.audio_path
        try:
            audio_bytes = Path(audio_path).read_bytes()
        except FileNotFoundError:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error=f"audio_file_not_found: {audio_path}",
            )
        except Exception as read_err:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error=f"audio_read_error: {read_err}",
            )

        mime_type = _guess_audio_mime(audio_path)
        model = request.model or self.DEFAULT_MODEL
        prompt = self._build_prompt(request)

        attempts = 0
        last_error: Optional[str] = None
        max_attempts = 1 + len(_RETRY_BACKOFFS_SEC)
        text = ""
        used_files_api = len(audio_bytes) > _INLINE_AUDIO_LIMIT_BYTES

        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                text = await asyncio.to_thread(
                    self._run_generate,
                    api_key=api_key,
                    model=model,
                    audio_bytes=audio_bytes,
                    audio_path=audio_path,
                    mime_type=mime_type,
                    prompt=prompt,
                    use_files_api=used_files_api,
                )
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < max_attempts - 1 and _is_transient_error(exc):
                    delay = _RETRY_BACKOFFS_SEC[attempt]
                    self.logger.warning(
                        "Gemini ASR transient failure (attempt %s/%s): %s — retrying in %.1fs",
                        attempts,
                        max_attempts,
                        last_error,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return ASRResponse(
                    success=False,
                    provider=self.provider_name,
                    error=last_error,
                    metadata={
                        "attempts": attempts,
                        "retried": attempts > 1,
                        "model": model,
                        "used_files_api": used_files_api,
                    },
                )

        text = (text or "").strip()
        if not text:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error="empty_transcription",
                metadata={
                    "attempts": attempts,
                    "retried": attempts > 1,
                    "model": model,
                    "used_files_api": used_files_api,
                },
            )

        return ASRResponse(
            success=True,
            provider=self.provider_name,
            text=text,
            metadata={
                "model": model,
                "attempts": attempts,
                "retried": attempts > 1,
                "used_files_api": used_files_api,
                "audio_bytes": len(audio_bytes),
            },
        )

    def _build_prompt(self, request: ASRRequest) -> str:
        prompt_parts = [_TRANSCRIBE_PROMPT_BASE]
        language = (request.language or "").strip()
        if language and language.lower() != "auto":
            prompt_parts.append(f"The audio is in language code '{language}'.")
        if request.prompt:
            prompt_parts.append(
                "Domain context / spelling hints from the operator:\n"
                f"{request.prompt.strip()}"
            )
        if request.hotwords:
            prompt_parts.append(
                "Bias recognition toward these terms when ambiguous: "
                f"{request.hotwords.strip()}"
            )
        return "\n\n".join(prompt_parts)

    def _run_generate(
        self,
        *,
        api_key: str,
        model: str,
        audio_bytes: bytes,
        audio_path: str,
        mime_type: str,
        prompt: str,
        use_files_api: bool,
    ) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        if use_files_api:
            uploaded = client.files.upload(file=audio_path)
            audio_part = types.Part.from_uri(
                file_uri=uploaded.uri,
                mime_type=uploaded.mime_type or mime_type,
            )
        else:
            audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

        response = client.models.generate_content(
            model=model,
            contents=[prompt, audio_part],
        )
        return self._extract_text(response)

    @staticmethod
    def _extract_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    return part_text.strip()
        return ""
