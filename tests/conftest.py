import os
import pytest
import pytest_asyncio
import logging  # Added for standardized logging
import nest_asyncio  # Added for attempting to fix loop issues
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text
from alembic.config import Config
from alembic import command as alembic_command

# Attempt to set up logging if not already configured by app import
if not logging.getLogger().hasHandlers():
    try:
        from mailwright.logging_config import setup_logging

        setup_logging()
    except ImportError:
        # This might happen if tests are run in an environment where mailwright package is not discoverable
        # in the standard way, or if logging_config itself has issues.
        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        logging.getLogger(__name__).warning(
            "Could not import central logging_config. Using basicConfig for conftest."
        )

logger = logging.getLogger(__name__)  # Added for standardized logging

# Define the existing test database name and connection details
# The user 'mailwright_admin' must have permissions to connect to TEST_DB_NAME
# and perform DML operations (SELECT, INSERT, UPDATE, DELETE) on its tables.
TEST_DATABASE_URL_BASE = os.getenv(
    "TEST_DATABASE_URL_BASE",
    "postgresql+asyncpg://mailwright_admin:experiture@localhost:5432",
)
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "mailwright_db")  # Changed to use existing mailwright_db

# URL for the application to use (SQLAlchemy and LangGraph checkpointer) - async version
APPLICATION_TEST_DB_URL_SQLALCHEMY_ASYNC = f"{TEST_DATABASE_URL_BASE}/{TEST_DB_NAME}"
# URL for Alembic (synchronous operations) - sync version
APPLICATION_TEST_DB_URL_SQLALCHEMY_SYNC = (
    APPLICATION_TEST_DB_URL_SQLALCHEMY_ASYNC.replace("+asyncpg", "")
)

APPLICATION_TEST_DB_URL_LANGGRAPH = APPLICATION_TEST_DB_URL_SQLALCHEMY_ASYNC.replace(
    "+asyncpg", ""
)

nest_asyncio.apply()  # Added for attempting to fix loop issues


@pytest.fixture(scope="session", autouse=True)
def setup_test_database_env_and_migrations():
    """
    Sets environment variables to use an existing test database and runs migrations.
    Assumes the database already exists.
    """
    # Set environment variables for the application (async URLs)
    os.environ["DATABASE_URL"] = APPLICATION_TEST_DB_URL_SQLALCHEMY_ASYNC
    os.environ["LANGGRAPH_CHECKPOINTER_DB_URL"] = APPLICATION_TEST_DB_URL_LANGGRAPH

    # Run Alembic migrations against the existing test database using a synchronous URL
    alembic_cfg = Config("alembic.ini")
    # Alembic needs a synchronous URL
    alembic_cfg.set_main_option(
        "sqlalchemy.url", APPLICATION_TEST_DB_URL_SQLALCHEMY_SYNC
    )

    logger.info(
        f"Running migrations on existing test database (sync URL for Alembic): {APPLICATION_TEST_DB_URL_SQLALCHEMY_SYNC}"
    )
    try:
        alembic_command.upgrade(alembic_cfg, "head")
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        # Depending on policy, you might want to raise this error or just warn.
        # If migrations fail, tests are likely to fail anyway.
        raise

    yield  # Tests run here

    # Clean up environment variables
    del os.environ["DATABASE_URL"]
    del os.environ["LANGGRAPH_CHECKPOINTER_DB_URL"]


@pytest_asyncio.fixture(scope="function")
async def async_db_engine():  # No longer needs to explicitly take event_loop
    """Creates an async engine for each test function that needs it."""
    engine = create_async_engine(
        APPLICATION_TEST_DB_URL_SQLALCHEMY_ASYNC, echo=False
    )  # echo can be based on settings.DEBUG
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def clear_tables_between_tests(
    setup_test_database_env_and_migrations, async_db_engine
):
    """
    Ensures relevant tables are cleared before each test function using the shared session engine.
    """
    async with async_db_engine.connect() as conn:
        tables_to_clear = ["checkpoints", "template_versions"]
        for table_name in tables_to_clear:
            try:
                await conn.execute(text(f"DELETE FROM {table_name}"))
                logger.debug(f"Cleared table: {table_name}")
            except Exception as e:
                logger.warning(f"Could not clear table {table_name}. Reason: {e}")
        await conn.commit()
    # No explicit yield needed if autouse=True and it's a setup/teardown fixture
    # However, to be clear about when the test runs, an explicit yield is good practice for autouse fixtures too.
    yield
