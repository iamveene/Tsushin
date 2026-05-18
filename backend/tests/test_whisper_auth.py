"""
BUG-703 regression: WhisperASRProvider.transcribe() and
WhisperContainerManager warm-up call must send `Authorization: Bearer <token>`
to the upstream Speaches API. Basic auth + X-API-Key produced 403 against
real Speaches and must NOT be re-introduced.

These tests intercept the outbound HTTP call (httpx for the provider, requests
for the container-manager warm-up) and assert the Authorization header is the
Bearer scheme and that no `X-API-Key` header is attached.
"""

import asyncio
import importlib.util
import io
import os
import struct
import sys
import tempfile
import types
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)


def _ensure_package(package_name: str, relative_path: str):
    module = sys.modules.get(package_name)
    if module is None:
        module = types.ModuleType(package_name)
        module.__path__ = [os.path.join(BACKEND_ROOT, relative_path)]
        sys.modules[package_name] = module
    return module


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        os.path.join(BACKEND_ROOT, relative_path),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_ensure_package("hub", "hub")
_ensure_package("hub.providers", os.path.join("hub", "providers"))
_ensure_package("services", "services")

# Load only the abstract-base + provider modules. We deliberately avoid
# importing the full `services.whisper_instance_service` (which transitively
# pulls in `models`, alembic, etc.) by stubbing it.
asr_provider_module = _load_module(
    "hub.providers.asr_provider",
    os.path.join("hub", "providers", "asr_provider.py"),
)


# Stub `services.whisper_instance_service` BEFORE importing the provider so
# the provider's `from services.whisper_instance_service import ...` resolves
# against the stub (no DB / models / alembic dependencies). The stub expects
# instances with a `_token` attribute (see _make_provider helpers below); the
# real `WhisperInstanceService.resolve_api_token` would try to decrypt
# `instance.api_token_encrypted` and fail.
#
# IMPORTANT: only install the stub if the real module CANNOT be imported.
# Pytest's collection phase imports every test module up-front (including
# this one), so a naive ``if "services.whisper_instance_service" not in
# sys.modules`` install runs BEFORE any other test can import the real
# module — which leaks the stub into tests like
# ``test_asr_cascade_on_delete.py`` that need ``create_instance`` on the
# real service. Probing the real module first ensures we only stub when
# the real one truly is unavailable (e.g. DB / alembic deps missing).
def _real_whisper_instance_service_importable():
    try:
        import services.whisper_instance_service  # noqa: F401
        return True
    except Exception:
        return False


if not _real_whisper_instance_service_importable():
    _whisper_instance_service_stub = types.ModuleType(
        "services.whisper_instance_service"
    )


    class _StubWhisperInstanceService:
        @staticmethod
        def resolve_api_token(instance, db):
            return getattr(instance, "_token", None) or "test-token-bearer-707"

        @staticmethod
        def get_instance(*args, **kwargs):  # pragma: no cover - stub for patches
            return None

        @staticmethod
        def update_instance(*args, **kwargs):  # pragma: no cover - stub
            return None

        @staticmethod
        def cascade_agent_skill_pins(*args, **kwargs):  # pragma: no cover - stub
            return {"reassigned": 0, "disabled": 0, "successor_instance_id": None}


    _whisper_instance_service_stub.WhisperInstanceService = _StubWhisperInstanceService
    _whisper_instance_service_stub.DEFAULT_MODEL_ID = (
        "Systran/faster-distil-whisper-small.en"
    )
    _whisper_instance_service_stub.DEFAULT_OPENAI_WHISPER_MODEL = "base"
    _whisper_instance_service_stub.default_model_for_vendor = lambda v: (
        "base" if v == "openai_whisper" else "Systran/faster-distil-whisper-small.en"
    )
    _whisper_instance_service_stub.SUPPORTED_VENDORS = {"speaches", "openai_whisper"}
    _whisper_instance_service_stub.AUTO_PROVISIONABLE_VENDORS = {"speaches", "openai_whisper"}
    sys.modules["services.whisper_instance_service"] = (
        _whisper_instance_service_stub
    )

