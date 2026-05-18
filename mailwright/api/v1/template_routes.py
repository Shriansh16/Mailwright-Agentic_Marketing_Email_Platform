from dotenv import load_dotenv

load_dotenv()

import logging  # Added for standardized logging
import uuid  # For generating unique IDs
from typing import Annotated, List  # Added List

from fastapi import APIRouter, status, HTTPException, Depends  # Added Depends
from fastapi.responses import JSONResponse, HTMLResponse  # Added HTMLResponse

from mailwright.schemas.template_schemas import (
    TemplateCreationRequest,
    TemplateCreationResponseSchema,
    TemplateStatusSchema,
    AmendedBriefRequest,  # Will be used for PUT endpoint
    TemplateVersionListSchema,
    VersionMetadataSchema,
    VersionPreviewURLsSchema,
    FeedbackRequestSchema,  # Sprint 3: New Schema
    ApprovalResponseSchema,  # Sprint 3: New Schema for Approval
)

# Ensure all necessary node names are available if used in interrupt_after
from mailwright.graphs.template_generation_graph import (
    create_graph_builder,
    LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME,
)
from mailwright.graphs.checkpointer import get_checkpointer_context_manager  # Added
from mailwright.graphs.state import GraphState  # Added
from mailwright.db.template_store import (
    get_template_version,
    get_db_session,
    get_all_template_versions_for_template_id,
    approve_template_version,
    get_approved_template_version_for_template,  # Sprint 3: Added for status check
)
from sqlalchemy.ext.asyncio import AsyncSession  # Added

logger = logging.getLogger(__name__)  # Added for standardized logging
router = APIRouter()


@router.post(
    "/",
    response_model=TemplateCreationResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate Email Template Generation",
    response_description="Details of the initiated template generation task.",
)
async def create_template_generation_task(request_data: TemplateCreationRequest):
    template_id = uuid.uuid4()
    config = {"configurable": {"thread_id": str(template_id)}}

    # --- Initialize Graph State based on the selected workflow ---
    if request_data.rag_flow:
        # RAG Workflow
        initial_graph_state_dict = GraphState(
            rag_flow=True,
            plain_text_brief=request_data.plain_text_brief,
            use_placeholders=request_data.use_placeholders,
            last_operation_status="INITIATED_RAG_FLOW",
        ).model_dump(exclude_none=True)
    else:
        # Legacy MJML Workflow
        initial_graph_state_dict = GraphState(
            user_brief_data=request_data.user_brief.model_dump(mode="json"),
            last_operation_status="INITIATED",
        ).model_dump(exclude_none=True)

    current_status = "pending_brief_analysis"  # Default status

    try:
        async with get_checkpointer_context_manager() as checkpointer:
            if checkpointer is None:
                logger.error(
                    "Failed to obtain a valid checkpointer instance from context manager in create_template_generation_task."
                )
                raise RuntimeError("Failed to initialize checkpointer for the graph.")

            builder = create_graph_builder()
            graph = builder.compile(checkpointer=checkpointer)

            # Invoke the graph, allowing it to interrupt after specific nodes
            await graph.ainvoke(
                initial_graph_state_dict,
                config=config,
                interrupt_after=[
                    LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME,
                    # Removed LG_MJML_GENERATION_NODE_NAME to allow automatic workflow continuation
                    # Add other relevant interruption points if the graph evolves
                ],
            )

            current_graph_state_snapshot = await graph.aget_state(
                config
            )  # Changed to await aget_state
            if (
                not current_graph_state_snapshot
                or not current_graph_state_snapshot.values
            ):
                logger.warning(
                    f"Graph execution for {template_id} started but current state is empty or not found immediately after invoke."
                )
                current_status = (
                    "pending_analysis_after_invoke_issue"  # Fallback status
                )
            else:
                current_state_values = current_graph_state_snapshot.values
                current_status = current_state_values.get(
                    "last_operation_status", "pending_brief_analysis"
                )

    except Exception as e:
        logger.exception(
            f"Error during graph initiation or initial invoke for {template_id}: {str(e)}"
        )
        # Log the full traceback for server-side debugging
        raise HTTPException(
            status_code=500,
            detail=f"Error initiating template generation graph: {str(e)}",
        ) from e

    status_poll_url = f"/api/v1/templates/{template_id}/status"

    return TemplateCreationResponseSchema(
        template_id=str(template_id),
        task_id=str(template_id),
        status=current_status,
        message="Template creation process initiated and graph invoked.",
        status_poll_url=status_poll_url,
    )


