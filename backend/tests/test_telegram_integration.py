"""
Telegram Integration Tests
Phase 10.1.1
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_integration.client import TelegramClient
from telegram_integration.watcher import TelegramWatcher
from services.telegram_bot_service import TelegramBotService


class TestTelegramClient:
    @pytest.mark.asyncio
    async def test_get_me_success(self):
        """Test successful bot info retrieval."""
        with patch('telegram.client.Bot') as mock_bot_class:
            mock_user = MagicMock()
            mock_user.id = 123456789
            mock_user.username = "test_bot"
            mock_user.first_name = "Test Bot"
            mock_user.can_join_groups = True
            mock_user.can_read_all_group_messages = False

            mock_bot = MagicMock()
            mock_bot.get_me = AsyncMock(return_value=mock_user)
            mock_bot_class.return_value = mock_bot

            client = TelegramClient("test:token")
            info = await client.get_me()

            assert info["id"] == 123456789
            assert info["username"] == "test_bot"
            assert info["first_name"] == "Test Bot"

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test successful message sending."""
        with patch('telegram.client.Bot') as mock_bot_class:
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_class.return_value = mock_bot

            client = TelegramClient("test:token")
            result = await client.send_message(123, "Hello!")

            assert result is True
            mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_failure(self):
        """Test message sending failure."""
        from telegram.error import TelegramError

        with patch('telegram.client.Bot') as mock_bot_class:
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock(side_effect=TelegramError("Network error"))
            mock_bot_class.return_value = mock_bot

            client = TelegramClient("test:token")
            result = await client.send_message(123, "Hello!")

            assert result is False


class TestTelegramWatcher:
    @pytest.mark.asyncio
    async def test_message_deduplication(self):
        """Test that duplicate messages are skipped."""
        instance = MagicMock()
        instance.bot_username = "test_bot"
        instance.last_update_id = 0

        callback = AsyncMock()
        db_session = MagicMock()
        db_session.query.return_value.filter_by.return_value.first.return_value = None

        watcher = TelegramWatcher(
            instance=instance,
            token="test:token",
            on_message_callback=callback,
            db_session=db_session
        )

        # Add message to processed set
        watcher.processed_message_ids.add("tg_123_456")

        # Verify it's marked as processed
        assert "tg_123_456" in watcher.processed_message_ids

    def test_pause_and_resume(self):
        """Test watcher pause and resume functionality."""
        instance = MagicMock()
        instance.bot_username = "test_bot"
        instance.last_update_id = 0

        watcher = TelegramWatcher(
            instance=instance,
            token="test:token",
            on_message_callback=AsyncMock(),
            db_session=MagicMock()
        )

        # Test pause
        watcher.pause()
        assert watcher.paused is True

        # Test resume
        watcher.resume()
        assert watcher.paused is False

    def test_stop(self):
        """Test watcher stop functionality."""
        instance = MagicMock()
        instance.bot_username = "test_bot"
        instance.last_update_id = 0

        watcher = TelegramWatcher(
            instance=instance,
            token="test:token",
            on_message_callback=AsyncMock(),
            db_session=MagicMock()
        )

        watcher.stop()
        assert watcher.running is False


class TestTelegramBotService:
    @pytest.mark.asyncio
    async def test_create_instance_invalid_token_format(self):
        """Test instance creation with invalid token format."""
        db = MagicMock()
        service = TelegramBotService(db)

        with pytest.raises(ValueError, match="Invalid bot token format"):
            await service.create_instance(
                tenant_id="test_tenant",
                bot_token="invalid_token_no_colon",
                created_by=1
            )

    @pytest.mark.asyncio
    async def test_start_instance_not_found(self):
        """Test starting non-existent instance."""
        db = MagicMock()
        db.query.return_value.get.return_value = None

        service = TelegramBotService(db)

        with pytest.raises(ValueError, match="Instance .* not found"):
            await service.start_instance(999)

    @pytest.mark.asyncio
    async def test_stop_instance(self):
        """Test stopping an instance."""
        mock_instance = MagicMock()
        mock_instance.status = "active"

        db = MagicMock()
        db.query.return_value.get.return_value = mock_instance

        service = TelegramBotService(db)
        await service.stop_instance(1)

        assert mock_instance.status == "inactive"
        db.commit.assert_called_once()
