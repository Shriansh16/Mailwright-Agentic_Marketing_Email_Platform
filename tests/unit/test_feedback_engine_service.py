import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from mailwright.config import Settings
from mailwright.core_services.feedback_engine_service import (
    FeedbackEngineService,
    FeedbackEngineServiceError,
)
from langchain_core.messages import AIMessage
from langchain_core.language_models.chat_models import BaseChatModel


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        OPENAI_API_KEY="test_key_openai",
        ANTHROPIC_API_KEY="test_key_anthropic",
        FEEDBACK_ENGINE_PROVIDER="openai",
        FEEDBACK_ENGINE_OPENAI_MODEL="gpt-test",
        FEEDBACK_ENGINE_ANTHROPIC_MODEL="claude-test",
    )


@pytest_asyncio.fixture
async def feedback_service(mock_settings: Settings):
    with (
        patch("mailwright.core_services.feedback_engine_service.settings", mock_settings),
        patch("mailwright.core_services.llm_factory.settings", mock_settings, create=True),
        patch(
            "mailwright.core_services.feedback_engine_service.get_configured_chat_model"
        ) as mock_get_llm_factory_call,
    ):
        mock_llm_instance = AsyncMock(spec=BaseChatModel)
        mock_llm_instance.ainvoke = AsyncMock()
        mock_get_llm_factory_call.return_value = mock_llm_instance

        service = FeedbackEngineService()
        yield service, mock_llm_instance, mock_get_llm_factory_call


@pytest.mark.asyncio
async def test_revise_mjml_successful(feedback_service):
    service, mock_llm, _ = feedback_service
    current_mjml = "<mjml><mj-body><mj-text>Hello</mj-text></mj-body></mjml>"
    feedback = "Change Hello to Goodbye"

    mock_llm_response_content = (
        "<mjml><mj-body><mj-text>Goodbye</mj-text></mj-body></mjml>"
    )
    mock_llm.ainvoke.return_value = AIMessage(content=mock_llm_response_content)

    revised_mjml = await service.revise_mjml_based_on_feedback(current_mjml, feedback)

    assert revised_mjml == mock_llm_response_content
    mock_llm.ainvoke.assert_called_once()

    called_prompt = mock_llm.ainvoke.call_args[0][0]
    assert "Original MJML:" in called_prompt
    assert current_mjml in called_prompt
    assert "User Feedback:" in called_prompt
    assert feedback in called_prompt
    assert "Revised MJML:" in called_prompt


@pytest.mark.asyncio
async def test_revise_mjml_llm_returns_markdown_block(feedback_service):
    service, mock_llm, _ = feedback_service
    current_mjml = "<mjml><mj-body><mj-text>Content</mj-text></mj-body></mjml>"
    feedback = "Wrap in section."

    raw_llm_response = "```mjml\n<mjml><mj-body><mj-section><mj-column><mj-text>Content</mj-text></mj-column></mj-section></mj-body></mjml>\n```"
    expected_cleaned_mjml = "<mjml><mj-body><mj-section><mj-column><mj-text>Content</mj-text></mj-column></mj-section></mj-body></mjml>"
    mock_llm.ainvoke.return_value = AIMessage(content=raw_llm_response)

    revised_mjml = await service.revise_mjml_based_on_feedback(current_mjml, feedback)

    assert revised_mjml == expected_cleaned_mjml
    mock_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_revise_mjml_empty_inputs(feedback_service):
    service, _, _ = feedback_service
    with pytest.raises(
        ValueError, match="Current MJML and feedback text cannot be empty."
    ):
        await service.revise_mjml_based_on_feedback("", "feedback")

    with pytest.raises(
        ValueError, match="Current MJML and feedback text cannot be empty."
    ):
        await service.revise_mjml_based_on_feedback("<mjml></mjml>", "")


@pytest.mark.asyncio
async def test_revise_mjml_llm_call_fails(feedback_service):
    service, mock_llm, _ = feedback_service
    current_mjml = "<mjml>...</mjml>"
    feedback = "Make it better"

    mock_llm.ainvoke.side_effect = Exception("LLM API Error")

    with pytest.raises(
        FeedbackEngineServiceError,
        match="Failed to revise MJML using LLM: LLM API Error",
    ):
        await service.revise_mjml_based_on_feedback(current_mjml, feedback)
    mock_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_revise_mjml_llm_returns_empty_content(feedback_service):
    service, mock_llm, _ = feedback_service
    current_mjml = "<mjml>...</mjml>"
    feedback = "Make it better"

    mock_llm.ainvoke.return_value = AIMessage(content="")

    with pytest.raises(
        FeedbackEngineServiceError,
        match="LLM returned empty content for MJML revision.",
    ):
        await service.revise_mjml_based_on_feedback(current_mjml, feedback)
    mock_llm.ainvoke.assert_called_once()


def test_feedback_service_initialization_fails(mock_settings: Settings):
    with (
        patch(
            "mailwright.core_services.feedback_engine_service.get_configured_chat_model",
            side_effect=Exception("Config Error"),
        ) as mock_get_llm,
        patch("mailwright.core_services.feedback_engine_service.settings", mock_settings),
    ):
        with pytest.raises(
            FeedbackEngineServiceError,
            match="Could not initialize LLM client: Config Error",
        ):
            FeedbackEngineService()
        mock_get_llm.assert_called_once()
