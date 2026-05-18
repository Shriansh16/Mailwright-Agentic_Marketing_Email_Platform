from dotenv import load_dotenv

load_dotenv()

import asyncio
import base64
import io

from openai import OpenAI, APIError, RateLimitError
from mailwright.config import settings
import logging
from mailwright.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _uses_gpt_image_model(model: str) -> bool:
    """OpenAI gpt-image-* models use different quality values than DALL-E 3."""
    return model.startswith("gpt-image")


def _normalize_openai_quality(model: str, quality: str) -> str:
    """Map legacy DALL-E quality names to the correct API values per model family."""
    q = quality.lower()
    if _uses_gpt_image_model(model):
        return {
            "standard": "auto",
            "hd": "high",
            "low": "low",
            "medium": "medium",
            "high": "high",
            "auto": "auto",
        }.get(q, "auto")
    return q if q in ("standard", "hd") else "standard"


class ImageGeneratorService:
    """
    Service to generate images using a configurable provider.

    Supported providers (set via IMAGE_GENERATION_PROVIDER in .env):
      - "openai"  — DALL-E 3 (returns a hosted image URL)
      - "google"  — Gemini image generation (returns a base64 data URI)
    """

    def __init__(self):
        provider = settings.IMAGE_GENERATION_PROVIDER.lower()

        if provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise ValueError(
                    "OPENAI_API_KEY is not set in settings for ImageGeneratorService."
                )
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            self.model = settings.IMAGE_GENERATION_OPENAI_DALLE_MODEL
            self._provider = "openai"

        elif provider == "google":
            if not settings.GOOGLE_API_KEY:
                raise ValueError(
                    "GOOGLE_API_KEY is not set in settings for ImageGeneratorService."
                )
            try:
                from google import genai as google_genai
            except ImportError as exc:
                raise ImportError(
                    "google-genai package is required for the Google image provider. "
                    "Run: pip install google-genai"
                ) from exc
            self.client = google_genai.Client(api_key=settings.GOOGLE_API_KEY)
            self.model = settings.IMAGE_GENERATION_GOOGLE_MODEL
            self._provider = "google"

        else:
            raise NotImplementedError(
                f"Image generation provider '{settings.IMAGE_GENERATION_PROVIDER}' is not supported. "
                "Supported providers: 'openai', 'google'."
            )

        logger.info(
            f"ImageGeneratorService initialized with provider: {provider}, model: {self.model}"
        )

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
    ) -> str | None:
        """
        Generates an image from a text prompt.

        For OpenAI (DALL-E 3): returns a hosted image URL.
        For Google (Gemini):   returns a base64 PNG data URI
                                ("data:image/png;base64,..."), usable as an
                                <img src> in HTML/MJML email templates.

        Args:
            prompt:  Textual description of the image to generate.
            size:    Desired dimensions — e.g. "1024x1024". Only used by DALL-E;
                     Gemini determines its own output size.
            quality: "standard" or "hd". Only used by DALL-E.
            n:       Number of images. Must be 1 for DALL-E 3; Gemini always
                     returns one image per call.

        Returns:
            A URL string (OpenAI) or base64 data URI (Google), or None on error.
        """
        if not prompt:
            logger.error("Image generation prompt cannot be empty.")
            return None

        if self._provider == "openai":
            return await self._generate_openai(prompt, size, quality, n)
        else:
            return await self._generate_google(prompt)

    # ------------------------------------------------------------------
    # Provider-specific helpers
    # ------------------------------------------------------------------

    async def _generate_openai(
        self, prompt: str, size: str, quality: str, n: int
    ) -> str | None:
        try:
            api_quality = _normalize_openai_quality(self.model, quality)
            logger.info(
                f"[OpenAI] Requesting image for prompt: '{prompt}' | "
                f"model: {self.model} | quality: {api_quality}"
            )
            kwargs: dict = {
                "model": self.model,
                "prompt": prompt,
                "quality": api_quality,
                "n": n,
            }
            if not _uses_gpt_image_model(self.model):
                kwargs["size"] = size  # type: ignore[assignment]

            response = await asyncio.to_thread(
                self.client.images.generate,
                **kwargs,
            )
            if not response.data:
                logger.error("[OpenAI] Image generation response contained no data.")
                return None

            item = response.data[0]
            if item.url:
                logger.info(f"[OpenAI] Image generated. URL: {item.url}")
                return item.url
            if item.b64_json:
                data_uri = f"data:image/png;base64,{item.b64_json}"
                logger.info(
                    f"[OpenAI] Image generated as base64 data URI "
                    f"({len(item.b64_json):,} chars)."
                )
                return data_uri

            logger.error("[OpenAI] Image generation response contained no URL or b64_json.")
            return None

        except RateLimitError as e:
            logger.error(f"[OpenAI] DALL-E rate limit exceeded: {e}")
            return None
        except APIError as e:
            logger.error(f"[OpenAI] DALL-E API error: {e}")
            return None
        except Exception as e:
            logger.error(f"[OpenAI] Unexpected error during image generation: {e}")
            return None

    async def _generate_google(self, prompt: str) -> str | None:
        """
        Calls the Gemini image generation API and returns a base64 PNG data URI.

        The Gemini response contains `parts`; image data lives in
        `part.inline_data`.  We convert it to a data URI so it can be used
        directly as an <img src> attribute in MJML / HTML templates.
        """
        try:
            from google.genai import types as google_types

            logger.info(f"[Google] Requesting image for prompt: '{prompt}' | model: {self.model}")

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=prompt,
                config=google_types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"]
                ),
            )

            for part in response.parts:
                if part.inline_data is not None:
                    mime_type = part.inline_data.mime_type or "image/png"
                    image_bytes = part.inline_data.data

                    # Normalise to PNG via PIL so we always return a consistent format
                    pil_image = part.as_image()
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format="PNG")
                    png_bytes = buffer.getvalue()

                    b64 = base64.b64encode(png_bytes).decode("utf-8")
                    data_uri = f"data:image/png;base64,{b64}"
                    logger.info(
                        f"[Google] Image generated successfully ({len(png_bytes):,} bytes, "
                        f"original mime: {mime_type})."
                    )
                    return data_uri

            logger.error("[Google] Gemini response contained no image parts.")
            return None

        except Exception as e:
            logger.error(f"[Google] Unexpected error during Gemini image generation: {e}")
            return None


# ---------------------------------------------------------------------------
# Manual smoke test  (python -m mailwright.core_services.image_generator_service)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    setup_logging()

    async def _smoke_test():
        provider = settings.IMAGE_GENERATION_PROVIDER.lower()
        if provider == "openai" and not settings.OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY not set.")
            return
        if provider == "google" and not settings.GOOGLE_API_KEY:
            logger.error("GOOGLE_API_KEY not set.")
            return

        svc = ImageGeneratorService()
        result = await svc.generate_image("A sunset over a futuristic city skyline, digital art")
        if result:
            if result.startswith("data:"):
                logger.info(f"Generated data URI (length: {len(result):,} chars).")
            else:
                logger.info(f"Generated image URL: {result}")
        else:
            logger.error("Image generation failed.")

    asyncio.run(_smoke_test())
