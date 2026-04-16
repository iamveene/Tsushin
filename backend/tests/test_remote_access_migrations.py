"""
Regression tests for the Remote Access migration fallback.
"""

import os
import sys
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrations.add_remote_access import upgrade_from_engine
from models import get_remote_access_proxy_target_url


def test_upgrade_from_engine_skips_non_sqlite_engines():
    engine = MagicMock()
    engine.dialect.name = "postgresql"

    with patch("migrations.add_remote_access.inspect") as mock_inspect:
        upgrade_from_engine(engine)

    mock_inspect.assert_not_called()


@patch.dict(os.environ, {"TSN_STACK_NAME": "tsushin-proofb"}, clear=False)
def test_upgrade_from_engine_seeds_stack_proxy_target_on_sqlite():
    engine = create_engine("sqlite:///:memory:", echo=False)
    try:
        upgrade_from_engine(engine)

        with engine.connect() as conn:
            target_url = conn.execute(
                text("SELECT target_url FROM remote_access_config WHERE id = 1")
            ).scalar_one()

        assert target_url == get_remote_access_proxy_target_url()
    finally:
        engine.dispose()