# Also stub container_runtime + docker_network_utils so we can import the
# container manager without docker/alembic side-effects. Same guard as above:
# don't clobber the real module if it's already loaded — downstream tests
# (e.g. test_provider_instance_hardening.py) need the real PORT_RANGES dict
# which includes "ollama".
if "services.container_runtime" not in sys.modules:
    _container_runtime_stub = types.ModuleType("services.container_runtime")
    _container_runtime_stub.PORT_RANGES = {
        "whisper": (9000, 9099),
        "kokoro": (9100, 9199),
        # Include keys other tests need so this stub is broadly compatible.
        "ollama": (11400, 11499),
        "vector_store": (6300, 6399),
        "searxng": (8800, 8899),
    }


    class _StubContainerNotFoundError(Exception):
        pass


    class _StubContainerRuntimeError(Exception):
        pass


    class _StubContainerRuntime:
        raw_client = None


    def _stub_get_container_runtime():
        return _StubContainerRuntime()


    def _stub_iter_port_range(_name):
        yield from range(9000, 9099)


    _container_runtime_stub.ContainerNotFoundError = _StubContainerNotFoundError
    _container_runtime_stub.ContainerRuntimeError = _StubContainerRuntimeError
    _container_runtime_stub.ContainerRuntime = _StubContainerRuntime
    _container_runtime_stub.get_container_runtime = _stub_get_container_runtime
    _container_runtime_stub.iter_port_range = _stub_iter_port_range
    sys.modules["services.container_runtime"] = _container_runtime_stub

if "services.docker_network_utils" not in sys.modules:
    _docker_network_stub = types.ModuleType("services.docker_network_utils")


    def _stub_resolve_tsushin_network_name(_client):
        return "tsushin-network"


    _docker_network_stub.resolve_tsushin_network_name = (
        _stub_resolve_tsushin_network_name
    )
    sys.modules["services.docker_network_utils"] = _docker_network_stub

provider_module = _load_module(
    "hub.providers.whisper_asr_provider",
    os.path.join("hub", "providers", "whisper_asr_provider.py"),
)
manager_module = _load_module(
    "services.whisper_container_manager",
    os.path.join("services", "whisper_container_manager.py"),
)

WhisperASRProvider = provider_module.WhisperASRProvider
ASRRequest = asr_provider_module.ASRRequest


