from dotenv import load_dotenv

load_dotenv()

import logging  # Added for standardized logging
import asyncio  # Added for running the test

# import traceback # Removed for Sprint 3 debugging
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END  # Removed CompiledGraph
from .state import GraphState
from .checkpointer import get_checkpointer_context_manager, SQLITE_CONN_STRING
from mailwright.schemas.template_schemas import UserBriefSchema
from mailwright.core_services.brief_analyzer_service import (
    analyze_brief_for_clarifications,
    BriefAnalysisResult,
)
from mailwright.core_services.mjml_service import MJMLService
from mailwright.core_services.image_generator_service import ImageGeneratorService
from mailwright.db.template_store import create_template_version  # Sprint 2: For StoreV0Node
from mailwright.db.models import AsyncSessionLocal  # Sprint 2: For StoreV0Node
from mailwright.schemas.template_schemas import (
    TemplateVersionCreate,
)  # Sprint 2: For StoreV0Node
from mailwright.core_services.feedback_engine_service import (
    FeedbackEngineService,
    FeedbackEngineServiceError,
)  # Sprint 3: Feedback Engine
from mailwright.config import settings

if settings.RAG_ENABLED:
    from mailwright.core_services.rag_template_service import RAGTemplateService  # Sprint 5: RAG Service
import uuid  # For generating template_id if needed
from typing import Dict, Any

logger = logging.getLogger(__name__)  # Added for standardized logging

# --- Node Names ---
LG_START_NODE_NAME = "LG_Start"
LG_BRIEF_ANALYZER_NODE_NAME = "LG_BriefAnalyzer"
LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME = "LG_WaitForAmendedBrief"
LG_IMAGE_GENERATION_NODE_NAME = "LG_ImageGeneration"  # Added for Sprint 2
LG_MJML_GENERATION_NODE_NAME = "LG_MJMLGeneration"
LG_MJML_VALIDATE_COMPILE_NODE_NAME = "LG_MJMLValidateCompile"
LG_STORE_V0_NODE_NAME = "LG_StoreV0"  # Sprint 2: New node for storing initial version
LG_FEEDBACK_ENGINE_NODE_NAME = "LG_FeedbackEngine"  # Sprint 3: New Node
LG_STORE_V_NEXT_NODE_NAME = "LG_StoreVNext"  # Sprint 3: New Node for revised versions

# --- RAG Node Names (Sprint 5) ---
LG_RAG_GENERATE_BRIEF_FINGERPRINT_NODE_NAME = "LG_RAG_GenerateBriefFingerprint"
LG_RAG_FIND_MATCHING_TEMPLATE_NODE_NAME = "LG_RAG_FindMatchingTemplate"
LG_RAG_POPULATE_CONTENT_NODE_NAME = "LG_RAG_PopulateContent"


# --- Instantiate Services ---
# For now, instantiate them globally. Consider dependency injection for more complex scenarios.
mjml_service = MJMLService()
image_generator_service = ImageGeneratorService()  # Added for Sprint 2
feedback_service = FeedbackEngineService()  # Sprint 3: Feedback Engine Service


# --- Define Node Functions (Placeholders for now) ---
async def start_node(state: GraphState) -> GraphState:
    """
    Placeholder for the starting node of the graph.
    This node would typically receive the initial user brief.
    """
    logger.info("--- Executing Start Node ---")  # Replaced print
    # In a real scenario, this might update the state with the initial brief
    # For now, it does nothing to the state.
    return state


async def brief_analyzer_node(state: GraphState) -> GraphState:
    """
    Analyzes the user's brief using an LLM to identify ambiguities or missing information.
    Updates the graph state with clarification questions or an OK status.
    """
    logger.info("--- Executing Brief Analyzer Node ---")  # Replaced print
    if not state.user_brief_data:
        logger.error(
            "User brief data is missing in state for brief_analyzer_node."
        )  # Replaced print
        state.error_message = "User brief data is missing."
        state.last_operation_status = "ERROR"
        return state

    try:
        user_brief_model = UserBriefSchema.model_validate(state.user_brief_data)
    except Exception as e:
        logger.error(f"Failed to validate user_brief_data: {e}")  # Replaced print
        state.error_message = f"Invalid user brief data format: {e}"
        state.last_operation_status = "ERROR"
        return state

    analysis_result: BriefAnalysisResult = await analyze_brief_for_clarifications(
        user_brief_model, clarification_round=state.clarification_rounds_count
    )
    state.last_operation_status = analysis_result.status
    state.error_message = (
        None  # Clear any previous error message if this step is reached
    )

    if analysis_result.status == "CLARIFICATION_NEEDED":
        state.clarification_questions = analysis_result.clarification_questions
        state.clarification_rounds_count += 1  # Increment the counter
        logger.info(
            f"Clarification needed (round {state.clarification_rounds_count}): {state.clarification_questions}"
        )  # Replaced print
    elif analysis_result.status == "BRIEF_OK":
        state.clarification_questions = None  # Ensure it's cleared
        logger.info("Brief is OK.")  # Replaced print

    elif analysis_result.status == "ERROR":
        state.error_message = (
            analysis_result.error_message
        )  # Set new error if one occurred
        logger.error(
            f"Error in brief analysis: {state.error_message}"
        )  # Replaced print

    # The actual branching logic (LG_ClarificationDecision) will be added in Task 4.2
    # For now, the graph flows linearly. # This comment seems outdated, conditional logic exists.
    return state


