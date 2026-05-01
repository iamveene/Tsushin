from unittest.mock import MagicMock, patch


@patch("agent.ai_client.genai.GenerativeModel")
@patch("agent.ai_client.genai.configure")
@patch("agent.ai_client.get_api_key")
def test_gemini_tts_preview_model_falls_back_to_text_generation_model(
    mock_get_api_key,
    mock_configure,
    mock_generative_model,
):
    mock_get_api_key.return_value = "gemini-test-key"

    from agent.ai_client import AIClient

    client = AIClient(
        provider="gemini",
        model_name="gemini-3.1-flash-tts-preview",
        db=MagicMock(),
    )

    assert client.model_name == "gemini-2.5-flash"
    mock_configure.assert_called_once_with(api_key="gemini-test-key")
    mock_generative_model.assert_called_once_with("gemini-2.5-flash")


@patch("agent.ai_client.genai.GenerativeModel")
@patch("agent.ai_client.genai.configure")
@patch("agent.ai_client.get_api_key")
def test_gemini_pro_tts_preview_model_falls_back_to_matching_text_model(
    mock_get_api_key,
    _mock_configure,
    mock_generative_model,
):
    mock_get_api_key.return_value = "gemini-test-key"

    from agent.ai_client import AIClient

    client = AIClient(
        provider="gemini",
        model_name="gemini-2.5-pro-tts-preview",
        db=MagicMock(),
    )

    assert client.model_name == "gemini-2.5-pro"
    mock_generative_model.assert_called_once_with("gemini-2.5-pro")
