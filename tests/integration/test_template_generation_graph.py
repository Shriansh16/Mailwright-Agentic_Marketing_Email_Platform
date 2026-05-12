import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
import logging
from datetime import datetime

# For MemorySaver
from langgraph.checkpoint.memory import MemorySaver

# For Postgres checkpointer testing
from mailwright.graphs.checkpointer import (
    get_checkpointer_context_manager as get_actual_checkpointer_cm,
)
from mailwright.db.template_store import (
    get_template_version,
    create_template_version,
    approve_template_version,
)

# AsyncSessionLocal will be patched in the test_graph_flow_with_store_v0_node
# from mailwright.db.models import AsyncSessionLocal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from mailwright.config import settings

from mailwright.graphs.template_generation_graph import (
    create_graph_builder,
    LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME,
    LG_STORE_V0_NODE_NAME,  # Import for interrupt_before
    LG_IMAGE_GENERATION_NODE_NAME,
    LG_MJML_VALIDATE_COMPILE_NODE_NAME,  # Ensured this is imported
    LG_FEEDBACK_ENGINE_NODE_NAME,  # Added for Sprint 3 feedback tests
    LG_STORE_V_NEXT_NODE_NAME,  # Added for Sprint 3 feedback tests
    # mjml_service, # Will be patched directly in template_generation_graph module
    # Imported for @patch.object if needed, or can also be patched in graph module
)
from mailwright.graphs.state import GraphState
from mailwright.schemas.template_schemas import UserBriefSchema, TemplateVersionCreate
from mailwright.core_services.brief_analyzer_service import BriefAnalysisResult
import pytest_asyncio

# Import MJMLService if needed for type hinting, but not for patching target here
# from mailwright.core_services.mjml_service import MJMLService
from sqlalchemy.exc import SQLAlchemyError  # Added for DB error simulation

# Setup logger for this test module
logger = logging.getLogger(
    __name__
)  # Or a more specific name like "tests.integration.graph_feedback"
logging.basicConfig(level=logging.INFO)  # Basic config for test run visibility

# Reduce verbosity of other loggers if needed, e.g., uvicorn or httpx
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Prevent LangGraph's default logger from propagating to root,
# to avoid duplicate messages if root logger is also configured at INFO level.
graph_module_logger = logging.getLogger("langgraph.graph.graph")
graph_module_logger.propagate = (
    False  # Important to prevent duplicates if root logger is also configured
)


@pytest_asyncio.fixture
async def db_session(
    async_db_engine,
) -> AsyncSession:  # Using async_db_engine from conftest.py
    """
    Provides a clean database session for integration tests in this module.
    """
    TestAsyncSessionLocal = sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with TestAsyncSessionLocal() as session:
        yield session


@pytest.fixture
def sample_user_brief_input():
    brief = UserBriefSchema(
        subject="Integration Test Subject",
        body_copy="Integration test body copy.",
        image_suggestions=["test_image.jpg"],
        cta_text="Test Now",
        cta_url="http://example.com/test",
    )
    return {"user_brief_data": brief.model_dump(mode="json")}


@pytest.fixture
def graph_components_with_memory_saver():  # Renamed for clarity and new behavior
    # This fixture now ONLY provides the checkpointer.
    # Builder creation will happen inside the test to ensure patches are active.
    checkpointer = MemorySaver()
    yield checkpointer  # Yield only checkpointer


@pytest_asyncio.fixture
async def active_postgres_checkpointer():
    checkpointer_cm = get_actual_checkpointer_cm()
    async with checkpointer_cm as checkpointer_instance:
        await checkpointer_instance.setup()
        yield checkpointer_instance


