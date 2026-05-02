from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
import sys
import types as pytypes
from datetime import datetime
from pathlib import Path

from analytics.token_tracker import MODEL_PRICING


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_package(package_name: str, relative_path: str):
    module = sys.modules.get(package_name)
    if module is None:
        module = pytypes.ModuleType(package_name)
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


_ensure_package("agent", "agent")
_ensure_package("agent.skills", os.path.join("agent", "skills"))
_ensure_package("services", "services")

base_module = _load_module("agent.skills.base", os.path.join("agent", "skills", "base.py"))
image_skill_module = _load_module(
    "agent.skills.image_skill",
    os.path.join("agent", "skills", "image_skill.py"),
)

InboundMessage = base_module.InboundMessage
ImageSkill = image_skill_module.ImageSkill


IMAGEN_MODELS = {
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-fast-generate-001",
}

OPENAI_IMAGE_MODELS = {
    "gpt-image-2",
}


def _install_fake_genai(monkeypatch, fake_client_cls, fake_types_module):
    google_module = pytypes.ModuleType("google")
    genai_module = pytypes.ModuleType("google.genai")

    genai_module.Client = fake_client_cls
    genai_module.types = fake_types_module
    google_module.genai = genai_module

    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types_module)


def _install_fake_openai(monkeypatch, fake_client_cls):
    openai_module = pytypes.ModuleType("openai")
    openai_module.OpenAI = fake_client_cls
    monkeypatch.setitem(sys.modules, "openai", openai_module)


class _FakeSavedImage:
    def save(self, output_path: str) -> None:
        Path(output_path).write_bytes(b"fake-png")


def test_imagen_models_are_exposed_in_skill_catalogs_and_pricing():
    supported = set(ImageSkill.SUPPORTED_MODELS)
    assert IMAGEN_MODELS.issubset(supported)
    assert OPENAI_IMAGE_MODELS.issubset(supported)
    assert ImageSkill.DEFAULT_MODEL == "imagen-4.0-generate-001"
    assert ImageSkill.get_default_config()["model"] == ImageSkill.DEFAULT_MODEL

    tool_schema = ImageSkill.get_mcp_tool_definition()["inputSchema"]
    assert IMAGEN_MODELS.issubset(set(tool_schema["properties"]["model"]["enum"]))
    assert OPENAI_IMAGE_MODELS.issubset(set(tool_schema["properties"]["model"]["enum"]))
    assert tool_schema["properties"]["model"]["default"] == ImageSkill.DEFAULT_MODEL

    config_schema = ImageSkill.get_config_schema()
    assert IMAGEN_MODELS.issubset(set(config_schema["properties"]["model"]["enum"]))
    assert OPENAI_IMAGE_MODELS.issubset(set(config_schema["properties"]["model"]["enum"]))
    assert config_schema["properties"]["model"]["default"] == ImageSkill.DEFAULT_MODEL

    assert MODEL_PRICING["imagen-4.0-fast-generate-001"]["prompt"] == 20.0
    assert MODEL_PRICING["imagen-4.0-generate-001"]["prompt"] == 40.0
    assert MODEL_PRICING["imagen-4.0-ultra-generate-001"]["prompt"] == 60.0
    assert MODEL_PRICING["gpt-image-2"] == {"prompt": 5.0, "completion": 30.0}


def test_imagen_generation_dispatches_to_generate_images(monkeypatch, tmp_path):
    calls = {}

    class FakeGenerateImagesConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_types_module = pytypes.ModuleType("google.genai.types")
    fake_types_module.GenerateImagesConfig = FakeGenerateImagesConfig

    class FakeModels:
        def generate_images(self, model, prompt, config):
            calls["model"] = model
            calls["prompt"] = prompt
            calls["config"] = config
            return pytypes.SimpleNamespace(
                generated_images=[pytypes.SimpleNamespace(image=_FakeSavedImage())]
            )

    class FakeClient:
        def __init__(self, api_key):
            calls["api_key"] = api_key
            self.models = FakeModels()

    _install_fake_genai(monkeypatch, FakeClient, fake_types_module)
    monkeypatch.setattr(image_skill_module.tempfile, "gettempdir", lambda: str(tmp_path))

    skill = ImageSkill()

    async def fake_get_api_key():
        return "gemini-key"

    monkeypatch.setattr(skill, "_get_api_key", fake_get_api_key)

    result = asyncio.run(
        skill._generate_image_with_gemini(
            prompt="Robot holding a red skateboard",
            model="imagen-4.0-fast-generate-001",
            config={},
            aspect_ratio="16:9",
        )
    )

    assert result["success"] is True
    assert calls["api_key"] == "gemini-key"
    assert calls["model"] == "imagen-4.0-fast-generate-001"
    assert calls["prompt"] == "Robot holding a red skateboard"
    assert calls["config"].kwargs == {"number_of_images": 1, "aspect_ratio": "16:9"}
    assert Path(result["output_path"]).name.startswith("img_imagen_")
    assert Path(result["output_path"]).read_bytes() == b"fake-png"


