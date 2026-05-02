import pytest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage  # Added
from xyra.graphs.state import GraphState
from xyra.core_services.mjml_service import MJMLService
from xyra.schemas.template_schemas import (
    UserBriefSchema,
)  # Assuming this is the schema for brief_data
from xyra.config import Settings


# Minimal settings for testing
@pytest.fixture
def test_settings():
    # Ensure MJML_GENERATION_PROVIDER is set for the test, as MJMLService relies on it.
    return Settings(
        MJML_GENERATION_PROVIDER="openai",  # Mock provider for tests
        MJML_GENERATION_OPENAI_MODEL="gpt-test",  # Mock model
        MJML_GENERATION_ANTHROPIC_MODEL="claude-test",  # Mock model
        OPENAI_API_KEY="test_key",
        ANTHROPIC_API_KEY="test_key",
    )


@pytest.fixture
def mjml_service(test_settings):
    with (
        patch("xyra.core_services.mjml_service.settings", test_settings),
        patch("xyra.core_services.llm_factory.settings", test_settings),
    ):  # Also patch settings for llm_factory
        # MJMLService now takes no arguments for __init__
        service = MJMLService()
        # Mock the LLM client that gets created inside MJMLService.__init__
        # This requires knowing how get_configured_chat_model is called or mocking it directly.
        # For simplicity here, we'll assume it's okay to re-mock service.llm_client if it was set.
        service.llm_client = AsyncMock()
        return service


@pytest.mark.asyncio
async def test_generate_mjml_node_success(mjml_service: MJMLService):
    """Test successful MJML generation."""
    # Mock the behavior of the llm_client when it's called by the chain
    mock_message = AIMessage(
        content="<mjml><mj-body><mj-text>Hello</mj-text></mj-body></mjml>"
    )
    mjml_service.llm_client.return_value = (
        mock_message  # chain calls llm_client directly
    )

    brief_data = UserBriefSchema(
        subject="Test", body_copy="Test body", call_to_action_text="Click"
    ).model_dump()
    initial_state = GraphState(user_brief_data=brief_data)

    result = await mjml_service.generate_mjml_node(initial_state)

    assert result["last_operation_status"] == "success"
    assert result["current_mjml"] == mock_message.content
    assert result["error_message"] is None
    mjml_service.llm_client.assert_called_once()  # Check if the llm_client mock itself was called


@pytest.mark.asyncio
async def test_generate_mjml_node_no_brief(mjml_service: MJMLService):
    """Test MJML generation when no brief is provided in state."""
    initial_state = GraphState(user_brief_data=None, amended_brief_data=None)

    result = await mjml_service.generate_mjml_node(initial_state)

    assert result["last_operation_status"] == "failure"
    assert result["error_message"] == "MJML Generation Failed: No user brief provided."
    assert result["current_mjml"] is None
    mjml_service.llm_client.assert_not_called()  # llm_client mock should not be called


@pytest.mark.asyncio
async def test_generate_mjml_node_llm_failure(mjml_service: MJMLService):
    """Test MJML generation when LLM call fails or returns invalid structure."""
    mock_message = AIMessage(content="This is not MJML")  # Invalid response
    mjml_service.llm_client.return_value = (
        mock_message  # chain calls llm_client directly
    )

    brief_data = UserBriefSchema(subject="Test", body_copy="Test body").model_dump()
    initial_state = GraphState(user_brief_data=brief_data)

    result = await mjml_service.generate_mjml_node(initial_state)

    assert result["last_operation_status"] == "failure"
    assert (
        result["error_message"]
        == "MJML Generation Failed: LLM did not produce valid MJML structure."
    )
    assert result["current_mjml"] == "This is not MJML"  # Stores the bad response
    mjml_service.llm_client.assert_called_once()  # Check if the llm_client mock itself was called


@pytest.mark.asyncio
async def test_generate_mjml_node_llm_exception(mjml_service: MJMLService):
    """Test MJML generation when LLM call raises an exception."""
    # Set side_effect on the llm_client mock itself
    mjml_service.llm_client.side_effect = Exception("LLM API Error")

    brief_data = UserBriefSchema(subject="Test", body_copy="Test body").model_dump()
    initial_state = GraphState(user_brief_data=brief_data)

    result = await mjml_service.generate_mjml_node(initial_state)

    assert result["last_operation_status"] == "ERROR_MJML_GENERATION"
    assert (
        "MJML Generation Failed: An unexpected error occurred: LLM API Error"
        in result["error_message"]
    )
    assert result["current_mjml"] is None
    mjml_service.llm_client.assert_called_once()  # Check if the llm_client mock itself was called


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_validate_and_compile_mjml_node_success(
    mock_subprocess_exec, mjml_service: MJMLService
):
    """Test successful MJML validation and compilation."""
    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(
        return_value=(b"<p>Compiled HTML</p>", b"")
    )  # stdout, stderr
    mock_process.returncode = 0
    mock_subprocess_exec.return_value = mock_process

    initial_state = GraphState(current_mjml="<mjml><mj-body></mj-body></mjml>")

    with (
        patch("os.path.exists", return_value=True),
        patch("os.remove"),
    ):  # Mock temp file handling
        result = await mjml_service.validate_and_compile_mjml_node(initial_state)

    assert result["last_operation_status"] == "success"
    assert result["compiled_html"] == "<p>Compiled HTML</p>"
    assert result["mjml_validation_status"] == "VALID"
    assert result["error_message"] is None
    mock_subprocess_exec.assert_called_once()


