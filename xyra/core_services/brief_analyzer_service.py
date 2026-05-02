import logging
import json
from typing import Optional, List
from pydantic import BaseModel  # Added missing import

from xyra.config import settings
from xyra.schemas.template_schemas import UserBriefSchema
from xyra.core_services.llm_factory import get_configured_chat_model

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

# Define the prompt template using LangChain's ChatPromptTemplate
LC_BRIEF_ANALYZER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert assistant helping to clarify email template requirements. Respond only in the specified JSON format.",
        ),
        (
            "human",
            """Analyze this email template request for critical missing information or ambiguities
that would prevent high-quality MJML generation.
The user brief is as follows:
Subject: {subject}
Body Copy/Instructions: {body_copy}
Image Suggestions: {image_suggestions}
CTA Text: {cta_text}
CTA URL: {cta_url}

{clarification_instruction}

If the brief is clear and sufficient, respond with only the JSON: {{"status": "BRIEF_OK"}}
If clarification is needed, respond with only a JSON object containing a list of questions:
{{"clarification_questions": ["Question 1...", "Question 2..."]}}
Do not include any other text or explanation outside the JSON response.""",
        ),
    ]
)


class BriefAnalysisResult(BaseModel):
    status: Optional[str] = None  # e.g., "BRIEF_OK", "CLARIFICATION_NEEDED", "ERROR"
    clarification_questions: Optional[List[str]] = None
    error_message: Optional[str] = None


async def analyze_brief_for_clarifications(
    brief: UserBriefSchema,
    clarification_round: int = 0,
) -> BriefAnalysisResult:
    """
    Analyzes the user's brief using a configured LLM to identify ambiguities or missing information.

    Args:
        brief: The UserBriefSchema object containing the user's input.

    Returns:
        A BriefAnalysisResult object containing either clarification questions,
        an indication that the brief is clear, or an error status.
    """
    try:
        llm_kwargs = {}
        if (
            settings.BRIEF_ANALYZER_PROVIDER == "openai"
            and settings.BRIEF_ANALYZER_OPENAI_MODEL
            in [
                "gpt-4-turbo-preview",
                "gpt-4-0125-preview",
                "gpt-3.5-turbo-1106",
                "gpt-3.5-turbo-0125",
            ]
        ):
            llm_kwargs["response_format"] = {"type": "json_object"}

        llm = get_configured_chat_model(
            task_provider_config_value=settings.BRIEF_ANALYZER_PROVIDER,
            task_openai_model_config_value=settings.BRIEF_ANALYZER_OPENAI_MODEL,
            task_anthropic_model_config_value=settings.BRIEF_ANALYZER_ANTHROPIC_MODEL,
            temperature=0.2,  # Lower temperature for more deterministic output
            **llm_kwargs,
        )

        chain = LC_BRIEF_ANALYZER_PROMPT | llm | StrOutputParser()

        # Adjust instruction based on clarification round
        if clarification_round >= 1:
            clarification_instruction = """This is an amended brief after previous clarification. Be MUCH more lenient and accepting.
Only ask for clarification if absolutely critical information is completely missing (like no CTA URL at all).
Minor details or preferences should be assumed or left to reasonable defaults.
Formulate at most 1 question if truly essential, otherwise proceed with BRIEF_OK."""
        else:
            clarification_instruction = """Formulate 1-3 specific questions for the user to clarify these points.
Explain briefly why each piece of information is important."""

        prompt_input_data = {
            "subject": brief.subject or "Not provided",
            "body_copy": brief.body_copy or "Not provided",
            "image_suggestions": ", ".join(brief.image_suggestions)
            if brief.image_suggestions
            else "None",
            "cta_text": brief.cta_text or "Not provided",
            "cta_url": str(brief.cta_url) if brief.cta_url else "Not provided",
            "clarification_instruction": clarification_instruction,
        }

        logger.info(
            f"--- Sending input to LLM chain for brief analysis: ---\n{prompt_input_data}\n-------------------------------------------------"
        )
        response_content = await chain.ainvoke(prompt_input_data)
        logger.info(
            f"--- LLM raw response for brief analysis: ---\n{response_content}\n---------------------------------------------"
        )

        if not response_content:
            return BriefAnalysisResult(
                status="ERROR", error_message="LLM returned empty response."
            )

        # Attempt to parse the JSON response
        try:
            parsed_response = json.loads(response_content)
            if "clarification_questions" in parsed_response and isinstance(
                parsed_response["clarification_questions"], list
            ):
                return BriefAnalysisResult(
                    status="CLARIFICATION_NEEDED",
                    clarification_questions=parsed_response["clarification_questions"],
                )
            elif parsed_response.get("status") == "BRIEF_OK":
                return BriefAnalysisResult(status="BRIEF_OK")
            else:
                # Fallback if JSON is valid but not in expected format
                logger.warning(
                    f"Warning: LLM response JSON was not in the expected format: {response_content}"
                )
                return BriefAnalysisResult(
                    status="CLARIFICATION_NEEDED",  # Assume clarification needed if unsure
                    clarification_questions=[
                        "The AI assistant's analysis was unclear. Could you please review your brief for completeness regarding subject, body, images, and call to action?"
                    ],
                    error_message="LLM response format unexpected.",
                )
        except json.JSONDecodeError:
            logger.error(
                f"Error: Failed to decode LLM JSON response: {response_content}"
            )
            # If JSON parsing fails, treat it as needing clarification with a generic question.
            return BriefAnalysisResult(
                status="CLARIFICATION_NEEDED",
                clarification_questions=[
                    "There was an issue processing the brief with the AI assistant. Please ensure your brief is clear and try again."
                ],
                error_message="Failed to parse LLM response as JSON.",
            )

    except Exception as e:
        logger.error(f"Error during LLM call for brief analysis: {e}")
        return BriefAnalysisResult(
            status="ERROR",
            error_message=f"An exception occurred during LLM call: {str(e)}",
        )


# Example usage (for testing this service directly)
if __name__ == "__main__":
    import asyncio

    async def test_service():
        sample_brief_ok = UserBriefSchema(
            subject="Summer Sale!",
            body_copy="Get 50% off all items. Limited time offer.",
            cta_text="Shop Now",
            cta_url="http://example.com/sale",
        )
        sample_brief_needs_clarification = UserBriefSchema(
            subject="New Product",
            body_copy="Check it out.",
            # Missing CTA, potentially unclear image needs
        )

        logger.info("\n--- Testing with a clear brief ---")
        result_ok = await analyze_brief_for_clarifications(sample_brief_ok)
        logger.info(
            f"Result: Status: {result_ok.status}, Questions: {result_ok.clarification_questions}, Error: {result_ok.error_message}"
        )

        logger.info("\n--- Testing with a brief needing clarification ---")
        result_clarify = await analyze_brief_for_clarifications(
            sample_brief_needs_clarification
        )
        logger.info(
            f"Result: Status: {result_clarify.status}, Questions: {result_clarify.clarification_questions}, Error: {result_clarify.error_message}"
        )

    # The factory now handles API key checks based on the configured provider.
    # For local testing, ensure at least one provider's key is set in .env
    # if you expect a live API call.
    try:
        from xyra.logging_config import setup_logging

        setup_logging()
        asyncio.run(test_service())
    except ValueError as e:
        logger.error(
            f"Skipping brief_analyzer_service test due to configuration error: {e}"
        )
    except ImportError:
        logger.error(
            "Could not import setup_logging. Run from project root or ensure PYTHONPATH is set."
        )
