# Xyra Logging Standardization Plan

**Overall Goal:**
Transition all application-level logging to use Python's `logging` module, configured centrally. This involves removing `print()` statements used for logging, replacing ad-hoc `logging.basicConfig()` calls, and ensuring a consistent logging format and level control.

## Phase 1: Initial Setup & Core Graph Refactoring

1.  **Centralized Logging Configuration (`xyra/logging_config.py`)**
    *   **Status:** COMPLETED
    *   Created `xyra/logging_config.py` with `setup_logging()`.
    *   Configuration uses `logging.basicConfig()`.
    *   Log Format: `%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s`
    *   Log Level: Controlled by `LOG_LEVEL` environment variable (via `os.environ.get` or `settings.LOG_LEVEL`), defaulting to `INFO`.
    *   Handler: `logging.StreamHandler()` to output to console.

2.  **Initialize Logging in Application Entry Point (`xyra/main.py`)**
    *   **Status:** COMPLETED
    *   `setup_logging()` is called at the very beginning of `xyra/main.py` to ensure logging is configured before any other imports or application logic.

3.  **Refactor `xyra/graphs/template_generation_graph.py`**
    *   **Status:** IN PROGRESS
    *   Add `import logging` and initialize `logger = logging.getLogger(__name__)` at the module level.
    *   Systematically replace all `print()` statements with appropriate `logger` calls (e.g., `logger.info()`, `logger.warning()`, `logger.error()`, `logger.debug()`).
    *   Replace `import traceback; traceback.print_exc()` calls with `logger.exception("Descriptive message")` (which automatically includes exception info).

## Phase 2: Standardize Logging in Core Services & Utilities

1.  **Refactor `xyra/graphs/checkpointer.py`**:
    *   Add `import logging` and `logger = logging.getLogger(__name__)`.
    *   Replace existing `print()` statements with `logger.info()` or `logger.debug()` as appropriate.

2.  **Refactor `xyra/core_services/image_generator_service.py`**:
    *   The file already uses `logger = logging.getLogger(__name__)` correctly at the module level.
    *   **Action**: Remove the `logging.basicConfig()` call from the `if __name__ == "__main__":` block. If this block is used for standalone testing, it should instead import and call `setup_logging` from `xyra.logging_config`.

3.  **Review `xyra/core_services/mjml_service.py`**:
    *   This file already correctly uses `logger = logging.getLogger(__name__)` and seems to rely on the central configuration. No changes are likely needed here beyond a quick confirmation.

4.  **Refactor `xyra/core_services/brief_analyzer_service.py`**:
    *   Add `import logging` and `logger = logging.getLogger(__name__)`.
    *   Search for and replace any `print()` statements or ad-hoc logging configurations.

5.  **Refactor `xyra/core_services/llm_factory.py`**:
    *   Add `import logging` and `logger = logging.getLogger(__name__)`.
    *   Search for and replace any `print()` statements or ad-hoc logging configurations.

6.  **Review and Refactor `xyra/config.py`**:
    *   Check for any `print()` statements used during settings loading (likely for debugging) and replace them with `logger.debug()` or `logger.info()`.
    *   **Enhancement**: Add a `LOG_LEVEL: str = "INFO"` field to the `Settings` Pydantic model. Update `xyra/logging_config.py` to use `settings.LOG_LEVEL` as a fallback if the `LOG_LEVEL` environment variable is not explicitly set. This provides a configuration-driven way to set the default log level.

## Phase 3: Standardize Logging in Scripts and Tests

1.  **Refactor `scripts/test_openai_access.py` (and any other utility scripts)**:
    *   At the beginning of the script, add:
        ```python
        from xyra.logging_config import setup_logging
        setup_logging()
        import logging
        logger = logging.getLogger(__name__)
        ```
    *   Replace `print()` statements with appropriate `logger.info()`, `logger.error()`, etc.

2.  **Refactor `tests/conftest.py`**:
    *   The `print()` statements are used for migration status. These can be converted to `logger.info()`.
    *   To ensure logging is configured when `pytest` collects/runs tests (especially if `conftest.py` is loaded early):
        *   Add the following at the top of `tests/conftest.py`:
            ```python
            import logging
            # Attempt to set up logging if not already configured by app import
            # This is a simple way; could be more sophisticated if needed
            if not logging.getLogger().hasHandlers():
                from xyra.logging_config import setup_logging
                setup_logging()
            logger = logging.getLogger(__name__) # For conftest specific logs
            ```
        *   Then, replace `print()` in `setup_test_database_env_and_migrations` with `logger.info()`.

## Phase 4: Alembic Logging (Review - No Action Expected)

1.  **`alembic/env.py` and `alembic.ini`**:
    *   Alembic uses its own logging configuration (`fileConfig` in `env.py` loading from `alembic.ini`). This is standard for Alembic and should be **left untouched**. The application's logging and Alembic's logging will operate independently and correctly.

## Phase 5: Documentation & Final Review

1.  **Update Documentation**:
    *   In `docs/working_context/primary_context.md`: Document the standardized logging approach, mentioning `xyra/logging_config.py`, the standard log format, and how to control the log level using the `LOG_LEVEL` environment variable (and potentially the new `settings.LOG_LEVEL`).
    *   In `docs/working_context/sprint_2_plan_tasks.md`: Update the "Standardize Logging" task details and mark it as completed upon finishing these steps.

2.  **Final Code Review**:
    *   Perform a codebase-wide search (e.g., `grep -r "print(" xyra/`) to find any missed `print()` statements in the `xyra` application directory (excluding `archive`, `tests/test_data`, `.venv`, etc.).
    *   Ensure consistency in logger instantiation: `logger = logging.getLogger(__name__)`. 