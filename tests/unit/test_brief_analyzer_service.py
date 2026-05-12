import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock

# Assuming mailwright is in PYTHONPATH or installed
from mailwright.core_services.brief_analyzer_service import analyze_brief_for_clarifications
from mailwright.schemas.template_schemas import UserBriefSchema
from mailwright.config import Settings  # To mock settings

# Mock settings values for tests
MOCK_OPENAI_API_KEY = "fake_openai_key"
MOCK_ANTHROPIC_API_KEY = "fake_anthropic_key"
MOCK_OPENAI_MODEL = "gpt-test-analyzer"
MOCK_ANTHROPIC_MODEL = "claude-test-analyzer"


@pytest.fixture
def sample_user_brief():
    return UserBriefSchema(
        subject="Test Subject",
        body_copy="Test body copy.",
        image_suggestions=["image1.jpg", "image2.png"],
        cta_text="Click Here",
        cta_url="http://example.com",
    )


@pytest.fixture
def mock_settings_openai_brief_analyzer():
    # This fixture provides settings configured for OpenAI for the brief analyzer
    return Settings(
        OPENAI_API_KEY=MOCK_OPENAI_API_KEY,
        ANTHROPIC_API_KEY=MOCK_ANTHROPIC_API_KEY,  # Can be set or None
        DEFAULT_LLM_PROVIDER="openai",
        BRIEF_ANALYZER_PROVIDER="openai",
        BRIEF_ANALYZER_OPENAI_MODEL=MOCK_OPENAI_MODEL,
        BRIEF_ANALYZER_ANTHROPIC_MODEL=MOCK_ANTHROPIC_MODEL,
        # Ensure other task-specific settings are also present if Settings expects them
        MJML_GENERATION_PROVIDER="openai",
        MJML_GENERATION_OPENAI_MODEL="gpt-test",
        MJML_GENERATION_ANTHROPIC_MODEL="claude-test",
        FEEDBACK_ENGINE_PROVIDER="openai",
        FEEDBACK_ENGINE_OPENAI_MODEL="gpt-test",
        FEEDBACK_ENGINE_ANTHROPIC_MODEL="claude-test",
    )


@pytest.fixture
def mock_settings_anthropic_brief_analyzer():
    # This fixture provides settings configured for Anthropic for the brief analyzer
    return Settings(
        OPENAI_API_KEY=MOCK_OPENAI_API_KEY,  # Can be set or None
        ANTHROPIC_API_KEY=MOCK_ANTHROPIC_API_KEY,
        DEFAULT_LLM_PROVIDER="anthropic",
        BRIEF_ANALYZER_PROVIDER="anthropic",
        BRIEF_ANALYZER_OPENAI_MODEL=MOCK_OPENAI_MODEL,
        BRIEF_ANALYZER_ANTHROPIC_MODEL=MOCK_ANTHROPIC_MODEL,
        MJML_GENERATION_PROVIDER="anthropic",
        MJML_GENERATION_OPENAI_MODEL="gpt-test",
        MJML_GENERATION_ANTHROPIC_MODEL="claude-test",
        FEEDBACK_ENGINE_PROVIDER="anthropic",
        FEEDBACK_ENGINE_OPENAI_MODEL="gpt-test",
        FEEDBACK_ENGINE_ANTHROPIC_MODEL="claude-test",
    )


