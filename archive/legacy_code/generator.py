import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import HttpUrl

from .content import Content
from .schema import (
    Designer,
    EmailTemplate,
    EmailTemplateMetadata,
    TemplateBodyStyle,
    TemplateContentStyle,
    TemplateJsonData,
    TemplateRequest,
    TemplateWebFont,
)
from .store import TemplateStore

load_dotenv()

# Configure logging (you can later adjust the logging level or handler for production)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TemplateExamples:
    """Template examples using content analysis and vector similarity"""

    def __init__(self):
        self.store = TemplateStore()
        self.content = Content(self.store)

    def get_example(self, request: TemplateRequest) -> List[Dict]:
        """Get relevant examples based on template request parameters"""
        # Create search text with more context from the request
        search_text = (
            f"Find {request.campaign_type} template for {request.industry} industry. "
        )
        search_text += (
            f"Tone: {request.tone}. Target audience: {request.target_audience}. "
        )
        search_text += f"Objective: {request.objective}."

        logger.debug("Searching for examples with text: %s", search_text)

        # Analyze search text
        embedding, _ = self.content.analyze_template(search_text, "data/templates")

        # Find similar templates
        examples = self.store.find_similar(embedding)
        logger.debug("Found %d example(s) with details: %s", len(examples), examples)
        # if score is less that 0.6, log a warning with template_id and score
        for example in examples:
            if example["score"] < 0.6:
                logger.warning(
                    "Template %s has score %f, which is less than 0.6",
                    example["template_id"],
                    example["score"],
                )

        return examples


def create_system_prompt(request: TemplateRequest) -> str:
    """Create a customized system prompt based on the template request"""
    template_examples = TemplateExamples()
    examples = template_examples.get_example(request)

    # Extract styling and structure from the example
    example_template = examples[0] if examples else None
    style_guidance = ""
    if example_template:
        style_guidance = f"""
        Follow the styling and structure of this example template:
        - Theme: {example_template.get("theme", "standard")}
        - Color scheme: {example_template.get("variables", {}).get("primary-theme-color", "default")}
        - Special features: {", ".join(example_template.get("features", []))}
        """

    return f"""You are an expert marketing copywriter specialized in creating email templates 
for the {request.industry} industry. Focus on {request.campaign_type} campaigns with a 
{request.tone} tone that resonates with {request.target_audience}.

The primary objective is to {request.objective}.

{style_guidance}

Example template for reference:
{examples}

Ensure the template:
1. Maintains the specified tone throughout
2. Addresses the target audience's pain points
3. Clearly communicates the value proposition
4. Includes compelling calls-to-action
5. Utilizes appropriate personalization variables
6. Matches the style and structure of the example template

Your response must be a valid JSON object with the following required fields:
- subject: The email subject line
- body: The main email content
- call_to_action: The primary CTA text
- key_benefits: An array of key benefits or selling points
- personalization_variables: An array of variables used in the template
- target_audience: The target audience (use: "{request.target_audience}")
- tone: The tone of the message (use: "{request.tone}")
- theme: The visual theme to apply
- features: Special features to include (e.g., animation, seasonal decorations)
"""


def generate_template(
    request: TemplateRequest, api_key: Optional[str] = None, model: str = "gpt-4-turbo"
) -> EmailTemplate:
    """
    Step 1 of template generation: Generate initial content using AI.
    Creates the basic content structure without styling or HTML formatting.

    Args:
        request: TemplateRequest object containing template parameters
        api_key: OpenAI API key (defaults to OPENAI_API_KEY environment variable)
        model: OpenAI model to use

    Returns:
        EmailTemplate object containing the generated content structure
    """
    client = OpenAI()  # Will automatically use OPENAI_API_KEY from environment

    # Create context string from request
    context = f"""Create a {request.campaign_type} email template for the {request.industry} industry.
Target audience: {request.target_audience}
Tone: {request.tone}
Objective: {request.objective}
"""

    if request.key_features:
        context += "\n\nKey features to highlight:\n" + "\n".join(
            f"- {feature}" for feature in request.key_features
        )

    if request.additional_context:
        context += f"\n\nAdditional context: {request.additional_context}"

    # Create system prompt
    system_prompt = create_system_prompt(request)

    # Make the API call
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ],
        response_format={"type": "json_object"},  # Ensure JSON response
    )

    # Parse the response into EmailTemplate
    template_dict = response.choices[0].message.content
    try:
        return EmailTemplate.model_validate_json(template_dict)
    except Exception as e:
        print("Validation Error occurred. API Response:")
        print(f"Raw template_dict: {template_dict}")
        print(f"Error: {str(e)}")
        raise


