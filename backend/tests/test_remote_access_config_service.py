"""
Regression tests for Remote Access config defaults, normalization, and backfill.
"""

import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

from models import Base, RemoteAccessConfig, get_remote_access_proxy_target_url
from services.remote_access_config_service import (
    backfill_remote_access_target_url,
    serialize_config,
    update_config,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


def _build_session():
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _seed_legacy_config(db_session):
    config = RemoteAccessConfig(
        id=1,
        target_url="http://frontend:3030",
    )
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    return config


class TestRemoteAccessConfigService:
    @patch.dict(os.environ, {"TSN_STACK_NAME": "tsushin-proofb"}, clear=False)
    def test_default_proxy_target_uses_stack_name(self):
        assert get_remote_access_proxy_target_url() == "http://tsushin-proofb-proxy:80"

    @patch.dict(os.environ, {"TSN_STACK_NAME": "tsushin-proofb"}, clear=False)
    def test_backfill_remote_access_target_url_repairs_legacy_frontend_target(self):
        db_session = _build_session()
        try:
            _seed_legacy_config(db_session)

            repaired = backfill_remote_access_target_url(db_session)
            expected_target = get_remote_access_proxy_target_url()

            assert repaired.target_url == expected_target
            assert (
                db_session.query(RemoteAccessConfig)
                .filter(RemoteAccessConfig.id == 1)
                .one()
                .target_url
                == expected_target
            )
        finally:
            db_session.close()

    @patch.dict(os.environ, {"TSN_STACK_NAME": "tsushin-proofb"}, clear=False)
    def test_update_config_normalizes_legacy_target_to_proxy_target(self):
        db_session = _build_session()
        try:
            _seed_legacy_config(db_session)
            expected_target = get_remote_access_proxy_target_url()

            with patch("services.remote_access_config_service.log_admin_action") as mock_log:
                updated = update_config(
                    db=db_session,
                    admin=SimpleNamespace(id=42, email="admin@example.com"),
                    payload={"target_url": "http://frontend:3030"},
                    expected_updated_at=None,
                    request=None,
                )

            assert updated.target_url == expected_target
            assert (
                db_session.query(RemoteAccessConfig)
                .filter(RemoteAccessConfig.id == 1)
                .one()
                .target_url
                == expected_target
            )
            mock_log.assert_not_called()
        finally:
            db_session.close()

    @patch.dict(os.environ, {"TSN_STACK_NAME": "tsushin-proofb"}, clear=False)
    def test_serialize_config_returns_proxy_target_for_legacy_row(self):
        db_session = _build_session()
        try:
            row = _seed_legacy_config(db_session)

            serialized = serialize_config(db_session, row)

            assert serialized["target_url"] == get_remote_access_proxy_target_url()
        finally:
            db_session.close()
