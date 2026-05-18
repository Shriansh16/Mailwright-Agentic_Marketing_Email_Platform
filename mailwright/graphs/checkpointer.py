from dotenv import load_dotenv

load_dotenv()

import logging
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)  # Corrected import path
from mailwright.config import settings
from pathlib import Path

logger = logging.getLogger(__name__)

# The connection string for AsyncSqliteSaver.from_conn_string() is the database file path.
SQLITE_CONN_STRING = settings.SQLITE_CHECKPOINTER_DB_FILE


def get_checkpointer_context_manager():
    """
    Returns an async context manager for the configured checkpointer.
    Prioritizes PostgreSQL if LANGGRAPH_CHECKPOINTER_DB_URL is set,
    otherwise falls back to SQLite.
    """
    if settings.LANGGRAPH_CHECKPOINTER_DB_URL:
        logger.info(
            f"Using PostgreSQL checkpointer with URL: {settings.LANGGRAPH_CHECKPOINTER_DB_URL}"
        )
        # AsyncPostgresSaver.from_conn_string expects a DSN like:
        # "postgresql://user:password@host:port/dbname"
        # Our current URL is "postgresql+asyncpg://..."
        # We might need to adjust this if AsyncPostgresSaver is strict.
        # For now, let's try with the existing URL format; psycopg might handle it.
        # If not, we'll need to create a psycopg-specific DSN.
        pg_conn_string = settings.LANGGRAPH_CHECKPOINTER_DB_URL
        if pg_conn_string.startswith("postgresql+asyncpg://"):
            pg_conn_string = pg_conn_string.replace(
                "postgresql+asyncpg://", "postgresql://", 1
            )
            logger.info(
                f"Adjusted PostgreSQL checkpointer URL for psycopg: {pg_conn_string}"
            )

        # The `AsyncPostgresSaver` itself needs to be initialized and its `setup` (or `asetup`)
        # method called to create tables if they don't exist.
        # `from_conn_string` typically returns a context manager that handles this.
        return AsyncPostgresSaver.from_conn_string(pg_conn_string)
    else:
        logger.info(
            f"LANGGRAPH_CHECKPOINTER_DB_URL not set. Falling back to SQLite checkpointer: {SQLITE_CONN_STRING}"
        )
        # Ensure the directory for the SQLite file exists.
        db_path = Path(SQLITE_CONN_STRING)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return AsyncSqliteSaver.from_conn_string(SQLITE_CONN_STRING)


async def ensure_checkpointer_schema() -> None:
    """
    Create LangGraph checkpoint tables if they do not exist.
    AsyncPostgresSaver / AsyncSqliteSaver require setup() before first use.
    """
    async with get_checkpointer_context_manager() as checkpointer:
        await checkpointer.setup()
    logger.info("LangGraph checkpointer schema is ready.")


# We will no longer export a pre-resolved 'checkpointer_instance'
# as it was causing the AttributeError. The graph compilation
# needs to occur within the async context of the checkpointer.
