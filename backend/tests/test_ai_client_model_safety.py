from unittest.mock import patch


@patch("agent.ai_client.genai.GenerativeModel")
@patch("agent.ai_client.genai.configure")
def test_gemini_tts_preview_model_falls_back_to_text_generation_model(
    mock_configure,
    mock_generative_model,
):
    from agent.ai_client import AIClient

    client = AIClient(
        provider="gemini",
        model_name="gemini-3.1-flash-tts-preview",
        api_key="gemini-test-key",
    )

    assert client.model_name == "gemini-2.5-flash"
    mock_configure.assert_called_once_with(api_key="gemini-test-key")
    mock_generative_model.assert_called_once_with("gemini-2.5-flash")


@patch("agent.ai_client.genai.GenerativeModel")
@patch("agent.ai_client.genai.configure")
def test_gemini_pro_tts_preview_model_falls_back_to_matching_text_model(
    _mock_configure,
    mock_generative_model,
):
    from agent.ai_client import AIClient

    client = AIClient(
        provider="gemini",
        model_name="gemini-2.5-pro-tts-preview",
        api_key="gemini-test-key",
    )

    assert client.model_name == "gemini-2.5-pro"
    mock_generative_model.assert_called_once_with("gemini-2.5-pro")