async def wait_for_amended_brief_node(state: GraphState) -> GraphState:
    """
    Placeholder node that waits for an amended brief if clarification was needed.
    In a real scenario, this node might pause until external input is received.
    """
    logger.info(
        f"--- Executing {LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME} (Placeholder) ---"
    )  # Replaced print
    # For now, assume the state might be updated externally or by a subsequent mechanism
    state.last_operation_status = "WAITING_FOR_AMENDED_BRIEF"
    # Potentially, this node could re-queue for brief analysis or directly to generation
    # depending on how the graph is designed to resume.
    # For this task, it will simply be a point in the graph.
    return state


async def image_generation_node(state: GraphState) -> GraphState:
    """
    Generates images based on prompts in the state using ImageGeneratorService.
    Updates the state with the URLs of the generated images and their mapping.
    """
    logger.info(f"--- Executing {LG_IMAGE_GENERATION_NODE_NAME} ---")  # Replaced print
    state.image_urls_map = {}  # Initialize/clear previous map
    state.generated_image_urls = []  # Initialize/clear previous list
    accumulated_errors = []

    if not state.image_prompts:
        logger.info(
            "No image prompts found in state. Skipping image generation."
        )  # Replaced print
        state.last_operation_status = "SKIPPED_IMAGE_GENERATION"
        state.error_message = None  # Ensure no error message if skipped
        return state

    for prompt in state.image_prompts:
        if not prompt:  # Skip empty prompts within the list
            logger.warning(
                "Skipping empty image prompt."
            )  # Replaced print and changed level
            state.image_urls_map[prompt] = (
                None  # Record that empty prompt was skipped/failed
            )
            accumulated_errors.append(f"Skipped empty image prompt: '{prompt}'")
            continue
        try:
            logger.info(
                f"Requesting image generation for prompt: '{prompt}'"
            )  # Replaced print
            url = await image_generator_service.generate_image(prompt=prompt)
            if url:
                logger.info(f"Generated image URL: {url}")  # Replaced print
                state.generated_image_urls.append(url)
                state.image_urls_map[prompt] = url
            else:
                logger.warning(
                    f"Failed to generate image for prompt: '{prompt}'"
                )  # Replaced print and changed level
                state.image_urls_map[prompt] = None
                accumulated_errors.append(
                    f"Failed to retrieve URL for prompt: '{prompt}'"
                )
        except Exception as e:
            logger.exception(
                f"Error during image generation for prompt '{prompt}'"
            )  # Replaced print with logger.exception and removed explicit {e}
            state.image_urls_map[prompt] = None
            accumulated_errors.append(f"Exception for prompt '{prompt}': {e}")

    if accumulated_errors:
        state.error_message = "; ".join(accumulated_errors)
        if not state.generated_image_urls:  # All prompts failed or resulted in errors
            state.last_operation_status = "ERROR_IMAGE_GENERATION"
        else:  # Some images were generated, but there were also errors
            state.last_operation_status = (
                "WARNING_IMAGE_GENERATION"  # Partial success with issues
            )
    else:  # All prompts processed successfully
        state.last_operation_status = "SUCCESS_IMAGE_GENERATION"
        state.error_message = None

    return state


