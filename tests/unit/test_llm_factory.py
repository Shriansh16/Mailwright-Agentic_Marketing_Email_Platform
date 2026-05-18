from dotenv import load_dotenv

load_dotenv()

import pytest
from unittest.mock import patch

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

# Assuming mailwright is in PYTHONPATH or installed
from mailwright.core_services.llm_factory import get_configured_chat_model
from mailwright.config import Settings  # To mock settings

# Mock settings values for tests
MOCK_OPENAI_API_KEY = "fake_openai_key"
MOCK_ANTHROPIC_API_KEY = "fake_anthropic_key"
MOCK_OPENAI_MODEL = "gpt-test"
MOCK_ANTHROPIC_MODEL = "claude-test"


@pytest.fixture
def mock_settings_openai_configured():
    settings = Settings(
        OPENAI_API_KEY=MOCK_OPENAI_API_KEY,
        ANTHROPIC_API_KEY=None,  # Ensure only OpenAI is fully configured for this test
        DEFAULT_LLM_PROVIDER="openai",
        BRIEF_ANALYZER_PROVIDER="openai",
        BRIEF_ANALYZER_OPENAI_MODEL=MOCK_OPENAI_MODEL,
        BRIEF_ANALYZER_ANTHROPIC_MODEL=MOCK_ANTHROPIC_MODEL,
        # Add other required fields for Settings if any, with default values
    )
    return settings


@pytest.fixture
def mock_settings_anthropic_configured():
    settings = Settings(
        OPENAI_API_KEY=None,  # Ensure only Anthropic is fully configured
        ANTHROPIC_API_KEY=MOCK_ANTHROPIC_API_KEY,
        DEFAULT_LLM_PROVIDER="anthropic",
        BRIEF_ANALYZER_PROVIDER="anthropic",
        BRIEF_ANALYZER_OPENAI_MODEL=MOCK_OPENAI_MODEL,
        BRIEF_ANALYZER_ANTHROPIC_MODEL=MOCK_ANTHROPIC_MODEL,
    )
    return settings


@pytest.fixture
def mock_settings_no_api_keys():
    settings = Settings(
        OPENAI_API_KEY=None,
        ANTHROPIC_API_KEY=None,
        DEFAULT_LLM_PROVIDER="openai",  # Provider doesn't matter if keys are missing
        BRIEF_ANALYZER_PROVIDER="openai",
        BRIEF_ANALYZER_OPENAI_MODEL=MOCK_OPENAI_MODEL,
        BRIEF_ANALYZER_ANTHROPIC_MODEL=MOCK_ANTHROPIC_MODEL,
    )
    return settings


@patch("mailwright.core_services.llm_factory.settings")
def test_get_configured_chat_model_openai(
    mock_settings_obj, mock_settings_openai_configured
):
    mock_settings_obj.OPENAI_API_KEY = mock_settings_openai_configured.OPENAI_API_KEY
    mock_settings_obj.ANTHROPIC_API_KEY = (
        mock_settings_openai_configured.ANTHROPIC_API_KEY
    )  # Keep it consistent
    # No need to mock other settings if the factory only reads API keys directly from the global `settings`

    llm = get_configured_chat_model(
        task_provider_config_value="openai",
        task_openai_model_config_value=MOCK_OPENAI_MODEL,
        task_anthropic_model_config_value=MOCK_ANTHROPIC_MODEL,
        temperature=0.5,
        custom_arg="test_val",
    )
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == MOCK_OPENAI_MODEL
    assert llm.temperature == 0.5
    assert (
        llm.openai_api_key.get_secret_value() == MOCK_OPENAI_API_KEY
    )  # Use get_secret_value()
    # To check custom_arg, you might need to inspect llm.model_kwargs or similar,
    # depending on how ChatOpenAI handles extra kwargs.
    # For ChatOpenAI, extra kwargs are often passed to model_kwargs
    assert llm.model_kwargs.get("custom_arg") == "test_val"


@patch("mailwright.core_services.llm_factory.settings")
def test_get_configured_chat_model_anthropic(
    mock_settings_obj, mock_settings_anthropic_configured
):
    mock_settings_obj.OPENAI_API_KEY = mock_settings_anthropic_configured.OPENAI_API_KEY
    mock_settings_obj.ANTHROPIC_API_KEY = (
        mock_settings_anthropic_configured.ANTHROPIC_API_KEY
    )

    llm = get_configured_chat_model(
        task_provider_config_value="anthropic",
        task_openai_model_config_value=MOCK_OPENAI_MODEL,
        task_anthropic_model_config_value=MOCK_ANTHROPIC_MODEL,
        temperature=0.3,
    )
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == MOCK_ANTHROPIC_MODEL  # Correct attribute is 'model'
    assert llm.temperature == 0.3
    assert (
        llm.anthropic_api_key.get_secret_value() == MOCK_ANTHROPIC_API_KEY
    )  # Use get_secret_value()


@patch("mailwright.core_services.llm_factory.settings")
def test_get_configured_chat_model_unsupported_provider(
    mock_settings_obj, mock_settings_openai_configured
):
    mock_settings_obj.OPENAI_API_KEY = (
        mock_settings_openai_configured.OPENAI_API_KEY
    )  # Irrelevant but set for completeness

    with pytest.raises(
        ValueError, match="Unsupported LLM provider configured for the task: unknown"
    ):
        get_configured_chat_model(
            task_provider_config_value="unknown",
            task_openai_model_config_value=MOCK_OPENAI_MODEL,
            task_anthropic_model_config_value=MOCK_ANTHROPIC_MODEL,
        )


@patch("mailwright.core_services.llm_factory.settings")
def test_get_configured_chat_model_openai_missing_key(
    mock_settings_obj, mock_settings_no_api_keys
):
    mock_settings_obj.OPENAI_API_KEY = mock_settings_no_api_keys.OPENAI_API_KEY
    mock_settings_obj.ANTHROPIC_API_KEY = mock_settings_no_api_keys.ANTHROPIC_API_KEY

    with pytest.raises(ValueError, match="OPENAI_API_KEY is not set in configuration."):
        get_configured_chat_model(
            task_provider_config_value="openai",
            task_openai_model_config_value=MOCK_OPENAI_MODEL,
            task_anthropic_model_config_value=MOCK_ANTHROPIC_MODEL,
        )


@patch("mailwright.core_services.llm_factory.settings")
def test_get_configured_chat_model_anthropic_missing_key(
    mock_settings_obj, mock_settings_no_api_keys
):
    mock_settings_obj.OPENAI_API_KEY = mock_settings_no_api_keys.OPENAI_API_KEY
    mock_settings_obj.ANTHROPIC_API_KEY = mock_settings_no_api_keys.ANTHROPIC_API_KEY

    with pytest.raises(
        ValueError, match="ANTHROPIC_API_KEY is not set in configuration."
    ):
        get_configured_chat_model(
            task_provider_config_value="anthropic",
            task_openai_model_config_value=MOCK_OPENAI_MODEL,
            task_anthropic_model_config_value=MOCK_ANTHROPIC_MODEL,
        )