@pytest.mark.asyncio
@patch("mailwright.core_services.brief_analyzer_service.settings")
@patch("mailwright.core_services.brief_analyzer_service.get_configured_chat_model")
async def test_analyze_brief_status_ok(
    mock_get_llm,
    mock_settings_obj,
    sample_user_brief,
    mock_settings_openai_brief_analyzer,
):
    mock_settings_obj.BRIEF_ANALYZER_PROVIDER = (
        mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_PROVIDER
    )
    mock_settings_obj.BRIEF_ANALYZER_OPENAI_MODEL = (
        mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_OPENAI_MODEL
    )
    mock_settings_obj.BRIEF_ANALYZER_ANTHROPIC_MODEL = (
        mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_ANTHROPIC_MODEL
    )
    mock_settings_obj.OPENAI_API_KEY = (
        mock_settings_openai_brief_analyzer.OPENAI_API_KEY
    )
    mock_settings_obj.ANTHROPIC_API_KEY = (
        mock_settings_openai_brief_analyzer.ANTHROPIC_API_KEY
    )

    mock_llm_instance = AsyncMock()
    mock_llm_instance.ainvoke = AsyncMock(
        return_value=json.dumps({"status": "BRIEF_OK"})
    )

    # Mock the chain components
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=json.dumps({"status": "BRIEF_OK"}))

    # Patch the chain creation part if LC_BRIEF_ANALYZER_PROMPT | llm | StrOutputParser() is complex
    # For simplicity, here we assume get_configured_chat_model returns something that, when chained,
    # results in an object whose ainvoke can be mocked.
    # A more direct way is to mock the final chain object if possible.

    # Let's refine the mocking to target the chain directly if the structure is `prompt | llm | parser`
    # We need to mock the result of this chain.
    # For this, we can patch `StrOutputParser` or the `llm` that `get_configured_chat_model` returns.

    mock_get_llm.return_value = mock_llm_instance  # llm part of the chain

    # To mock the full chain `LC_BRIEF_ANALYZER_PROMPT | llm | StrOutputParser()`
    # we can patch the `ainvoke` of the final object in the chain.
    # If StrOutputParser().ainvoke is called, mock that.
    # Or, if the llm.ainvoke is what ultimately produces the string, mock that.
    # The current brief_analyzer_service.py uses `chain = LC_BRIEF_ANALYZER_PROMPT | llm | StrOutputParser()`
    # and then `await chain.ainvoke(...)`. So we mock `chain.ainvoke`.
    # This requires `chain` to be an object we can patch.
    # A simpler way for this test is to ensure `get_configured_chat_model` returns an LLM
    # whose `ainvoke` (when used in the chain) results in the mocked response.
    # The `StrOutputParser` will just pass this string through.

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock
    ) as mock_chain_ainvoke:
        mock_chain_ainvoke.return_value = json.dumps({"status": "BRIEF_OK"})

        result = await analyze_brief_for_clarifications(sample_user_brief)

    assert result.status == "BRIEF_OK"
    assert result.clarification_questions is None
    assert result.error_message is None
    mock_get_llm.assert_called_once()
    # Check if response_format was passed for openai if applicable
    if (
        mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_PROVIDER == "openai"
        and mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_OPENAI_MODEL
        in [
            "gpt-4-turbo-preview",
            "gpt-4-0125-preview",
            "gpt-3.5-turbo-1106",
            "gpt-3.5-turbo-0125",
        ]
    ):
        assert mock_get_llm.call_args.kwargs.get("response_format") == {
            "type": "json_object"
        }


@pytest.mark.asyncio
@patch("mailwright.core_services.brief_analyzer_service.settings")
@patch("mailwright.core_services.brief_analyzer_service.get_configured_chat_model")
async def test_analyze_brief_clarification_needed(
    mock_get_llm,
    mock_settings_obj,
    sample_user_brief,
    mock_settings_anthropic_brief_analyzer,
):
    mock_settings_obj.BRIEF_ANALYZER_PROVIDER = (
        mock_settings_anthropic_brief_analyzer.BRIEF_ANALYZER_PROVIDER
    )
    mock_settings_obj.BRIEF_ANALYZER_OPENAI_MODEL = (
        mock_settings_anthropic_brief_analyzer.BRIEF_ANALYZER_OPENAI_MODEL
    )
    mock_settings_obj.BRIEF_ANALYZER_ANTHROPIC_MODEL = (
        mock_settings_anthropic_brief_analyzer.BRIEF_ANALYZER_ANTHROPIC_MODEL
    )
    mock_settings_obj.OPENAI_API_KEY = (
        mock_settings_anthropic_brief_analyzer.OPENAI_API_KEY
    )
    mock_settings_obj.ANTHROPIC_API_KEY = (
        mock_settings_anthropic_brief_analyzer.ANTHROPIC_API_KEY
    )

    questions = ["Question 1?", "Question 2?"]

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock
    ) as mock_chain_ainvoke:
        mock_chain_ainvoke.return_value = json.dumps(
            {"clarification_questions": questions}
        )
        result = await analyze_brief_for_clarifications(sample_user_brief)

    assert result.status == "CLARIFICATION_NEEDED"
    assert result.clarification_questions == questions
    assert result.error_message is None
    mock_get_llm.assert_called_once()