async def store_v0_node(
    state: GraphState, config: RunnableConfig | None = None
) -> Dict[str, Any]:  # Return type will effectively be Dict[str, Any]
    """
    Stores the first successfully generated version (v0) of the template
    to the TemplateStoreDB. This node is now flexible and can store the output
    from either the legacy MJML workflow or the new RAG workflow.
    """
    logger.info(f"--- Starting execution of {LG_STORE_V0_NODE_NAME} ---")
    updates_to_state: Dict[str, Any] = {}

    thread_id = (
        config.get("configurable", {}).get("thread_id") if config else None
    )
    template_id = str(thread_id) if thread_id else str(uuid.uuid4())
    version_id = "v0"

    # --- Prepare version_data based on workflow ---
    if state.rag_flow:
        logger.info("Preparing to store RAG workflow output.")
        if not state.final_html_content:
            updates_to_state["error_message"] = (
                "Final HTML content from RAG flow is missing."
            )
            updates_to_state["last_operation_status"] = (
                "ERROR_STORING_VERSION_RAG_MISSING_CONTENT"
            )
            return updates_to_state

        version_data = TemplateVersionCreate(
            template_id=template_id,
            version_id=version_id,
            mjml_source="",  # No MJML in RAG flow
            compiled_html=state.final_html_content,
            user_brief_snapshot={
                "brief": state.plain_text_brief
            },  # Store the plain text brief
            image_assets={"urls": []},  # No images generated in this flow yet
            change_trigger={
                "event": "rag_generation",
                "details": "First successful RAG generation",
            },
            is_approved=False,
        )
    else:
        logger.info("Preparing to store legacy MJML workflow output.")
        if not state.current_mjml or not state.compiled_html:
            updates_to_state["error_message"] = (
                "MJML source or compiled HTML missing for storing version."
            )
            updates_to_state["last_operation_status"] = "ERROR_STORING_VERSION"
            return updates_to_state

        version_data = TemplateVersionCreate(
            template_id=template_id,
            version_id=version_id,
            mjml_source=state.current_mjml,
            compiled_html=state.compiled_html,
            user_brief_snapshot=state.user_brief_data,
            image_assets={"urls": state.generated_image_urls or []},
            change_trigger={
                "event": "initial_generation",
                "details": "First successful generation",
            },
            is_approved=False,
        )

    # --- Commit to Database ---
    logger.info(
        f"LG_STORE_V0_NODE: Attempting to use AsyncSessionLocal: {AsyncSessionLocal}"
    )
    async with AsyncSessionLocal() as db_session:
        logger.info(f"LG_STORE_V0_NODE: Acquired db_session: {type(db_session)}")
        try:
            logger.info(
                f"LG_STORE_V0_NODE: Calling create_template_version with version_id='{version_data.version_id}'"
            )
            stored_version = await create_template_version(
                db=db_session, version_data=version_data
            )
            logger.info(
                f"LG_STORE_V0_NODE: create_template_version returned. Stored version_id: '{stored_version.version_id}'"
            )

            updates_to_state["last_operation_status"] = "SUCCESS_STORED_V0"
            updates_to_state["stored_version_info"] = {
                "template_id": stored_version.template_id,
                "version_id": stored_version.version_id,
                "created_at": str(stored_version.created_at),
            }
            updates_to_state["current_version_id_stored"] = stored_version.version_id
            updates_to_state["error_message"] = None
            logger.info(
                f"LG_STORE_V0_NODE: Successfully stored version. updates_to_state: {updates_to_state}"
            )
        except Exception as e:
            logger.exception(
                "LG_STORE_V0_NODE: Database error during create_template_version call."
            )
            updates_to_state["error_message"] = (
                f"Database error storing version v0: {e}"
            )
            updates_to_state["last_operation_status"] = "ERROR_STORING_VERSION"
            logger.error(f"LG_STORE_V0_NODE: Error. Returning: {updates_to_state}")

    logger.info(
        f"--- Finishing execution of {LG_STORE_V0_NODE_NAME}. Returning: {updates_to_state} ---"
    )
    return updates_to_state


# --- Sprint 3: Feedback Engine Node ---
async def feedback_engine_node(state: GraphState) -> GraphState:
    """
    Processes user feedback using FeedbackEngineService to revise MJML.
    Updates state with revised_mjml_candidate.
    """
    logger.info(f"--- Executing {LG_FEEDBACK_ENGINE_NODE_NAME} ---")

    if not state.user_feedback_content:
        logger.error(
            f"User feedback content is missing in state for {LG_FEEDBACK_ENGINE_NODE_NAME}."
        )
        state.error_message = "User feedback content is missing for revision."
        state.last_operation_status = "ERROR_REVISION_GENERATION_NO_FEEDBACK"
        return state

    if not state.current_mjml:  # This should be the MJML of the version being revised
        logger.error(
            f"Current MJML is missing in state for {LG_FEEDBACK_ENGINE_NODE_NAME} to revise."
        )
        state.error_message = "Current MJML is missing for revision based on feedback."
        state.last_operation_status = "ERROR_REVISION_GENERATION_NO_MJML"
        return state

    try:
        logger.info(
            f"Calling FeedbackEngineService to revise MJML for version_id: {state.version_id_for_feedback}"
        )
        revised_mjml = await feedback_service.revise_mjml_based_on_feedback(
            current_mjml=state.current_mjml, feedback_text=state.user_feedback_content
        )

        state.revised_mjml_candidate = revised_mjml
        state.last_operation_status = "SUCCESS_REVISION_GENERATED"
        state.error_message = None  # Clear previous errors
        logger.info(
            f"Successfully generated revised MJML candidate. Length: {len(revised_mjml) if revised_mjml else 0}"
        )

    except FeedbackEngineServiceError as e:
        logger.error(
            f"FeedbackEngineService error in {LG_FEEDBACK_ENGINE_NODE_NAME}: {e}",
            exc_info=True,
        )
        state.error_message = f"Feedback engine failed to revise MJML: {e}"
        state.last_operation_status = "ERROR_REVISION_GENERATION"
        state.revised_mjml_candidate = None  # Ensure no stale candidate
    except Exception as e:
        logger.error(
            f"Unexpected error in {LG_FEEDBACK_ENGINE_NODE_NAME}: {e}", exc_info=True
        )
        state.error_message = f"Unexpected error during MJML revision: {e}"
        state.last_operation_status = "ERROR_REVISION_GENERATION"
        state.revised_mjml_candidate = None  # Ensure no stale candidate

    return state