def _silent_wav_path() -> str:
    """Write a 1s mono 16k WAV to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sample_rate = 16000
    frames = sample_rate
    with wave.open(tmp.name, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack("<h", 0) * frames)
    tmp.close()
    return tmp.name


class _CapturingAsyncClient:
    """Minimal stand-in for httpx.AsyncClient that records the headers
    of the outbound POST."""

    captured = {}

    def __init__(self, *_, **__):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, *, headers=None, files=None, data=None):
        _CapturingAsyncClient.captured = {
            "url": url,
            "headers": dict(headers or {}),
            "data": dict(data or {}),
            "files_keys": list((files or {}).keys()),
        }
        return SimpleNamespace(
            status_code=200,
            text="",
            json=lambda: {"text": "ok"},
        )


class _SequencedAsyncClient:
    """Minimal httpx.AsyncClient fake that returns/raises queued outcomes."""

    outcomes = []
    calls = []
    file_handles = []

    def __init__(self, *_, **__):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, *, headers=None, files=None, data=None):
        file_handle = (files or {}).get("file", (None, None))[1]
        _SequencedAsyncClient.file_handles.append(file_handle)
        _SequencedAsyncClient.calls.append({
            "url": url,
            "headers": dict(headers or {}),
            "data": dict(data or {}),
            "files_keys": list((files or {}).keys()),
        })
        outcome = _SequencedAsyncClient.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _speaches_response(status_code=200, *, text="", payload=None):
    if payload is None:
        payload = {"text": "ok"}
    return SimpleNamespace(
        status_code=status_code,
        text=text,
        json=lambda: payload,
    )


async def _no_sleep(_delay):
    return None


def _make_speaches_provider():
    instance = SimpleNamespace(
        base_url="http://whisper-test:8000",
        default_model="Systran/faster-distil-whisper-small.en",
        auth_username="tsushin",
        _token="bearer-secret-abc123",
    )
    db = MagicMock()
    return WhisperASRProvider(instance=instance, db=db, tenant_id="tenant_test"), db


def _run_speaches_with_outcomes(audio_path, outcomes):
    _SequencedAsyncClient.outcomes = list(outcomes)
    _SequencedAsyncClient.calls = []
    _SequencedAsyncClient.file_handles = []
    provider, db = _make_speaches_provider()

    from services import whisper_instance_service as wis
    with patch.object(
        wis.WhisperInstanceService,
        "resolve_api_token",
        staticmethod(
            lambda inst, db: getattr(inst, "_token", None)
            or "test-token-bearer-707"
        ),
    ), patch.object(
        provider_module.httpx,
        "AsyncClient",
        _SequencedAsyncClient,
    ), patch.object(
        provider_module.asyncio,
        "sleep",
        _no_sleep,
    ):
        request = ASRRequest(
            audio_path=audio_path,
            model="Systran/faster-distil-whisper-small.en",
        )
        response = asyncio.run(provider.transcribe(request))

    return response, db, _SequencedAsyncClient.calls, _SequencedAsyncClient.file_handles


def test_provider_transcribe_sends_bearer_not_basic():
    """BUG-703: provider must use `Authorization: Bearer <token>` and must
    NOT send Basic auth or X-API-Key."""
    audio_path = _silent_wav_path()
    instance = SimpleNamespace(
        base_url="http://whisper-test:8000",
        default_model="Systran/faster-distil-whisper-small.en",
        auth_username="tsushin",
        _token="bearer-secret-abc123",
    )
    db = MagicMock()
    provider = WhisperASRProvider(instance=instance, db=db, tenant_id="tenant_test")

    # When the real ``WhisperInstanceService`` is loaded (broader test runs),
    # ``resolve_api_token`` reads ``instance.api_token_encrypted`` and tries
    # to decrypt it. Our SimpleNamespace test instance only carries ``_token``,
    # so patch ``resolve_api_token`` to honour the test contract.
    from services import whisper_instance_service as wis
    with patch.object(
        wis.WhisperInstanceService,
        "resolve_api_token",
        staticmethod(lambda inst, db: getattr(inst, "_token", None) or "test-token-bearer-707"),
    ), patch.object(provider_module, "httpx", SimpleNamespace(AsyncClient=_CapturingAsyncClient)):
        request = ASRRequest(audio_path=audio_path, model="Systran/faster-distil-whisper-small.en")
        response = asyncio.run(provider.transcribe(request))

    assert response.success is True
    db.rollback.assert_called_once()
    captured = _CapturingAsyncClient.captured
    headers = captured["headers"]

    auth = headers.get("Authorization", "")
    assert auth.startswith("Bearer "), (
        f"Expected Bearer auth, got: {auth!r}"
    )
    assert auth == "Bearer bearer-secret-abc123"
    assert not auth.startswith("Basic "), (
        f"Basic auth must not be used (BUG-703). Got: {auth!r}"
    )
    assert "X-API-Key" not in headers, (
        f"X-API-Key must be dropped (Speaches ignores it). Got headers: {headers!r}"
    )
    # Hit the right route
    assert captured["url"].endswith("/v1/audio/transcriptions")

    os.unlink(audio_path)


@pytest.mark.parametrize("status_code", [429, 503])
def test_provider_retries_transient_http_and_reopens_audio_file(status_code):
    audio_path = _silent_wav_path()
    try:
        response, db, calls, file_handles = _run_speaches_with_outcomes(
            audio_path,
            [
                _speaches_response(status_code, text="temporary"),
                _speaches_response(200, payload={"text": "retry ok"}),
            ],
        )
    finally:
        os.unlink(audio_path)

    assert response.success is True
    assert response.text == "retry ok"
    assert response.metadata["attempts"] == 2
    assert response.metadata["retried"] is True
    db.rollback.assert_called_once()
    assert len(calls) == 2
    assert len(file_handles) == 2
    assert len({id(handle) for handle in file_handles}) == 2
    assert all(handle.closed for handle in file_handles)


def test_provider_retries_remote_protocol_error():
    audio_path = _silent_wav_path()
    try:
        response, _db, calls, file_handles = _run_speaches_with_outcomes(
            audio_path,
            [
                httpx.RemoteProtocolError("server disconnected without response"),
                _speaches_response(200, payload={"text": "after remote reset"}),
            ],
        )
    finally:
        os.unlink(audio_path)

    assert response.success is True
    assert response.text == "after remote reset"
    assert response.metadata["attempts"] == 2
    assert response.metadata["retried"] is True
    assert len(calls) == 2
    assert len({id(handle) for handle in file_handles}) == 2
    assert all(handle.closed for handle in file_handles)


def test_provider_does_not_retry_non_transient_4xx():
    audio_path = _silent_wav_path()
    try:
        response, _db, calls, _file_handles = _run_speaches_with_outcomes(
            audio_path,
            [_speaches_response(403, text="forbidden")],
        )
    finally:
        os.unlink(audio_path)

    assert response.success is False
    assert response.error == "http_403: forbidden"
    assert response.metadata["attempts"] == 1
    assert response.metadata["retried"] is False
    assert len(calls) == 1


def test_provider_returns_retry_metadata_on_timeout_failure():
    audio_path = _silent_wav_path()
    try:
        response, _db, calls, _file_handles = _run_speaches_with_outcomes(
            audio_path,
            [httpx.TimeoutException("queue timeout") for _ in range(4)],
        )
    finally:
        os.unlink(audio_path)

    assert response.success is False
    assert response.error.startswith("request_error: TimeoutException: queue timeout")
    assert response.metadata["attempts"] == 4
    assert response.metadata["retried"] is True
    assert len(calls) == 4


class _CapturingRequests:
    """Stand-in for the `requests` module used in the warm-up call."""

    last_call = {}

    @staticmethod
    def post(url, *, headers=None, files=None, data=None, timeout=None):
        _CapturingRequests.last_call = {
            "url": url,
            "headers": dict(headers or {}),
            "data": dict(data or {}),
            "files_keys": list((files or {}).keys()),
            "timeout": timeout,
        }
        return SimpleNamespace(status_code=200, text="")


def test_warmup_call_sends_bearer_not_basic():
    """BUG-703: container manager warm-up call must use Bearer auth."""
    manager = manager_module.WhisperContainerManager.__new__(
        manager_module.WhisperContainerManager
    )

    with patch.object(manager_module, "requests", _CapturingRequests):
        ok = manager._warm_up_detached(
            base_url="http://whisper-test:8000",
            token="warmup-bearer-xyz",
            model="Systran/faster-distil-whisper-small.en",
            vendor="speaches",
        )

    assert ok is True
    headers = _CapturingRequests.last_call["headers"]

    auth = headers.get("Authorization", "")
    assert auth == "Bearer warmup-bearer-xyz", (
        f"Warm-up must use Bearer auth (BUG-703). Got: {auth!r}"
    )
    assert not auth.startswith("Basic "), (
        f"Warm-up must NOT use Basic auth. Got: {auth!r}"
    )
    assert "X-API-Key" not in headers, (
        f"X-API-Key must be dropped from warm-up. Got headers: {headers!r}"
    )


class _RecordingRequests:
    """Stand-in for `requests` that records every POST in order."""

    def __init__(self):
        self.calls = []

    def post(self, url, *, headers=None, files=None, data=None, timeout=None):
        self.calls.append({
            "url": url,
            "headers": dict(headers or {}),
            "data": dict(data or {}),
            "files_keys": list((files or {}).keys()),
            "timeout": timeout,
        })
        return SimpleNamespace(status_code=200, text="")


def test_speaches_warmup_downloads_model_before_transcribing():
    """The Speaches `latest-cpu` image does not honor PRELOAD_MODELS, so the
    container manager must POST /v1/models/{model} to fetch the asset before
    the silent-WAV warm-up. Without this, `/v1/audio/transcriptions` 404s with
    'Model not installed locally' and the instance lands in cstatus=error."""
    manager = manager_module.WhisperContainerManager.__new__(
        manager_module.WhisperContainerManager
    )
    rec = _RecordingRequests()

    with patch.object(manager_module, "requests", rec):
        ok = manager._warm_up_detached(
            base_url="http://whisper-test:8000",
            token="warmup-bearer-xyz",
            model="Systran/faster-whisper-tiny",
            vendor="speaches",
        )

    assert ok is True
    assert len(rec.calls) == 2, (
        f"Expected 2 POSTs (model-download then transcribe). Got: {rec.calls!r}"
    )

    download_call, transcribe_call = rec.calls
    assert download_call["url"] == (
        "http://whisper-test:8000/v1/models/Systran/faster-whisper-tiny"
    ), f"First POST must be the model download. Got: {download_call['url']!r}"
    assert download_call["headers"].get("Authorization") == "Bearer warmup-bearer-xyz"
    assert download_call["files_keys"] == [], (
        "Model-download POST must not carry a file payload"
    )

    assert transcribe_call["url"].endswith("/v1/audio/transcriptions")
    assert transcribe_call["headers"].get("Authorization") == "Bearer warmup-bearer-xyz"


def test_speaches_warmup_attempts_transcribe_even_if_model_download_fails():
    """Defense in depth: if /v1/models returns a non-2xx (e.g. already cached
    in some Speaches versions, or transient hiccup), the warm-up should still
    attempt the silent-WAV transcribe rather than bailing early. The transcribe
    call's status is the source of truth for readiness."""
    manager = manager_module.WhisperContainerManager.__new__(
        manager_module.WhisperContainerManager
    )

    class _FlakyDownload:
        def __init__(self):
            self.calls = []

        def post(self, url, *, headers=None, files=None, data=None, timeout=None):
            self.calls.append(url)
            if "/v1/models/" in url and "/v1/audio" not in url:
                return SimpleNamespace(status_code=500, text="oh no")
            return SimpleNamespace(status_code=200, text="")

    rec = _FlakyDownload()
    with patch.object(manager_module, "requests", rec):
        ok = manager._warm_up_detached(
            base_url="http://whisper-test:8000",
            token="t",
            model="Systran/faster-whisper-tiny",
            vendor="speaches",
        )

    assert ok is True
    assert any(c.endswith("/v1/audio/transcriptions") for c in rec.calls), (
        "Transcribe warm-up must be attempted even when model-download fails. "
        f"Got: {rec.calls!r}"
    )


def test_no_basic_auth_helper_remains_in_provider_or_manager():
    """Defence-in-depth: assert the Basic-auth helper functions were removed,
    so a future regression cannot accidentally re-introduce Basic auth via
    a leftover helper."""
    assert not hasattr(provider_module, "_basic_auth"), (
        "WhisperASRProvider._basic_auth helper must be removed (BUG-703)"
    )
    assert not hasattr(manager_module, "_make_basic_auth_header"), (
        "WhisperContainerManager._make_basic_auth_header helper must be removed (BUG-703)"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
