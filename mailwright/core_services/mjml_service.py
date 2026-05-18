from dotenv import load_dotenv

load_dotenv()

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel

from mailwright.graphs.state import GraphState
from mailwright.core_services.llm_factory import get_configured_chat_model  # Updated import
from mailwright.config import settings

# Placeholder for logger, to be replaced with a proper logger
import logging

logger = logging.getLogger(__name__)

# Placeholders substituted with real image URLs after LLM generation (avoids sending base64 to the LLM).
def _image_placeholder(index: int) -> str:
    return f"__MAILWRIGHT_IMAGE_{index + 1}__"


def resolve_mjml_cli(configured: str | None = None) -> str:
    """Resolve the MJML CLI executable (Windows: mjml.cmd in npm global dir)."""
    candidates: list[str] = []
    if configured and configured.strip():
        candidates.append(configured.strip())
    candidates.extend(["mjml", "mjml.cmd"])

    for name in candidates:
        found = shutil.which(name)
        if found:
            return found

    npm_global = Path(os.environ.get("APPDATA", "")) / "npm" / "mjml.cmd"
    if npm_global.is_file():
        return str(npm_global)

    raise FileNotFoundError(
        "MJML CLI not found. Install with: npm install -g mjml "
        "Then set MJML_CLI_PATH in .env to the full path if needed."
    )


def _format_images_for_mjml_prompt(
    image_urls: list[str],
    image_prompts: list[str] | None = None,
) -> tuple[str, dict[str, str]]:
    """
    Build LLM-safe image instructions using placeholders instead of raw URLs/data URIs.
    Returns (prompt_text, placeholder -> actual_src mapping for post-processing).
    """
    if not image_urls:
        return "No images provided or generated.", {}

    lines: list[str] = []
    mapping: dict[str, str] = {}
    prompts = image_prompts or []

    for i, url in enumerate(image_urls):
        if not url:
            continue
        placeholder = _image_placeholder(i)
        mapping[placeholder] = url
        desc = prompts[i] if i < len(prompts) else f"Generated marketing image {i + 1}"
        lines.append(
            f'- Image {i + 1}: use exactly src="{placeholder}" in <mj-image> '
            f'(content: {desc})'
        )

    if not lines:
        return "No images provided or generated.", {}

    header = (
        "Use the exact placeholder strings below as mj-image src values. "
        "Do not invent or replace them with real URLs.\n"
    )
    return header + "\n".join(lines), mapping


def _inject_image_placeholders(mjml: str, mapping: dict[str, str]) -> str:
    """Replace placeholder tokens with actual image URLs (including data URIs)."""
    result = mjml
    for placeholder, url in mapping.items():
        result = result.replace(placeholder, url)
    return result


def _run_mjml_cli_sync(mjml_path: str, mjml_cli: str) -> Tuple[int, str, str]:
    """Run MJML CLI synchronously (Windows-safe; avoids asyncio subprocess limits)."""
    cmd = [mjml_cli, mjml_path, "--config.validationLevel=strict"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout or "", result.stderr or ""


MJML_GENERATION_PROMPT_TEMPLATE = """
You are an expert MJML developer. Your task is to generate a complete, responsive MJML email template based on the following user brief.
The MJML should be well-structured and valid. Do not include any explanations or conversational text outside of the MJML code block.
Ensure the MJML is complete from <mjml> to </mjml>.

User Brief:
Subject: {subject}
Body: {body}
Call to Action: {call_to_action}
{additional_details}

Generated images (if any — use the exact placeholder src values in <mj-image> tags):
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
        MJML-specific settings in `mailwright.config.settings`.
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
            body = brief_to_use.get("body") or brief_to_use.get(
                "body_copy", "No Body Content Provided"
            )
            call_to_action = brief_to_use.get("call_to_action") or " ".join(
                filter(
                    None,
                    [
                        brief_to_use.get("cta_text"),
                        brief_to_use.get("cta_url"),
                    ],
                )
            ).strip() or "No Call to Action Provided"

            # Consolidate other potential brief fields into additional_details
            _skip_keys = {
                "subject",
                "body",
                "body_copy",
                "call_to_action",
                "cta_text",
                "cta_url",
                "image_suggestions",
            }
            other_details_dict = {
                k: v
                for k, v in brief_to_use.items()
                if k not in _skip_keys and v
            }
            additional_details_str = ""
            if other_details_dict:
                additional_details_str = "\nAdditional Details:\n"
                for k, v in other_details_dict.items():
                    additional_details_str += (
                        f"- {k.replace('_', ' ').capitalize()}: {v}\n"
                    )

            # Use placeholders in the LLM prompt — never embed base64 data URIs in the request.
            image_urls_for_prompt_str, image_placeholder_map = (
                _format_images_for_mjml_prompt(
                    state.generated_image_urls or [],
                    state.image_prompts,
                )
            )
            logger.info(
                "MJML generation: %d image placeholder(s): %s",
                len(image_placeholder_map),
                list(image_placeholder_map.keys()),
            )

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

            if image_placeholder_map and isinstance(generated_mjml, str):
                generated_mjml = _inject_image_placeholders(
                    generated_mjml, image_placeholder_map
                )

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
            mjml_cli = resolve_mjml_cli(settings.MJML_CLI_PATH)
            cmd = [mjml_cli, temp_mjml_file, "--config.validationLevel=strict"]

            logger.info(
                f"MJML Validator/Compiler Node: Executing command: {' '.join(cmd)}"
            )

            returncode, stdout, stderr = await asyncio.to_thread(
                _run_mjml_cli_sync, temp_mjml_file, mjml_cli
            )

            if returncode == 0:
                compiled_html_output = stdout.strip()
                stderr_output = stderr.strip()

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
                stderr_output = stderr.strip()
                logger.error(
                    f"MJML Validator/Compiler Node: mjml CLI failed with return code {returncode}. Stderr: {stderr_output}"
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
#     from mailwright.schemas.template_schemas import UserBriefSchema # Assuming this exists
#
#     async def main():
#         # Mock settings if not running in FastAPI context
#         from mailwright.config import Settings
#         settings_instance = Settings(llm_provider="openai", openai_api_key="your_key") # or "anthropic"
#         # This is a bit of a hack for standalone testing; normally settings are loaded globally.
#         # For real testing, use pytest fixtures to manage settings.
#         global settings
#         settings = settings_instance
#
#         service = MJMLService()
#         test_brief = UserBriefSchema(
#             subject="Welcome to mailwright!",
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