# --- Sprint 3: Store Revised Version Node ---
async def store_v_next_node(
    state: GraphState, config: RunnableConfig | None = None
) -> Dict[str, Any]:  # Return type will effectively be Dict[str, Any]
    """
    Stores a successfully revised and validated MJML template as a new version.
    Triggered after LG_MJMLValidateCompileNode in the feedback revision loop.
    """
    logger.info(f"--- Executing {LG_STORE_V_NEXT_NODE_NAME} ---")
    updates_to_state: Dict[str, Any] = {}

    # Check if the preceding validation was successful
    # The MJMLService.validate_and_compile_mjml_node sets last_operation_status = "success"
    # and mjml_validation_status = "VALID"
    if not (
        state.mjml_validation_status == "VALID"
        and state.last_operation_status == "success"
    ):
        error_msg = f"Preceding MJML validation failed or did not complete successfully. Status: {state.mjml_validation_status}, OpStatus: {state.last_operation_status}"
        logger.error(f"Error in {LG_STORE_V_NEXT_NODE_NAME}: {error_msg}")
        updates_to_state["error_message"] = error_msg
        updates_to_state["last_operation_status"] = (
            "ERROR_STORING_REVISED_VERSION_PRE_VALIDATION_FAILED"
        )
        return updates_to_state

    if not state.current_mjml or not state.compiled_html:
        error_msg = "Validated MJML source or compiled HTML missing for storing revised version."
        logger.error(f"Error in {LG_STORE_V_NEXT_NODE_NAME}: {error_msg}")
        updates_to_state["error_message"] = error_msg
        updates_to_state["last_operation_status"] = (
            "ERROR_STORING_REVISED_VERSION_CONTENT_MISSING"
        )
        return updates_to_state

    thread_id = (
        config.get("configurable", {}).get("thread_id") if config else None
    )
    if not thread_id:
        logger.error(
            f"No thread_id (template_id) in config for {LG_STORE_V_NEXT_NODE_NAME}."
        )
        updates_to_state["error_message"] = (
            "Template ID missing, cannot store revised version."
        )
        updates_to_state["last_operation_status"] = (
            "ERROR_STORING_REVISED_VERSION_NO_TEMPLATE_ID"
        )
        return updates_to_state
    template_id = str(thread_id)

    # Generate a new unique version_id for the revised version.
    # Using a prefix for clarity, though a simple UUID is also fine.
    new_version_id = f"v_rev_{uuid.uuid4().hex[:8]}"

    logger.info(
        f"Preparing to store revised version. Template ID: {template_id}, New Version ID: {new_version_id}"
    )

    # Prepare change_trigger information
    change_trigger_info = {
        "event": "feedback_revision",
        "source_version_id": state.version_id_for_feedback or "unknown",
        # Truncate feedback to avoid overly large JSON in DB, if necessary
        "feedback_text_snippet": (state.user_feedback_content or "")[:250] + "..."
        if state.user_feedback_content and len(state.user_feedback_content) > 250
        else (state.user_feedback_content or "No feedback provided"),
    }

    version_data = TemplateVersionCreate(
        template_id=template_id,
        version_id=new_version_id,
        mjml_source=state.current_mjml,  # This should be the validated revised MJML
        compiled_html=state.compiled_html,
        # For user_brief_snapshot and image_assets, we use what's currently in the state.
        # Ideally, for a revised version, these should be copied from the 'source_version_id'.
        # This might require fetching the source version from DB if not carried in state.
        # For now, using current state values as a simplification.
        user_brief_snapshot=state.user_brief_data,
        image_assets={"urls": state.generated_image_urls or []},
        change_trigger=change_trigger_info,
        is_approved=False,  # Revised versions are drafts
    )

    async with AsyncSessionLocal() as db_session:
        try:
            logger.info(
                f"Attempting to store revised version: {template_id}/{new_version_id}"
            )
            stored_version = await create_template_version(
                db=db_session, version_data=version_data
            )
            updates_to_state["last_operation_status"] = "SUCCESS_STORED_REVISED_VERSION"
            # Update state with info about this NEWLY stored version
            updates_to_state["stored_version_info"] = {
                "template_id": stored_version.template_id,
                "version_id": stored_version.version_id,
                "created_at": str(stored_version.created_at),
            }
            updates_to_state["current_version_id_stored"] = stored_version.version_id
            updates_to_state["error_message"] = None
            logger.info(
                f"Successfully stored revised version: {updates_to_state['stored_version_info']}"
            )

            # Clear fields related to the completed feedback cycle
            updates_to_state["user_feedback_content"] = None
            updates_to_state["version_id_for_feedback"] = None
            # revised_mjml_candidate is cleared by the validation node itself

        except Exception as e:
            # print("\n--- LG_StoreVNextNode CAUGHT EXCEPTION ---") # REMOVED DEBUGGING
            # traceback.print_exc() # REMOVED DEBUGGING
            # print("-----------------------------------------") # REMOVED DEBUGGING
            logger.exception(
                f"Error in {LG_STORE_V_NEXT_NODE_NAME}: Database error storing revised version"
            )
            updates_to_state["error_message"] = (
                f"Database error storing revised version {new_version_id}: {e}"
            )
            updates_to_state["last_operation_status"] = (
                "ERROR_STORING_REVISED_VERSION_DB_ERROR"
            )
            # raise e # TEMPORARILY RE-RAISE FOR DEBUGGING - THIS IS THE CHANGE

    return updates_to_state  # Return dict of changes


