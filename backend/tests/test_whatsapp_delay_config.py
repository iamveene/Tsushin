from models import Config


def test_config_whatsapp_delay_default_and_update(test_db):
    config = Config(messages_db_path="test.db")
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)

    assert config.whatsapp_conversation_delay_seconds == 5.0

    config.whatsapp_conversation_delay_seconds = 7.5
    test_db.commit()
    test_db.refresh(config)

    assert config.whatsapp_conversation_delay_seconds == 7.5