@pytest.mark.asyncio
async def test_validate_and_compile_mjml_node_no_mjml(mjml_service: MJMLService):
    """Test validation when no MJML content is in state."""
    initial_state = GraphState(current_mjml=None)

    result = await mjml_service.validate_and_compile_mjml_node(initial_state)

    assert result["last_operation_status"] == "failure_mjml_validation_compilation"
    assert result["mjml_validation_status"] == "NOT_AVAILABLE"
    assert "No MJML content provided" in result["error_message"]


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_validate_and_compile_mjml_node_cli_validation_error(
    mock_subprocess_exec, mjml_service: MJMLService
):
    """Test validation when mjml CLI returns a validation error."""
    mock_process = AsyncMock()
    # Simulate MJML CLI output for a validation error
    mock_process.communicate = AsyncMock(
        return_value=(b"", b"Line 2: Invalid MJML syntax - validation error")
    )
    mock_process.returncode = (
        0  # MJML CLI might return 0 even with validation errors printed to stderr
    )
    mock_subprocess_exec.return_value = mock_process

    initial_state = GraphState(
        current_mjml="<mjml><mj-body><mj-text>Invalid</mj-text></mj-body></mjml>"
    )

    with patch("os.path.exists", return_value=True), patch("os.remove"):
        result = await mjml_service.validate_and_compile_mjml_node(initial_state)

    assert result["last_operation_status"] == "failure_mjml_validation_compilation"
    assert result["mjml_validation_status"] == "INVALID"
    assert "Line 2: Invalid MJML syntax" in result["error_message"]


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_validate_and_compile_mjml_node_cli_compilation_error(
    mock_subprocess_exec, mjml_service: MJMLService
):
    """Test validation when mjml CLI returns a non-zero exit code (compilation error)."""
    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(
        return_value=(b"", b"Fatal error during compilation!")
    )
    mock_process.returncode = 1  # Non-zero indicates failure
    mock_subprocess_exec.return_value = mock_process

    initial_state = GraphState(
        current_mjml="<mjml><mj-body><mj-text>Broken</mj-text></mj-body></mjml>"
    )

    with patch("os.path.exists", return_value=True), patch("os.remove"):
        result = await mjml_service.validate_and_compile_mjml_node(initial_state)

    assert result["last_operation_status"] == "failure_mjml_validation_compilation"
    assert result["mjml_validation_status"] == "INVALID"
    assert "Fatal error during compilation!" in result["error_message"]


@pytest.mark.asyncio
@patch(
    "asyncio.create_subprocess_exec", side_effect=FileNotFoundError("mjml not found")
)
async def test_validate_and_compile_mjml_node_cli_not_found(
    mock_subprocess_exec, mjml_service: MJMLService
):
    """Test validation when mjml CLI is not found."""
    initial_state = GraphState(current_mjml="<mjml></mjml>")

    # No need to mock os.path.exists or os.remove as it won't reach that point
    result = await mjml_service.validate_and_compile_mjml_node(initial_state)

    assert result["last_operation_status"] == "failure_mjml_validation_compilation"
    assert result["mjml_validation_status"] == "ERROR"
    assert "mjml CLI not found" in result["error_message"]


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_validate_and_compile_mjml_node_unexpected_exception(
    mock_subprocess_exec, mjml_service: MJMLService
):
    """Test validation with an unexpected exception during subprocess call."""
    mock_subprocess_exec.side_effect = Exception("Unexpected subprocess error")

    initial_state = GraphState(current_mjml="<mjml></mjml>")

    with patch("os.path.exists", return_value=True), patch("os.remove"):
        result = await mjml_service.validate_and_compile_mjml_node(initial_state)

    assert result["last_operation_status"] == "failure_mjml_validation_compilation"
    assert result["mjml_validation_status"] == "ERROR"
    assert "Unexpected subprocess error" in result["error_message"]
