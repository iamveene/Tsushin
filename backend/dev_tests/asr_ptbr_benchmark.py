#!/usr/bin/env python3
"""PT-BR ASR benchmark helper for local Speaches model trials.

This script intentionally keeps audio and transcript artifacts out of the repo.
By default it prints a compact side-by-side JSON result to stdout. If
``--output`` is provided, point it at an ignored/private path such as
``.private/asr-benchmarks/run.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


DEFAULT_MODELS = [
    "Systran/faster-whisper-small",
    "Systran/faster-whisper-medium",
    "deepdml/faster-whisper-large-v3-turbo-ct2",
]


def _read_audio(path: Path) -> tuple[str, bytes]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    return path.name, path.read_bytes()


def _probe_duration_seconds(path: Path) -> float | None:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None

    raw = completed.stdout.strip()
    if not raw:
        return None
    try:
        duration = float(raw)
    except ValueError:
        return None
    return round(duration, 3) if duration > 0 else None


def _ensure_speaches_model(*, base_url: str, token: str, model: str, timeout: int) -> dict[str, Any]:
    start = time.perf_counter()
    resp = requests.post(
        f"{base_url.rstrip('/')}/v1/models/{quote(model, safe='')}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    elapsed = time.perf_counter() - start
    ok = resp.status_code in {200, 201, 202, 204, 409}
    return {
        "model": model,
        "ok": ok,
        "status_code": resp.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "error": None if ok else resp.text[:500],
    }


def _post_speaches(
    *,
    base_url: str,
    token: str,
    audio_path: Path,
    model: str,
    language: str,
    vad_filter: bool | None,
    prompt: str | None,
    hotwords: str | None,
    timeout: int,
) -> dict[str, Any]:
    name, audio = _read_audio(audio_path)
    data: dict[str, str] = {"model": model}
    if language != "auto":
        data["language"] = language
    if vad_filter is not None:
        data["vad_filter"] = "true" if vad_filter else "false"
    if prompt:
        data["prompt"] = prompt
    if hotwords:
        data["hotwords"] = hotwords

    start = time.perf_counter()
    resp = requests.post(
        f"{base_url.rstrip('/')}/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (name, audio, "application/octet-stream")},
        data=data,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - start
    ok = resp.status_code == 200
    text = ""
    error = None
    if ok:
        try:
            payload = resp.json()
            text = (payload.get("text") or "").strip() if isinstance(payload, dict) else str(payload).strip()
        except Exception as exc:
            ok = False
            error = f"json_error: {exc}"
    else:
        error = f"http_{resp.status_code}: {resp.text[:500]}"
    return {
        "provider": "speaches",
        "model": model,
        "ok": ok,
        "elapsed_seconds": round(elapsed, 3),
        "text": text,
        "error": error,
    }


def _post_openai(
    *,
    audio_path: Path,
    model: str,
    language: str,
    prompt: str | None,
    timeout: int,
) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except Exception as exc:
        return {
            "provider": "openai",
            "model": model,
            "ok": False,
            "elapsed_seconds": 0,
            "text": "",
            "error": f"openai_import_error: {exc}",
        }

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "provider": "openai",
            "model": model,
            "ok": False,
            "elapsed_seconds": 0,
            "text": "",
            "error": "missing_OPENAI_API_KEY",
        }

    client = OpenAI(api_key=api_key, timeout=timeout)
    kwargs: dict[str, Any] = {"model": model}
    if language != "auto":
        kwargs["language"] = language
    if prompt:
        kwargs["prompt"] = prompt

    start = time.perf_counter()
    try:
        with audio_path.open("rb") as audio_file:
            response = client.audio.transcriptions.create(file=audio_file, **kwargs)
        elapsed = time.perf_counter() - start
        return {
            "provider": "openai",
            "model": model,
            "ok": True,
            "elapsed_seconds": round(elapsed, 3),
            "text": (getattr(response, "text", "") or "").strip(),
            "error": None,
        }
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return {
            "provider": "openai",
            "model": model,
            "ok": False,
            "elapsed_seconds": round(elapsed, 3),
            "text": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _parse_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y", "on"}:
        return True
    if lowered in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true/false/null")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", action="append", required=True, help="Audio file path. Repeat for multiple clips.")
    parser.add_argument("--speaches-base-url", required=True, help="Speaches base URL, e.g. http://127.0.0.1:6400")
    parser.add_argument("--speaches-token-env", default="SPEACHES_API_KEY", help="Env var containing the Speaches bearer token.")
    parser.add_argument("--model", action="append", dest="models", help="Speaches model id. Defaults to the PT-BR candidate set.")
    parser.add_argument("--language", default="pt", help="Language hint, default: pt")
    parser.add_argument("--vad-filter", type=_parse_bool, default=False, help="true/false/null, default: false")
    parser.add_argument("--prompt", default=None, help="Optional transcription prompt/context.")
    parser.add_argument("--hotwords", default=None, help="Optional Speaches hotwords string.")
    parser.add_argument("--skip-warm-models", action="store_true", help="Do not call Speaches model download/warm endpoint before transcription.")
    parser.add_argument("--openai-reference", action="store_true", help="Also run OpenAI cloud transcription as a reference ceiling.")
    parser.add_argument("--openai-model", default="whisper-1", help="OpenAI transcription model for reference.")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--output", default=None, help="Optional ignored/private JSON output path.")
    args = parser.parse_args()

    token = os.getenv(args.speaches_token_env)
    if not token:
        raise SystemExit(f"Missing Speaches token env var: {args.speaches_token_env}")

    models = args.models or DEFAULT_MODELS
    warmup_results = []
    if not args.skip_warm_models:
        for model in models:
            warmup_results.append(
                _ensure_speaches_model(
                    base_url=args.speaches_base_url,
                    token=token,
                    model=model,
                    timeout=args.timeout,
                )
            )

    results: list[dict[str, Any]] = []
    for raw_audio in args.audio:
        audio_path = Path(raw_audio)
        duration = _probe_duration_seconds(audio_path)
        clip_results = []
        for model in models:
            clip_results.append(
                _post_speaches(
                    base_url=args.speaches_base_url,
                    token=token,
                    audio_path=audio_path,
                    model=model,
                    language=args.language,
                    vad_filter=args.vad_filter,
                    prompt=args.prompt,
                    hotwords=args.hotwords,
                    timeout=args.timeout,
                )
            )
        if args.openai_reference:
            clip_results.append(
                _post_openai(
                    audio_path=audio_path,
                    model=args.openai_model,
                    language=args.language,
                    prompt=args.prompt,
                    timeout=args.timeout,
                )
            )
        ok_latencies = [r["elapsed_seconds"] for r in clip_results if r["ok"]]
        results.append(
            {
                "audio_name": audio_path.name,
                "audio_bytes": audio_path.stat().st_size,
                "duration_seconds": duration,
                "latency_seconds_median": round(statistics.median(ok_latencies), 3) if ok_latencies else None,
                "realtime_factor_median": (
                    round(statistics.median(ok_latencies) / duration, 3)
                    if duration and ok_latencies
                    else None
                ),
                "runs": clip_results,
            }
        )

    payload = {
        "language": args.language,
        "vad_filter": args.vad_filter,
        "prompt_configured": bool(args.prompt),
        "hotwords_configured": bool(args.hotwords),
        "warmup_results": warmup_results,
        "results": results,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