@router.get(
    "/{template_id}/status",
    response_model=TemplateStatusSchema,
    status_code=status.HTTP_200_OK,
    summary="Get Template Generation Task Status",
    response_description="Current status and details of the template generation task.",
)
async def get_template_task_status(
    template_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db_session)]
):
    config = {"configurable": {"thread_id": str(template_id)}}

    try:
        # Sprint 3: Check for an approved version first
        approved_db_version = await get_approved_template_version_for_template(
            db, str(template_id)
        )

        if approved_db_version:
            logger.info(
                f"Template {template_id} has an approved version: {approved_db_version.version_id}. Reporting as 'approved_pending_import'."
            )
            return TemplateStatusSchema(
                template_id=str(template_id),
                task_id=str(
                    template_id
                ),  # task_id is same as template_id in this system
                status="approved_pending_import",
                approved_version_id=approved_db_version.version_id,
                current_version_id=approved_db_version.version_id,  # The current active version is the approved one
                html_preview_url=f"/api/v1/templates/{template_id}/versions/{approved_db_version.version_id}/html",
                mjml_source_url=f"/api/v1/templates/{template_id}/versions/{approved_db_version.version_id}/mjml",
                message=f"Template version {approved_db_version.version_id} is approved and pending import.",
                # Graph-specific fields are generally not applicable or are superseded by approval
                clarification_questions=None,
                brief_submission_token=None,
                current_mjml=None,  # Or could be set to the approved version's MJML if desired
                compiled_html=None,  # Or could be set to the approved version's HTML
                mjml_validation_status=None,  # Or "N/A"
            )

        # If no approved version, proceed to check graph state
        async with get_checkpointer_context_manager() as checkpointer:
            if checkpointer is None:
                logger.error(
                    "Failed to obtain a valid checkpointer instance from context manager in get_template_task_status."
                )
                # Consider if a 500 or 404 is more appropriate if checkpointer itself fails.
                # For now, a 500 seems reasonable as it's an internal server issue.
                raise HTTPException(
                    status_code=500,
                    detail="Failed to initialize checkpointer to retrieve task status.",
                )

            builder = create_graph_builder()
            graph = builder.compile(checkpointer=checkpointer)
            graph_state_snapshot = await graph.aget_state(
                config
            )  # Changed to await aget_state

            if not graph_state_snapshot or not graph_state_snapshot.values:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template task with ID {template_id} not found or no state persisted.",
                )

            state_values = graph_state_snapshot.values

            # Determine current status and preview readiness
            last_operation_status = state_values.get("last_operation_status", "unknown")
            current_version_id_stored = state_values.get("current_version_id_stored")
            current_mjml_content = state_values.get("current_mjml")
            compiled_html_content = state_values.get("compiled_html")
            mjml_validation_state = state_values.get("mjml_validation_status")

            status_for_response = last_operation_status
            html_preview_url_val = None
            mjml_source_url_val = None

            is_ready_for_preview = (
                current_version_id_stored is not None
                and current_mjml_content is not None
                and compiled_html_content is not None
                and mjml_validation_state
                == "VALID"  # Assuming "VALID" is the success status
            )

            if is_ready_for_preview:
                status_for_response = "READY_FOR_PREVIEW"
                html_preview_url_val = f"/api/v1/templates/{template_id}/versions/{current_version_id_stored}/html"
                mjml_source_url_val = f"/api/v1/templates/{template_id}/versions/{current_version_id_stored}/mjml"

            status_message = f"Current status: {status_for_response}"
            error_message = state_values.get("error_message")
            if error_message:
                status_message += f". Error: {error_message}"

            brief_token_for_put = None
            if (
                status_for_response == "WAITING_FOR_AMENDED_BRIEF"
            ):  # Or whatever status the node sets
                # Placeholder for token generation logic if needed for PUT /brief
                pass

            return TemplateStatusSchema(
                template_id=str(template_id),
                task_id=str(template_id),
                status=status_for_response,
                current_version_id=current_version_id_stored,
                html_preview_url=html_preview_url_val,
                mjml_source_url=mjml_source_url_val,
                clarification_questions=state_values.get("clarification_questions"),
                brief_submission_token=brief_token_for_put,
                message=status_message,
                current_mjml=current_mjml_content,
                compiled_html=compiled_html_content,
                mjml_validation_status=mjml_validation_state,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving task status for {template_id}: {str(e)}")
        # Log the full traceback for server-side debugging
        raise HTTPException(
            status_code=500, detail=f"Error retrieving task status: {str(e)}"
        ) from e


@router.put(
    "/{template_id}/brief",
    # Not using response_model for now, returning JSONResponse directly
    # response_model=TemplateCreationResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Amended Brief for Template",
    response_description="Confirmation that the amended brief has been received and processing has resumed.",
)
async def update_template_brief(
    template_id: uuid.UUID, amended_brief_request: AmendedBriefRequest
):
    config = {"configurable": {"thread_id": str(template_id)}}
    new_status = "unknown_after_amend"  # Default status

    try:
        async with get_checkpointer_context_manager() as checkpointer:
            if checkpointer is None:
                logger.error(
                    "Failed to obtain a valid checkpointer instance from context manager in update_template_brief."
                )
                raise HTTPException(
                    status_code=500,
                    detail="Failed to initialize checkpointer to update brief.",
                )

            builder = create_graph_builder()
            graph = builder.compile(checkpointer=checkpointer)

            # Optional: Validate current state before update
            current_state_snapshot = await graph.aget_state(
                config
            )  # Changed to await aget_state
            if not current_state_snapshot or not current_state_snapshot.values:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template task with ID {template_id} not found for update.",
                )

            # Example check: Ensure the graph is actually waiting for a brief.
            # current_op_status = current_state_snapshot.values.get("last_operation_status")
            # if current_op_status != "WAITING_FOR_AMENDED_BRIEF": # Or the specific status set by LG_WaitForAmendedBriefNode
            #     raise HTTPException(
            #         status_code=status.HTTP_409_CONFLICT,
            #         detail=f"Template {template_id} is not currently awaiting an amended brief. Current status: {current_op_status}"
            #     )

            values_to_update = {
                "user_brief_data": amended_brief_request.user_brief.model_dump(
                    mode="json"
                ),
                "clarification_questions": None,  # Clear previous questions
                "error_message": None,  # Clear previous errors
                "last_operation_status": "AMENDED_BRIEF_RECEIVED",  # New status before re-invoke
            }

            await graph.aupdate_state(
                config, values_to_update
            )  # Changed to await aupdate_state

            # Invoke the graph again to process the updated state.
            await graph.ainvoke(
                None,  # Input is None as the relevant data is now in the state via update_state
                config=config,
                interrupt_after=[
                    LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME,  # Might loop back if still needs clarification
                    # Removed LG_MJML_GENERATION_NODE_NAME to allow automatic workflow continuation
                ],
            )

            new_state_snapshot = await graph.aget_state(
                config
            )  # Changed to await aget_state
            if not new_state_snapshot or not new_state_snapshot.values:
                logger.warning(
                    f"State for {template_id} not found or empty after amend and invoke."
                )
                # new_status remains "unknown_after_amend"
            else:
                new_status = new_state_snapshot.values.get(
                    "last_operation_status", "pending_brief_analysis"
                )

        status_poll_url = f"/api/v1/templates/{template_id}/status"

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "template_id": str(template_id),
                "task_id": str(template_id),
                "status": new_status,
                "message": "Amended brief received by LangGraph. Processing resumed.",
                "status_poll_url": status_poll_url,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating template brief for {template_id}: {str(e)}")
        # Log the full traceback for server-side debugging
        raise HTTPException(
            status_code=500, detail=f"Error processing amended brief: {str(e)}"
        ) from e


