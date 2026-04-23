import os
import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


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
    KnowledgeService,
    normalize_document_tags,
    sanitize_document_name,
)


class _FakeQuery:
    def __init__(self, record):
        self.record = record

    def get(self, knowledge_id):
        if self.record and self.record.id == knowledge_id:
            return self.record
        return None


class _FakeDb:
    def __init__(self, record):
        self.record = record
        self.commits = 0
        self.refreshes = 0

    def query(self, _model):
        return _FakeQuery(self.record)

    def commit(self):
        self.commits += 1

    def refresh(self, record):
        self.refreshes += 1
        self.record = record


def _make_service(record):
    service = KnowledgeService.__new__(KnowledgeService)
    service.db = _FakeDb(record)
    return service


def test_sanitize_document_name_strips_path_and_whitespace():
    assert sanitize_document_name("  ../Quarterly\nReport.pdf  ") == "Quarterly Report.pdf"


def test_normalize_document_tags_deduplicates_and_limits():
    tags = normalize_document_tags([" Billing ", "billing", "FAQ", "", "Onboarding Team"])
    assert tags == ["billing", "faq", "onboarding team"]


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