# --- Test Cases ---


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)  # Patch method on instance in graph module
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node",
    new_callable=AsyncMock,
)  # Patching on the instance in graph module
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)  # Patching on the instance in graph module
async def test_graph_flow_brief_ok(
    mock_mjml_instance_generate_node,  # Innermost: mjml_service.generate_mjml_node in graph module
    mock_mjml_instance_validate_node,  # Next: mjml_service.validate_and_compile_mjml_node in graph module
    mock_image_generate_on_instance,  # Next: image_generator_service.generate_image in graph module
    mock_analyze_brief_func,  # Outermost: analyze_brief_for_clarifications in graph module
    graph_components_with_memory_saver,  # Fixture now yields only checkpointer
    sample_user_brief_input,
):
    """
    Tests the graph flow when the brief analyzer returns BRIEF_OK,
    and subsequent generation/validation steps are mocked to succeed.
    """
    checkpointer = graph_components_with_memory_saver  # Get checkpointer from fixture
    builder = create_graph_builder()  # Create builder here, after patches are active
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Mock Brief Analyzer function: Brief is OK
    mock_analyze_brief_func.return_value = BriefAnalysisResult(status="BRIEF_OK")

    # 2. Mock Image Generation service call: Success
    mock_image_url = "http://example.com/mock_image_for_brief_ok.jpg"
    mock_image_generate_on_instance.return_value = mock_image_url

    # 3. Mock MJML Generation node : Success
    test_mjml = "<mjml><mj-body><mj-text>Brief OK Test MJML</mj-text></mj-body></mjml>"

    async def mock_mjml_generate_side_effect(state: GraphState):
        return {
            "current_mjml": test_mjml,
            "last_operation_status": "success_mjml_generated",
            "error_message": None,
        }

    mock_mjml_instance_generate_node.side_effect = mock_mjml_generate_side_effect

    # 4. Mock MJML Validation/Compilation node: Success
    test_html = "<div>Brief OK Test HTML</div>"

    async def mock_mjml_validate_compile_side_effect(state: GraphState):
        return {
            "current_mjml": state.current_mjml
            if state.current_mjml is not None
            else test_mjml,
            "compiled_html": test_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "SUCCESS_MJML_VALIDATE_COMPILE",
            "error_message": None,
        }

    mock_mjml_instance_validate_node.side_effect = (
        mock_mjml_validate_compile_side_effect
    )

    full_input = {
        **sample_user_brief_input,
        "image_prompts": ["test image prompt for brief_ok flow"],
    }

    final_state_data = await graph.ainvoke(
        full_input,
        config=config,
        interrupt_before=[LG_STORE_V0_NODE_NAME],  # Interrupt before LG_StoreV0
    )

    assert final_state_data is not None, "Graph did not return a final state."
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert final_state is not None, (
        "Could not construct GraphState from ainvoke output."
    )
    assert final_state.user_brief_data == sample_user_brief_input["user_brief_data"]
    assert final_state.clarification_questions is None
    assert final_state.error_message is None, (
        f"Error message was: {final_state.error_message}"
    )

    mock_analyze_brief_func.assert_called_once()
    if full_input["image_prompts"]:
        mock_image_generate_on_instance.assert_called_once_with(
            prompt="test image prompt for brief_ok flow"
        )
    else:
        mock_image_generate_on_instance.assert_not_called()

    mock_mjml_instance_generate_node.assert_called_once()
    mock_mjml_instance_validate_node.assert_called_once()

    assert final_state.last_operation_status == "SUCCESS_MJML_VALIDATE_COMPILE"
    assert final_state.current_mjml == test_mjml
    assert final_state.compiled_html == test_html
    assert final_state.mjml_validation_status == "VALID"
    if full_input["image_prompts"]:
        assert final_state.generated_image_urls == [mock_image_url]


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
async def test_graph_flow_clarification_needed(
    mock_analyze_brief,
    graph_components_with_memory_saver,  # Fixture now yields only checkpointer
    sample_user_brief_input,
):
    checkpointer = graph_components_with_memory_saver
    builder = create_graph_builder()  # Create builder here
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    clarification_qs = ["What is the target audience?", "Any specific tone?"]
    mock_analyze_brief.return_value = BriefAnalysisResult(
        status="CLARIFICATION_NEEDED", clarification_questions=clarification_qs
    )

    final_state_data = await graph.ainvoke(
        sample_user_brief_input,
        config=config,
        interrupt_after=[LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME],
    )

    assert final_state_data is not None
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert final_state is not None
    assert final_state.user_brief_data == sample_user_brief_input["user_brief_data"]
    assert final_state.last_operation_status == "WAITING_FOR_AMENDED_BRIEF"
    assert final_state.clarification_questions == clarification_qs
    assert final_state.error_message is None

    mock_analyze_brief.assert_called_once()
    assert isinstance(mock_analyze_brief.call_args[0][0], UserBriefSchema)
    assert (
        mock_analyze_brief.call_args[0][0].subject
        == UserBriefSchema.model_validate(
            sample_user_brief_input["user_brief_data"]
        ).subject
    )


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
async def test_graph_flow_brief_analyzer_error(
    mock_analyze_brief,
    graph_components_with_memory_saver,  # Fixture now yields only checkpointer
    sample_user_brief_input,
):
    checkpointer = graph_components_with_memory_saver
    builder = create_graph_builder()  # Create builder here
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    error_msg = "LLM unavailable"
    mock_analyze_brief.return_value = BriefAnalysisResult(
        status="ERROR", error_message=error_msg
    )

    final_state_data = await graph.ainvoke(sample_user_brief_input, config=config)

    assert final_state_data is not None
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert final_state is not None
    assert final_state.user_brief_data == sample_user_brief_input["user_brief_data"]
    assert final_state.last_operation_status == "ERROR"
    assert final_state.error_message == error_msg
    assert final_state.clarification_questions is None

    mock_analyze_brief.assert_called_once()
    assert isinstance(mock_analyze_brief.call_args[0][0], UserBriefSchema)
    assert (
        mock_analyze_brief.call_args[0][0].subject
        == UserBriefSchema.model_validate(
            sample_user_brief_input["user_brief_data"]
        ).subject
    )


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
async def test_graph_flow_with_store_v0_node(
    mock_analyze_brief_s0,  # Innermost
    mock_mjml_validate_s0,  # Next
    mock_mjml_generate_s0,  # Next
    mock_image_generate_s0,  # Outermost
    active_postgres_checkpointer,
    sample_user_brief_input,
    event_loop,  # Add pytest-asyncio event_loop fixture
):
    # Parameter order reversed to match decorator stack (bottom-up)
    # mock_image_generate_s0, mock_mjml_generate_s0, mock_mjml_validate_s0, mock_analyze_brief_s0

    checkpointer = active_postgres_checkpointer
    builder = create_graph_builder()
    # Graph compilation will happen inside the patch context if it also uses AsyncSessionLocal internally,
    # but for node execution, the patch below is key.
    # For now, compile graph outside, assuming compilation itself doesn't need the patched session.
    graph = builder.compile(checkpointer=checkpointer)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    mock_analyze_brief_s0.return_value = BriefAnalysisResult(status="BRIEF_OK")

    mock_image_url = "http://example.com/mock_image.jpg"
    mock_image_generate_s0.return_value = mock_image_url

    test_mjml = "<mjml><mj-body><mj-text>Test MJML from mock</mj-text></mj-body></mjml>"

    async def mock_mjml_generate_side_effect(state: GraphState):
        return {
            "current_mjml": test_mjml,
            "last_operation_status": "success",
            "error_message": None,
        }

    mock_mjml_generate_s0.side_effect = mock_mjml_generate_side_effect

    test_html = "<div>Test HTML from mock</div>"

    async def mock_mjml_validate_compile_side_effect(state: GraphState):
        return {
            "current_mjml": state.current_mjml
            if state.current_mjml is not None
            else test_mjml,
            "compiled_html": test_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "SUCCESS_MJML_VALIDATE_COMPILE",
            "error_message": None,
        }

    mock_mjml_validate_s0.side_effect = mock_mjml_validate_compile_side_effect

    full_input = {
        **sample_user_brief_input,
        "image_prompts": ["test image prompt for store v0"],
    }

    # Create a test-specific engine and session factory using the test's event loop
    # Ensure DATABASE_URL is correctly loaded via settings
    if not settings.DATABASE_URL:
        pytest.fail(
            "DATABASE_URL not configured in settings for test_graph_flow_with_store_v0_node"
        )

    # SQLAlchemy 2.x create_async_engine should automatically use the running event loop
    # when called from within an async context (like a pytest-asyncio test).
    test_specific_engine = create_async_engine(settings.DATABASE_URL)
    TestScopedAsyncSessionLocal = sessionmaker(
        bind=test_specific_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # Patch AsyncSessionLocal where it's used by the store_v0_node
    # (likely in mailwright.graphs.template_generation_graph or mailwright.db.template_store if imported there)
    # Assuming store_v0_node in template_generation_graph imports AsyncSessionLocal from mailwright.db.models
    # or has it available in its module scope. The direct import in template_generation_graph is from mailwright.db.models
    with (
        patch(
            "mailwright.graphs.template_generation_graph.AsyncSessionLocal",
            TestScopedAsyncSessionLocal,
        ),
    ):  # Also patch where get_template_version might use it
        # final_state_data = await graph.ainvoke(full_input, config=config) # Old way
        await graph.ainvoke(full_input, config=config)  # Run to completion

        checkpoint_at_end = await graph.aget_state(config)
        final_state_data = checkpoint_at_end.values if checkpoint_at_end else {}

        assert final_state_data is not None, (
            "Graph did not return a final state dictionary from aget_state.values."
        )
        final_state = (
            GraphState(**final_state_data)
            if isinstance(final_state_data, dict)
            else final_state_data
        )

        mock_analyze_brief_s0.assert_called_once()
        mock_image_generate_s0.assert_called_once_with(
            prompt="test image prompt for store v0"
        )
        mock_mjml_generate_s0.assert_called_once()
        mock_mjml_validate_s0.assert_called_once()

        assert final_state.last_operation_status == "SUCCESS_STORED_V0", (
            f"Expected SUCCESS_STORED_V0, got {final_state.last_operation_status}. Error: {final_state.error_message}"
        )
        assert final_state.error_message is None, (
            f"Expected no error, got: {final_state.error_message}"
        )
        assert final_state.stored_version_info is not None
        assert final_state.stored_version_info["template_id"] == thread_id
        assert final_state.stored_version_info["version_id"] == "v0"
        assert final_state.current_version_id_stored == "v0"
        assert final_state.generated_image_urls == [mock_image_url]

        # This subsequent check should also use the test-scoped session
        async with TestScopedAsyncSessionLocal() as db_session_for_check:
            stored_db_version = await get_template_version(
                db=db_session_for_check, template_id=thread_id, version_id="v0"
            )
        assert stored_db_version is not None, (
            "Template version v0 not found in the database."
        )
    assert stored_db_version.template_id == thread_id
    assert stored_db_version.version_id == "v0"
    assert stored_db_version.mjml_source == test_mjml
    assert stored_db_version.compiled_html == test_html
    assert (
        stored_db_version.user_brief_snapshot
        == sample_user_brief_input["user_brief_data"]
    )
    assert stored_db_version.image_assets == {"urls": [mock_image_url]}
    assert stored_db_version.is_approved is False
    print(f"Successfully verified version {thread_id}/v0 in database.")


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
async def test_graph_resumability_after_clarification_postgres(
    mock_analyze_brief,  # Innermost
    mock_mjml_validate_node,  # Next
    mock_mjml_generate_node,  # Next
    mock_image_generate,  # Outermost
    active_postgres_checkpointer,
    sample_user_brief_input,
):
    """
    Tests graph resumability with PostgreSQL checkpointer after a brief clarification.
    1. Initial brief -> Clarification needed.
    2. Amend brief in state.
    3. Resume graph -> Should proceed without re-analyzing, using amended brief.
    """
    checkpointer = active_postgres_checkpointer
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # --- Part 1: Initial invocation, clarification needed ---
    clarification_qs = ["What is the primary goal?"]
    mock_analyze_brief.return_value = BriefAnalysisResult(
        status="CLARIFICATION_NEEDED", clarification_questions=clarification_qs
    )

    # Invoke, expecting interruption
    interrupted_state_data = await graph.ainvoke(
        sample_user_brief_input,
        config=config,
        interrupt_after=[LG_WAIT_FOR_AMENDED_BRIEF_NODE_NAME],
    )
    assert interrupted_state_data is not None
    interrupted_state = GraphState(**interrupted_state_data)
    assert interrupted_state.last_operation_status == "WAITING_FOR_AMENDED_BRIEF"
    assert interrupted_state.clarification_questions == clarification_qs
    assert mock_analyze_brief.call_count == 1  # Called for the first time

    # --- Part 2: Update state with amended brief and resume ---
    amended_brief_content = UserBriefSchema(
        subject="Amended Subject",
        body_copy="Amended body with primary goal stated.",
        cta_text="Go Amended",
    )
    # The following `values_to_update` was unused.
    # `values_to_update_for_resumption` is the one used for aupdate_state.
    # values_to_update = {
    #     "user_brief_data": amended_brief_content.model_dump(mode="json"),
    #     "amended_brief_data": amended_brief_content.model_dump(mode="json"),
    #     "clarification_questions": None,
    #     "error_message": None,
    #     "last_operation_status": "AMENDED_BRIEF_RECEIVED_FOR_RESUME_TEST",
    # }
    # The LG_WaitForAmendedBriefNode itself would typically set user_brief_data from amended_brief_data
    # For this test, we'll assume the node that consumes the amended brief looks for 'amended_brief_data'
    # or that 'user_brief_data' is updated by the LG_WaitForAmendedBriefNode upon receiving the PUT.
    # Let's ensure the brief analyzer node (if it were to run again) would get the *new* brief.
    # The actual brief processing node (e.g. image gen, mjml gen) should use the *effective* brief.
    # For simplicity, let's assume the graph is designed such that the next processing steps
    # will use `amended_brief_data` if present, or `user_brief_data` if `amended_brief_data` is not.
    # Or, more robustly, the LG_WaitForAmendedBriefNode should update `user_brief_data` itself.
    # For this test, we'll set `user_brief_data` to the amended one directly for the resumption.

    values_to_update_for_resumption = {
        "user_brief_data": amended_brief_content.model_dump(
            mode="json"
        ),  # Simulate LG_WaitForAmendedBriefNode updating the main brief
        "image_prompts": [
            "prompt for amended brief"
        ],  # Ensure image prompts are set for the resumed flow
        "clarification_questions": None,
        "error_message": None,
        "last_operation_status": "AMENDED_BRIEF_READY_FOR_PROCESSING",
    }

    await graph.aupdate_state(config, values_to_update_for_resumption)

    # Configure mocks for successful run after resumption
    # Brief analyzer WILL be called again due to the graph structure.
    # It should now return BRIEF_OK for the amended brief.
    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")

    mock_image_url = "http://example.com/amended_mock_image.jpg"
    mock_image_generate.return_value = mock_image_url

    resumed_mjml = (
        "<mjml><mj-body><mj-text>Resumed Test MJML</mj-text></mj-body></mjml>"
    )

    async def mock_mjml_generate_resumed_side_effect(state: GraphState):
        # Ensure it's using the amended brief data for generation
        assert state.user_brief_data["subject"] == "Amended Subject"
        return {
            "current_mjml": resumed_mjml,
            "last_operation_status": "success_mjml_generated_resumed",
            "error_message": None,
        }

    mock_mjml_generate_node.side_effect = mock_mjml_generate_resumed_side_effect

    resumed_html = "<div>Resumed Test HTML</div>"

    async def mock_mjml_validate_resumed_side_effect(state: GraphState):
        return {
            "current_mjml": state.current_mjml if state.current_mjml else resumed_mjml,
            "compiled_html": resumed_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "SUCCESS_MJML_VALIDATE_COMPILE_RESUMED",
            "error_message": None,
        }

    mock_mjml_validate_node.side_effect = mock_mjml_validate_resumed_side_effect

    # Re-invoke the graph (input is None as state is updated)
    # Interrupt before store to check state just before persistence of resumed data
    final_state_data_resumed = await graph.ainvoke(
        None, config=config, interrupt_before=[LG_STORE_V0_NODE_NAME]
    )

    assert final_state_data_resumed is not None
    final_state_resumed = GraphState(**final_state_data_resumed)

    # Assertions for resumed flow:
    # 1. Brief analyzer was called again (total 2 times).
    assert mock_analyze_brief.call_count == 2

    # 2. Subsequent nodes were called
    mock_image_generate.assert_called_once_with(prompt="prompt for amended brief")

    mock_mjml_generate_node.assert_called_once()
    mock_mjml_validate_node.assert_called_once()

    assert (
        final_state_resumed.last_operation_status
        == "SUCCESS_MJML_VALIDATE_COMPILE_RESUMED"
    )
    assert final_state_resumed.user_brief_data["subject"] == "Amended Subject"
    assert final_state_resumed.clarification_questions is None
    assert final_state_resumed.error_message is None
    assert final_state_resumed.current_mjml == resumed_mjml
    assert final_state_resumed.compiled_html == resumed_html
    assert final_state_resumed.mjml_validation_status == "VALID"
    assert final_state_resumed.generated_image_urls == [mock_image_url]

    print("Successfully tested graph resumability after clarification with PostgreSQL.")


@pytest.mark.asyncio
async def test_graph_error_brief_analyzer_missing_data(
    graph_components_with_memory_saver,  # Fixture yields only checkpointer
):
    """Tests graph error when user_brief_data is missing."""
    checkpointer = graph_components_with_memory_saver
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_input = {"user_brief_data": None}  # Explicitly set to None

    final_state_data = await graph.ainvoke(initial_input, config=config)

    assert final_state_data is not None
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert final_state.error_message == "User brief data is missing."
    assert final_state.last_operation_status == "ERROR"

    # Check if graph reached END (no next node)
    current_graph_config_state = await graph.aget_state(config)
    assert not current_graph_config_state.next, "Graph should have ended due to error."


@pytest.mark.asyncio
async def test_graph_error_brief_analyzer_invalid_data(
    graph_components_with_memory_saver,  # Fixture yields only checkpointer
):
    """Tests graph error when user_brief_data is invalid and fails Pydantic validation."""
    checkpointer = graph_components_with_memory_saver
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_input = {
        "user_brief_data": {"unexpected_field": "some_value", "subject": 12345}
    }  # Invalid data

    final_state_data = await graph.ainvoke(initial_input, config=config)

    assert final_state_data is not None
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert "Invalid user brief data format" in final_state.error_message
    assert final_state.last_operation_status == "ERROR"

    # Check if graph reached END
    current_graph_config_state = await graph.aget_state(config)
    assert not current_graph_config_state.next, "Graph should have ended due to error."


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
async def test_graph_error_image_generation_service_exception(
    mock_image_generate,  # Corresponds to image_generator_service.generate_image
    mock_analyze_brief,  # Corresponds to analyze_brief_for_clarifications
    graph_components_with_memory_saver,
    sample_user_brief_input,
):
    """Tests error in LG_ImageGeneration when image_generator_service.generate_image raises an exception."""
    checkpointer = graph_components_with_memory_saver
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Mock Brief Analyzer to return BRIEF_OK to proceed to image generation
    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")

    # Mock Image Generation service to raise an exception
    mock_image_generate.side_effect = Exception("DALL-E unavailable")

    initial_input_with_prompts = {
        **sample_user_brief_input,
        "image_prompts": ["a cat"],
    }

    # So, we'll interrupt before the next logical step (MJML Generation) to check the state.
    final_state_data = await graph.ainvoke(
        initial_input_with_prompts,
        config=config,
        interrupt_after=[
            LG_IMAGE_GENERATION_NODE_NAME
        ],  # Interrupt after image generation node
    )

    assert final_state_data is not None
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert (
        "Exception for prompt 'a cat': DALL-E unavailable" in final_state.error_message
    )
    assert final_state.last_operation_status == "ERROR_IMAGE_GENERATION"
    assert final_state.generated_image_urls == []
    assert final_state.image_urls_map == {"a cat": None}

    # Check that analyze_brief was called
    mock_analyze_brief.assert_called_once()
    # Check that image_generate was called
    mock_image_generate.assert_called_once_with(prompt="a cat")

    # Even with image gen error, graph proceeds. To check if it *would* end, we'd need to see the next step in conditional logic
    # For now, we confirm the error is logged and status is set. The graph continues to MJML gen then Validate then StoreV0 then END.
    # If all images fail and it hits mjml_generation_node and then mjml_validation_node,
    # the should_store_or_end_after_validation will route to StoreV0 if mjml is valid.
    # The error from image gen is just noted in the state.


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
async def test_graph_error_image_generation_all_prompts_fail(
    mock_image_generate,  # Corresponds to image_generator_service.generate_image
    mock_analyze_brief,  # Corresponds to analyze_brief_for_clarifications
    graph_components_with_memory_saver,
    sample_user_brief_input,
):
    """Tests error in LG_ImageGeneration when all image prompts fail to generate URLs."""
    checkpointer = graph_components_with_memory_saver
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")
    mock_image_generate.return_value = None  # Simulate failure for all prompts

    prompts = ["cat", "dog"]
    initial_input_with_prompts = {
        **sample_user_brief_input,
        "image_prompts": prompts,
    }

    final_state_data = await graph.ainvoke(
        initial_input_with_prompts,
        config=config,
        interrupt_after=[
            LG_IMAGE_GENERATION_NODE_NAME
        ],  # Interrupt after image generation node
    )

    assert final_state_data is not None
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert "Failed to retrieve URL for prompt: 'cat'" in final_state.error_message
    assert "Failed to retrieve URL for prompt: 'dog'" in final_state.error_message
    assert final_state.last_operation_status == "ERROR_IMAGE_GENERATION"
    assert final_state.generated_image_urls == []
    assert final_state.image_urls_map == {"cat": None, "dog": None}

    mock_analyze_brief.assert_called_once()
    # Check that image_generate was called for each prompt
    assert mock_image_generate.call_count == len(prompts)
    mock_image_generate.assert_any_call(prompt="cat")
    mock_image_generate.assert_any_call(prompt="dog")


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
@patch(  # Patching the MJML service method directly
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)
async def test_graph_error_mjml_generation_service_exception(
    mock_mjml_generate_node,  # Mock for mjml_service.generate_mjml_node
    mock_image_generate,  # Corresponds to image_generator_service.generate_image
    mock_analyze_brief,  # Corresponds to analyze_brief_for_clarifications
    graph_components_with_memory_saver,
    sample_user_brief_input,
):
    """Tests error in LG_MJMLGeneration when the underlying LLM call within mjml_service.generate_mjml_node raises an exception."""
    checkpointer = graph_components_with_memory_saver
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Mock preceding nodes to succeed
    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")
    mock_image_generate.return_value = "http://example.com/mock_image.jpg"

    # Mock the MJML generation to return an error
    async def mjml_generation_error_side_effect(state: GraphState):
        return {
            "error_message": "MJML Generation Failed: An unexpected error occurred: MJML LLM direct call failed",
            "last_operation_status": "ERROR_MJML_GENERATION",
            "current_mjml": None,
        }

    mock_mjml_generate_node.side_effect = mjml_generation_error_side_effect

    initial_input_with_prompts = {
        **sample_user_brief_input,
        "image_prompts": ["a cat"],  # Ensure image prompts are present
    }

    final_state_data = await graph.ainvoke(
        initial_input_with_prompts,
        config=config
        # No longer interrupting, let the graph route to END
        # interrupt_after=[
        #     LG_MJML_GENERATION_NODE_NAME
        # ],
    )

    assert final_state_data is not None
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert final_state.error_message is not None, f"Expected error message, got None. Status: {final_state.last_operation_status}"
    assert (
        "MJML Generation Failed: An unexpected error occurred: MJML LLM direct call failed"
        in final_state.error_message
    )
    assert final_state.last_operation_status == "ERROR_MJML_GENERATION"

    # Check that the graph has terminated due to the MJML generation error
    # When MJML generation fails, the graph routes to END (no next nodes)
    current_graph_config_state = await graph.aget_state(config)
    assert not current_graph_config_state.next, (
        "Graph should have ended after MJML generation error, but found next nodes: "
        f"{current_graph_config_state.next}"
    )


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node",
    new_callable=AsyncMock,
)
@patch(  # Patching the DB call within store_v0_node
    "mailwright.graphs.template_generation_graph.create_template_version",
    new_callable=AsyncMock,
)
async def test_graph_error_store_v0_database_error(
    mock_create_template_version,  # Corrected mock name for create_template_version
    mock_mjml_validate_node,
    mock_mjml_generate_node,
    mock_image_generate,
    mock_analyze_brief,
    graph_components_with_memory_saver,
    sample_user_brief_input,
):
    """Tests error in LG_StoreV0Node when a database error occurs during save."""
    checkpointer = graph_components_with_memory_saver
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Mock preceding nodes to succeed and provide a complete state for storing
    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")
    mock_image_generate.return_value = "http://example.com/mock_image.jpg"

    valid_mjml = (
        "<mjml><mj-body><mj-text>StoreV0 DB Error Test</mj-text></mj-body></mjml>"
    )

    async def mjml_gen_success(state: GraphState):
        return {
            "current_mjml": valid_mjml,
            "last_operation_status": "success_mjml_gen",
            "error_message": None,
        }

    mock_mjml_generate_node.side_effect = mjml_gen_success

    valid_html = "<div>StoreV0 DB Error Test HTML</div>"

    async def mjml_validate_success(state: GraphState):
        return {
            "compiled_html": valid_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success_mjml_validate",
            "error_message": None,
        }

    mock_mjml_validate_node.side_effect = mjml_validate_success

    # Mock the database call to raise an SQLAlchemyError
    mock_create_template_version.side_effect = SQLAlchemyError(
        "Simulated DB connection error"
    )

    initial_input_with_prompts = {
        **sample_user_brief_input,
        "image_prompts": ["db error test"],
    }

    final_state_data = await graph.ainvoke(initial_input_with_prompts, config=config)

    assert final_state_data is not None
    final_state = (
        GraphState(**final_state_data)
        if isinstance(final_state_data, dict)
        else final_state_data
    )

    assert (
        "Database error storing version v0: Simulated DB connection error"
        in final_state.error_message
    )
    assert final_state.last_operation_status == "ERROR_STORING_VERSION"
    assert final_state.stored_version_info is None

    # Check that the graph has ended
    current_graph_config_state = await graph.aget_state(config)
    assert not current_graph_config_state.next, (
        "Graph should have ended after StoreV0 DB error."
    )