@router.get(
    "/{template_id}/versions",
    response_model=TemplateVersionListSchema,
    status_code=status.HTTP_200_OK,
    summary="List All Versions for a Template",
    response_description="A list of metadata for all available versions of the template.",
)
async def list_template_versions(
    template_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db_session)]
):
    logger.debug(f"Listing versions for template_id: {template_id}")
    db_versions = await get_all_template_versions_for_template_id(
        db=db,
        template_id=str(template_id),  # Ensure template_id is string for DB query
    )

    version_metadata_list: List[VersionMetadataSchema] = []
    for db_version in db_versions:
        preview_urls = VersionPreviewURLsSchema(
            html=f"/api/v1/templates/{db_version.template_id}/versions/{db_version.version_id}/html",
            mjml=f"/api/v1/templates/{db_version.template_id}/versions/{db_version.version_id}/mjml",
        )
        version_metadata = VersionMetadataSchema(
            version_id=db_version.version_id,
            created_at=db_version.created_at,
            change_trigger=db_version.change_trigger,  # This is already a dict/JSONB
            is_approved=db_version.is_approved,
            preview_urls=preview_urls,
        )
        version_metadata_list.append(version_metadata)

    return TemplateVersionListSchema(versions=version_metadata_list)


@router.get(
    "/{template_id}/versions/{version_id}/html",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Compiled HTML for a Template Version",
    response_description="The compiled HTML content of the specified template version.",
)
async def get_template_version_html(
    template_id: uuid.UUID,
    version_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    logger.debug(
        f"Getting HTML for template_id: {template_id}, version_id: {version_id}"
    )
    try:
        template_version = await get_template_version(db, str(template_id), version_id)
        if not template_version or not template_version.compiled_html:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="HTML content not found for this template version.",
            )
        return HTMLResponse(content=template_version.compiled_html)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Error retrieving HTML for template {template_id} version {version_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving HTML content: {str(e)}",
        ) from e


