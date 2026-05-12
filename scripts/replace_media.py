import asyncio
import re
from bs4 import BeautifulSoup
import os
import logging
from openai import OpenAI
from mailwright.core_services.image_generator_service import ImageGeneratorService
from mailwright.logging_config import setup_logging
from mailwright.config import settings

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# --- Configuration ---
INPUT_HTML_PATH = "output/test-movie-premier.html"
OUTPUT_HTML_PATH = "output/test-movie-premier-replaced.html"
# Use a general-purpose LLM for prompt generation
PROMPT_GENERATION_MODEL = "gpt-4o"

# --- LLM Client for Prompt Generation ---
# Ensure the API key is available
if not settings.OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set. Cannot initialize LLM client.")
llm_client = OpenAI(api_key=settings.OPENAI_API_KEY)


async def generate_global_context(html_content: str) -> str:
    """
    Uses an LLM to generate a high-level summary of the HTML document's theme and purpose.
    """
    logger.info("Generating global context for the HTML document...")
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        document_text = soup.get_text(separator=" ", strip=True)

        system_prompt = "You are an expert at analyzing marketing content. Summarize the following email content in one sentence. Focus on the main subject, the product being advertised, and the overall tone. This summary will be used to provide context for generating images."

        response = await asyncio.to_thread(
            llm_client.chat.completions.create,
            model=PROMPT_GENERATION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": document_text},
            ],
            temperature=0.2,
        )
        summary = response.choices[0].message.content
        logger.info(f"Generated global context: {summary}")
        return summary if summary else "A promotional email."
    except Exception as e:
        logger.error(f"Failed to generate global context: {e}")
        return "A promotional email for a product or service."


async def generate_detailed_image_prompt(
    global_context: str, local_html_snippet: str, image_attrs: dict
) -> str:
    """
    Uses an LLM to generate a detailed DALL-E 3 prompt based on global and local context.
    """
    logger.info(
        f"Generating detailed prompt for image with original src: {image_attrs.get('src')}"
    )

    system_prompt = """
You are an expert prompt engineer for the DALL-E 3 image generation model.
Your task is to create a detailed, specific, and creative prompt based on the provided context.

You will be given:
1.  **Global Context**: A high-level summary of the entire email.
2.  **Local HTML Snippet**: The exact HTML section where the image will be placed. This shows the surrounding text and structure, which is the most important clue.
3.  **Image Attributes**: The original placeholder's dimensions and alt text (which may be unhelpful).

**Instructions:**
1.  Analyze the HTML snippet to understand the image's specific purpose (e.g., is it a header, a product shot, a headshot of a person mentioned nearby?).
2.  Use the global context to inform the overall style and theme.
3.  Generate a single, concise DALL-E 3 prompt that will create a visually compelling and contextually appropriate image.
4.  Do NOT output anything other than the prompt itself. No explanations, no preamble. Just the prompt text.
"""

    user_prompt = f"""
**Global Context:**
{global_context}

**Local HTML Snippet:**
```html
{local_html_snippet}
```

**Image Attributes:**
- Original Dimensions: {image_attrs.get("width")}x{image_attrs.get("height")}
- DALL-E 3 Target Size: {image_attrs.get("dalle_size")}
- Original Alt Text: "{image_attrs.get("alt")}"

Generate the DALL-E 3 prompt now.
"""

    try:
        response = await asyncio.to_thread(
            llm_client.chat.completions.create,
            model=PROMPT_GENERATION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        detailed_prompt = response.choices[0].message.content
        logger.info(f"Generated detailed prompt: {detailed_prompt}")
        return detailed_prompt if detailed_prompt else "A high-quality, relevant image."
    except Exception as e:
        logger.error(f"Failed to generate detailed prompt: {e}")
        return "A high-quality, visually appealing, and contextually relevant image for a promotional email."


async def main():
    """
    Main function to run the intelligent image replacement process.
    """
    logger.info(f"Starting intelligent image replacement for: {INPUT_HTML_PATH}")

    try:
        with open(INPUT_HTML_PATH, "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        logger.error(f"Input HTML file not found at: {INPUT_HTML_PATH}")
        return

    soup = BeautifulSoup(html_content, "html.parser")
    global_context = await generate_global_context(html_content)

    images = soup.find_all("img")
    placeholder_images = [
        img for img in images if img.get("src") and "placehold.co" in img["src"]
    ]
    logger.info(f"Found {len(placeholder_images)} placeholder images to replace.")

    image_service = ImageGeneratorService()

    for img in placeholder_images:
        src = img["src"]
        match = re.search(r"\/(\d+x\d+)\/", src)
        if not match:
            logger.warning(f"Could not extract dimensions from src: {src}. Skipping.")
            continue

        dims_str = match.group(1)
        width, height = map(int, dims_str.split("x"))

        aspect_ratio = width / height if height > 0 else 1
        dalle_size = (
            "1792x1024"
            if aspect_ratio > 1.2
            else "1024x1792"
            if aspect_ratio < 0.8
            else "1024x1024"
        )

        # Find a meaningful parent container for local context
        parent_container = img.find_parent("td") or img.find_parent("div") or img
        local_snippet = str(parent_container.prettify())

        image_attrs = {
            "src": src,
            "alt": img.get("alt", ""),
            "width": width,
            "height": height,
            "dalle_size": dalle_size,
        }

        # Generate the intelligent prompt
        detailed_prompt = await generate_detailed_image_prompt(
            global_context, local_snippet, image_attrs
        )

        logger.info(
            f"Generating image with prompt: '{detailed_prompt}' and size {dalle_size}"
        )

        # Generate the image
        new_image_url = await image_service.generate_image(
            prompt=detailed_prompt, size=dalle_size
        )

        if new_image_url:
            logger.info(f"Successfully generated new image: {new_image_url}")
            img["src"] = new_image_url
            img["title"] = img.get("alt", "Generated Image")  # Use alt text for title
        else:
            logger.error(f"Failed to generate image for prompt: {detailed_prompt}")

    try:
        with open(OUTPUT_HTML_PATH, "w", encoding="utf-8") as f:
            f.write(str(soup))
        logger.info(f"Successfully saved modified HTML to: {OUTPUT_HTML_PATH}")
    except IOError as e:
        logger.error(f"Failed to write to output file: {e}")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning(
            "OPENAI_API_KEY environment variable not found. The script may fail."
        )

    asyncio.run(main())