# --- Sprint 3: Integration Tests for Feedback Loop ---


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.feedback_service.revise_mjml_based_on_feedback",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.create_template_version",
    new_callable=AsyncMock,
)  # To intercept DB calls for V0 and V_Next
async def test_feedback_loop_v0_to_v_revised(
    mock_db_create_template_version: AsyncMock,  # For create_template_version
    mock_feedback_revise_mjml: AsyncMock,  # For feedback_service.revise_mjml_based_on_feedback
    mock_mjml_validate_node: AsyncMock,  # Changed to AsyncMock
    mock_mjml_generate_node: AsyncMock,  # Changed to AsyncMock
    mock_image_generate: AsyncMock,  # For image_generator_service.generate_image
    mock_analyze_brief: AsyncMock,  # For analyze_brief_for_clarifications
    active_postgres_checkpointer,
    sample_user_brief_input,
    db_session: AsyncSession,  # For direct DB verification
):
    """Test V0 creation -> feedback -> V_revised (V_Next) creation."""
    # Ensure test logger is verbose for this specific test run if needed
    # test_logger = logging.getLogger("tests.integration.test_template_generation_graph")
    # test_logger.setLevel(logging.DEBUG) # Or use pytest --log-cli-level=DEBUG

    checkpointer = active_postgres_checkpointer
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    template_id_str = str(uuid.uuid4())
    config = {"configurable": {"thread_id": template_id_str}}

    # --- Part 1: Create V0 ---
    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")
    mock_image_generate.return_value = "http://example.com/v0_image.jpg"
    v0_mjml = "<mjml><mj-body><mj-text>Initial V0</mj-text></mj-body></mjml>"
    v0_html = "<p>Initial V0 HTML</p>"

    async def mjml_generate_v0_side_effect(
        state: GraphState,
    ):  # Side effect should be async
        # logger.debug("TEST MOCK: mjml_generate_v0_side_effect called")
        return {
            "current_mjml": v0_mjml,
            "last_operation_status": "success",
            "error_message": None,
        }

    mock_mjml_generate_node.side_effect = mjml_generate_v0_side_effect

    async def mjml_validate_v0_side_effect(
        state: GraphState,
    ):  # Side effect should be async
        # logger.debug("TEST MOCK: mjml_validate_v0_side_effect called")
        return {
            "current_mjml": state.current_mjml,
            "compiled_html": v0_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success",
            "error_message": None,
        }

    mock_mjml_validate_node.side_effect = mjml_validate_v0_side_effect

    v0_db_mock = MagicMock(spec=TemplateVersionCreate)
    v0_db_mock.template_id = template_id_str
    v0_db_mock.version_id = "v0"  # Expected by store_v0_node
    v0_db_mock.mjml_source = v0_mjml
    v0_db_mock.compiled_html = v0_html
    v0_db_mock.is_approved = False
    v0_db_mock.created_at = datetime.utcnow()
    v0_db_mock.user_brief_snapshot = sample_user_brief_input["user_brief_data"]
    v0_db_mock.image_assets = {"urls": ["http://example.com/v0_image.jpg"]}
    v0_db_mock.change_trigger = {"event": "initial_generation"}

    v_revised_mjml = "<mjml><mj-body><mj-text>V_Revised MJML</mj-text></mj-body></mjml>"
    v_revised_html = "<p>V_Revised HTML</p>"

    v_next_db_mock = MagicMock(spec=TemplateVersionCreate)
    v_next_db_mock.template_id = template_id_str
    # v_next_db_mock.version_id will be set by the custom side_effect below
    v_next_db_mock.mjml_source = v_revised_mjml
    v_next_db_mock.compiled_html = v_revised_html
    v_next_db_mock.is_approved = False
    v_next_db_mock.created_at = datetime.utcnow()
    v_next_db_mock.user_brief_snapshot = sample_user_brief_input["user_brief_data"]
    v_next_db_mock.image_assets = {"urls": ["http://example.com/v0_image.jpg"]}
    # change_trigger for v_next_db_mock will be asserted based on what create_template_version is called with.

    # Custom side_effect for mock_db_create_template_version to log calls and set dynamic version_id
    call_log_for_create_version = []

    async def verbose_create_template_version_side_effect(
        db: AsyncSession, version_data: TemplateVersionCreate
    ):
        call_log_for_create_version.append(version_data.version_id)
        logger.info(
            f"TEST MOCK (create_template_version call #{len(call_log_for_create_version)}): Called with version_id='{version_data.version_id}', mjml_snippet='{version_data.mjml_source[:30]}...'"
        )
        if len(call_log_for_create_version) == 1:  # First call, for V0
            assert version_data.version_id == "v0", (
                "First call to create_template_version should be for v0"
            )
            return v0_db_mock
        elif len(call_log_for_create_version) == 2:  # Second call, for V_Next
            # Ensure v_next_db_mock has the dynamically generated version_id it's being stored with
            v_next_db_mock.version_id = version_data.version_id
            logger.info(
                f"TEST MOCK (create_template_version call #{len(call_log_for_create_version)}): Returning v_next_db_mock configured with version_id='{v_next_db_mock.version_id}'"
            )
            return v_next_db_mock
        else:
            logger.error(
                f"TEST MOCK (create_template_version): UNEXPECTED CALL #{len(call_log_for_create_version)} with version_id='{version_data.version_id}'"
            )
            raise AssertionError(
                f"create_template_version called {len(call_log_for_create_version)} times, expected at most 2."
            )

    mock_db_create_template_version.side_effect = (
        verbose_create_template_version_side_effect
    )

    initial_graph_input = {**sample_user_brief_input, "image_prompts": ["v0 prompt"]}
    logger.info("TEST: Invoking graph for V0 creation...")
    # state_after_v0_stored_dict = await graph.ainvoke(initial_graph_input, config=config, interrupt_after=[LG_STORE_V0_NODE_NAME]) # Old direct use
    await graph.ainvoke(
        initial_graph_input, config=config, interrupt_after=[LG_STORE_V0_NODE_NAME]
    )
    checkpoint_after_v0 = await graph.aget_state(config)
    state_after_v0_stored_values = (
        checkpoint_after_v0.values if checkpoint_after_v0 else {}
    )
    logger.info(
        f"TEST: After V0 ainvoke. Call count for create_template_version: {mock_db_create_template_version.call_count}. Log: {call_log_for_create_version}"
    )

    assert (
        state_after_v0_stored_values.get("last_operation_status") == "SUCCESS_STORED_V0"
    )
    assert state_after_v0_stored_values.get("current_version_id_stored") == "v0"
    assert mock_db_create_template_version.call_count == 1
    v0_call_args_kwargs = mock_db_create_template_version.call_args.kwargs
    assert "version_data" in v0_call_args_kwargs
    v0_version_data_arg = v0_call_args_kwargs["version_data"]
    assert v0_version_data_arg.version_id == "v0"

    # --- Part 2: Simulate Feedback Submission and Process Revision ---
    feedback_text = "Please change V0 to V_Revised"
    mock_feedback_revise_mjml.return_value = v_revised_mjml

    mock_mjml_validate_node.reset_mock()

    async def mjml_validate_revised_side_effect(state: GraphState):
        # logger.debug("TEST MOCK: mjml_validate_revised_side_effect called")
        assert state.revised_mjml_candidate == v_revised_mjml
        return {
            "current_mjml": v_revised_mjml,
            "compiled_html": v_revised_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success",
            "error_message": None,
        }

    mock_mjml_validate_node.side_effect = mjml_validate_revised_side_effect

    feedback_state_update = {
        "user_feedback_content": feedback_text,
        "version_id_for_feedback": "v0",
        "current_mjml": v0_mjml,
        "last_operation_status": "FEEDBACK_RECEIVED",
    }
    logger.info(
        f"TEST: Updating state with feedback. Call count for create_template_version before update: {mock_db_create_template_version.call_count}. Log: {call_log_for_create_version}"
    )
    await graph.aupdate_state(config, feedback_state_update)
    logger.info(
        f"TEST: After aupdate_state. Call count for create_template_version: {mock_db_create_template_version.call_count}. Log: {call_log_for_create_version}"
    )

    logger.info("TEST: Invoking graph for feedback engine processing...")
    await graph.ainvoke(
        feedback_state_update,
        config=config,
        interrupt_after=[LG_FEEDBACK_ENGINE_NODE_NAME],
    )
    logger.info(
        f"TEST: After feedback engine ainvoke. Call count for create_template_version: {mock_db_create_template_version.call_count}. Log: {call_log_for_create_version}"
    )

    state_after_feedback_engine = await graph.aget_state(config)
    feedback_engine_state_values = (
        state_after_feedback_engine.values if state_after_feedback_engine else {}
    )

    assert (
        feedback_engine_state_values.get("last_operation_status")
        == "SUCCESS_REVISION_GENERATED"
    ), (
        f"Expected status SUCCESS_REVISION_GENERATED, got {feedback_engine_state_values.get('last_operation_status')}"
    )
    assert feedback_engine_state_values.get("revised_mjml_candidate") == v_revised_mjml
    mock_feedback_revise_mjml.assert_called_once_with(
        current_mjml=v0_mjml, feedback_text=feedback_text
    )

    logger.info("TEST: Invoking graph for V_Next storage...")
    await graph.ainvoke(
        None, config=config, interrupt_after=[LG_STORE_V_NEXT_NODE_NAME]
    )
    logger.info(
        f"TEST: After final ainvoke for V_Next. Call count for create_template_version: {mock_db_create_template_version.call_count}. Log: {call_log_for_create_version}"
    )

    state_after_v_next_stored = await graph.aget_state(config)
    final_state_values = (
        state_after_v_next_stored.values if state_after_v_next_stored else {}
    )

    assert (
        final_state_values.get("last_operation_status")
        == "SUCCESS_STORED_REVISED_VERSION"
    )
    newly_stored_version_id = final_state_values.get("current_version_id_stored")
    assert newly_stored_version_id is not None
    assert newly_stored_version_id != "v0"
    assert "v_rev_" in newly_stored_version_id

    assert mock_db_create_template_version.call_count == 2

    last_call_args = mock_db_create_template_version.call_args
    assert last_call_args is not None
    v_next_call_args_kwargs = last_call_args.kwargs

    assert "version_data" in v_next_call_args_kwargs
    v_next_version_data_arg = v_next_call_args_kwargs["version_data"]
    assert v_next_version_data_arg.template_id == template_id_str
    assert v_next_version_data_arg.version_id == newly_stored_version_id
    assert v_next_version_data_arg.mjml_source == v_revised_mjml
    assert v_next_version_data_arg.change_trigger["event"] == "feedback_revision"
    assert v_next_version_data_arg.change_trigger["source_version_id"] == "v0"
    assert (
        feedback_text[:100]
        in v_next_version_data_arg.change_trigger["feedback_text_snippet"]
    )
    assert v_next_version_data_arg.is_approved is False

    logger.info(
        f"Test test_feedback_loop_v0_to_v_revised completed. Stored revised version: {newly_stored_version_id}"
    )


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.feedback_service.revise_mjml_based_on_feedback",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.create_template_version",
    new_callable=AsyncMock,
)
async def test_feedback_loop_two_revisions(
    mock_db_create_template_version: AsyncMock,
    mock_feedback_revise_mjml: AsyncMock,
    mock_mjml_validate_node: AsyncMock,
    mock_mjml_generate_node: AsyncMock,
    mock_image_generate: AsyncMock,
    mock_analyze_brief: AsyncMock,
    active_postgres_checkpointer,
    sample_user_brief_input,
    db_session: AsyncSession,  # For potential direct DB verification (though mostly mock based here)
):
    """Test V0 -> Feedback1 -> V_Rev1 -> Feedback2 -> V_Rev2."""
    checkpointer = active_postgres_checkpointer
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    template_id_str = str(uuid.uuid4())
    config = {"configurable": {"thread_id": template_id_str}}

    # --- Mocked Data ---
    v0_mjml = "<mjml>V0</mjml>"
    v0_html = "<p>V0 HTML</p>"
    v0_image_url = "http://example.com/v0_image.jpg"

    v_rev1_mjml = "<mjml>V_Rev1</mjml>"
    v_rev1_html = "<p>V_Rev1 HTML</p>"

    v_rev2_mjml = "<mjml>V_Rev2</mjml>"
    v_rev2_html = "<p>V_Rev2 HTML</p>"

    # --- DB Mocks --- (To be returned by the side_effect)
    v0_db_mock = MagicMock(spec=TemplateVersionCreate)
    v0_db_mock.template_id = template_id_str
    v0_db_mock.version_id = "v0"
    v0_db_mock.created_at = datetime.utcnow()

    v_rev1_db_mock = MagicMock(spec=TemplateVersionCreate)
    v_rev1_db_mock.template_id = template_id_str
    v_rev1_db_mock.created_at = datetime.utcnow()
    # version_id for v_rev1_db_mock will be set by side_effect based on actual call

    v_rev2_db_mock = MagicMock(spec=TemplateVersionCreate)
    v_rev2_db_mock.template_id = template_id_str
    v_rev2_db_mock.created_at = datetime.utcnow()
    # version_id for v_rev2_db_mock will be set by side_effect

    call_log_for_create_version = []

    async def verbose_create_template_version_side_effect(
        db: AsyncSession, version_data: TemplateVersionCreate
    ):
        call_log_for_create_version.append(version_data.version_id)
        logger.info(
            f"TEST MOCK (create_template_version call #{len(call_log_for_create_version)}): Called for version_id='{version_data.version_id}'"
        )
        if len(call_log_for_create_version) == 1:  # V0
            assert version_data.version_id == "v0"
            v0_db_mock.mjml_source = (
                version_data.mjml_source
            )  # Ensure mock has the data it was called with
            v0_db_mock.compiled_html = version_data.compiled_html
            return v0_db_mock
        elif len(call_log_for_create_version) == 2:  # V_Rev1
            v_rev1_db_mock.version_id = version_data.version_id
            v_rev1_db_mock.mjml_source = version_data.mjml_source
            v_rev1_db_mock.compiled_html = version_data.compiled_html
            return v_rev1_db_mock
        elif len(call_log_for_create_version) == 3:  # V_Rev2
            v_rev2_db_mock.version_id = version_data.version_id
            v_rev2_db_mock.mjml_source = version_data.mjml_source
            v_rev2_db_mock.compiled_html = version_data.compiled_html
            return v_rev2_db_mock
        else:
            raise AssertionError(
                f"Unexpected call to create_template_version: #{len(call_log_for_create_version)}"
            )

    mock_db_create_template_version.side_effect = (
        verbose_create_template_version_side_effect
    )

    # --- Part 1: Create V0 ---
    logger.info("TEST: Part 1 - Creating V0")
    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")
    mock_image_generate.return_value = v0_image_url

    async def mjml_gen_v0(s: GraphState):
        return {"current_mjml": v0_mjml, "last_operation_status": "success"}

    mock_mjml_generate_node.side_effect = mjml_gen_v0

    async def mjml_val_v0(s: GraphState):
        return {
            "current_mjml": s.current_mjml,
            "compiled_html": v0_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success",
        }

    mock_mjml_validate_node.side_effect = mjml_val_v0

    initial_graph_input = {**sample_user_brief_input, "image_prompts": ["v0 prompt"]}
    state_after_v0 = await graph.ainvoke(
        initial_graph_input, config=config, interrupt_after=[LG_STORE_V0_NODE_NAME]
    )
    assert state_after_v0["last_operation_status"] == "SUCCESS_STORED_V0"
    assert state_after_v0["current_version_id_stored"] == "v0"
    assert mock_db_create_template_version.call_count == 1

    # --- Part 2: First Revision (V0 -> V_Rev1) ---
    logger.info("TEST: Part 2 - First Revision (V0 -> V_Rev1)")
    feedback1_text = "Feedback for V_Rev1"
    mock_feedback_revise_mjml.return_value = (
        v_rev1_mjml  # Config for first feedback call
    )

    mock_mjml_validate_node.reset_mock()  # Reset for next validation call

    async def mjml_val_v_rev1(s: GraphState):
        return {
            "current_mjml": v_rev1_mjml,
            "compiled_html": v_rev1_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success",
        }

    mock_mjml_validate_node.side_effect = mjml_val_v_rev1

    feedback1_state_update = {
        "user_feedback_content": feedback1_text,
        "version_id_for_feedback": "v0",
        "current_mjml": v0_mjml,
        "last_operation_status": "FEEDBACK_RECEIVED",
    }
    await graph.aupdate_state(config, feedback1_state_update)
    await graph.ainvoke(
        feedback1_state_update,
        config=config,
        interrupt_after=[LG_FEEDBACK_ENGINE_NODE_NAME],
    )  # Run feedback engine
    state_after_fe1 = await graph.aget_state(config)
    assert (
        state_after_fe1.values["last_operation_status"] == "SUCCESS_REVISION_GENERATED"
    )

    await graph.ainvoke(
        None, config=config, interrupt_after=[LG_STORE_V_NEXT_NODE_NAME]
    )  # Run validation and store
    state_after_v_rev1 = await graph.aget_state(config)
    assert (
        state_after_v_rev1.values["last_operation_status"]
        == "SUCCESS_STORED_REVISED_VERSION"
    )
    v_rev1_id = state_after_v_rev1.values["current_version_id_stored"]
    assert v_rev1_id != "v0" and "v_rev_" in v_rev1_id
    assert mock_db_create_template_version.call_count == 2

    # --- Part 3: Second Revision (V_Rev1 -> V_Rev2) ---
    logger.info("TEST: Part 3 - Second Revision (V_Rev1 -> V_Rev2)")
    feedback2_text = "Feedback for V_Rev2"
    mock_feedback_revise_mjml.reset_mock()
    mock_feedback_revise_mjml.return_value = (
        v_rev2_mjml  # Config for second feedback call
    )

    mock_mjml_validate_node.reset_mock()

    async def mjml_val_v_rev2(s: GraphState):
        return {
            "current_mjml": v_rev2_mjml,
            "compiled_html": v_rev2_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success",
        }

    mock_mjml_validate_node.side_effect = mjml_val_v_rev2

    feedback2_state_update = {
        "user_feedback_content": feedback2_text,
        "version_id_for_feedback": v_rev1_id,
        "current_mjml": v_rev1_mjml,
        "last_operation_status": "FEEDBACK_RECEIVED",
    }
    await graph.aupdate_state(config, feedback2_state_update)
    await graph.ainvoke(
        feedback2_state_update,
        config=config,
        interrupt_after=[LG_FEEDBACK_ENGINE_NODE_NAME],
    )  # Run feedback engine
    state_after_fe2 = await graph.aget_state(config)
    assert (
        state_after_fe2.values["last_operation_status"] == "SUCCESS_REVISION_GENERATED"
    )

    await graph.ainvoke(
        None, config=config, interrupt_after=[LG_STORE_V_NEXT_NODE_NAME]
    )  # Run validation and store
    state_after_v_rev2 = await graph.aget_state(config)
    assert (
        state_after_v_rev2.values["last_operation_status"]
        == "SUCCESS_STORED_REVISED_VERSION"
    )
    v_rev2_id = state_after_v_rev2.values["current_version_id_stored"]
    assert v_rev2_id != v_rev1_id and "v_rev_" in v_rev2_id
    assert mock_db_create_template_version.call_count == 3

    logger.info("Test test_feedback_loop_two_revisions completed successfully.")