@router.get(
    "/{template_id}/versions/{version_id}/mjml",
    # response_model=MJMLSourceResponseSchema, # Or just return JSON directly
    status_code=status.HTTP_200_OK,
    summary="Get MJML Source for a Template Version",
    response_description="The MJML source code of the specified template version.",
)
async def get_template_version_mjml(
    template_id: uuid.UUID,
    version_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    logger.debug(
        f"Getting MJML for template_id: {template_id}, version_id: {version_id}"
    )
    try:
        template_version = await get_template_version(db, str(template_id), version_id)
        if not template_version or not template_version.mjml_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="MJML source not found for this template version.",
            )
        return JSONResponse(content={"mjml_source": template_version.mjml_source})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Error retrieving MJML for template {template_id} version {version_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving MJML source: {str(e)}",
        ) from e


# --- Sprint 3: Feedback Endpoint ---


@router.post(
    "/{template_id}/versions/{version_id}/feedback",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Feedback for a Template Version and Trigger Revision",
    response_description="Feedback received and revision process initiated.",
    # Potentially add a response model if we want to return more than just 202
)
async def submit_template_feedback(
    template_id: uuid.UUID,
    version_id: str,
    feedback_data: FeedbackRequestSchema,  # Sprint 3: New Schema
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    logger.info(f"Received feedback for template {template_id}, version {version_id}")

    # 1. Validate template_id and version_id existence
    db_version = await get_template_version(
        db=db, template_id=str(template_id), version_id=version_id
    )
    if not db_version:
        logger.warning(
            f"Template version not found: {template_id}/{version_id} for feedback submission."
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template ID {template_id} with version ID {version_id} not found.",
        )

    config = {"configurable": {"thread_id": str(template_id)}}

    try:
        async with get_checkpointer_context_manager() as checkpointer:
            if checkpointer is None:
                logger.error("Failed to obtain checkpointer for feedback submission.")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to initialize checkpointer for feedback processing.",
                )

            builder = create_graph_builder()
            graph = builder.compile(checkpointer=checkpointer)

            # Get current state to update it
            # current_graph_state_snapshot = await graph.aget_state(config)
            # if not current_graph_state_snapshot or not current_graph_state_snapshot.values:
            #     logger.error(f"No existing graph state found for template {template_id} to apply feedback.")
            #     raise HTTPException(
            #         status_code=status.HTTP_404_NOT_FOUND,
            #         detail=f"Graph state for template {template_id} not found. Cannot apply feedback."
            #     )
            # current_state_values = current_graph_state_snapshot.values

            # Prepare updated state values for the graph
            # We are not directly modifying the *current* state snapshot from aget_state,
            # but rather providing the update dictionary to ainvoke, which internally handles state updates.
            # LangGraph's aupdate_state might be an alternative if we need to ensure the state is updated *before* a subsequent ainvoke
            # but for passing new inputs to resume/trigger a flow, passing them in ainvoke's input is standard.

            update_payload = {
                "user_feedback_content": feedback_data.feedback_text,
                "version_id_for_feedback": version_id,
                "current_mjml": db_version.mjml_source,  # Provide the MJML of the version being reviewed
                "last_operation_status": "FEEDBACK_RECEIVED",
                # Clear any previous errors specific to generation before feedback round
                "error_message": None,
                "clarification_questions": None,  # Clear any pending clarifications
            }

            logger.info(
                f"Invoking graph for template {template_id} with feedback for version {version_id}."
            )

            # Invoke the graph with the new feedback.
            # The graph's internal logic will route to the feedback engine.
            # We might need to specify interrupt_after or interrupt_before specific nodes
            # related to the feedback loop once those are defined in the graph.
            # For now, let it run until its next natural interruption or end.
            await graph.ainvoke(
                update_payload,
                config=config,
                # interrupt_after=[LG_SOME_FEEDBACK_NODE] # Example
            )

            # Potentially retrieve and log the new status after feedback processing starts
            # new_graph_state_snapshot = await graph.aget_state(config)
            # new_status = "unknown_after_feedback"
            # if new_graph_state_snapshot and new_graph_state_snapshot.values:
            #     new_status = new_graph_state_snapshot.values.get("last_operation_status", new_status)
            # logger.info(f"Graph status for {template_id} after feedback invocation: {new_status}")

            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "message": "Feedback received and revision process initiated."
                },
            )

    except HTTPException:  # Re-raise HTTPExceptions directly
        raise
    except Exception as e:
        logger.exception(
            f"Error processing feedback for template {template_id}, version {version_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing feedback: {str(e)}",
        ) from e


