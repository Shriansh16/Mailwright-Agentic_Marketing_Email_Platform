import logging
import asyncio

from mailwright.config import settings
from mailwright.core_services.llm_factory import get_configured_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)


class FeedbackEngineServiceError(Exception):
    """Custom exception for feedback engine service errors."""

    pass


class FeedbackEngineService:
    """
    Service to revise MJML content based on user feedback using an LLM.
    """

    def __init__(self):
        try:
            self.llm_client: BaseChatModel = get_configured_chat_model(
                task_provider_config_value=settings.FEEDBACK_ENGINE_PROVIDER,
                task_openai_model_config_value=settings.FEEDBACK_ENGINE_OPENAI_MODEL,
                task_anthropic_model_config_value=settings.FEEDBACK_ENGINE_ANTHROPIC_MODEL,
                # Add other necessary params like temperature, max_tokens if configured globally
            )
            logger.info(
                f"FeedbackEngineService initialized with provider: {settings.FEEDBACK_ENGINE_PROVIDER}"
            )
        except Exception as e:
            logger.error(
                f"Error initializing LLM client for FeedbackEngineService: {e}"
            )
            raise FeedbackEngineServiceError(
                f"Could not initialize LLM client: {e}"
            ) from e

    async def revise_mjml_based_on_feedback(
        self, current_mjml: str, feedback_text: str
    ) -> str:
        """
        Revises the given MJML content based on the provided feedback text using an LLM.

        Args:
            current_mjml: The current MJML string.
            feedback_text: The user's feedback.

        Returns:
            The revised MJML string.

        Raises:
            FeedbackEngineServiceError: If the revision process fails.
        """
        if not current_mjml or not feedback_text:
            logger.warning("Current MJML or feedback text is empty. Skipping revision.")
            # Or raise error, depending on desired behavior for empty inputs
            raise ValueError("Current MJML and feedback text cannot be empty.")

        prompt_template = """
You are an expert MJML email template designer.
Your task is to revise an existing MJML template based on user feedback.
Ensure the revised MJML is valid and adheres to best practices.
Do NOT add any commentary before or after the MJML code block. Output only the revised MJML.

Original MJML:
```mjml
{current_mjml}
```

User Feedback:
{feedback_text}

Revised MJML:
```mjml
[Your revised MJML code here]
```
"""
        formatted_prompt = prompt_template.format(
            current_mjml=current_mjml, feedback_text=feedback_text
        )

        try:
            logger.debug(
                f"Sending MJML revision prompt to LLM. Feedback: '{feedback_text[:100]}...' Current MJML length: {len(current_mjml)}"
            )
            response = await self.llm_client.ainvoke(formatted_prompt)

            revised_mjml_content = response.content

            # Basic cleaning: extract content from potential markdown code blocks
            if revised_mjml_content.strip().startswith("```mjml"):
                revised_mjml_content = revised_mjml_content.split("```mjml\n", 1)[1]
                if revised_mjml_content.strip().endswith("```"):
                    revised_mjml_content = revised_mjml_content.rsplit("\n```", 1)[0]
                else:
                    pass

            revised_mjml_content = revised_mjml_content.strip()

            if not revised_mjml_content:
                logger.error("LLM returned empty content for MJML revision.")
                raise FeedbackEngineServiceError(
                    "LLM returned empty content for MJML revision."
                )

            logger.info(
                f"Successfully received revised MJML from LLM. Length: {len(revised_mjml_content)}"
            )
            return revised_mjml_content

        except Exception as e:
            logger.error(f"Error during LLM call for MJML revision: {e}", exc_info=True)
            raise FeedbackEngineServiceError(
                f"Failed to revise MJML using LLM: {e}"
            ) from e


# Example Usage (for testing or direct invocation if needed, usually called by a graph node)
async def main_test():
    # Ensure settings are loaded if running standalone; requires .env or environment variables
    # from mailwright.config import settings # Already imported

    logging.basicConfig(level=logging.DEBUG)  # Enable debug logging for this test

    sample_mjml = """
    <mjml>
      <mj-body>
        <mj-section>
          <mj-column>
            <mj-text>Hello World</mj-text>
          </mj-column>
        </mj-section>
      </mj-body>
    </mjml>
    """
    sample_feedback = (
        "Change 'Hello World' to 'Greetings Universe' and make the text blue."
    )

    service = FeedbackEngineService()
    try:
        revised_mjml = await service.revise_mjml_based_on_feedback(
            sample_mjml, sample_feedback
        )
        print("\n--- Revised MJML ---")
        print(revised_mjml)
        print("--------------------\n")
    except FeedbackEngineServiceError as e:
        print(f"Service Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    # This allows running this file directly for quick testing of the service
    # Note: Ensure your environment (especially API keys in .env) is correctly set up.
    asyncio.run(main_test())
