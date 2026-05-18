from dotenv import load_dotenv

load_dotenv()

import pytest
from unittest.mock import AsyncMock, patch

from mailwright.graphs.state import GraphState
from mailwright.graphs.template_generation_graph import image_generation_node
# from mailwright.core_services.image_generator_service import ImageGeneratorService # For type hinting if needed


@pytest.mark.asyncio
async def test_image_generation_node_single_prompt_success():
    """Test image_generation_node with a single successful prompt."""
    initial_prompt = "A cute cat playing with a yarn ball."
    expected_url = "https://example.com/cute_cat.png"

    initial_state = GraphState(image_prompts=[initial_prompt])

    with patch(
        "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
        new_callable=AsyncMock,
    ) as mock_generate_image_call:
        mock_generate_image_call.return_value = expected_url
        result_state_update = await image_generation_node(initial_state)

    mock_generate_image_call.assert_called_once_with(prompt=initial_prompt)
    assert result_state_update is not None
    assert result_state_update.last_operation_status == "SUCCESS_IMAGE_GENERATION"
    assert result_state_update.error_message is None
    assert result_state_update.image_urls_map == {initial_prompt: expected_url}
    assert result_state_update.generated_image_urls == [expected_url]


@pytest.mark.asyncio
async def test_image_generation_node_multiple_prompts_success():
    """Test image_generation_node with multiple successful prompts."""
    prompts = [
        "A futuristic cityscape at dusk.",
        "A serene forest with a hidden waterfall.",
    ]
    expected_urls_map_values = [
        "https://example.com/cityscape.png",
        "https://example.com/waterfall.jpg",
    ]
    expected_image_urls_map = dict(zip(prompts, expected_urls_map_values))
    initial_state = GraphState(image_prompts=prompts)

    async def mock_generate_side_effect(prompt: str):
        if prompt == prompts[0]:
            return expected_urls_map_values[0]
        if prompt == prompts[1]:
            return expected_urls_map_values[1]
        return None

    with patch(
        "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
        new_callable=AsyncMock,
    ) as mock_generate_image_call:
        mock_generate_image_call.side_effect = mock_generate_side_effect
        result_state_update = await image_generation_node(initial_state)

    assert mock_generate_image_call.call_count == len(prompts)
    assert result_state_update.last_operation_status == "SUCCESS_IMAGE_GENERATION"
    assert result_state_update.error_message is None
    assert result_state_update.image_urls_map == expected_image_urls_map
    assert sorted(result_state_update.generated_image_urls) == sorted(
        expected_urls_map_values
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("no_prompts_value", [None, []])
async def test_image_generation_node_no_prompts(no_prompts_value):
    """Test image_generation_node when no image_prompts are provided (None or empty list)."""
    initial_state = GraphState(image_prompts=no_prompts_value)
    with patch(
        "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
        new_callable=AsyncMock,
    ) as mock_generate_image_call:
        result_state_update = await image_generation_node(initial_state)

    mock_generate_image_call.assert_not_called()
    assert result_state_update.last_operation_status == "SKIPPED_IMAGE_GENERATION"
    assert result_state_update.error_message is None
    assert result_state_update.image_urls_map == {}
    assert result_state_update.generated_image_urls == []


@pytest.mark.asyncio
async def test_image_generation_node_partial_failure():
    """Test image_generation_node when some prompts fail and others succeed."""
    prompts = [
        "A working prompt for a sunny beach.",
        "A deliberately failing prompt.",
        "Another working prompt for a mountain view.",
    ]
    successful_url1 = "https://example.com/sunny_beach.png"
    successful_url2 = "https://example.com/mountain_view.jpg"
    expected_image_urls_map = {
        prompts[0]: successful_url1,
        prompts[1]: None,
        prompts[2]: successful_url2,
    }
    initial_state = GraphState(image_prompts=prompts)

    async def mock_generate_side_effect(prompt: str):
        if prompt == prompts[0]:
            return successful_url1
        if prompt == prompts[1]:
            return None
        if prompt == prompts[2]:
            return successful_url2
        return None

    with patch(
        "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
        new_callable=AsyncMock,
    ) as mock_generate_image_call:
        mock_generate_image_call.side_effect = mock_generate_side_effect
        result_state_update = await image_generation_node(initial_state)

    assert mock_generate_image_call.call_count == len(prompts)
    assert result_state_update.last_operation_status == "WARNING_IMAGE_GENERATION"
    error_msg = result_state_update.error_message
    assert error_msg is not None
    assert f"Failed to retrieve URL for prompt: '{prompts[1]}'" in error_msg
    assert (
        len(result_state_update.error_message.split("; ")) == 1
    )  # Only one error in this scenario
    assert result_state_update.image_urls_map == expected_image_urls_map
    assert sorted(result_state_update.generated_image_urls) == sorted(
        [successful_url1, successful_url2]
    )


@pytest.mark.asyncio
async def test_image_generation_node_total_failure():
    """Test image_generation_node when all image prompts fail to generate."""
    prompts = ["A prompt that will fail.", "Another prompt that will also fail."]
    expected_image_urls_map = {prompts[0]: None, prompts[1]: None}
    initial_state = GraphState(image_prompts=prompts)

    with patch(
        "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
        new_callable=AsyncMock,
    ) as mock_generate_image_call:
        mock_generate_image_call.return_value = None
        result_state_update = await image_generation_node(initial_state)

    assert mock_generate_image_call.call_count == len(prompts)
    assert result_state_update.last_operation_status == "ERROR_IMAGE_GENERATION"
    error_msg = result_state_update.error_message
    assert error_msg is not None
    assert f"Failed to retrieve URL for prompt: '{prompts[0]}'" in error_msg
    assert f"Failed to retrieve URL for prompt: '{prompts[1]}'" in error_msg
    assert len(result_state_update.error_message.split("; ")) == 2  # Two errors
    assert result_state_update.image_urls_map == expected_image_urls_map
    assert result_state_update.generated_image_urls == []


@pytest.mark.asyncio
async def test_image_generation_node_service_exception():
    """Test image_generation_node when the image_generator_service raises an unhandled exception."""
    initial_prompt = "A prompt that causes an unexpected error."
    exception_message = "Network unavailable or critical service error"
    initial_state = GraphState(image_prompts=[initial_prompt])

    with patch(
        "mailwright.graphs.template_generation_graph.image_generator_service.generate_image",
        new_callable=AsyncMock,
    ) as mock_generate_image_call:
        mock_generate_image_call.side_effect = Exception(exception_message)
        result_state_update = await image_generation_node(initial_state)

    mock_generate_image_call.assert_called_once_with(prompt=initial_prompt)
    assert result_state_update.last_operation_status == "ERROR_IMAGE_GENERATION"
    error_msg = result_state_update.error_message
    assert error_msg is not None
    assert f"Exception for prompt '{initial_prompt}': {exception_message}" in error_msg
    assert result_state_update.image_urls_map == {initial_prompt: None}
    assert result_state_update.generated_image_urls == []
