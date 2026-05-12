from typing import Any
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from mailwright.config import settings


def get_configured_chat_model(
    task_provider_config_value: str,
    task_openai_model_config_value: str,
    task_anthropic_model_config_value: str,
    temperature: float = 0.7,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Instantiates and returns a LangChain chat model based on task-specific configuration values.

    Args:
        task_provider_config_value: The configured provider ("openai" or "anthropic").
        task_openai_model_config_value: The OpenAI model name to use if provider is "openai".
        task_anthropic_model_config_value: The Anthropic model name to use if provider is "anthropic".
        temperature: The temperature setting for the LLM.
        **kwargs: Additional keyword arguments to pass to the LLM constructor.

    Returns:
        An instance of BaseChatModel (ChatOpenAI or ChatAnthropic).

    Raises:
        ValueError: If an unsupported provider is configured or API key is missing.
    """
    provider = task_provider_config_value

    if provider == "openai":
        model_name = task_openai_model_config_value
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set in configuration.")
        return ChatOpenAI(
            model_name=model_name, api_key=api_key, temperature=temperature, **kwargs
        )
    elif provider == "anthropic":
        model_name = task_anthropic_model_config_value
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set in configuration.")
        return ChatAnthropic(
            model=model_name,  # Correct attribute for ChatAnthropic is 'model'
            api_key=api_key,
            temperature=temperature,
            max_tokens=16384,  # Set a generous token limit for HTML generation
            **kwargs,
        )
    else:
        raise ValueError(
            f"Unsupported LLM provider configured for the task: {provider}"
        )