# --- Conditional Edge Functions ---


def route_rag_or_legacy(state: GraphState) -> str:
    """
    Routes to the RAG workflow or the legacy MJML workflow based on the rag_flow flag.
    If RAG_ENABLED is false the RAG path is unavailable and all requests fall through
    to the legacy workflow regardless of the rag_flow flag.
    """
    logger.info(
        f"--- Decision Point: RAG or Legacy Flow? rag_flow={state.rag_flow}, RAG_ENABLED={settings.RAG_ENABLED} ---"
    )
    if state.rag_flow:
        if not settings.RAG_ENABLED:
            logger.warning(
                "rag_flow=true was requested but RAG_ENABLED=false. "
                "Falling back to legacy MJML workflow."
            )
        else:
            logger.info(f"Routing to: {LG_RAG_GENERATE_BRIEF_FINGERPRINT_NODE_NAME}")
            return LG_RAG_GENERATE_BRIEF_FINGERPRINT_NODE_NAME

    logger.info("Delegating to legacy flow router: route_initial_or_feedback")
    return route_initial_or_feedback(state)


def route_initial_or_feedback(state: GraphState) -> str:
    """
    Routes to feedback engine if feedback is present, otherwise to brief analyzer.
    This should be called early in the graph.
    """
    logger.info(
        f"--- Decision Point: route_initial_or_feedback. Feedback content present: {bool(state.user_feedback_content)}, "
        f"Last Op: {state.last_operation_status} ---"
    )
    # Check if feedback has been submitted (e.g., via API which sets these fields)
    if state.user_feedback_content and state.version_id_for_feedback:
        # The API sets last_operation_status = "FEEDBACK_RECEIVED" before invoking for feedback processing.
        # We can use this or directly check for user_feedback_content.
        logger.info(
            f"Routing to: {LG_FEEDBACK_ENGINE_NODE_NAME} due to pending feedback."
        )
        return LG_FEEDBACK_ENGINE_NODE_NAME
    else:
        logger.info(
            f"Routing to: {LG_BRIEF_ANALYZER_NODE_NAME} for initial or continued brief processing."
        )
        return LG_BRIEF_ANALYZER_NODE_NAME


def should_request_clarification(state: GraphState) -> str:
    """
    Determines the next path based on whether clarification questions are present.
    """
    logger.info(  # Replaced print
        f"--- Decision Point: Evaluating state for clarification. Questions: {state.clarification_questions}, Last Op Status: {state.last_operation_status} ---"
    )
    if state.last_operation_status == "ERROR":
        logger.info(f"Routing to: {END} due to error.")  # Replaced print
        return END  # Directly go to END if an error occurred in the previous node
    elif (
        state.clarification_questions
        and state.last_operation_status == "CLARIFICATION_NEEDED"
    ):
        logger.info(
            f"Routing to: {LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME}"
        )  # Replaced print
        return LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME
    else:
        # This covers BRIEF_OK or cases where clarification_questions might be None/empty
        # and status is not CLARIFICATION_NEEDED (e.g., after an amended brief, or if brief was initially OK)
        # BRIEF_OK should now go to Image Generation
        logger.info(f"Routing to: {LG_IMAGE_GENERATION_NODE_NAME}")  # Replaced print
        return LG_IMAGE_GENERATION_NODE_NAME


