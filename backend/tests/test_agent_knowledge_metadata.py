import os
import sys
import types
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sentence_transformers_stub = types.ModuleType("sentence_transformers")


class _SentenceTransformer:
    def __init__(self, *_args, **_kwargs):
        pass


sentence_transformers_stub.SentenceTransformer = _SentenceTransformer
sys.modules.setdefault("sentence_transformers", sentence_transformers_stub)

chromadb_stub = types.ModuleType("chromadb")


class _PersistentClient:
    def __init__(self, *_args, **_kwargs):
        pass


chromadb_stub.PersistentClient = _PersistentClient
sys.modules.setdefault("chromadb", chromadb_stub)

chromadb_config_stub = types.ModuleType("chromadb.config")


class _Settings:
    def __init__(self, *_args, **_kwargs):
        pass


chromadb_config_stub.Settings = _Settings
sys.modules.setdefault("chromadb.config", chromadb_config_stub)

from agent.knowledge.knowledge_service import (  # noqa: E402
    KnowledgeMetadataError,
    KnowledgeService,
    normalize_document_tags,
    sanitize_document_name,
)
import agent.knowledge.knowledge_service as knowledge_service_module  # noqa: E402


class _FakeQuery:
    def __init__(self, record):
        self.record = record

    def get(self, knowledge_id):
        if self.record and self.record.id == knowledge_id:
            return self.record
        return None


class _FakeDb:
    def __init__(self, record, *, fail_on_commit=False):
        self.record = record
        self.commits = 0
        self.flushes = 0
        self.refreshes = 0
        self.rollbacks = 0
        self.fail_on_commit = fail_on_commit

    def query(self, _model):
        return _FakeQuery(self.record)

    def add(self, record):
        self.record = record

    def flush(self):
        self.flushes += 1
        if self.record is not None and getattr(self.record, "id", None) is None:
            self.record.id = 101

    def commit(self):
        self.commits += 1
        if self.fail_on_commit:
            raise RuntimeError("commit failed")

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, record):
        self.refreshes += 1
        self.record = record


def _make_service(record, *, storage_dir=None, fail_on_commit=False):
    service = KnowledgeService.__new__(KnowledgeService)
    service.db = _FakeDb(record, fail_on_commit=fail_on_commit)
    service.storage_dir = Path(storage_dir) if storage_dir else Path.cwd()
    return service


def test_sanitize_document_name_strips_path_and_whitespace():
    assert sanitize_document_name("  ../Quarterly\nReport.pdf  ") == "Quarterly Report.pdf"


def test_normalize_document_tags_deduplicates_and_limits():
    tags = normalize_document_tags([" Billing ", "billing", "FAQ", "", "Onboarding Team"])
    assert tags == ["billing", "faq", "onboarding team"]


def test_normalize_document_tags_rejects_overlong_or_excessive_input():
    with pytest.raises(ValueError, match="48 characters or fewer"):
        normalize_document_tags(["x" * 49])

    with pytest.raises(ValueError, match="up to 12 tags"):
        normalize_document_tags([f"tag-{index}" for index in range(13)])


def test_update_document_persists_name_and_tags_without_schema_change(tmp_path):
    document_path = tmp_path / "policy.pdf"
    document_path.write_text("stub", encoding="utf-8")

    knowledge = SimpleNamespace(
        id=7,
        document_name="Original.pdf",
        file_path=str(document_path),
        updated_at=None,
    )
    service = _make_service(knowledge)

    updated = service.update_document(
        knowledge_id=7,
        document_name="  Customer Success Playbook  ",
        tags=["Billing", "how-to", "billing"],
    )

    metadata_path = Path(f"{document_path}.meta.json")
    assert updated is knowledge
    assert updated.document_name == "Customer Success Playbook"
    assert updated.tags == ["billing", "how-to"]
    assert isinstance(updated.updated_at, datetime)
    assert metadata_path.exists()
    assert service.db.commits == 1
    assert service.db.flushes == 1
    assert service.db.refreshes == 1


def test_get_document_tags_returns_empty_list_when_metadata_missing(tmp_path):
    document_path = tmp_path / "faq.txt"
    document_path.write_text("stub", encoding="utf-8")

    knowledge = SimpleNamespace(
        id=8,
        document_name="FAQ.txt",
        file_path=str(document_path),
        updated_at=None,
    )
    service = _make_service(knowledge)

    assert service.get_document_tags(knowledge) == []


def test_get_document_tags_raises_for_corrupt_metadata(tmp_path):
    document_path = tmp_path / "faq.txt"
    document_path.write_text("stub", encoding="utf-8")
    metadata_path = Path(f"{document_path}.meta.json")
    metadata_path.write_text("{not-json", encoding="utf-8")

    knowledge = SimpleNamespace(
        id=9,
        document_name="FAQ.txt",
        file_path=str(document_path),
        updated_at=None,
    )
    service = _make_service(knowledge)

    with pytest.raises(KnowledgeMetadataError, match="unreadable"):
        service.get_document_tags(knowledge)


def test_update_document_restores_sidecar_when_commit_fails(tmp_path):
    document_path = tmp_path / "playbook.txt"
    document_path.write_text("stub", encoding="utf-8")
    metadata_path = Path(f"{document_path}.meta.json")
    metadata_path.write_text(json.dumps({"tags": ["existing"]}), encoding="utf-8")

    knowledge = SimpleNamespace(
        id=10,
        document_name="Playbook.txt",
        file_path=str(document_path),
        updated_at=None,
    )
    service = _make_service(knowledge, fail_on_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        service.update_document(knowledge_id=10, tags=["replacement"])

    restored = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert restored == {"tags": ["existing"]}
    assert service.db.rollbacks == 1


def test_upload_document_rolls_back_stored_file_when_metadata_write_fails(tmp_path, monkeypatch):
    source_path = tmp_path / "notes.txt"
    source_path.write_text("hello world", encoding="utf-8")
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()

    service = _make_service(None, storage_dir=storage_dir)

    def fail_write(_knowledge, _metadata):
        raise KnowledgeMetadataError("metadata write failed")

    class _StubAgentKnowledge:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr(knowledge_service_module, "AgentKnowledge", _StubAgentKnowledge)
    monkeypatch.setattr(service, "_write_document_metadata_atomically", fail_write)

    with pytest.raises(KnowledgeMetadataError, match="metadata write failed"):
        service.upload_document(
            agent_id=42,
            file_path=str(source_path),
            document_name="notes.txt",
            document_type="txt",
        )

    agent_dir = storage_dir / "agent_42"
    stored_files = [path for path in agent_dir.rglob("*") if path.is_file()] if agent_dir.exists() else []
    assert stored_files == []
    assert service.db.rollbacks == 1
