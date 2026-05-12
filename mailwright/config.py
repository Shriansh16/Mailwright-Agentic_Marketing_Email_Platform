from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine the base directory of the project
# This assumes config.py is in mailwright/config.py, so two .parent calls go up to the project root
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from the project root if it exists
# This is primarily for local development.
# In production, environment variables should be set directly.
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)


class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "Mailwright - Agentic Marketing Email Platform"
    DEBUG: bool = False  # Default to False for safety
    LOG_LEVEL: str = "INFO"  # Added for centralized log level configuration

    # LLM Provider Settings (Example for OpenAI)
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    # Default LLM Provider ("openai" or "anthropic")
    DEFAULT_LLM_PROVIDER: str = "anthropic"

    # --- Task-Specific LLM Configurations ---
    # Brief Analyzer
    BRIEF_ANALYZER_PROVIDER: str = "anthropic"  # or "anthropic"
    BRIEF_ANALYZER_OPENAI_MODEL: str = "gpt-4-turbo-preview"
    BRIEF_ANALYZER_ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # MJML Generation
    MJML_GENERATION_PROVIDER: str = "anthropic"  # or "anthropic"
    MJML_GENERATION_OPENAI_MODEL: str = "gpt-4-turbo-preview"
    MJML_GENERATION_ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Feedback Engine
    FEEDBACK_ENGINE_PROVIDER: str = "anthropic"  # or "anthropic"
    FEEDBACK_ENGINE_OPENAI_MODEL: str = "gpt-4-turbo-preview"
    FEEDBACK_ENGINE_ANTHROPIC_MODEL: str = (
        "claude-sonnet-4-20250514"  # Example: Sonnet for potentially less complex task
    )

    # Image Generation
    IMAGE_GENERATION_PROVIDER: str = "openai"  # "openai" or "google"
    IMAGE_GENERATION_OPENAI_DALLE_MODEL: str = "dall-e-3"
    IMAGE_GENERATION_GOOGLE_MODEL: str = "gemini-3.1-flash-image-preview"

    # RAG feature flag — set to false to disable the RAG workflow and skip
    # pgvector-dependent migrations entirely.
    RAG_ENABLED: bool = True

    # RAG Embedding Model (Sprint 5)
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"

    # RAG Generation Model (Sprint 5)
    PROMPT_GENERATION_MODEL: str = "gpt-4o"

    # Task-specific RAG Generation settings for the factory
    RAG_GENERATION_PROVIDER: str = "openai"
    RAG_GENERATION_OPENAI_MODEL: str = "gpt-4o"
    RAG_GENERATION_ANTHROPIC_MODEL: str = "claude-3-sonnet-20240229"

    # MJML CLI Path (if not in system PATH, or to specify a version)
    MJML_CLI_PATH: str = "mjml"  # Assumes mjml is in the system PATH

    # Database settings
    DATABASE_URL: str | None = None  # For TemplateStoreDB (PostgreSQL)

    # LangGraph Checkpointer Settings
    LANGGRAPH_CHECKPOINTER_DB_URL: str | None = (
        None  # For LangGraph state persistence (PostgreSQL)
    )
    SQLITE_CHECKPOINTER_DB_FILE: str = str(
        BASE_DIR / "data" / "langgraph_checkpoints.sqlite"
    )  # Sprint 1, will be replaced

    model_config = SettingsConfigDict(
        env_file=str(dotenv_path) if dotenv_path.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra fields from .env not defined in Settings
    )


settings = Settings()

# You can add helper functions here if needed, e.g., to get a database session
# or initialize external services based on settings.
