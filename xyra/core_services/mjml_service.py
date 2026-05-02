import asyncio
import tempfile
import os
from typing import Dict, Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel

from xyra.graphs.state import GraphState
from xyra.core_services.llm_factory import get_configured_chat_model  # Updated import
from xyra.config import settings

# Placeholder for logger, to be replaced with a proper logger
import logging

logger = logging.getLogger(__name__)

MJML_GENERATION_PROMPT_TEMPLATE = """
You are an expert MJML developer. Your task is to generate a complete, responsive MJML email template based on the following user brief.
The MJML should be well-structured and valid. Do not include any explanations or conversational text outside of the MJML code block.
Ensure the MJML is complete from <mjml> to </mjml>.

User Brief:
Subject: {subject}
Body: {body}
Call to Action: {call_to_action}
{additional_details}

Generated Image URLs (if any, incorporate them appropriately into the MJML, e.g., using <mj-image src="URL" />):
{image_urls_for_prompt}

Generate the MJML code now.
"""


class MJMLService:
    """
    Service responsible for MJML generation, validation, and compilation.
    This will contain the logic for the LangGraph nodes related to MJML.
    """

    def __init__(self):
        """
        Initializes the MJMLService, configuring the LLM client based on
        MJML-specific settings in `xyra.config.settings`.
        """
        self.llm_provider = (
            settings.MJML_GENERATION_PROVIDER
        )  # Get provider from settings
        self.llm_client: BaseChatModel = get_configured_chat_model(
            task_provider_config_value=settings.MJML_GENERATION_PROVIDER,
            task_openai_model_config_value=settings.MJML_GENERATION_OPENAI_MODEL,
            task_anthropic_model_config_value=settings.MJML_GENERATION_ANTHROPIC_MODEL,
            # temperature can also be made configurable if needed, e.g. settings.MJML_GENERATION_TEMPERATURE
            temperature=0.7,
        )

    async def generate_mjml_node(self, state: GraphState) -> Dict[str, Any]:
        """
        LangGraph node to generate MJML from a user brief.
        """
        logger.info("MJML Generation Node: Starting MJML generation.")
        update_fields: Dict[str, Any] = {
            "last_operation_status": "failure",
            "current_mjml": None,
            "error_message": None,
        }

        brief_to_use = (
            state.amended_brief_data
            if state.amended_brief_data
            else state.user_brief_data
        )

        if not brief_to_use:
            logger.error("MJML Generation Node: No brief data found in state.")
            update_fields["error_message"] = (
                "MJML Generation Failed: No user brief provided."
            )
            return update_fields

        try:
            subject = brief_to_use.get("subject", "No Subject Provided")
            body = brief_to_use.get("body", "No Body Content Provided")
            call_to_action = brief_to_use.get(
                "call_to_action", "No Call to Action Provided"
            )

            # Consolidate other potential brief fields into additional_details
            other_details_dict = {
                k: v
                for k, v in brief_to_use.items()
                if k not in ["subject", "body", "call_to_action"] and v
            }
            additional_details_str = ""
            if other_details_dict:
                additional_details_str = "\nAdditional Details:\n"
                for k, v in other_details_dict.items():
                    additional_details_str += (
                        f"- {k.replace('_', ' ').capitalize()}: {v}\n"
                    )

            # Prepare image URLs for the prompt
            image_urls_for_prompt_str = "No images provided or generated."
            if state.generated_image_urls:
                image_urls_for_prompt_str = "Available images:\n"
                for i, url in enumerate(state.generated_image_urls):
                    image_urls_for_prompt_str += f"- Image {i + 1}: {url}\n"

            logger.info(f"Image URLs for prompt: {state.generated_image_urls}")

            prompt = ChatPromptTemplate.from_template(MJML_GENERATION_PROMPT_TEMPLATE)
            chain = prompt | self.llm_client

            logger.info(
                f"MJML Generation Node: Invoking LLM with provider {self.llm_provider}."
            )
            response = await chain.ainvoke(
                {
                    "subject": subject,
                    "body": body,
                    "call_to_action": call_to_action,
                    "additional_details": additional_details_str.strip(),
                    "image_urls_for_prompt": image_urls_for_prompt_str.strip(),
                }
            )

            generated_mjml = response.content

            # Clean up potential markdown code blocks from LLM response
            if isinstance(generated_mjml, str):
                generated_mjml = generated_mjml.strip()
                if generated_mjml.startswith("```mjml"):
                    generated_mjml = generated_mjml.split("```mjml\n", 1)[1]
                    if generated_mjml.strip().endswith("```"):
                        generated_mjml = generated_mjml.rsplit("\n```", 1)[0]
                generated_mjml = generated_mjml.strip()

            # Basic check to see if it looks like MJML
            if (
                isinstance(generated_mjml, str)
                and "<mjml>" in generated_mjml
                and "</mjml>" in generated_mjml
            ):
                logger.info(
                    "MJML Generation Node: Successfully generated MJML from LLM."
                )
                update_fields["current_mjml"] = generated_mjml.strip()
                update_fields["last_operation_status"] = "success"
            else:
                logger.error(
                    f"MJML Generation Node: LLM did not return valid MJML. Response: {generated_mjml}"
                )
                update_fields["error_message"] = (
                    "MJML Generation Failed: LLM did not produce valid MJML structure."
                )
                update_fields["current_mjml"] = (
                    generated_mjml  # Store what was returned for debugging
                )

        except Exception as e:
            logger.exception("MJML Generation Node: Exception during MJML generation.")
            update_fields["error_message"] = (
                f"MJML Generation Failed: An unexpected error occurred: {str(e)}"
            )
            update_fields["last_operation_status"] = "ERROR_MJML_GENERATION"

        return update_fields

    async def validate_and_compile_mjml_node(self, state: GraphState) -> Dict[str, Any]:
        """
        LangGraph node to validate and compile MJML using the mjml CLI.
        Prioritizes `state.revised_mjml_candidate` if available, otherwise uses `state.current_mjml`.
        Updates the state with compiled HTML and validation status.
        Clears `revised_mjml_candidate` after processing.
        """
        logger.info(
            "MJML Validator/Compiler Node: Starting MJML validation and compilation."
        )
        update_fields: Dict[str, Any] = {
            "last_operation_status": "failure_mjml_validation_compilation",  # More specific default
            "compiled_html": None,
            "mjml_validation_status": "UNKNOWN",
            "error_message": None,
        }

        mjml_to_process: Optional[str] = None

        if state.revised_mjml_candidate and state.revised_mjml_candidate.strip():
            logger.info(
                "MJML Validator/Compiler Node: Using 'revised_mjml_candidate' for validation."
            )
            mjml_to_process = state.revised_mjml_candidate
            update_fields["current_mjml"] = mjml_to_process
        elif state.current_mjml and state.current_mjml.strip():
            logger.info(
                "MJML Validator/Compiler Node: Using 'current_mjml' for validation."
            )
            mjml_to_process = state.current_mjml
        else:
            logger.error(
                "MJML Validator/Compiler Node: No MJML content found in 'revised_mjml_candidate' or 'current_mjml'."
            )
            update_fields["error_message"] = (
                "Validation Failed: No MJML content provided for validation/compilation."
            )
            update_fields["mjml_validation_status"] = "NOT_AVAILABLE"
            update_fields["revised_mjml_candidate"] = None
            return update_fields

        temp_mjml_file = None
        try:
            # Create a temporary file to store the MJML content
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".mjml", encoding="utf-8"
            ) as tmp_mjml:
                tmp_mjml.write(mjml_to_process)  # Use mjml_to_process
                temp_mjml_file = tmp_mjml.name

            logger.info(
                f"MJML Validator/Compiler Node: MJML written to temporary file: {temp_mjml_file}"
            )

            # Command to compile MJML to HTML, strict validation is implicit with mjml CLI
            # The output HTML will be sent to stdout.
            # Using --config.validationLevel=strict for explicit strict validation.
            # The mjml CLI path might need to be configurable or ensured it's in PATH.
            cmd = ["mjml", temp_mjml_file, "--config.validationLevel=strict"]

            logger.info(
                f"MJML Validator/Compiler Node: Executing command: {' '.join(cmd)}"
            )

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                compiled_html_output = stdout.decode("utf-8").strip()
                stderr_output = stderr.decode("utf-8").strip()

                if (
                    "validation error" in stderr_output.lower()
                    or not compiled_html_output
                ):
                    # Some validation errors might still result in returncode 0 but print to stderr
                    logger.error(
                        f"MJML Validator/Compiler Node: MJML validation failed. Stderr: {stderr_output}"
                    )
                    update_fields["error_message"] = (
                        f"MJML Validation Failed: {stderr_output or 'Unknown validation error'}"
                    )
                    update_fields["mjml_validation_status"] = "INVALID"
                    update_fields["compiled_html"] = (
                        compiled_html_output  # Store potentially partial/broken HTML for debugging
                    )
                else:
                    logger.info(
                        "MJML Validator/Compiler Node: MJML validated and compiled successfully."
                    )
                    update_fields["compiled_html"] = compiled_html_output
                    update_fields["mjml_validation_status"] = "VALID"
                    update_fields["last_operation_status"] = "success"
                    if stderr_output:  # Log warnings if any
                        logger.warning(
                            f"MJML Validator/Compiler Node: MJML compilation produced warnings: {stderr_output}"
                        )
            else:
                stderr_output = stderr.decode("utf-8").strip()
                logger.error(
                    f"MJML Validator/Compiler Node: mjml CLI failed with return code {process.returncode}. Stderr: {stderr_output}"
                )
                update_fields["error_message"] = (
                    f"MJML Compilation Failed: {stderr_output}"
                )
                update_fields["mjml_validation_status"] = "INVALID"

        except FileNotFoundError:
            logger.exception(
                "MJML Validator/Compiler Node: mjml CLI not found. Ensure it is installed and in PATH."
            )
            update_fields["error_message"] = "MJML Tooling Error: mjml CLI not found."
            update_fields["mjml_validation_status"] = "ERROR"
        except Exception as e:
            logger.exception(
                "MJML Validator/Compiler Node: Exception during MJML validation/compilation."
            )
            update_fields["error_message"] = (
                f"MJML Validation/Compilation Error: An unexpected error occurred: {str(e)}"
            )
            update_fields["mjml_validation_status"] = "ERROR"
        finally:
            if temp_mjml_file and os.path.exists(temp_mjml_file):
                os.remove(temp_mjml_file)
                logger.info(
                    f"MJML Validator/Compiler Node: Deleted temporary file: {temp_mjml_file}"
                )

        update_fields["revised_mjml_candidate"] = None

        return update_fields