@pytest.mark.asyncio
@patch("mailwright.core_services.brief_analyzer_service.settings")
@patch("mailwright.core_services.brief_analyzer_service.get_configured_chat_model")
async def test_analyze_brief_json_decode_error(
    mock_get_llm,
    mock_settings_obj,
    sample_user_brief,
    mock_settings_openai_brief_analyzer,
):
    mock_settings_obj.BRIEF_ANALYZER_PROVIDER = (
        mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_PROVIDER
    )
    # ... (set other mock_settings_obj attributes as in previous tests) ...
    mock_settings_obj.OPENAI_API_KEY = (
        mock_settings_openai_brief_analyzer.OPENAI_API_KEY
    )
    mock_settings_obj.ANTHROPIC_API_KEY = (
        mock_settings_openai_brief_analyzer.ANTHROPIC_API_KEY
    )

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock
    ) as mock_chain_ainvoke:
        mock_chain_ainvoke.return_value = "This is not JSON"
        result = await analyze_brief_for_clarifications(sample_user_brief)

    assert result.status == "CLARIFICATION_NEEDED"  # Fallback behavior
    assert "issue processing the brief" in result.clarification_questions[0]
    assert result.error_message == "Failed to parse LLM response as JSON."


@pytest.mark.asyncio
@patch("mailwright.core_services.brief_analyzer_service.settings")
@patch("mailwright.core_services.brief_analyzer_service.get_configured_chat_model")
async def test_analyze_brief_unexpected_json_format(
    mock_get_llm,
    mock_settings_obj,
    sample_user_brief,
    mock_settings_openai_brief_analyzer,
):
    mock_settings_obj.BRIEF_ANALYZER_PROVIDER = (
        mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_PROVIDER
    )
    # ... (set other mock_settings_obj attributes) ...
    mock_settings_obj.OPENAI_API_KEY = (
        mock_settings_openai_brief_analyzer.OPENAI_API_KEY
    )
    mock_settings_obj.ANTHROPIC_API_KEY = (
        mock_settings_openai_brief_analyzer.ANTHROPIC_API_KEY
    )

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock
    ) as mock_chain_ainvoke:
        mock_chain_ainvoke.return_value = json.dumps({"unexpected_key": "some_value"})
        result = await analyze_brief_for_clarifications(sample_user_brief)

    assert result.status == "CLARIFICATION_NEEDED"  # Fallback behavior
    assert "AI assistant's analysis was unclear" in result.clarification_questions[0]
    assert result.error_message == "LLM response format unexpected."


@pytest.mark.asyncio
@patch("mailwright.core_services.brief_analyzer_service.settings")
@patch("mailwright.core_services.brief_analyzer_service.get_configured_chat_model")
async def test_analyze_brief_llm_call_exception(
    mock_get_llm,
    mock_settings_obj,
    sample_user_brief,
    mock_settings_openai_brief_analyzer,
):
    mock_settings_obj.BRIEF_ANALYZER_PROVIDER = (
        mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_PROVIDER
    )
    # ... (set other mock_settings_obj attributes) ...
    mock_settings_obj.OPENAI_API_KEY = (
        mock_settings_openai_brief_analyzer.OPENAI_API_KEY
    )
    mock_settings_obj.ANTHROPIC_API_KEY = (
        mock_settings_openai_brief_analyzer.ANTHROPIC_API_KEY
    )

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock
    ) as mock_chain_ainvoke:
        mock_chain_ainvoke.side_effect = Exception("LLM API is down")
        result = await analyze_brief_for_clarifications(sample_user_brief)

    assert result.status == "ERROR"
    assert result.clarification_questions is None
    assert "LLM API is down" in result.error_message


@pytest.mark.asyncio
@patch("mailwright.core_services.brief_analyzer_service.settings")
@patch("mailwright.core_services.brief_analyzer_service.get_configured_chat_model")
async def test_analyze_brief_empty_llm_response(
    mock_get_llm,
    mock_settings_obj,
    sample_user_brief,
    mock_settings_openai_brief_analyzer,
):
    mock_settings_obj.BRIEF_ANALYZER_PROVIDER = (
        mock_settings_openai_brief_analyzer.BRIEF_ANALYZER_PROVIDER
    )
    # ... (set other mock_settings_obj attributes) ...
    mock_settings_obj.OPENAI_API_KEY = (
        mock_settings_openai_brief_analyzer.OPENAI_API_KEY
    )
    mock_settings_obj.ANTHROPIC_API_KEY = (
        mock_settings_openai_brief_analyzer.ANTHROPIC_API_KEY
    )

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock
    ) as mock_chain_ainvoke:
        mock_chain_ainvoke.return_value = ""  # Empty string response
        result = await analyze_brief_for_clarifications(sample_user_brief)

    assert result.status == "ERROR"  # Code returns ERROR for empty response
    assert (
        result.clarification_questions is None
    )  # No questions when it's an ERROR status
    assert result.error_message == "LLM returned empty response."