def test_imagen_generation_reports_missing_output(monkeypatch, tmp_path):
    class FakeGenerateImagesConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_types_module = pytypes.ModuleType("google.genai.types")
    fake_types_module.GenerateImagesConfig = FakeGenerateImagesConfig

    class FakeModels:
        def generate_images(self, **_kwargs):
            return pytypes.SimpleNamespace(generated_images=[])

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    _install_fake_genai(monkeypatch, FakeClient, fake_types_module)
    monkeypatch.setattr(image_skill_module.tempfile, "gettempdir", lambda: str(tmp_path))

    skill = ImageSkill()

    async def fake_get_api_key():
        return "gemini-key"

    monkeypatch.setattr(skill, "_get_api_key", fake_get_api_key)

    result = asyncio.run(
        skill._generate_image_with_gemini(
            prompt="Nothing",
            model="imagen-4.0-generate-001",
            config={},
        )
    )

    assert result == {"success": False, "error": "No image generated in response"}


def test_openai_generation_dispatches_to_images_generate(monkeypatch, tmp_path):
    calls = {}
    image_payload = base64.b64encode(b"fake-openai-png").decode()

    class FakeImages:
        def generate(self, model, prompt, n, size):
            calls["model"] = model
            calls["prompt"] = prompt
            calls["n"] = n
            calls["size"] = size
            return pytypes.SimpleNamespace(
                data=[pytypes.SimpleNamespace(b64_json=image_payload)],
                usage=pytypes.SimpleNamespace(input_tokens=123, output_tokens=456),
            )

    class FakeOpenAI:
        def __init__(self, api_key):
            calls["api_key"] = api_key
            self.images = FakeImages()

    _install_fake_openai(monkeypatch, FakeOpenAI)
    monkeypatch.setattr(image_skill_module.tempfile, "gettempdir", lambda: str(tmp_path))

    skill = ImageSkill()

    async def fake_get_openai_api_key():
        return "openai-key"

    async def fail_gemini_api_key():
        raise AssertionError("OpenAI image generation must not request a Gemini key")

    monkeypatch.setattr(skill, "_get_openai_api_key", fake_get_openai_api_key)
    monkeypatch.setattr(skill, "_get_api_key", fail_gemini_api_key)

    result = asyncio.run(
        skill._generate_image_with_gemini(
            prompt="A product photo on a clean white background",
            model="gpt-image-2",
            config={},
            aspect_ratio="9:16",
        )
    )

    assert result["success"] is True
    assert calls == {
        "api_key": "openai-key",
        "model": "gpt-image-2",
        "prompt": "A product photo on a clean white background",
        "n": 1,
        "size": "1024x1536",
    }
    assert result["input_tokens"] == 123
    assert result["output_tokens"] == 456
    assert Path(result["output_path"]).name.startswith("img_openai_")
    assert Path(result["output_path"]).read_bytes() == b"fake-openai-png"


def test_openai_generation_reports_missing_output(monkeypatch, tmp_path):
    class FakeImages:
        def generate(self, **_kwargs):
            return pytypes.SimpleNamespace(data=[])

    class FakeOpenAI:
        def __init__(self, api_key):
            self.images = FakeImages()

    _install_fake_openai(monkeypatch, FakeOpenAI)
    monkeypatch.setattr(image_skill_module.tempfile, "gettempdir", lambda: str(tmp_path))

    skill = ImageSkill()

    async def fake_get_openai_api_key():
        return "openai-key"

    monkeypatch.setattr(skill, "_get_openai_api_key", fake_get_openai_api_key)

    result = asyncio.run(
        skill._generate_image_with_gemini(
            prompt="Nothing",
            model="gpt-image-2",
            config={},
        )
    )

    assert result == {"success": False, "error": "No image generated in response"}


def test_openai_edit_dispatches_to_images_edit(monkeypatch, tmp_path):
    calls = {}
    input_path = tmp_path / "input.png"
    input_path.write_bytes(b"input-image")
    image_payload = base64.b64encode(b"fake-openai-edit-png").decode()

    class FakeImages:
        def edit(self, model, image, prompt, n, size):
            calls["model"] = model
            calls["image_bytes"] = image.read()
            calls["prompt"] = prompt
            calls["n"] = n
            calls["size"] = size
            return pytypes.SimpleNamespace(
                data=[{"b64_json": image_payload}],
                usage={"input_tokens": 321, "output_tokens": 654},
            )

    class FakeOpenAI:
        def __init__(self, api_key):
            calls["api_key"] = api_key
            self.images = FakeImages()

    _install_fake_openai(monkeypatch, FakeOpenAI)
    monkeypatch.setattr(image_skill_module.tempfile, "gettempdir", lambda: str(tmp_path))

    skill = ImageSkill()

    async def fake_get_openai_api_key():
        return "openai-key"

    async def fail_gemini_api_key():
        raise AssertionError("OpenAI image edits must not request a Gemini key")

    monkeypatch.setattr(skill, "_get_openai_api_key", fake_get_openai_api_key)
    monkeypatch.setattr(skill, "_get_api_key", fail_gemini_api_key)

    result = asyncio.run(
        skill._edit_image_with_gemini(
            image_path=str(input_path),
            instruction="add a blue background",
            model="gpt-image-2",
            config={},
        )
    )

    assert result["success"] is True
    assert calls == {
        "api_key": "openai-key",
        "model": "gpt-image-2",
        "image_bytes": b"input-image",
        "prompt": "add a blue background",
        "n": 1,
        "size": "auto",
    }
    assert result["input_tokens"] == 321
    assert result["output_tokens"] == 654
    assert Path(result["output_path"]).name.startswith("img_openai_edit_")
    assert Path(result["output_path"]).read_bytes() == b"fake-openai-edit-png"