# Example usage (for testing purposes, not part of the node logic itself)
# if __name__ == "__main__":
#     import asyncio
#     from xyra.schemas.template_schemas import UserBriefSchema # Assuming this exists
#
#     async def main():
#         # Mock settings if not running in FastAPI context
#         from xyra.config import Settings
#         settings_instance = Settings(llm_provider="openai", openai_api_key="your_key") # or "anthropic"
#         # This is a bit of a hack for standalone testing; normally settings are loaded globally.
#         # For real testing, use pytest fixtures to manage settings.
#         global settings
#         settings = settings_instance
#
#         service = MJMLService()
#         test_brief = UserBriefSchema(
#             subject="Welcome to Xyra!",
#             body_copy="Thanks for signing up. We're excited to have you.",
#             call_to_action_text="Explore Now",
#             # Add other fields as per your UserBriefSchema
#         )
#         initial_state = GraphState(user_brief_data=test_brief.model_dump())
#         result_state_update = await service.generate_mjml_node(initial_state)
#
#         print("--- MJML Generation Result ---")
#         if result_state_update.get("current_mjml"):
#             print(result_state_update["current_mjml"])
#         else:
#             print(f"Error: {result_state_update.get('error_message')}")
#         print(f"Status: {result_state_update.get('last_operation_status')}")
#
#     asyncio.run(main())