# Updated conditional edge function for Sprint 3 feedback loop
def should_route_after_validation(state: GraphState) -> str:
    """
    Determines routing after MJML validation.
    If valid and in feedback loop (version_id_for_feedback is set), routes to StoreVNext.
    If valid and initial generation, routes to StoreV0.
    If invalid or error, routes to END.
    """
    logger.info(
        f"--- Decision Point: After MJML Validation. Status: {state.mjml_validation_status}, "
        f"Op: {state.last_operation_status}, FeedbackVer: {state.version_id_for_feedback} ---"
    )

    # Check for prior errors from the validation node itself
    # The MJML service node sets its own last_operation_status, e.g. "success" or "failure_mjml_validation_compilation"
    if (
        state.last_operation_status == "failure_mjml_validation_compilation"
        or state.mjml_validation_status == "ERROR"
    ):
        logger.warning(
            f"MJML validation/compilation node indicated failure. Status: {state.mjml_validation_status}, Op: {state.last_operation_status}. Routing to END."
        )
        return END

    if state.mjml_validation_status == "VALID":
        # The mjml_service.validate_and_compile_mjml_node sets last_operation_status = "success" on valid compilation
        if state.last_operation_status != "success":
            # This case should ideally not be hit if the validator node correctly sets its status upon successful validation.
            logger.warning(
                f"MJML validation status is VALID, but last_operation_status is '{state.last_operation_status}' instead of 'success'. Proceeding to store."
            )

        if (
            state.version_id_for_feedback
        ):  # Indicates we are in a feedback revision loop
            logger.info(f"Routing to: {LG_STORE_V_NEXT_NODE_NAME} for revised version.")
            return LG_STORE_V_NEXT_NODE_NAME
        else:  # Initial generation flow
            logger.info(f"Routing to: {LG_STORE_V0_NODE_NAME} for initial version.")
            return LG_STORE_V0_NODE_NAME
    elif state.mjml_validation_status == "INVALID":
        logger.warning("MJML validation status is INVALID. Routing to END.")
        return END
    else:
        # Fallback for any other UNKNOWN or unexpected mjml_validation_status
        logger.error(
            f"Unexpected MJML validation state: '{state.mjml_validation_status}'. Routing to END."
        )
        return END


def did_mjml_generation_fail(state: GraphState) -> str:
    """
    Checks if the MJML generation step failed and routes accordingly.
    """
    logger.info(
        f"--- Decision Point: After MJML Generation. Status: {state.last_operation_status} ---"
    )
    if state.last_operation_status == "ERROR_MJML_GENERATION":
        logger.error("MJML generation failed. Routing to END.")
        return END
    else:
        logger.info(f"MJML generation succeeded. Routing to {LG_MJML_VALIDATE_COMPILE_NODE_NAME}.")
        return LG_MJML_VALIDATE_COMPILE_NODE_NAME