def transform_to_metadata(
    template: EmailTemplate, request: TemplateRequest
) -> EmailTemplateMetadata:
    """
    Steps 2-5 of template generation: Transform content into full template.

    Args:
        template: Generated EmailTemplate content
        request: Original TemplateRequest for context

    Returns:
        EmailTemplateMetadata object containing the complete template
    """
    # Decide if we want to use creative generation (assume request.creative_mode exists)
    if getattr(request, "creative_mode", False):
        html_content = generate_creative_html_content(template)
        # You might also want to have LLM-driven styling/asset generation
        template_json = generate_creative_template_styling()  # fallback for now
    else:
        html_content = generate_html_content(template)
        template_json = generate_template_styling()

    # Step 1: Structure Transformation
    metadata = {
        "categories": [request.industry.lower(), request.campaign_type.lower()],
        "collections": "",
        "description": f"A {request.tone.lower()} {request.campaign_type.lower()} template for {request.industry} targeting {request.target_audience}.",
        "short_description": f"{request.campaign_type} template for {request.industry}",
        "template_type": "email",
        "tags": [request.tone.lower(), request.target_audience.lower()],
        "title": f"{request.industry} {request.campaign_type}",
    }

    # Step 4: Asset Generation
    assets = generate_template_assets(template)

    # Combine all components
    return EmailTemplateMetadata(
        **metadata,
        designer=get_default_designer(),
        html_data=html_content,
        html_url=assets["html_url"],
        id=generate_unique_id(),
        json_data=template_json,
        order="0",
        published_at=datetime.now().isoformat(),
        thumbnail_large=assets["thumbnail_large"],
        thumbnail=assets["thumbnail"],
    )


