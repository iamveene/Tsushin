import json
import shutil
import struct
import subprocess
from pathlib import Path


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ASR_FIXTURES = [
    FIXTURES_DIR / "asr_test_en.ogg",
    FIXTURES_DIR / "asr_test_pt.ogg",
]


def _run_json(*cmd: str) -> dict:
    result = subprocess.run(
        list(cmd),
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(result.stdout)


def _decode_max_amplitude(path: Path) -> float:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required to validate ASR fixture amplitude"

    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "f32le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    samples = result.stdout
    assert samples, f"{path.name} decoded to an empty PCM stream"

    peak = 0.0
    for (value,) in struct.iter_unpack("<f", samples):
        sample_abs = abs(value)
        if sample_abs > peak:
            peak = sample_abs
    return peak


def test_asr_audio_fixtures_exist_and_probe_cleanly():
    ffprobe = shutil.which("ffprobe")
    assert ffprobe, "ffprobe is required to validate ASR fixture metadata"

    for path in ASR_FIXTURES:
        assert path.exists(), f"Missing ASR fixture: {path}"
        assert path.stat().st_size > 0, f"{path.name} is empty"

        data = _run_json(
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,channels:format=duration",
            "-of",
            "json",
            str(path),
        )
        stream = data["streams"][0]
        duration = float(data["format"]["duration"])

        assert stream["codec_name"] == "opus"
        assert stream["channels"] == 1
        assert 3.0 <= duration <= 10.0, f"{path.name} duration {duration:.2f}s outside fixture window"


def test_asr_audio_fixtures_are_not_silence():
    for path in ASR_FIXTURES:
        peak = _decode_max_amplitude(path)
        assert peak > 0.01, f"{path.name} peak amplitude too low ({peak:.5f})"
