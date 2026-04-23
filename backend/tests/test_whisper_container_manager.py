"""
Focused regressions for the Track D Whisper/Speaches container manager helpers.
"""

import io
import os
import socket
import sys
import types
import wave
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

from services.whisper_container_manager import (  # noqa: E402
    PORT_RANGE_END,
    PORT_RANGE_START,
    WhisperContainerManager,
    _build_silent_wav_bytes,
    _make_basic_auth_header,
)


class _FakePortQuery:
    def __init__(self, ports):
        self._ports = ports

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return [(p,) for p in self._ports]


class _FakeDB:
    def __init__(self, used_ports):
        self._used = used_ports

    def query(self, *args, **kwargs):
        return _FakePortQuery(self._used)


def test_make_basic_auth_header_uses_tsushin_contract():
    header = _make_basic_auth_header("tsushin", "secret-token")
    assert header.startswith("Basic ")
    assert "dHN1c2hpbjpzZWNyZXQtdG9rZW4=" in header


def test_build_silent_wav_bytes_returns_valid_wav():
    blob = _build_silent_wav_bytes(1.0)
    with wave.open(io.BytesIO(blob), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 16000
        assert wav.getsampwidth() == 2
        assert wav.getnframes() > 0


def test_allocate_port_stays_within_whisper_range():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    port = mgr._allocate_port(_FakeDB([]))
    assert PORT_RANGE_START <= port <= PORT_RANGE_END


def test_allocate_port_skips_ports_bound_on_loopback():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        held_port = None
        for candidate in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            try:
                s.bind(("127.0.0.1", candidate))
                held_port = candidate
                break
            except OSError:
                continue
        assert held_port is not None
        mgr = WhisperContainerManager.__new__(WhisperContainerManager)
        port = mgr._allocate_port(_FakeDB([]))
        assert port != held_port
    finally:
        s.close()


def test_warm_up_uses_basic_auth_and_x_api_key():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    instance = SimpleNamespace(
        base_url="http://whisper.internal:8000",
        default_model="Systran/faster-distil-whisper-small.en",
    )
    with patch("services.whisper_container_manager.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        ok = mgr._warm_up(instance, token="secret-token", username="tsushin")

    assert ok is True
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"].startswith("Basic ")
    assert kwargs["headers"]["X-API-Key"] == "secret-token"
    assert kwargs["data"]["model"] == "Systran/faster-distil-whisper-small.en"