# --- Sprint 3: Approval Endpoint ---


@router.post(
    "/{template_id}/versions/{version_id}/approve",
    response_model=ApprovalResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Approve a Specific Template Version",
    response_description="Confirmation of the template version approval.",
)
async def approve_specific_template_version(
    template_id: uuid.UUID,
    version_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    logger.info(
        f"Attempting to approve template ID: {template_id}, Version ID: {version_id}"
    )

    try:
        approved_version = await approve_template_version(
            db=db, template_id=str(template_id), version_id_to_approve=version_id
        )

        if not approved_version:
            logger.warning(
                f"Approval failed: Template ID {template_id}, Version {version_id} not found."
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template ID {template_id} with version ID {version_id} not found for approval.",
            )

        # Log placeholder for Beefree import
        logger.info(
            f"Template {template_id}, Version {version_id} approved. Placeholder: Beefree import would be initiated here."
        )

        return ApprovalResponseSchema(
            template_id=str(approved_version.template_id),
            approved_version_id=approved_version.version_id,
            # The status and message fields in ApprovalResponseSchema have defaults,
            # but can be overridden if needed based on more complex logic.
            # For now, default values are fine.
        )
    except HTTPException:  # Re-raise HTTPExceptions specifically
        raise
    except Exception as e:
        logger.exception(
            f"Error during approval of template {template_id}, version {version_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while approving version {version_id}.",
        ) from e