def test_legacy_gemini_image_generation_keeps_generate_content_path(monkeypatch, tmp_path):
    calls = {"generate_images": 0, "generate_content": 0}

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_types_module = pytypes.ModuleType("google.genai.types")
    fake_types_module.GenerateContentConfig = FakeGenerateContentConfig

    class FakePart:
        inline_data = object()

        def as_image(self):
            return _FakeSavedImage()

    class FakeModels:
        def generate_images(self, **_kwargs):
            calls["generate_images"] += 1
            raise AssertionError("legacy Gemini image generation must not use generate_images")

        def generate_content(self, model, contents, config):
            calls["generate_content"] += 1
            calls["model"] = model
            calls["contents"] = contents
            calls["config"] = config
            return pytypes.SimpleNamespace(parts=[FakePart()])

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    _install_fake_genai(monkeypatch, FakeClient, fake_types_module)
    monkeypatch.setattr(image_skill_module.tempfile, "gettempdir", lambda: str(tmp_path))

    skill = ImageSkill()

    async def fake_get_api_key():
        return "gemini-key"

    monkeypatch.setattr(skill, "_get_api_key", fake_get_api_key)

    result = asyncio.run(
        skill._generate_image_with_gemini(
            prompt="A quiet product shot",
            model="gemini-2.5-flash-image",
            config={},
            aspect_ratio="1:1",
        )
    )

    assert result["success"] is True
    assert calls["generate_content"] == 1
    assert calls["generate_images"] == 0
    assert calls["model"] == "gemini-2.5-flash-image"
    assert calls["contents"] == ["Generate an image: A quiet product shot"]
    assert calls["config"].kwargs == {"response_modalities": ["TEXT", "IMAGE"]}
    assert Path(result["output_path"]).name.startswith("img_gen_")


def test_imagen_edit_mode_fails_clearly_before_api_call(monkeypatch):
    skill = ImageSkill()

    async def fail_get_api_key():
        raise AssertionError("Imagen edit rejection should not call the Gemini API")

    monkeypatch.setattr(skill, "_get_api_key", fail_get_api_key)

    result = asyncio.run(
        skill._edit_image_with_gemini(
            image_path="/tmp/not-needed.png",
            instruction="make the sky blue",
            model="imagen-4.0-generate-001",
            config={},
        )
    )

    assert result["success"] is False
    assert "only supports text-to-image generation" in result["error"]
    assert "image editing" in result["error"]


def test_process_rejects_imagen_edit_with_skill_result(monkeypatch):
    skill = ImageSkill()

    async def fail_get_api_key():
        raise AssertionError("process should reject Imagen edit before API lookup")

    monkeypatch.setattr(skill, "_get_api_key", fail_get_api_key)

    message = InboundMessage(
        id="msg-1",
        sender="user",
        sender_key="user-1",
        body="change the background",
        chat_id="chat-1",
        chat_name=None,
        is_group=False,
        timestamp=datetime.utcnow(),
        media_type="image/png",
        media_path="/tmp/not-needed.png",
        channel="playground",
    )

    result = asyncio.run(
        skill.process(message, {"model": "imagen-4.0-ultra-generate-001"})
    )

    assert result.success is False
    assert "only supports text-to-image generation" in result.output
    assert result.metadata == {
        "error": "imagen_edit_unsupported",
        "model": "imagen-4.0-ultra-generate-001",
        "skip_ai": True,
    }


def test_openai_image_usage_is_tracked_with_openai_provider():
    captured = {}

    class FakeTracker:
        def track_usage(self, **kwargs):
            captured.update(kwargs)

    skill = ImageSkill(token_tracker=FakeTracker())
    message = InboundMessage(
        id="msg-2",
        sender="user",
        sender_key="user-2",
        body="generate an image",
        chat_id="chat-2",
        chat_name=None,
        is_group=False,
        timestamp=datetime.utcnow(),
        channel="playground",
    )

    skill._track_usage(
        model="gpt-image-2",
        instruction="generate an image",
        message=message,
        result={"input_tokens": 11, "output_tokens": 22},
        mode="generate",
    )

    assert captured["model_provider"] == "openai"
    assert captured["model_name"] == "gpt-image-2"
    assert captured["operation_type"] == "image_generate"
    assert captured["prompt_tokens"] == 11
    assert captured["completion_tokens"] == 22
