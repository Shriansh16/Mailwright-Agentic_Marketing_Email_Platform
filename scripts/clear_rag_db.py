from dotenv import load_dotenv

load_dotenv()

import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
# IMPORTANT: This script assumes a default local PostgreSQL setup.
# The DATABASE_URL is hardcoded here because this script doesn't load the full mailwright environment.
# If your database is running elsewhere, please update this URL.
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/mailwright"
TABLE_TO_CLEAR = "rag_templates"


async def clear_rag_table():
    """
    Connects to the database and deletes all entries from the specified RAG table.
    """
    logger.info(f"Connecting to the database at {DATABASE_URL}...")
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.begin() as conn:
            logger.info(f"Executing DELETE statement on table: '{TABLE_TO_CLEAR}'...")
            await conn.execute(text(f"DELETE FROM {TABLE_TO_CLEAR}"))
            logger.info("Successfully deleted all entries.")
        logger.info("Database connection closed.")
    except Exception as e:
        logger.error(f"An error occurred while trying to clear the table: {e}")
        logger.error(
            "Please ensure the database is running and the DATABASE_URL is correct."
        )


async def main():
    """
    Main function to orchestrate the database clearing process.
    """
    logger.info("--- Starting Process to Clear RAG Corpus Table ---")
    await clear_rag_table()
    logger.info("--- Process Finished ---")


if __name__ == "__main__":
    asyncio.run(main()) 