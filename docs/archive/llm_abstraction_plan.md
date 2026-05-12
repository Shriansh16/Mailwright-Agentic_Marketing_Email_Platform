# Plan: Flexible LLM Provider Abstraction and Testing

This document outlines the plan for enabling flexible switching between LLM providers (e.g., OpenAI, Anthropic) within the Mailwright - Agentic Marketing Email Platform, leveraging LangChain's native model I/O capabilities. It also includes the associated testing strategy.

## 1. Revised Plan: Enabling Flexible Model Switching using LangChain's Model I/O

**1.1. Core Principle: Leverage LangChain's Native Model Abstractions**

Instead of creating a custom LLM service interface, the plan is to utilize LangChain's built-in model provider classes (e.g., `langchain_openai.ChatOpenAI`, `langchain_anthropic.ChatAnthropic`). These classes conform to a common `BaseChatModel` interface, providing the necessary abstraction.

**1.2. Configuration Enhancements (`mailwright/config.py`)**

The application configuration (`mailwright/config.py`) will be expanded to manage provider and model choices for different tasks:
*   **API Keys:** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
*   **Default Provider (Optional):** `DEFAULT_LLM_PROVIDER` (e.g., "openai").
*   **Task-Specific Model Configuration:**
    *   Example: `BRIEF_ANALYZER_PROVIDER`, `BRIEF_ANALYZER_OPENAI_MODEL`, `BRIEF_ANALYZER_ANTHROPIC_MODEL`.
    *   Similar settings for MJML generation, feedback engine, etc.

**1.3. LLM Instance Factory/Selector (`mailwright/core_services/llm_factory.py`)**

A utility function, `get_configured_chat_model`, will be created to instantiate the appropriate LangChain model based on configuration.

```python
# Suggested content for mailwright/core_services/llm_factory.py
from typing import Optional, Dict, Any
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from mailwright.config import settings # Assuming your Pydantic settings instance

def get_configured_chat_model(
    task_provider_config: str,
    task_openai_model_config: str,
    task_anthropic_model_config: str,
    temperature: float = 0.7,
    **kwargs: Any
) -> BaseChatModel:
    provider = task_provider_config
    
    if provider == "openai":
        model_name = task_openai_model_config
        # ... (instantiate ChatOpenAI with api_key, model_name, temperature, **kwargs)
        # Add error handling for missing API key
        return ChatOpenAI(...) 
    elif provider == "anthropic":
        model_name = task_anthropic_model_config
        # ... (instantiate ChatAnthropic with api_key, model_name, temperature, **kwargs)
        # Add error handling for missing API key
        return ChatAnthropic(...)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
```

**1.4. Refactor Core Services (e.g., `mailwright/core_services/brief_analyzer_service.py`)**

Core services interacting with LLMs will:
*   Use the `get_configured_chat_model` factory.
*   Invoke methods on the returned `BaseChatModel` instance (e.g., `await llm.ainvoke(prompt_messages)`).
*   Handle prompt construction and parsing of LLM responses, adapting for potential provider differences (e.g., ensuring JSON output).

**1.5. LangGraph Node Adjustments (`mailwright/graphs/template_generation_graph.py`)**

LangGraph nodes will use the refactored core services. The LLM selection logic will be abstracted within the services.

**1.6. Prompt Engineering and Management**

*   Prompts need to be engineered for cross-model compatibility.
*   Provider-specific instructions (e.g., for JSON output) will be handled within services or via `**kwargs` in the factory.
*   LangChain's `ChatPromptTemplate` will be used. Complex prompts might be stored externally.

**1.7. Benefits**
*   Reduced custom code by leveraging LangChain components.
*   Seamless integration within the LangChain/LangGraph ecosystem.
*   Extensibility to other LangChain-compatible providers.
*   Configuration-driven model selection.

## 2. Testing Strategy for Flexible LLM Switching

**2.1. Unit Testing**

*   **`llm_factory.py`:**
    *   Test correct instantiation of `ChatOpenAI` and `ChatAnthropic` based on mocked `settings`.
    *   Test error handling for unsupported providers and missing API keys.
    *   Test passing of `**kwargs`.
*   **Refactored Core Services:**
    *   Mock `get_configured_chat_model` and the `ainvoke` method of `BaseChatModel`.
    *   Test service logic with mocked OpenAI and Anthropic responses.
    *   Test successful JSON parsing and graceful handling of `JSONDecodeError`.
    *   Test handling of LLM API errors (mocked `ainvoke` raising exceptions).
    *   Test prompt construction logic if complex or conditional.

**2.2. Integration Testing (LangGraph Context)**

*   **Objective:** Test end-to-end functionality with actual (or carefully mocked HTTP) LLM API interactions through LangGraph nodes.
*   **Strategy:** Use a simple LangGraph flow (e.g., `Start -> LG_BriefAnalyzer -> EndState`) and a test-specific checkpointer.
*   **Test Cases:**
    *   Brief analysis with configured OpenAI: Verify node completion and output consistency.
    *   Brief analysis with configured Anthropic: Verify node completion and output consistency.
    *   Test model-specific features (e.g., OpenAI JSON mode) if used.
    *   Test error propagation in the graph when a mocked LLM call fails.
*   *(Considerations: Live API calls can be slow/costly. Explore `pytest-recording`, `VCR.py`, or HTTP request-level mocking for CI.)*

**2.3. Test Environment & Dependencies**

*   Framework: `pytest`.
*   Dev Dependencies: `langchain-openai`, `langchain-anthropic`.
*   Secure API key management for integration tests.

**2.4. Continuous Integration (CI)**

*   Run unit tests on every commit/PR.
*   Run integration tests on a schedule, specific branches, or manually to manage cost/time.

This combined plan and testing strategy aims to ensure a robust, flexible, and maintainable system for leveraging multiple LLM providers.

## 3. Implementation Status (as of 2025-05-21)

The following components of this plan have been implemented and unit tested:

*   **Section 1.2: Configuration Enhancements (`mailwright/config.py`)**: Completed. Settings for multiple LLM providers and task-specific model choices have been added.
*   **Section 1.3: LLM Instance Factory/Selector (`mailwright/core_services/llm_factory.py`)**: Completed. The `get_configured_chat_model` function has been created.
*   **Section 1.4: Refactor Core Services**:
    *   `mailwright/core_services/brief_analyzer_service.py`: Completed. Refactored to use the LLM factory.
    *   Other services (e.g., for MJML generation, feedback engine) are pending creation/refactoring.
*   **Section 2.1: Unit Testing**:
    *   Unit tests for `llm_factory.py` created and passing.
    *   Unit tests for the refactored `brief_analyzer_service.py` created and passing.
*   **Section 2.3 & 2.4: Test Environment & CI Dependencies**:
    *   `pytest`, `pytest-asyncio`, `langchain-openai`, `langchain-anthropic` added to `requirements.txt`.

The foundational elements for LLM abstraction are in place for the `BriefAnalyzerService`. Further work involves refactoring or creating other LLM-dependent services as per the project's main plan.