@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.feedback_service.revise_mjml_based_on_feedback",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.create_template_version",
    new_callable=AsyncMock,
)
async def test_feedback_loop_revision_fails_validation(
    mock_db_create_template_version: AsyncMock,
    mock_feedback_revise_mjml: AsyncMock,
    mock_mjml_validate_node: AsyncMock,
    mock_mjml_generate_node: AsyncMock,
    mock_image_generate: AsyncMock,
    mock_analyze_brief: AsyncMock,
    active_postgres_checkpointer,
    sample_user_brief_input,
):
    """Tests feedback loop where revised MJML fails validation; no new version should be stored."""
    checkpointer = active_postgres_checkpointer
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    template_id_str = str(uuid.uuid4())
    config = {"configurable": {"thread_id": template_id_str}}

    # --- Part 1: Create V0 (Simplified) ---
    logger.info("TEST: Part 1 - Creating V0 for feedback failure test")
    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")
    mock_image_generate.return_value = "http://example.com/v0_image.jpg"
    v0_mjml = "<mjml>V0 Valid</mjml>"
    v0_html = "<p>V0 Valid HTML</p>"

    async def mjml_gen_v0(s: GraphState):
        return {"current_mjml": v0_mjml, "last_operation_status": "success"}

    mock_mjml_generate_node.side_effect = mjml_gen_v0

    async def mjml_val_v0(s: GraphState):
        return {
            "current_mjml": s.current_mjml,
            "compiled_html": v0_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success",
        }

    mock_mjml_validate_node.side_effect = mjml_val_v0

    v0_db_mock = MagicMock(spec=TemplateVersionCreate)
    v0_db_mock.template_id = template_id_str  # Ensure this is set
    v0_db_mock.version_id = "v0"
    v0_db_mock.mjml_source = v0_mjml  # Though store node uses state.current_mjml
    v0_db_mock.compiled_html = v0_html  # Though store node uses state.compiled_html
    v0_db_mock.created_at = datetime.utcnow()  # Ensure this is set
    v0_db_mock.is_approved = False  # Ensure this is set
    # Add other fields if LG_StoreV0Node accesses them from stored_version beyond id and created_at for stored_version_info
    v0_db_mock.user_brief_snapshot = sample_user_brief_input["user_brief_data"]
    v0_db_mock.image_assets = {"urls": ["http://example.com/v0_image.jpg"]}
    v0_db_mock.change_trigger = {"event": "initial_generation"}

    mock_db_create_template_version.return_value = v0_db_mock

    initial_graph_input = {**sample_user_brief_input, "image_prompts": ["v0 prompt"]}
    await graph.ainvoke(
        initial_graph_input, config=config, interrupt_after=[LG_STORE_V0_NODE_NAME]
    )
    checkpoint_after_v0_stored = await graph.aget_state(config)
    logger.info(
        f"TEST DEBUG (V0 Creation): checkpoint_after_v0_stored object: {checkpoint_after_v0_stored} (type: {type(checkpoint_after_v0_stored)})"
    )  # ADDED
    state_after_v0_stored_values = (
        checkpoint_after_v0_stored.values
        if checkpoint_after_v0_stored and hasattr(checkpoint_after_v0_stored, "values")
        else {}
    )
    logger.info(
        f"TEST DEBUG (V0 Creation): state_after_v0_stored_values: {state_after_v0_stored_values}"
    )

    mock_db_create_template_version.assert_called_once()  # V0 stored
    # Use .get() to avoid KeyError and assert the value if present, or handle absence
    v0_current_version_id_stored = state_after_v0_stored_values.get(
        "current_version_id_stored"
    )
    assert v0_current_version_id_stored == "v0", (
        f"Expected current_version_id_stored to be 'v0', got '{v0_current_version_id_stored}'. Full state: {state_after_v0_stored_values}"
    )

    # --- Part 2: Simulate Feedback leading to invalid MJML ---
    logger.info("TEST: Part 2 - Feedback leading to invalid revision")
    feedback_text = "Make this MJML invalid"
    invalid_revised_mjml = "<mjml><mj-text>This is not valid MJML structure</mj-text></mjml>"  # Example invalid

    mock_feedback_revise_mjml.return_value = (
        invalid_revised_mjml  # Use invalid_revised_mjml
    )

    mock_mjml_validate_node.reset_mock()
    validation_error_msg = "MJML Validation Error: Structure is broken."

    async def mjml_val_invalid_revised(s: GraphState):
        assert (
            s.revised_mjml_candidate == invalid_revised_mjml
        )  # Assert against invalid_revised_mjml
        return {
            "current_mjml": invalid_revised_mjml,  # The invalid MJML is passed through
            "compiled_html": None,
            "mjml_validation_status": "INVALID",
            "last_operation_status": "failure_mjml_validation_compilation",  # Specific status for failure
            "error_message": validation_error_msg,
            "revised_mjml_candidate": None,  # Explicitly clear as the real node would
        }

    mock_mjml_validate_node.side_effect = mjml_val_invalid_revised

    feedback_state_update = {
        "user_feedback_content": feedback_text,
        "version_id_for_feedback": "v0",
        "current_mjml": v0_mjml,
        "last_operation_status": "FEEDBACK_RECEIVED",
        "current_version_id_stored": v0_current_version_id_stored,  # Carry forward from V0 creation
    }
    await graph.aupdate_state(
        config, feedback_state_update
    )  # Update state in checkpointer first

    # Invoke for feedback, interrupt after validation node
    # Pass the feedback_state_update as input to ensure all necessary fields are present for this run
    await graph.ainvoke(
        feedback_state_update,
        config=config,
        interrupt_after=[LG_MJML_VALIDATE_COMPILE_NODE_NAME],
    )

    final_state_checkpoint = await graph.aget_state(config)
    final_state_values = final_state_checkpoint.values
    logger.info(
        f"TEST DEBUG: final_state_values after validation failure interrupt: {final_state_values}"
    )  # ADDED FOR DEBUGGING

    assert (
        final_state_values["last_operation_status"]
        == "failure_mjml_validation_compilation"
    )
    assert final_state_values["mjml_validation_status"] == "INVALID"
    assert final_state_values["error_message"] == validation_error_msg
    assert (
        final_state_values["revised_mjml_candidate"] is None
    )  # Should be cleared by validation node
    assert (
        final_state_values["current_mjml"] == invalid_revised_mjml
    )  # current_mjml was updated by validation node before it failed
    assert (
        final_state_values["current_version_id_stored"] == "v0"
    )  # No new version stored

    # Ensure create_template_version was NOT called a second time (StoreVNext was skipped)
    assert mock_db_create_template_version.call_count == 1  # Still 1 from V0 creation

    # Verify graph ended or is at an error state (no further progression to StoreVNext)
    # The should_route_after_validation routes to END if validation fails.
    assert not final_state_checkpoint.next, (
        "Graph should have ended after validation failure of revised MJML."
    )
    logger.info(
        "Test test_feedback_loop_revision_fails_validation completed successfully."
    )


