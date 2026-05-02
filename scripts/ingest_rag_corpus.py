import asyncio
import os
import json
import logging
from typing import List
import io
import httpx
from PIL import Image

from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from xyra.config import settings
from xyra.db.models import RAGTemplate
from xyra.logging_config import setup_logging

# --- Basic Setup ---
setup_logging()
logger = logging.getLogger(__name__)

# --- Configuration ---
# The directory where you will place the JSON templates for ingestion.
INGEST_DIR = "ingest/"
PROMPT_GENERATION_MODEL = settings.PROMPT_GENERATION_MODEL
EMBEDDING_MODEL = settings.EMBEDDING_MODEL_NAME

# --- Surgical HTML Processor ---
async def process_html(html: str) -> str:
    """
    Processes the raw HTML to replace media with placeholders, ignoring UI/branding images.
    Fetches original images to get real dimensions for accurate placeholders.
    """
    logger.info("Processing HTML to replace media with placeholders...")
    soup = BeautifulSoup(html, "html.parser")

    async with httpx.AsyncClient() as client:
        for img in soup.find_all("img"):
            original_src = img.get("src", "")
            if not original_src or "app-rsrc.getbee.io" in original_src:
                continue
            
            try:
                response = await client.get(original_src, timeout=10)
                response.raise_for_status()
                image_data = io.BytesIO(response.content)
                with Image.open(image_data) as pil_image:
                    width, height = pil_image.size
                
                placeholder_url = f"https://placehold.co/{width}x{height}/EEE/31343C?text=Image"
                img["src"] = placeholder_url
                logger.info(f"Replaced src for {original_src} with {placeholder_url}")
            except Exception as e:
                logger.error(f"Could not process image {original_src}: {e}")
                continue

        for video_link in soup.find_all("a", class_="video-preview"):
            video_block = video_link.find_parent("table")
            if not video_block:
                continue
            
            wrapper = soup.new_tag('div', attrs={'align': 'center'})
            width, height = "600", "337"
            placeholder_div_str = f'''
            <div style="width: 100%; max-width: {width}px; height: 0; padding-top: 56.25%; background-color: #333; position: relative;">
                <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; color: #fff; display: flex; align-items: center; justify-content: center; font-family: sans-serif; font-size: 18px; font-weight: bold;">
                    Video Placeholder ({width}x{height})
                </div>
            </div>
            '''
            placeholder_soup = BeautifulSoup(placeholder_div_str, "html.parser")
            wrapper.append(placeholder_soup)
            video_block.replace_with(wrapper)
            logger.info("Replaced video block with a centered placeholder div.")
            
    return str(soup)