# --- Function to Create the Graph Builder ---
def create_graph_builder() -> StateGraph:
    """
    Builds and configures the StateGraph for template generation.
    """
    builder = StateGraph(GraphState)

    # --- Add Nodes ---
    # Legacy Nodes
    builder.add_node(LG_START_NODE_NAME, start_node)
    builder.add_node(LG_BRIEF_ANALYZER_NODE_NAME, brief_analyzer_node)
    builder.add_node(LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME, wait_for_amended_brief_node)
    builder.add_node(LG_IMAGE_GENERATION_NODE_NAME, image_generation_node)
    # The MJML service nodes are methods of the mjml_service instance
    builder.add_node(
        LG_MJML_GENERATION_NODE_NAME, mjml_service.generate_mjml_node
    )  # Updated
    builder.add_node(
        LG_MJML_VALIDATE_COMPILE_NODE_NAME, mjml_service.validate_and_compile_mjml_node
    )  # Updated
    builder.add_node(LG_STORE_V0_NODE_NAME, store_v0_node)
    builder.add_node(LG_FEEDBACK_ENGINE_NODE_NAME, feedback_engine_node)
    builder.add_node(LG_STORE_V_NEXT_NODE_NAME, store_v_next_node)

    # RAG Nodes (Sprint 5) — only added when RAG_ENABLED=true
    if settings.RAG_ENABLED:
        builder.add_node(
            LG_RAG_GENERATE_BRIEF_FINGERPRINT_NODE_NAME,
            lg_rag_generate_brief_fingerprint_node,
        )
        builder.add_node(
            LG_RAG_FIND_MATCHING_TEMPLATE_NODE_NAME, lg_rag_find_matching_template_node
        )
        builder.add_node(LG_RAG_POPULATE_CONTENT_NODE_NAME, lg_rag_populate_content_node)

    # --- Add Edges ---
    # Entry point routing
    rag_edge_map = {}
    if settings.RAG_ENABLED:
        rag_edge_map[LG_RAG_GENERATE_BRIEF_FINGERPRINT_NODE_NAME] = LG_RAG_GENERATE_BRIEF_FINGERPRINT_NODE_NAME

    builder.add_conditional_edges(
        START,
        route_rag_or_legacy,
        {
            **rag_edge_map,
            # Legacy paths
            LG_BRIEF_ANALYZER_NODE_NAME: LG_BRIEF_ANALYZER_NODE_NAME,
            LG_FEEDBACK_ENGINE_NODE_NAME: LG_FEEDBACK_ENGINE_NODE_NAME,
        },
    )

    # RAG Workflow Edges — only when RAG is enabled
    if settings.RAG_ENABLED:
        builder.add_edge(
            LG_RAG_GENERATE_BRIEF_FINGERPRINT_NODE_NAME,
            LG_RAG_FIND_MATCHING_TEMPLATE_NODE_NAME,
        )
        builder.add_edge(
            LG_RAG_FIND_MATCHING_TEMPLATE_NODE_NAME, LG_RAG_POPULATE_CONTENT_NODE_NAME
        )
        builder.add_edge(LG_RAG_POPULATE_CONTENT_NODE_NAME, LG_STORE_V0_NODE_NAME)

    # Legacy Workflow Edges
    # builder.add_conditional_edges(START, route_initial_or_feedback) # This is now replaced by the new entry point
    builder.add_conditional_edges(
        LG_BRIEF_ANALYZER_NODE_NAME,
        should_request_clarification,
        {
            LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME: LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME,
            LG_IMAGE_GENERATION_NODE_NAME: LG_IMAGE_GENERATION_NODE_NAME,  # Changed from MJMLGeneration
            END: END,  # Add this path for error handling
        },
    )

    # If brief was amended, it goes back to brief analyzer.
    builder.add_edge(LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME, LG_BRIEF_ANALYZER_NODE_NAME)

    # After image generation, proceed to MJML generation
    builder.add_edge(LG_IMAGE_GENERATION_NODE_NAME, LG_MJML_GENERATION_NODE_NAME)

    # After MJML generation, check for failure before proceeding to validation
    builder.add_conditional_edges(
        LG_MJML_GENERATION_NODE_NAME,
        did_mjml_generation_fail,
        {
            LG_MJML_VALIDATE_COMPILE_NODE_NAME: LG_MJML_VALIDATE_COMPILE_NODE_NAME,
            END: END,
        },
    )

    # Conditional edge after MJML validation (handles both initial and revised flows)
    builder.add_conditional_edges(
        LG_MJML_VALIDATE_COMPILE_NODE_NAME,
        should_route_after_validation,  # Use the new conditional router
        {
            LG_STORE_V0_NODE_NAME: LG_STORE_V0_NODE_NAME,
            LG_STORE_V_NEXT_NODE_NAME: LG_STORE_V_NEXT_NODE_NAME,  # Added route to new store node
            END: END,
        },
    )

    # After storing V0, go to END for now.
    builder.add_edge(LG_STORE_V0_NODE_NAME, END)
    # After storing a revised version (VNext), also go to END.
    builder.add_edge(LG_STORE_V_NEXT_NODE_NAME, END)  # Added edge to END

    # --- Edges for the Feedback Loop ---
    # From Feedback Engine to MJML Validation (which is now flexible)
    builder.add_edge(
        LG_FEEDBACK_ENGINE_NODE_NAME, LG_MJML_VALIDATE_COMPILE_NODE_NAME
    )  # Added edge
    # How does the graph get to LG_FEEDBACK_ENGINE_NODE_NAME?
    # This is typically triggered by an API call that updates the state and invokes the graph.

    return builder


# Example of how to invoke (for testing, not for API layer yet):
async def run_graph():
    logger.info(
        f"Attempting to use SQLite database at: {SQLITE_CONN_STRING}"
    )  # Replaced print

    config = {"configurable": {"thread_id": "test_thread_1"}}

    # Create a UserBriefSchema instance for the initial input
    sample_brief = UserBriefSchema(
        subject="Exciting Summer Sale Announcement!",
        body_copy="Get ready for our biggest summer sale yet! Amazing discounts on all your favorite products. This email will showcase a vibrant beach scene and a clear call to action to visit our website.",
        cta_text="Shop Summer Sale Now",
        cta_url="https://example.com/summer-sale",
        image_suggestions=[
            "A vibrant beach scene with people enjoying the sun",
            "Product collage of sale items",
        ],  # Though we'll use image_prompts below
    )
    initial_input = {  # Pass as a dictionary
        "user_brief_data": sample_brief.model_dump(mode="json"),
        "image_prompts": [
            "A photo of a cute tabby cat napping in a sunbeam",
            "A detailed illustration of a futuristic robot assistant",
        ],
        "is_test_forcing_brief_ok": True,  # Temporary for testing
    }

    logger.info(
        f"\n--- Invoking graph with input: {initial_input} and config: {config} ---"
    )  # Replaced print

    async with get_checkpointer_context_manager() as checkpointer:
        if checkpointer is None:
            logger.error(
                "Failed to obtain a valid checkpointer instance."
            )  # Replaced print
            return

        logger.info("Checkpointer obtained successfully.")  # Replaced print

        # Create the builder and compile the graph inside the checkpointer's context
        graph_builder = create_graph_builder()
        graph_to_run = graph_builder.compile(checkpointer=checkpointer)
        logger.info("Graph compiled successfully with checkpointer.")  # Replaced print

        # The following block for re-initializing sample_brief and initial_input is redundant
        # and has been removed. The initial_input defined earlier will be used.
        # Create a UserBriefSchema instance for the initial input
        # sample_brief = UserBriefSchema(
        #     subject="Test Subject from Graph Run",
        #     body_copy="This is a test body copy for the initial graph execution."
        # )
        # # This re-initialization of initial_input seems redundant if it's the same as above.
        # # Assuming it was for clarity or a potential change, will update it as well.
        # initial_input = {"user_brief_data": sample_brief.model_dump(mode='json')}

        # print(f"\n--- Invoking graph with input: {initial_input} and config: {config} ---") # This print is also redundant

        try:
            # Use the initial_input defined before the 'async with' block
            async for event in graph_to_run.astream_events(
                initial_input, config=config, version="v1"
            ):
                logger.debug(
                    f"\nGraph Event:\n{event}\n"
                )  # Replaced print, changed to debug
        except Exception as e:
            logger.exception(
                f"An error occurred during graph execution: {e}"
            )  # Replaced print and traceback with logger.exception, but kept explicit {e} for now
            # import traceback # Removed
            # traceback.print_exc() # Removed

    logger.info(
        "--- Graph execution finished (checkpointer context exited) ---"
    )  # Replaced print