# --- Sprint 3: Integration Test for Feedback on Approved Version (Sub-task 6.3) ---
@pytest.mark.asyncio
@patch(
    "mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.feedback_service.revise_mjml_based_on_feedback",
    new_callable=AsyncMock,
)
@patch(
    "mailwright.graphs.template_generation_graph.create_template_version",
    new_callable=AsyncMock,
)
async def test_feedback_on_approved_version(
    mock_db_create_template_version: AsyncMock,
    mock_feedback_revise_mjml: AsyncMock,
    mock_mjml_validate_node: AsyncMock,
    mock_mjml_generate_node: AsyncMock,
    mock_image_generate: AsyncMock,
    mock_analyze_brief: AsyncMock,
    active_postgres_checkpointer,
    sample_user_brief_input,
    db_session: AsyncSession,  # For DB operations
):
    """Tests submitting feedback on an approved V0, ensuring V0 stays approved and a new unapproved version is created."""
    checkpointer = active_postgres_checkpointer
    builder = create_graph_builder()
    graph = builder.compile(checkpointer=checkpointer)
    template_id_str = str(uuid.uuid4())
    config = {"configurable": {"thread_id": template_id_str}}

    # --- Mocked Data ---
    v0_mjml = "<mjml>Approved V0</mjml>"
    v0_html = "<p>Approved V0 HTML</p>"
    v0_image_url = "http://example.com/approved_v0_image.jpg"
    v_rev_approved_mjml = "<mjml>Revised from Approved V0</mjml>"
    v_rev_approved_html = "<p>Revised from Approved V0 HTML</p>"

    # --- DB Mocks & Side Effect for create_template_version ---
    v0_db_mock = MagicMock(spec=TemplateVersionCreate)
    v0_db_mock.template_id = template_id_str
    v0_db_mock.version_id = "v0"
    v0_db_mock.created_at = datetime.utcnow()
    v0_db_mock.is_approved = (
        True  # Will be set to true after creation by approve_template_version
    )

    v_rev_approved_db_mock = MagicMock(spec=TemplateVersionCreate)
    v_rev_approved_db_mock.template_id = template_id_str
    v_rev_approved_db_mock.created_at = datetime.utcnow()
    v_rev_approved_db_mock.is_approved = (
        True  # This mock will represent an approved version
    )

    # We need to use the real create_template_version for V0 to allow approve_template_version to work on it.
    # Then, we mock create_template_version only for the V_Next storage.
    # This is tricky. Alternative: mock get_template_version within approve_template_version if we fully mock create_template_version.

    # Simpler: We will mock create_template_version for both calls, but then use db_session to directly verify approval status.
    # The approve_template_version function will be called on real DB session.

    call_log_for_create_version = []

    async def verbose_create_template_version_side_effect(
        db: AsyncSession, version_data: TemplateVersionCreate
    ):
        call_log_for_create_version.append(version_data.version_id)
        logger.info(
            f"TEST MOCK (create_template_version call #{len(call_log_for_create_version)}): Called for version_id='{version_data.version_id}'"
        )
        if len(call_log_for_create_version) == 1:  # V0
            assert version_data.version_id == "v0"
            v0_db_mock.mjml_source = (
                version_data.mjml_source
            )  # Ensure mock has the data it was called with
            v0_db_mock.compiled_html = version_data.compiled_html
            return v0_db_mock
        elif len(call_log_for_create_version) == 2:  # V_Rev_Approved
            v_rev_approved_db_mock.version_id = version_data.version_id
            v_rev_approved_db_mock.mjml_source = version_data.mjml_source
            v_rev_approved_db_mock.compiled_html = version_data.compiled_html
            return v_rev_approved_db_mock
        raise AssertionError(
            f"Unexpected call to create_template_version: #{len(call_log_for_create_version)}"
        )

    mock_db_create_template_version.side_effect = (
        verbose_create_template_version_side_effect
    )

    # --- Part 1: Create V0 ---
    logger.info("TEST: Part 1 - Creating V0 (feedback on approved test)")
    mock_analyze_brief.return_value = BriefAnalysisResult(status="BRIEF_OK")
    mock_image_generate.return_value = v0_image_url

    async def mjml_gen_v0(s: GraphState):
        return {"current_mjml": v0_mjml, "last_operation_status": "success"}

    mock_mjml_generate_node.side_effect = mjml_gen_v0

    async def mjml_val_v0(s: GraphState):
        return {
            "current_mjml": s.current_mjml,
            "compiled_html": v0_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success",
        }

    mock_mjml_validate_node.side_effect = mjml_val_v0

    initial_graph_input = {**sample_user_brief_input, "image_prompts": ["v0 prompt"]}
    await graph.ainvoke(
        initial_graph_input, config=config, interrupt_after=[LG_STORE_V0_NODE_NAME]
    )
    assert mock_db_create_template_version.call_count == 1

    # --- Part 1b: Approve V0 in DB using actual db_session and approve_template_version ---
    # To do this, we need V0 to *actually* be in the database.
    # So, we must let the first call to create_template_version go through to the real DB.
    mock_db_create_template_version.side_effect = (
        None  # Disable mock for real V0 creation
    )
    mock_db_create_template_version.return_value = (
        None  # Not used if side_effect is None
    )

    # Re-run V0 creation with real DB storage for V0
    logger.info("TEST: Re-running V0 creation for real DB storage")
    real_v0_data = TemplateVersionCreate(
        template_id=template_id_str,
        version_id="v0",
        mjml_source=v0_mjml,
        compiled_html=v0_html,
        user_brief_snapshot=sample_user_brief_input["user_brief_data"],
        image_assets={"urls": [v0_image_url]},
        change_trigger={"event": "initial_generation"},
        is_approved=False,
    )
    # We need to use the real create_template_version from db_store for this one call
    # The @patch still patches it at the graph module level. This is tricky.
    # Better: Create V0 directly, then approve, then mock for the feedback part.

    # Let's simplify: create and approve V0 directly using db_session, then proceed to feedback part with mocks.
    await create_template_version(db_session, real_v0_data)  # Direct call
    approved_v0 = await approve_template_version(
        db_session, template_id_str, "v0"
    )  # Direct call
    assert approved_v0 is not None and approved_v0.is_approved is True
    logger.info(
        f"TEST: V0 created and approved directly in DB. Version: {approved_v0.version_id}, Approved: {approved_v0.is_approved}"
    )

    # Now, re-enable mock for create_template_version for the V_Next part of the feedback
    mock_db_create_template_version.side_effect = (
        verbose_create_template_version_side_effect  # Re-enable general mock
    )
    call_log_for_create_version.clear()  # Clear log from any previous (now bypassed) mock calls

    # The side_effect needs to expect the *first* call it now sees to be for V_Rev_Approved
    async def single_call_side_effect_for_v_rev(
        db: AsyncSession, version_data: TemplateVersionCreate
    ):
        call_log_for_create_version.append(version_data.version_id)
        logger.info(
            f"TEST MOCK (single_call_side_effect_for_v_rev): Called for version_id='{version_data.version_id}'"
        )
        v_rev_approved_db_mock.version_id = version_data.version_id
        return v_rev_approved_db_mock

    mock_db_create_template_version.side_effect = single_call_side_effect_for_v_rev
    mock_db_create_template_version.reset_mock()  # Reset call count for this specific mocking phase

    # --- Part 2: Simulate Feedback on Approved V0 ---
    logger.info("TEST: Part 2 - Feedback on approved V0")
    feedback_text = "Feedback on approved V0"
    mock_feedback_revise_mjml.return_value = v_rev_approved_mjml

    mock_mjml_validate_node.reset_mock()

    async def mjml_val_v_rev_approved(s: GraphState):
        return {
            "current_mjml": v_rev_approved_mjml,
            "compiled_html": v_rev_approved_html,
            "mjml_validation_status": "VALID",
            "last_operation_status": "success",
        }

    mock_mjml_validate_node.side_effect = mjml_val_v_rev_approved

    feedback_state_update = {
        "user_feedback_content": feedback_text,
        "version_id_for_feedback": "v0",
        "current_mjml": v0_mjml,
        "last_operation_status": "FEEDBACK_RECEIVED",
    }
    await graph.aupdate_state(config, feedback_state_update)

    await graph.ainvoke(
        feedback_state_update,
        config=config,
        interrupt_after=[LG_FEEDBACK_ENGINE_NODE_NAME],
    )
    state_after_fe = await graph.aget_state(config)
    assert (
        state_after_fe.values["last_operation_status"] == "SUCCESS_REVISION_GENERATED"
    )

    await graph.ainvoke(
        None, config=config, interrupt_after=[LG_STORE_V_NEXT_NODE_NAME]
    )
    state_after_v_rev_appr = await graph.aget_state(config)
    final_state_values = state_after_v_rev_appr.values

    assert (
        final_state_values["last_operation_status"] == "SUCCESS_STORED_REVISED_VERSION"
    )
    v_rev_appr_id = final_state_values["current_version_id_stored"]
    assert v_rev_appr_id != "v0" and "v_rev_" in v_rev_appr_id
    mock_db_create_template_version.assert_called_once()  # Should be called once for this V_Rev_Approved

    # --- Part 3: Verify DB State ---
    # Fetch V0 (original approved version) - it should still be approved
    v0_from_db = await get_template_version(
        db_session, template_id_str, "v0"
    )  # Direct call
    assert v0_from_db is not None
    assert v0_from_db.is_approved is True, "Original V0 should remain approved"

    # Fetch V_Rev_Approved (new unapproved version) - This was mock-stored, so we check the mock call's data
    v_rev_appr_call_data = mock_db_create_template_version.call_args.kwargs[
        "version_data"
    ]
    assert v_rev_appr_call_data.version_id == v_rev_appr_id
    assert v_rev_appr_call_data.is_approved is False, (
        "Newly revised version should be unapproved"
    )
    assert v_rev_appr_call_data.change_trigger["event"] == "feedback_revision"
    assert v_rev_appr_call_data.change_trigger["source_version_id"] == "v0"
    assert (
        feedback_text[:100]
        in v_rev_appr_call_data.change_trigger["feedback_text_snippet"]
    )
    assert v_rev_appr_call_data.is_approved is False

    logger.info("Test test_feedback_on_approved_version completed successfully.")