def generate_html_content(
    template: EmailTemplate, example_template: Optional[Dict] = None
) -> str:
    """Generate HTML structure from EmailTemplate content, adapting to example template structure"""
    # Extract structure and features from example if available
    template_structure = {
        "has_animations": False,
        "has_seasonal_decorations": False,
        "layout_type": "standard",
        "special_sections": [],
    }

    if example_template:
        template_structure.update(
            {
                "has_animations": "animated" in example_template.get("categories", []),
                "has_seasonal_decorations": any(
                    cat in example_template.get("categories", [])
                    for cat in ["christmas", "holiday", "seasonal"]
                ),
                "layout_type": example_template.get("layout_type", "standard"),
                "special_sections": example_template.get("special_sections", []),
            }
        )

    # Generate base HTML with conditional features
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{template.subject}</title>
        {generate_animation_styles() if template_structure["has_animations"] else ""}
    </head>
    <body>
        <div class="email-wrapper {template_structure["layout_type"]}">
            {generate_seasonal_decorations() if template_structure["has_seasonal_decorations"] else ""}
            {generate_header_section(template)}
            {generate_main_content_section(template)}
            {generate_footer_section(template)}
        </div>
    </body>
    </html>
    """

    # Apply template variables
    return apply_template_variables(html_content, template)


def generate_template_styling(
    example_template: Optional[Dict] = None,
) -> TemplateJsonData:
    """Generate styling configuration based on example template"""
    # Define the base web font
    web_font = TemplateWebFont(
        fontFamily="Arial, sans-serif",
        name="Arial",
        url="https://fonts.googleapis.com/css2?family=Arial&display=swap",
    )

    # Define body and content styles
    body_style = TemplateBodyStyle(backgroundColor="#ffffff")
    content_style = TemplateContentStyle(
        backgroundColor="#ffffff", color="#000000", width="600px"
    )

    # Create the complete template JSON structure
    template_data = {
        "page": {
            "body": {"default": body_style},
            "content": {"default": content_style},
            "type": "email",
            "webFonts": [web_font],
        },
        "description": "Generated email template",
        "rows": [
            {
                "cells": [
                    {
                        "blocks": [{"type": "text"}],
                        "style": {"default": {"width": "100%"}},
                    }
                ]
            }
        ],
        "template": {"name": "generated_template", "version": "1.0"},
        "title": "Generated Template",
    }

    if example_template:
        # Extract and adapt styles from example
        theme_colors = example_template.get("variables", {})
        if theme_colors:
            content_style.backgroundColor = theme_colors.get(
                "background-color", "#ffffff"
            )
            content_style.color = theme_colors.get("text-color", "#000000")

    return TemplateJsonData(**template_data)


def generate_template_assets(template: EmailTemplate) -> Dict[str, HttpUrl]:
    """Generate template assets based on example template structure"""
    template_id = generate_unique_id()
    base_url = "https://templates.example.com/assets"

    assets = {
        "html_url": HttpUrl(f"{base_url}/{template_id}/preview.html"),
        "thumbnail_large": HttpUrl(f"{base_url}/{template_id}/preview-large.png"),
        "thumbnail": HttpUrl(f"{base_url}/{template_id}/preview-small.png"),
    }

    return assets


def get_default_designer() -> Designer:
    """Return default designer information"""
    return Designer(
        avatar_url="https://example.com/default-avatar.png",
        description="AI Template Generator",
        short_description="AI Generator",
        display_name="Template AI",
        id="template-ai-1",
    )


def generate_unique_id() -> str:
    """Generate a unique template identifier"""
    return f"template-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def create_template(request: TemplateRequest) -> EmailTemplateMetadata:
    """
    Complete template generation workflow.

    Args:
        request: TemplateRequest object containing template parameters

    Returns:
        EmailTemplateMetadata object containing the complete template
    """
    # Step 1: Generate content
    content = generate_template(request)

    # Steps 2-5: Transform to full template
    template = transform_to_metadata(content, request)

    # Step 6: Store template (implement in store.py)
    return template


def generate_animation_styles() -> str:
    """Generate CSS for animated elements"""
    return """
    <style>
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        @keyframes slideIn {
            from { transform: translateY(20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        
        .animate-fade {
            animation: fadeIn ${animation-duration} ease-in-out;
        }
        
        .animate-slide {
            animation: slideIn ${animation-duration} ease-in-out;
        }
    </style>
    """


def generate_seasonal_decorations() -> str:
    """Generate seasonal decoration elements"""
    return """
    <div class="seasonal-decorations">
        <img src="${decoration_top}" class="seasonal-decoration top-left" alt="Decoration">
        <img src="${decoration_bottom}" class="seasonal-decoration bottom-right" alt="Decoration">
    </div>
    """


def generate_header_section(template: EmailTemplate) -> str:
    """Generate the header section of the email"""
    return f"""
    <div class="header">
        <div class="logo-container">
            <img src="${{logo_url}}" alt="Logo" class="logo">
        </div>
        <h1 class="main-title animate-fade">{template.subject}</h1>
    </div>
    """


def generate_main_content_section(template: EmailTemplate) -> str:
    """Generate the main content section of the email"""
    # Format body content into paragraphs
    paragraphs = template.body.split("\n\n")
    formatted_content = "\n".join(
        [
            f'<div class="content-block animate-slide"><p>{p.strip()}</p></div>'
            for p in paragraphs
            if p.strip()
        ]
    )

    # Generate benefits list
    benefits_list = "\n".join(
        [
            f'<li class="benefit-item animate-slide">{benefit}</li>'
            for benefit in template.key_benefits
        ]
    )

    return f"""
    <div class="main-content">
        {formatted_content}
        
        <div class="benefits-block">
            <h2 class="benefits-title">Key Benefits</h2>
            <ul class="benefits-list">
                {benefits_list}
            </ul>
        </div>
        
        <div class="cta-container animate-fade">
            <a href="#" class="cta-button">
                {template.call_to_action}
            </a>
        </div>
    </div>
    """


def generate_footer_section(template: EmailTemplate) -> str:
    """Generate the footer section of the email"""
    return """
    <div class="footer">
        <div class="social-links">
            <a href="${facebook_url}" class="social-icon"><img src="${facebook_icon}" alt="Facebook"></a>
            <a href="${twitter_url}" class="social-icon"><img src="${twitter_icon}" alt="Twitter"></a>
            <a href="${linkedin_url}" class="social-icon"><img src="${linkedin_icon}" alt="LinkedIn"></a>
        </div>
        
        <div class="footer-content">
            <p class="company-info">${company_name}</p>
            <p class="address">${company_address}</p>
            <p class="compliance">${compliance_text}</p>
        </div>
        
        <div class="footer-links">
            <a href="${unsubscribe_url}" class="footer-link">Unsubscribe</a>
            <a href="${preferences_url}" class="footer-link">Update Preferences</a>
        </div>
    </div>
    """


def apply_template_variables(html_content: str, template: EmailTemplate) -> str:
    """Apply template variables to the HTML content"""
    # Default variables that should be available in all templates
    default_vars = {
        "company_name": "${company_name}",
        "company_address": "${company_address}",
        "logo_url": "${logo_url}",
        "unsubscribe_url": "${unsubscribe_url}",
        "preferences_url": "${preferences_url}",
        "compliance_text": "${compliance_text}",
        "facebook_url": "${social.facebook}",
        "twitter_url": "${social.twitter}",
        "linkedin_url": "${social.linkedin}",
        "facebook_icon": "${icons.facebook}",
        "twitter_icon": "${icons.twitter}",
        "linkedin_icon": "${icons.linkedin}",
    }

    # Add template-specific personalization variables
    for var in template.personalization_variables:
        default_vars[var] = "${" + var + "}"

    # Apply all variables to the content
    content = html_content
    for key, value in default_vars.items():
        content = content.replace("${" + key + "}", value)

    return content


def generate_creative_html_content(
    template: EmailTemplate, example_template: Optional[Dict] = None
) -> str:
    """
    Use LLM to generate a creative and personalized HTML layout
    for the email template.
    """
    creative_prompt = f"""
    Given the following email template details:
    Subject: {template.subject}
    Body: {template.body}
    Call to Action: {template.call_to_action}
    And the following creative context based on an example (if provided): {example_template}
    
    Please generate an innovative HTML layout for an email. The design should be creative, 
    incorporate modern aesthetics, and adjust the layout to enhance engagement.
    Provide the complete HTML document.
    """

    client = OpenAI()  # or reuse an existing client instance

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": creative_prompt}],
        response_format={"type": "text"},
    )

    return response.choices[0].message.content


def generate_creative_template_styling(
    example_template: Optional[Dict] = None,
) -> TemplateJsonData:
    """
    Generate creative styling configuration for the template by leveraging LLM responses.
    Prompts the LLM for color palettes and layout suggestions.
    Returns a valid TemplateJsonData object.
    Fallbacks are used if the LLM response does not conform to expected schema.
    """
    prompt = (
        "Provide a JSON object for an email template styling configuration. "
        "The JSON object should adhere to the following schema: "
        "{"
        "  'page': {"
        "      'body': {'default': {'backgroundColor': <string>}}, "
        "      'content': {'default': {'backgroundColor': <string>, 'color': <string>, 'width': <string>}}, "
        "      'type': 'email', "
        "      'webFonts': [{'fontFamily': <string>, 'name': <string>, 'url': <string>}]"
        "  }, "
        "  'description': <string>, "
        "  'rows': [ ... ], "
        "  'template': {'name': <string>, 'version': <string>}, "
        "  'title': <string> "
        "}"
    )

    client = OpenAI()  # Use existing client logic
    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {
                "role": "system",
                "content": "You are an expert in email template design.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )

    creative_styling = response.choices[0].message.content
    try:
        return TemplateJsonData.model_validate_json(creative_styling)
    except Exception as e:
        logger.warning(
            "Creative template styling validation failed, using default styling. Error: %s",
            e,
        )
        return generate_template_styling(example_template)


def generate_dynamic_template_assets(template: EmailTemplate) -> Dict[str, HttpUrl]:
    """
    Dynamically select template assets like thumbnail and html_url based on creative context.
    Uses LLM-driven hints to determine the most appropriate assets.
    Falls back to deterministic defaults if necessary.
    """
    try:
        prompt = (
            f"Based on the following template details: "
            f"Subject: {template.subject}, Tone: {template.tone}, Campaign: {template.call_to_action}, "
            f"select appropriate asset URLs for html_url, thumbnail_large, and thumbnail from our media repository. "
            f"Provide a JSON object with keys 'html_url', 'thumbnail_large', and 'thumbnail'."
        )

        client = OpenAI()  # or reuse the existing client instance
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert in media asset selection.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        assets = response.choices[0].message.content
        # Validate required keys:
        if not all(
            key in assets for key in ["html_url", "thumbnail_large", "thumbnail"]
        ):
            raise ValueError("Missing keys in creative asset selection.")

        return {
            "html_url": HttpUrl(assets["html_url"]),
            "thumbnail_large": HttpUrl(assets["thumbnail_large"]),
            "thumbnail": HttpUrl(assets["thumbnail"]),
        }
    except Exception as e:
        logger.warning(
            "Dynamic asset generation failed, using default assets. Error: %s", e
        )
        return generate_template_assets(template)


# Example usage/ testing
if __name__ == "__main__":
    request = TemplateRequest(
        industry="Technology",
        brand_name="Experiture",
        campaign_type="Sales Outreach",
        target_audience="IT Decision Makers",
        tone="Professional",
        objective="Book product demos",
        key_features=["AI-powered automation", "Enterprise security", "24/7 support"],
        custom_variables=["first_name", "company", "role"],
        additional_context="Focus on ROI and time savings",
        creative_mode=True,
    )

    # Create filename from objective and timestamp
    filename = (
        f"data/tmp/book_product_demos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    # Generate template
    template = create_template(request)

    # Create tmp directory if it doesn't exist
    os.makedirs("data/tmp", exist_ok=True)

    # Write template to file
    with open(filename, "w") as f:
        f.write(template.model_dump_json(indent=2))

    print(f"Template written to: {filename}")
