import pytest
from unittest.mock import patch, MagicMock
from openai.types import ImagesResponse
from openai.types.image import Image
from datetime import datetime

from xyra.core_services.image_generator_service import ImageGeneratorService
from xyra.config import settings


# Helper to create a mock ImagesResponse object
def create_mock_image_response(url: str) -> ImagesResponse:
    mock_image = Image(b64_json=None, revised_prompt=None, url=url)
    # As of openai client v1.x, ImagesResponse expects 'created' as int (timestamp)
    # and 'data' as a list of Image objects.
    return ImagesResponse(created=int(datetime.now().timestamp()), data=[mock_image])


@pytest.fixture
def image_service() -> ImageGeneratorService:
    """Fixture to create an instance of ImageGeneratorService."""
    # Temporarily ensure the correct provider is set for testing this service
    original_provider = settings.IMAGE_GENERATION_PROVIDER
    original_api_key = settings.OPENAI_API_KEY

    settings.IMAGE_GENERATION_PROVIDER = (
        "openai"  # Ensure OpenAI is selected for this test
    )
    if not settings.OPENAI_API_KEY:
        settings.OPENAI_API_KEY = (
            "test_api_key_for_unit_test"  # Provide a dummy key if None
        )

    service = ImageGeneratorService()

    yield service  # Provide the service to the test

    # Restore original settings after test
    settings.IMAGE_GENERATION_PROVIDER = original_provider
    settings.OPENAI_API_KEY = original_api_key


@pytest.mark.asyncio
async def test_generate_image_success(image_service: ImageGeneratorService):
    """Test successful image generation."""
    test_prompt = "A beautiful landscape"
    expected_url = "https://example.com/generated_image.png"
    mock_response = create_mock_image_response(expected_url)

    # For async method, if the mocked method is synchronous, patch it directly.
    # If the mocked method itself were async, we'd use AsyncMock.
    # Here, 'generate' is sync, but called via to_thread.
    # We are mocking the synchronous 'generate' method of the OpenAI client.
    with patch.object(
        image_service.client.images, "generate", return_value=mock_response
    ) as mock_generate:
        image_url = await image_service.generate_image(
            prompt=test_prompt
        )  # Added await

        assert image_url == expected_url
        mock_generate.assert_called_once_with(
            model=settings.IMAGE_GENERATION_OPENAI_DALLE_MODEL,
            prompt=test_prompt,
            size="1024x1024",  # Default size
            quality="standard",  # Default quality
            n=1,  # Default n
        )


@pytest.mark.asyncio
async def test_generate_image_empty_prompt(image_service: ImageGeneratorService):
    """Test image generation with an empty prompt."""
    with patch.object(image_service.client.images, "generate") as mock_generate:
        image_url = await image_service.generate_image(prompt="")  # Added await
        assert image_url is None
        mock_generate.assert_not_called()


@pytest.mark.asyncio
async def test_generate_image_api_error(image_service: ImageGeneratorService):
    """Test image generation when the API call fails."""
    test_prompt = "An image that will cause an error"

    from openai import APIError  # Import here to keep it local to the test if preferred
    import httpx  # Required for the request object

    # Create a mock httpx.Request object
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.method = "POST"
    mock_request.url = "https://api.openai.com/v1/images/generations"

    with patch.object(
        image_service.client.images,
        "generate",
        side_effect=APIError("Test API Error", request=mock_request, body=None),
    ) as mock_generate:
        image_url = await image_service.generate_image(
            prompt=test_prompt
        )  # Added await
        assert image_url is None
        mock_generate.assert_called_once()


@pytest.mark.asyncio
async def test_generate_image_no_url_in_response(image_service: ImageGeneratorService):
    """Test image generation when API response is successful but contains no URL."""
    test_prompt = "A prompt for an image"
    mock_image_without_url = Image(b64_json=None, revised_prompt=None, url=None)
    mock_response_no_url = ImagesResponse(
        created=int(datetime.now().timestamp()), data=[mock_image_without_url]
    )

    with patch.object(
        image_service.client.images, "generate", return_value=mock_response_no_url
    ) as mock_generate:
        image_url = await image_service.generate_image(
            prompt=test_prompt
        )  # Added await
        assert image_url is None
        mock_generate.assert_called_once()


def test_image_service_initialization_no_api_key():
    """Test service initialization when OPENAI_API_KEY is missing."""
    original_api_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = None  # Simulate missing key
    settings.IMAGE_GENERATION_PROVIDER = (
        "openai"  # Ensure provider is openai for this check
    )

    with pytest.raises(ValueError, match="OPENAI_API_KEY is not set"):
        ImageGeneratorService()

    settings.OPENAI_API_KEY = original_api_key  # Restore


def test_image_service_initialization_unsupported_provider():
    """Test service initialization with an unsupported provider."""
    original_provider = settings.IMAGE_GENERATION_PROVIDER
    settings.IMAGE_GENERATION_PROVIDER = "unsupported_provider"

    with pytest.raises(
        NotImplementedError,
        match="Image generation provider 'unsupported_provider' is not supported.",
    ):
        ImageGeneratorService()

    settings.IMAGE_GENERATION_PROVIDER = original_provider  # Restore