if __name__ == "__main__":
    # This is a basic test run, actual invocation will be from API endpoints.
    logger.info("--- Starting test graph execution ---")  # Replaced print
    asyncio.run(run_graph())
    logger.info("--- Test graph execution complete ---")  # Replaced print


# --- RAG Workflow Nodes (Sprint 5) ---
async def lg_rag_generate_brief_fingerprint_node(state: GraphState) -> Dict[str, Any]:
    """
    Generates a structural fingerprint from the plain-text brief and then
    creates a vector embedding from that fingerprint.
    """
    logger.info(f"--- Executing {LG_RAG_GENERATE_BRIEF_FINGERPRINT_NODE_NAME} ---")
    updates_to_state = {}
    async with AsyncSessionLocal() as db_session:
        try:
            rag_service = RAGTemplateService(db_session)

            # Step 1: Generate the fingerprint string
            fingerprint = await rag_service.generate_fingerprint_for_brief(
                state.plain_text_brief
            )
            if not fingerprint:
                raise ValueError("Fingerprint generation resulted in an empty string.")

            updates_to_state["brief_fingerprint"] = fingerprint

            # Step 2: Generate the embedding from the fingerprint
            embedding = await rag_service.generate_embedding(fingerprint)
            if not embedding:
                raise ValueError("Embedding generation resulted in an empty list.")

            updates_to_state["brief_embedding"] = embedding
            updates_to_state["last_operation_status"] = "SUCCESS_FINGERPRINT_EMBEDDED"

        except Exception as e:
            logger.error(f"Error in fingerprint/embedding node: {e}", exc_info=True)
            updates_to_state["error_message"] = (
                f"Failed to generate brief fingerprint or embedding: {e}"
            )
            updates_to_state["last_operation_status"] = "ERROR_FINGERPRINT_EMBEDDING"
    return updates_to_state


async def lg_rag_find_matching_template_node(state: GraphState) -> Dict[str, Any]:
    """
    Finds the best matching template in the RAG corpus based on the brief's embedding.
    """
    logger.info(f"--- Executing {LG_RAG_FIND_MATCHING_TEMPLATE_NODE_NAME} ---")
    if not state.brief_embedding:
        return {
            "last_operation_status": "ERROR_MISSING_EMBEDDING",
            "error_message": "Brief embedding was not generated.",
        }

    async with AsyncSessionLocal() as session:
        rag_service = RAGTemplateService(session)
        # Pass the use_placeholders flag from the state to the service
        retrieved_html = await rag_service.find_best_matching_template(
            state.brief_embedding, state.use_placeholders
        )

        if not retrieved_html:
            return {
                "last_operation_status": "ERROR_TEMPLATE_NOT_FOUND",
                "error_message": "No suitable template found in the RAG corpus.",
            }

        return {
            "retrieved_template_html": retrieved_html,
            "last_operation_status": "SUCCESS_TEMPLATE_FOUND",
        }


async def lg_rag_populate_content_node(state: GraphState) -> Dict[str, Any]:
    """
    Populates the retrieved template with content from the brief.
    """
    logger.info(f"--- Executing {LG_RAG_POPULATE_CONTENT_NODE_NAME} ---")
    updates_to_state = {}
    async with AsyncSessionLocal() as db_session:
        try:
            rag_service = RAGTemplateService(db_session)
            final_html = await rag_service.populate_template_with_brief(
                state.retrieved_template_html, state.plain_text_brief
            )
            updates_to_state["final_html_content"] = final_html
            updates_to_state["last_operation_status"] = "SUCCESS_CONTENT_POPULATED"
        except Exception as e:
            logger.error(f"Error in content population node: {e}", exc_info=True)
            updates_to_state["error_message"] = f"Failed to populate content: {e}"
            updates_to_state["last_operation_status"] = "ERROR_CONTENT_POPULATION"
    return updates_to_state
