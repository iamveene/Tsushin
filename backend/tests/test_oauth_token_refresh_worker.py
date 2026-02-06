from datetime import datetime, timedelta

from hub.oauth_token_refresh_worker import OAuthTokenRefreshWorker
from models import CalendarIntegration, OAuthToken


def test_oauth_token_refresh_worker_filters_expiring_tokens(test_db, monkeypatch):
    engine = test_db.get_bind()

    integration = CalendarIntegration(
        type="calendar",
        name="Calendar - test@example.com",
        display_name="Calendar",
        email_address="test@example.com",
        authorized_at=datetime.utcnow(),
        is_active=True
    )
    test_db.add(integration)
    test_db.flush()

    expiring = OAuthToken(
        integration_id=integration.id,
        access_token_encrypted="access",
        refresh_token_encrypted="refresh",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    later = OAuthToken(
        integration_id=integration.id,
        access_token_encrypted="access2",
        refresh_token_encrypted="refresh2",
        expires_at=datetime.utcnow() + timedelta(days=2)
    )
    test_db.add_all([expiring, later])
    test_db.commit()

    worker = OAuthTokenRefreshWorker(
        engine,
        poll_interval_minutes=30,
        refresh_threshold_hours=24
    )

    called = []

    def record_refresh(db, token):
        called.append(token.integration_id)

    monkeypatch.setattr(worker, "_refresh_token", record_refresh)

    worker._check_and_refresh_tokens()

    assert called == [integration.id]
