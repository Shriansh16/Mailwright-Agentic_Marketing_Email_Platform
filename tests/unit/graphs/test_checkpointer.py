from dotenv import load_dotenv

load_dotenv()

import pytest
from pathlib import Path
from unittest.mock import patch

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from mailwright.graphs.checkpointer import get_checkpointer_context_manager
from mailwright.config import Settings  # To mock settings

# Define a temporary test database path
TEST_DB_DIR = Path(__file__).parent.parent.parent / "test_data"  # tests/test_data
TEST_DB_FILE = TEST_DB_DIR / "test_checkpoints.sqlite"


@pytest.fixture
def mock_settings_for_checkpointer():
    # Ensure the test data directory is clean before and after tests if needed,
    # or use a unique name for each test run if files are created.
    # For this test, we'll focus on the function's behavior.

    # Clean up before test if file exists from previous failed run
    if TEST_DB_FILE.exists():
        TEST_DB_FILE.unlink()
    if TEST_DB_DIR.exists() and not any(TEST_DB_DIR.iterdir()):  # remove dir if empty
        TEST_DB_DIR.rmdir()

    settings = Settings(
        SQLITE_CHECKPOINTER_DB_FILE=str(TEST_DB_FILE)
        # Add other required fields for Settings if any, with default values
    )
    yield settings  # Use yield to allow cleanup after test

    # Cleanup after test
    if TEST_DB_FILE.exists():
        TEST_DB_FILE.unlink()
    if TEST_DB_DIR.exists() and not any(TEST_DB_DIR.iterdir()):
        # Check again if directory is empty before removing
        try:
            # Small hack: sometimes the .db-wal or .db-shm files might linger for a bit
            # on some systems, so we try to remove them if they exist.
            # This is more relevant if the checkpointer was actually used to write.
            # For this specific test of get_checkpointer_context_manager, it might not write.
            for suffix in ["-wal", "-shm"]:
                lingering_file = Path(str(TEST_DB_FILE) + suffix)
                if lingering_file.exists():
                    lingering_file.unlink()

            # Re-check if dir is empty
            if not any(TEST_DB_DIR.iterdir()):
                TEST_DB_DIR.rmdir()
        except OSError:
            pass  # Ignore cleanup errors, e.g. if dir is not empty due to other files


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.checkpointer.settings"
)  # Keep this patch if settings are used for dir creation path
async def test_get_checkpointer_context_manager_returns_async_sqlite_saver(
    mock_settings_obj, mock_settings_for_checkpointer
):
    # This test primarily checks the type and directory creation.
    # The actual connection string usage is tested in another test by mocking from_conn_string.

    # Ensure the function takes the SQLite path for this test
    mock_settings_obj.LANGGRAPH_CHECKPOINTER_DB_URL = None
    mock_settings_obj.SQLITE_CHECKPOINTER_DB_FILE = (
        mock_settings_for_checkpointer.SQLITE_CHECKPOINTER_DB_FILE
    )

    # We need to patch SQLITE_CONN_STRING for this test to ensure the directory logic uses the test path
    # This patch might be redundant if mock_settings_obj.SQLITE_CHECKPOINTER_DB_FILE is correctly used by the SUT
    # but kept for safety if SQLITE_CONN_STRING is directly referenced after settings load.
    with patch("mailwright.graphs.checkpointer.SQLITE_CONN_STRING", str(TEST_DB_FILE)):
        checkpointer_cm_obj = get_checkpointer_context_manager()

        # The function returns the result of AsyncSqliteSaver.from_conn_string(),
        # which is an async context manager.
        # To check the instance type, we need to enter the context.
        async with checkpointer_cm_obj as checkpointer_instance:
            assert isinstance(checkpointer_instance, AsyncSqliteSaver)

    # Check if the directory was created (by the original, unmocked mkdir)
    assert TEST_DB_DIR.exists()
    assert TEST_DB_DIR.is_dir()


@patch("mailwright.graphs.checkpointer.settings")  # Patch settings
@patch(
    "mailwright.graphs.checkpointer.SQLITE_CONN_STRING",
    new_callable=lambda: str(TEST_DB_FILE),
)
@patch("pathlib.Path.mkdir")
def test_get_checkpointer_context_manager_creates_directory(
    mock_mkdir,
    mock_sql_conn_string_module_var,  # Renamed for clarity
    mock_settings_in_checkpointer_module,  # Added mock for settings
):
    # Ensure the function takes the SQLite path by making LANGGRAPH_CHECKPOINTER_DB_URL None
    mock_settings_in_checkpointer_module.LANGGRAPH_CHECKPOINTER_DB_URL = None
    # SQLITE_CHECKPOINTER_DB_FILE still needs to be valid for the Path operations
    mock_settings_in_checkpointer_module.SQLITE_CHECKPOINTER_DB_FILE = str(TEST_DB_FILE)

    # Ensure the directory does not exist before the call for this specific test
    if TEST_DB_DIR.exists():
        if TEST_DB_FILE.exists():  # remove file first if it exists
            TEST_DB_FILE.unlink()
        # Only remove dir if it's truly empty or we are sure it's safe
        if not any(TEST_DB_DIR.iterdir()):
            TEST_DB_DIR.rmdir()

    assert not TEST_DB_DIR.exists()  # Pre-condition

    get_checkpointer_context_manager()

    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    # Note: The actual directory creation is done by pathlib.Path.mkdir.
    # If we didn't mock mkdir, we'd check TEST_DB_DIR.exists() again.
    # Since we mocked it, we check that our mock was called.
    # For a more integrated test of this part, don't mock mkdir and assert TEST_DB_DIR.exists().
    # The previous test case implicitly covers the directory creation by checking TEST_DB_DIR.exists().


# To test the connection string usage more directly, mock AsyncSqliteSaver.from_conn_string.
@patch("mailwright.graphs.checkpointer.settings")  # Patch settings used by the function
@patch("langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver.from_conn_string")
@patch(
    "mailwright.graphs.checkpointer.SQLITE_CONN_STRING",
    new_callable=lambda: str(TEST_DB_FILE),
)  # Patch module-level var
def test_get_checkpointer_context_manager_uses_correct_conn_string(
    mock_sql_conn_string_module_var,  # Renamed for clarity, this patches SQLITE_CONN_STRING directly
    mock_sqlite_saver_from_conn_string,  # This is the mock for AsyncSqliteSaver.from_conn_string
    mock_settings_in_checkpointer_module,  # This is the mock for mailwright.graphs.checkpointer.settings
):
    # Ensure the function takes the SQLite path by making LANGGRAPH_CHECKPOINTER_DB_URL None
    mock_settings_in_checkpointer_module.LANGGRAPH_CHECKPOINTER_DB_URL = None
    # SQLITE_CHECKPOINTER_DB_FILE still needs to be valid for the Path operations if not fully mocked out
    mock_settings_in_checkpointer_module.SQLITE_CHECKPOINTER_DB_FILE = str(TEST_DB_FILE)

    get_checkpointer_context_manager()

    # AsyncSqliteSaver.from_conn_string should be called with the patched SQLITE_CONN_STRING (via TEST_DB_FILE)
    mock_sqlite_saver_from_conn_string.assert_called_once_with(str(TEST_DB_FILE))
