import asyncio
import sys
import os

# Add project root to sys.path to allow importing 'mailwright'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

# All imports should be grouped at the top
from openai import AsyncOpenAI, APIError  # noqa: E402
from mailwright.config import settings  # To get API key and model name  # noqa: E402
from mailwright.logging_config import setup_logging  # noqa: E402
import logging  # noqa: E402

# Call logging setup early, after all imports
setup_logging()

# Initialize logger after setup
logger = logging.getLogger(__name__)


async def check_openai_access():
    """
    Tests OpenAI API key validity and model access.
    """
    if not settings.OPENAI_API_KEY:
        logger.error(
            "OPENAI_API_KEY is not set in your .env file or environment."
        )  # Replaced print
        logger.error(  # Replaced print
            "Please ensure it's correctly configured in .env and loaded by mailwright/config.py"
        )
        return

    logger.info(  # Replaced print
        f"Using API Key: {settings.OPENAI_API_KEY[:5]}...{settings.OPENAI_API_KEY[-4:]}"
    )  # Print partial key for verification
    logger.info(
        f"Attempting to use model: {settings.OPENAI_MODEL_NAME}"
    )  # Replaced print

    aclient = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # Test 1: List some models
    try:
        logger.info(
            "\n--- Attempting to list models (first few)... ---"
        )  # Replaced print
        models = await aclient.models.list()
        if models.data:
            logger.info("Available models (first 5 or fewer):")  # Replaced print
            for i, model in enumerate(models.data):
                if i < 5:  # Print first 5 models
                    logger.info(f"- {model.id}")  # Replaced print
                else:
                    break
            logger.info("Successfully listed some models.")  # Replaced print
        else:
            logger.warning("No models found or returned by the API.")  # Replaced print
    except APIError as e:
        logger.error(f"API Error listing models: {e}")  # Replaced print
        logger.error(  # Replaced print
            "This might be a permission issue not related to chat completion access, or an issue with the API key itself."
        )
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred while listing models: {e}"
        )  # Replaced print with logger.exception

    # Test 2: Simple chat completion
    logger.info(  # Replaced print
        f"\n--- Attempting a simple chat completion with model: {settings.OPENAI_MODEL_NAME}... ---"
    )
    try:
        chat_completion = await aclient.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": "Hello, world! This is a test.",
                }
            ],
            model=settings.OPENAI_MODEL_NAME,
            max_tokens=50,
        )
        logger.info("Chat completion successful!")  # Replaced print
        logger.info("Response:")  # Replaced print
        logger.info(chat_completion.choices[0].message.content)  # Replaced print
        if chat_completion.model:
            logger.info(f"Model used by API: {chat_completion.model}")  # Replaced print

    except APIError as e:
        logger.error(f"API Error during chat completion: {e}")  # Replaced print
        if hasattr(e, "status_code"):
            logger.error(f"Status Code: {e.status_code}")  # Replaced print
        if (
            hasattr(e, "response")
            and e.response is not None
            and hasattr(e.response, "json")
        ):
            try:
                error_details = e.response.json()
                logger.error(f"Error Details: {error_details}")  # Replaced print
            except Exception:  # If response.json() itself fails or isn't JSON
                logger.error(
                    "Could not parse error response details."
                )  # Replaced print
        elif hasattr(e, "message"):
            logger.error(f"Error Message: {e.message}")  # Replaced print

    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during chat completion: {e}"
        )  # Replaced print and traceback with logger.exception
        # import traceback # Removed
        # traceback.print_exc() # Removed

    finally:
        await aclient.close()


if __name__ == "__main__":
    logger.info("--- OpenAI Access Test Script ---")  # Replaced print
    asyncio.run(check_openai_access())
    logger.info("--- Test complete ---")  # Replaced print