async def generate_fingerprint_and_embedding(llm_client: AsyncOpenAI, processed_html: str, template_metadata: dict) -> List[float]:
    """
    Generates the structural fingerprint with a content suffix and creates the vector embedding.
    """
    logger.info("Generating fingerprint and embedding...")

    # The prompt we workshopped together
    system_prompt = """
You are a meticulous and hyper-literal Structural Analyst AI. Your sole purpose is to convert descriptions of webpage layouts into a standardized, content-agnostic, single-line "Structural Fingerprint" with a content-aware suffix.

You must adhere to the following rules without deviation.

**1. THE CONTROLLED VOCABULARY:**
You MUST use ONLY the following terms to describe components and layouts.

* **Global Layouts:** `layout: single-column-dominant`, `layout: multi-column-dominant`, `layout: mixed-layout`
* **Section Layouts:** `single-column-stack`, `two-column`, `three-column`, `four-column`, `alternating-2-col`, `alternating-2-col-reversed`, `grid-2-col`, `grid-3-col`, `grid-4-col`, `list-block`
* **Image Components:** `image-hero`, `image-avatar`, `image-icon`, `image-logo`, `image-banner`, `image-gallery`, `image-standard`
* **Text Components:** `h1`, `h2`, `h3`, `p-lead`, `p-body`, `caption`, `label`, `text-link`, `list-item`
* **Interactive Components:** `button-primary-cta`, `button-secondary`, `nav-links`, `icon-group`, `search-bar`, `form-input`, `video-placeholder`
* **Generic Containers:** `container`, `card`, `cell`

**2. THE FINGERPRINT SYNTAX & FORMATTING RULES:**
You MUST format the output according to this strict syntax:

* **Single Line Output:** The entire fingerprint must be a single line of text with no line breaks.
* **Section Separator:** Use a pipe `|` surrounded by spaces to separate major sections (e.g., `header | section-1 | footer`).
* **Property Separator:** Use a semicolon `;` followed by a space to separate key-value properties within a section.
* **Hierarchy:** Use a greater-than sign `>` with no spaces to show nesting (e.g., `header>hero>image-hero`).
* **Key-Value Pairs:** Use a colon `:` with no spaces for key-value pairs (e.g., `layout:mixed-layout`).
* **Quantification:** Use parentheses `()` to specify component counts (e.g., `components:h2(2), p-body(4)`). List components alphabetically within a `components` block.

**3. CORE DIRECTIVES:**
* **Separation of Concerns:** The fingerprint is divided into two parts by the `::CONTENT>>` separator.
    *   The part **before** the separator is the **Structural Fingerprint**. It MUST be purely structural and content-agnostic.
    *   The part **after** the separator is the **Content Suffix**. It is derived from the template's metadata.
* **No Explanations:** Do NOT output any text, explanation, or commentary. Your entire response must be ONLY the fingerprint string itself.
* **Top-Down Order:** Always analyze the template from top to bottom, preserving the section order for the structural part.

**4. THE CONTENT SUFFIX:**
After generating the structural fingerprint, you MUST append the exact separator ` ::CONTENT>> ` followed by a content summary.

* **Input:** You will receive the `categories` and `description` from the template's JSON metadata.
* **Format:** The suffix must follow this format: `categories:tag1,tag2,tag3; summary:a-kebab-cased-summary-of-the-description`
* **Instructions:**
    1.  List the categories exactly as provided, joined by commas.
    2.  Read the description and generate a concise, descriptive summary of about 5-10 words.
    3.  Convert this summary to `kebab-case` (all lowercase, spaces replaced with hyphens).
"""

    user_prompt = f"""
**Processed HTML to analyze:**
```html
{processed_html}
```

**Template Metadata for Content Suffix:**
- categories: {json.dumps(template_metadata.get("categories", []))}
- description: {json.dumps(template_metadata.get("description", ""))}

Generate the fingerprint now.
"""

    try:
        # --- Generate the fingerprint string ---
        logger.info("Calling LLM to generate structural fingerprint...")
        response = await llm_client.chat.completions.create(
            model=PROMPT_GENERATION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        fingerprint_string = response.choices[0].message.content
        logger.info(f"Generated fingerprint: {fingerprint_string}")

        # --- Generate the embedding from the fingerprint ---
        if fingerprint_string:
            logger.info("Calling OpenAI to generate embedding...")
            embedding_response = await llm_client.embeddings.create(
                input=fingerprint_string,
                model=EMBEDDING_MODEL,
            )
            embedding = embedding_response.data[0].embedding
            logger.info(
                f"Successfully generated embedding of dimension {len(embedding)}."
            )
            return embedding
        else:
            logger.error("LLM failed to return a fingerprint string.")
            return []  # Return empty list on failure

    except Exception as e:
        logger.error(
            f"An error occurred during fingerprint or embedding generation: {e}", exc_info=True
        )
        return []


async def main():
    """
    Main function to orchestrate the ingestion of RAG templates.
    """
    logger.info("Starting RAG corpus ingestion process...")
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set.")
        
    # Correctly instantiate and manage the client within the main async function
    llm_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    # Setup database session
    if not settings.DATABASE_URL:
        logger.error("DATABASE_URL is not configured.")
        raise ValueError("DATABASE_URL is not configured.")
    async_engine = create_async_engine(settings.DATABASE_URL)
    AsyncSessionLocal = sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with AsyncSessionLocal() as session:
            # --- File System Scan ---
            try:
                json_files = [f for f in os.listdir(INGEST_DIR) if f.endswith(".json")]
                if not json_files:
                    logger.warning(f"No JSON files found in '{INGEST_DIR}'. Exiting.")
                    return

                logger.info(f"Found {len(json_files)} templates to process.")

                for file_name in json_files:
                    file_path = os.path.join(INGEST_DIR, file_name)
                    template_name = os.path.splitext(file_name)[0]
                    logger.info(f"--- Processing: {template_name} ---")

                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            template_data = json.load(f)

                        raw_html = template_data.get("html_data")
                        if not raw_html:
                            logger.warning(
                                f"Skipping '{file_name}': 'html_data' key not found or is empty."
                            )
                            continue

                        # Process the raw HTML to get the version with placeholders
                        processed_html = await process_html(raw_html)

                        embedding = await generate_fingerprint_and_embedding(
                            llm_client, processed_html, template_data
                        )

                        if embedding:
                            db_record = RAGTemplate(
                                template_name=template_name,
                                raw_html=raw_html,  # Store the original HTML
                                processed_html=processed_html, # Store the processed HTML
                                fingerprint_embedding=embedding,
                            )
                            session.add(db_record)
                            logger.info(f"Staged '{template_name}' for database insertion.")
                        else:
                            logger.error(
                                f"Skipping database insertion for '{template_name}' due to embedding failure."
                            )

                    except json.JSONDecodeError:
                        logger.error(f"Skipping '{file_name}': Invalid JSON.")
                    except Exception as e:
                        logger.error(
                            f"An unexpected error occurred processing '{file_name}': {e}", exc_info=True
                        )

                logger.info("Committing all staged records to the database...")
                await session.commit()
                logger.info("Successfully committed records.")

            except FileNotFoundError:
                logger.error(
                    f"Ingestion directory '{INGEST_DIR}' not found. Please create it and add templates."
                )
    finally:
        await llm_client.close()
        logger.info("Cleanly closed LLM client.")

    logger.info("RAG corpus ingestion process finished.")


if __name__ == "__main__":
    # Ensure the ingest directory exists
    if not os.path.exists(INGEST_DIR):
        logger.warning(
            f"Ingestion directory '{INGEST_DIR}' not found. Please create it and add JSON templates."
        )
        # Create it to prevent errors if the user runs it without reading the message
        os.makedirs(INGEST_DIR)

    asyncio.run(main())
