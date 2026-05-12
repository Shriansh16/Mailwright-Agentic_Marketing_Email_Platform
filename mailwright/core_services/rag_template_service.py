import logging
import json
import re
from typing import List, Dict, Any

from bs4 import BeautifulSoup, NavigableString
from langchain_core.prompts import ChatPromptTemplate
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from mailwright.config import settings
from mailwright.core_services.llm_factory import get_configured_chat_model
from mailwright.db.models import RAGTemplate

logger = logging.getLogger(__name__)


def _extract_editable_content(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Parses the BeautifulSoup object to find editable text and styles.
    It adds temporary IDs directly to the tags in the soup object for reliable injection later.
    Returns a structured "content map" to be sent to the LLM.
    """
    content_map = {"text_elements": [], "style_elements": []}
    
    # --- Text Extraction: Find all non-empty NavigableString objects ---
    text_element_id_counter = 0
    # Find all text nodes in the document
    for text_node in soup.find_all(string=True):
        # Filter out whitespace, script/style content, and very short strings
        if (isinstance(text_node, NavigableString) and 
            text_node.parent.name not in ['script', 'style'] and 
            len(text_node.strip()) > 1):
            
            parent_tag = text_node.parent
            temp_id = f"mailwright-text-{text_element_id_counter}"
            
            # Add a temporary ID to the parent tag for later injection
            parent_tag['data-mailwright-temp-id'] = temp_id
            
            content_map["text_elements"].append({
                "id": temp_id,
                "tag": parent_tag.name,
                "current_text": text_node.strip()
            })
            text_element_id_counter += 1

    # --- Style Extraction: Both from <style> blocks and inline styles ---
    style_element_id_counter = 0
    
    # Part 1: Extract from <style> blocks
    for style_tag in soup.find_all("style"):
        style_content = style_tag.string or ""
        # Regex to find selectors and their properties
        rule_matches = re.finditer(r'([^{]+)\s*\{([^}]+)\}', style_content, re.DOTALL)
        for match in rule_matches:
            selectors = match.group(1).strip()
            declarations = match.group(2).strip()
            
            # Find all color properties within the rule block
            color_matches = re.finditer(r'(color|background-color)\s*:\s*([^;]+);?', declarations)
            for color_match in color_matches:
                prop = color_match.group(1).strip()
                value = color_match.group(2).strip()
                
                temp_id = f"mailwright-style-{style_element_id_counter}"
                content_map["style_elements"].append({
                    "id": temp_id,
                    "selector": selectors, # The CSS selector (e.g., '.bee-button')
                    "property": prop,
                    "current_value": value
                })
                style_element_id_counter += 1

    # Part 2: Extract from inline style attributes
    for tag in soup.find_all(style=True):
        style = tag.get("style", "")
        color_matches = re.finditer(r'(color|background-color)\s*:\s*([^;]+)', style)
        for color_match in color_matches:
            prop = color_match.group(1).strip()
            value = color_match.group(2).strip()
            
            temp_id = f"mailwright-style-inline-{style_element_id_counter}"
            tag['data-mailwright-temp-id-inline'] = temp_id
            
            content_map["style_elements"].append({
                "id": temp_id,
                "selector": f"inline-{tag.name}-{style_element_id_counter}", # A synthetic selector for context
                "property": prop,
                "current_value": value
            })
            style_element_id_counter += 1
            
    return content_map


def _inject_content(soup: BeautifulSoup, updated_content_map: Dict[str, Any]) -> str:
    """
    Injects the modified text and styles from the LLM back into the BeautifulSoup object
    using the temporary IDs. Cleans up the temporary IDs before returning the final HTML string.
    """
    # --- Inject Text ---
    if "text_elements" in updated_content_map:
        for element in updated_content_map["text_elements"]:
            tag_to_update = soup.find(attrs={"data-mailwright-temp-id": element["id"]})
            if tag_to_update and "new_text" in element and tag_to_update.string and isinstance(tag_to_update.string, NavigableString):
                tag_to_update.string.replace_with(element["new_text"])

    # --- Inject Styles ---
    if "style_elements" in updated_content_map:
        style_updates = {el['id']: el for el in updated_content_map['style_elements'] if 'new_value' in el}

        # Part 1: Update <style> block
        for style_tag in soup.find_all("style"):
            original_style_content = style_tag.string or ""
            modified_style_content = original_style_content
            
            for style_id, element in style_updates.items():
                if not style_id.startswith("mailwright-style-inline-"):
                    selector = re.escape(element['selector'])
                    prop = re.escape(element['property'])
                    old_val = re.escape(element['current_value'])
                    new_val = element['new_value']
                    # A regex to safely replace the style property inside its rule block
                    # This is complex because a selector can appear multiple times.
                    # This simplified version will work for many cases but isn't a full CSS parser.
                    modified_style_content = re.sub(
                        f'({selector}[^{{}}]*{{[^{{}}]*?){prop}\\s*:\\s*{old_val}',
                        f'\\g<1>{prop}: {new_val}',
                        modified_style_content
                    )
            style_tag.string.replace_with(modified_style_content)

        # Part 2: Update inline styles
        for element_id, element in style_updates.items():
             if element_id.startswith("mailwright-style-inline-"):
                tag_to_update = soup.find(attrs={"data-mailwright-temp-id-inline": element_id})
                if tag_to_update:
                    style_str = tag_to_update.get("style", "")
                    style_dict = {k.strip(): v.strip() for k, v in (item.split(':', 1) for item in style_str.split(';') if ':' in item)}
                    style_dict[element["property"]] = element["new_value"]
                    new_style_str = "; ".join([f"{k}: {v}" for k, v in style_dict.items()]) + ";"
                    tag_to_update["style"] = new_style_str


    # --- Cleanup Temporary IDs ---
    for tag in soup.find_all(attrs={"data-mailwright-temp-id": True}):
        del tag["data-mailwright-temp-id"]
    for tag in soup.find_all(attrs={"data-mailwright-temp-id-inline": True}):
        del tag["data-mailwright-temp-id-inline"]
        
    return str(soup)


class RAGTemplateService:
    """
    This service encapsulates the core logic for the RAG (Retrieval-Augmented Generation)
    workflow. It handles generating fingerprints from briefs, finding matching templates
    in the corpus, and populating those templates with content.
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        # Use the factory to get the correctly configured chat model for RAG
        self.chat_model = get_configured_chat_model(
            task_provider_config_value=settings.RAG_GENERATION_PROVIDER,
            task_openai_model_config_value=settings.RAG_GENERATION_OPENAI_MODEL,
            task_anthropic_model_config_value=settings.RAG_GENERATION_ANTHROPIC_MODEL,
        )
        # Create a dedicated client for OpenAI embeddings
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set for embedding client.")
        self.embedding_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def generate_fingerprint_for_brief(self, brief: str) -> str:
        """
        Uses an LLM to convert a user's plain-text brief into a structural fingerprint
        that is consistent with the fingerprints generated from HTML templates.
        """
        logger.info("Generating fingerprint for the user brief...")

        system_prompt = """
You are a meticulous and hyper-literal Structural Analyst AI. Your sole purpose is to convert a user's natural language description of a webpage layout into a standardized, single-line "Structural Fingerprint."

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
* **Input is Natural Language:** You will be given a user's brief describing a template. Your job is to parse this description to identify the structure.
* **Separation of Concerns:** The fingerprint is divided into two parts by the `::CONTENT>>` separator.
    *   The part **before** the separator is the **Structural Fingerprint**. It MUST be purely structural and content-agnostic, based on the layout description.
    *   The part **after** the separator is the **Content Suffix**. It is derived by analyzing the *thematic content* of the brief.
* **No Explanations:** Do NOT output any text, explanation, or commentary. Your entire response must be ONLY the fingerprint string itself.
* **Top-Down Order:** Always analyze the template from top to bottom as described in the brief, preserving the section order for the structural part.

**4. THE CONTENT SUFFIX (DERIVED FROM BRIEF):**
After generating the structural fingerprint from the layout description, you MUST append the exact separator ` ::CONTENT>> ` followed by a content summary derived *from the user's brief*.

* **Format:** The suffix must follow this format: `categories:inferred-tag1,inferred-tag2; summary:a-kebab-cased-summary-of-the-brief`
* **Instructions:**
    1.  Read the entire brief and infer 2-4 thematic categories (e.g., `media-entertainment`, `product-launch`, `holiday`, `e-commerce`). List these as comma-separated `kebab-case` tags.
    2.  Generate a concise, descriptive summary of the brief's theme (about 5-10 words).
    3.  Convert this summary to `kebab-case`.
"""
        try:
            prompt = ChatPromptTemplate.from_messages(
                [("system", system_prompt), ("user", "{input}")]
            )
            chain = prompt | self.chat_model
            response = await chain.ainvoke({"input": brief})
            fingerprint = response.content
            logger.info(f"Successfully generated fingerprint for brief: {fingerprint}")
            return fingerprint
        except Exception as e:
            logger.error(f"Failed to generate fingerprint for brief: {e}")
            return ""

    async def generate_embedding(self, text_to_embed: str) -> List[float]:
        """
        Generates a vector embedding for a given text string.
        """
        if not text_to_embed:
            logger.warning("No text provided to generate embedding. Returning empty list.")
            return []
        try:
            logger.info("Calling OpenAI to generate embedding for text...")
            embedding_response = await self.embedding_client.embeddings.create(
                input=text_to_embed,
                model=settings.EMBEDDING_MODEL_NAME,
            )
            embedding = embedding_response.data[0].embedding
            logger.info(f"Successfully generated embedding of dimension {len(embedding)}.")
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return []

    async def find_best_matching_template(
        self, brief_embedding: List[float], use_placeholders: bool = True
    ) -> str:
        """
        Finds the best matching template from the RAG corpus using vector similarity search
        and returns either the raw or processed HTML based on the use_placeholders flag.
        """
        if not brief_embedding:
            logger.warning(
                "Brief embedding is empty. Cannot find a matching template."
            )
            return ""

        try:
            # Use l2_distance for similarity search; you can also try cosine_distance
            # The order_by clause sorts the results by their distance to the input vector
            stmt = (
                select(RAGTemplate)
                .order_by(RAGTemplate.fingerprint_embedding.l2_distance(brief_embedding))
                .limit(1)
            )
            result = await self.db_session.execute(stmt)
            best_match = result.scalars().first()

            if best_match:
                logger.info(
                    f"Found best matching template: ID {best_match.id} ('{best_match.template_name}')"
                )
                if use_placeholders:
                    logger.info("Returning processed HTML with placeholders.")
                    return best_match.processed_html
                else:
                    logger.info("Returning raw HTML with original media.")
                    return best_match.raw_html
            else:
                logger.warning("No matching templates found in the RAG corpus.")
                return ""
        except Exception as e:
            logger.error(f"Error finding best matching template: {e}", exc_info=True)
            return ""

    async def populate_template_with_brief(self, template_html: str, brief: str) -> str:
        """
        Uses a multi-step, component-based approach to populate the template.
        1. Extract: Parses the HTML to find editable text/styles and creates a "content map".
        2. Modify: Sends this lightweight JSON map (not the HTML) to an LLM to get updated content.
        3. Inject: Uses the LLM's response to precisely inject content back into the HTML structure.
        """
        logger.info("Starting component-based template population...")

        # 1. Extract content and get a traversable soup object
        try:
            soup = BeautifulSoup(template_html, "html.parser")
            content_map = _extract_editable_content(soup)
            
            if not content_map["text_elements"] and not content_map["style_elements"]:
                logger.warning("Could not extract any editable content from the template. Returning original.")
                return template_html
            logger.info(f"Extracted {len(content_map['text_elements'])} text elements and {len(content_map['style_elements'])} style elements.")
        except Exception as e:
            logger.error(f"Failed during HTML content extraction: {e}", exc_info=True)
            return template_html

        # 2. Modify content using the LLM
        system_prompt = """
You are a Content Adaptation Specialist AI. Your task is to intelligently map content from a user's brief to a structured JSON object representing an HTML template's content.

**Rules:**
1.  **Analyze the Brief:** Read the user's brief to understand the core message, tone, and key pieces of information (headlines, calls-to-action, etc.).
2.  **Map to JSON:** You will be given a JSON object with `text_elements` and `style_elements`. Your goal is to add new values to them that reflect the brief.
3.  **Create New Text:** For each object in `text_elements`, use its `current_text` as context. Add a `new_text` field containing the most appropriate content from the brief.
4.  **Create New Styles:** For each object in `style_elements`, use its `current_value` as context. Analyze the brief's theme (e.g., "professional," "playful," "urgent") and add a `new_value` field with a more appropriate color code.
5.  **Do Not Modify Original Data:** You MUST NOT change the original `id`, `tag`, `current_text`, `property`, or `current_value` fields. Only add `new_text` and `new_value`.
6.  **Return JSON Only:** Your entire response MUST be only the updated JSON object. Do not include explanations or markdown. Ensure the JSON is valid.
7.  **Completeness:** You must return the full JSON object with all original elements, adding `new_text` or `new_value` to each one.
"""
        user_prompt_template = """
**User Brief:**
{brief}

**Content Map from HTML Template:**
```json
{content_map_json}
```

Please add a `new_text` field to each text element and a `new_value` field to each style element based on the user brief. Return the complete JSON object.
"""
        try:
            prompt = ChatPromptTemplate.from_messages(
                [("system", system_prompt), ("user", user_prompt_template)]
            )
            chain = prompt | self.chat_model
            
            content_map_str = json.dumps(content_map, indent=2)
            
            logger.info("Sending content map to LLM for modification...")
            response = await chain.ainvoke({"brief": brief, "content_map_json": content_map_str})
            
            # The response is often wrapped in ```json ... ```, so we extract it.
            response_content = response.content
            match = re.search(r'```json\n(.*)\n```', response_content, re.DOTALL)
            json_string = match.group(1) if match else response_content

            updated_content_map = json.loads(json_string)
            logger.info("Successfully received and parsed updated content map from LLM.")

        except Exception as e:
            logger.error(f"Failed during LLM content modification: {e}", exc_info=True)
            # Fallback to the old method if the new one fails
            return await self.populate_template_with_brief_legacy(template_html, brief)

        # 3. Inject content back into the HTML
        try:
            final_html = _inject_content(soup, updated_content_map)
            logger.info("Successfully injected updated content into the template.")
            return final_html
        except Exception as e:
            logger.error(f"Failed during content injection: {e}", exc_info=True)
            return template_html # Return original template on injection failure

    async def populate_template_with_brief_legacy(self, template_html: str, brief: str) -> str:
        """
        The original method of populating the template. Kept as a fallback.
        """
        logger.info("Falling back to legacy template population method...")
        system_prompt = """
You are an expert Content and Style Integration AI. Your task is to take a user's currently incompatable plain-text brief, extract the main content, and rewrite it to work with the existing HTML template, then intelligently populate and style the template to create a final, complete HTML document.

You must adhere to the following rules:

1.  **Structural Integrity is Paramount:** You MUST NOT alter the HTML structure of the template. This means no adding, deleting, or reordering `<table>`, `<tr>`, `<td>`, or `<div>` elements. Your only job is to modify the *content and styling* within the existing structure.
    If there is any conflict between the brief and template, you MUST prioritize sticking to the template. Make the brief fit the template, not the other way around. Identify conflicts ahead of time betwwen the brief and template.

2.  **Content Population:**
    *   Carefully read the user's brief to understand the key messages, headlines, body copy, and calls-to-action. Mold the content in the brief to fit the template, not the other way around.
    *   Replace the text with the corresponding content from the brief. Match content to its likely location (e.g., a short, bolded phrase in the brief is likely a headline).
    *   For `<img>` tags with `placehold.co` links, write a descriptive `alt` text based on the brief's content. **DO NOT change the `src` attribute.**
    *   For video placeholders, replace the generic text with a descriptive title from the brief.

3.  **Styling Adjustments (Colors & Fonts):**
    *   Analyze the theme and tone of the user's brief (e.g., "dark and scary," "light and professional," "playful and vibrant").
    *   You ARE PERMITTED to change inline `style` attributes related to `color`, `background-color`, and `font-family` to better match the brief's theme.
    *   **Example:** If the brief is for a luxury brand, you might change a default `font-family` to `'Times New Roman', Times, serif`. If it's for a Halloween event, you might change a blue `background-color` to a dark gray like `#1c1c1c`.
    *   You MUST NOT change layout-related styles like `width`, `padding`, `margin`, or `display`.

4.  **Final Output:** Your entire output MUST be only the final, populated and re-styled HTML code. Do not include any commentary, explanations, or markdown formatting like ```html.
"""
        user_prompt_template = """
**User Brief to rewrite:**
{brief}

**HTML Template to Populate:**
```html
{template_html}
```

Populate the template now based on the rules.
"""
        try:
            prompt = ChatPromptTemplate.from_messages(
                [("system", system_prompt), ("user", user_prompt_template)]
            )
            chain = prompt | self.chat_model
            response = await chain.ainvoke({"brief": brief, "template_html": template_html})
            final_html = response.content
            logger.info("Successfully populated template with brief content (legacy method).")
            return final_html
        except Exception as e:
            logger.error(f"Failed to populate template with legacy method: {e}", exc_info=True)
            return template_html