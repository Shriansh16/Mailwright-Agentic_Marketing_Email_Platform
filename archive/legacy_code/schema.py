from dotenv import load_dotenv

load_dotenv()

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, HttpUrl

"""
Template Schema Definitions

This module defines two primary schema types:
1. EmailTemplate: Used for initial AI content generation
2. EmailTemplateMetadata: Used for final template storage and rendering

The typical workflow is:
1. Generate content using EmailTemplate
2. Transform content into EmailTemplateMetadata with styling and structure
3. Store the complete template in the template store
"""


class EmailTemplate(BaseModel):
    """
    Core template content structure - used for initial AI generation.
    This is the intermediate format before full template compilation.

    Workflow:
    1. AI generates content using this schema
    2. Content is transformed into EmailTemplateMetadata
    3. Final template is stored with full styling and structure
    """

    subject: str = Field(..., description="The email subject line")
    body: str = Field(..., description="The main body of the email")
    call_to_action: str = Field(..., description="The primary call-to-action text")
    target_audience: str = Field(..., description="Description of the target audience")
    tone: str = Field(
        ..., description="The tone of the email (e.g., professional, friendly, urgent)"
    )
    key_benefits: List[str] = Field(
        ..., description="List of key benefits or selling points"
    )
    personalization_variables: Optional[List[str]] = Field(
        default=[],
        description="Variables that can be used for personalization (e.g., {first_name}, {company})",
    )


class Designer(BaseModel):
    """
    Information about the template designer.
    Includes profile details and identification.
    """

    avatar_url: HttpUrl = Field(..., description="URL to designer's avatar image")
    description: str = Field(..., description="Detailed description of the designer")
    short_description: str = Field("", description="Brief description of the designer")
    display_name: str = Field(..., description="Designer's display name")
    id: str = Field(..., description="Unique identifier for the designer")


class TemplateWebFont(BaseModel):
    """
    Web font configuration for the template.
    Defines the fonts used in the email template.
    """

    fontFamily: str = Field(..., description="CSS font-family definition")
    name: str = Field(..., description="Font name")
    url: HttpUrl = Field(..., description="URL to font resource")


class TemplateBodyStyle(BaseModel):
    """
    Styling configuration for the template body.
    Defines the visual appearance of the template container.
    """

    backgroundColor: str = Field(..., description="Background color")


class TemplateContentStyle(BaseModel):
    """
    Styling configuration for the template content.
    Defines the visual appearance of the content area.
    """

    backgroundColor: Optional[str] = Field(None, description="Background color")
    backgroundImage: Optional[str] = Field(None, description="Background image URL")
    backgroundPosition: Optional[str] = Field(None, description="Background position")
    backgroundRepeat: Optional[str] = Field(
        None, description="Background repeat setting"
    )
    color: Optional[str] = Field(None, description="Text color")
    width: Optional[str] = Field(None, description="Content width")


class TemplatePageProperties(BaseModel):
    """
    Page-level properties for the template.
    Defines the overall structure and styling of the template.
    """

    body: Dict[str, TemplateBodyStyle] = Field(..., description="Body styles")
    content: Dict[str, Union[TemplateContentStyle, Dict[str, str]]] = Field(
        ..., description="Content styles and computed styles"
    )
    type: str = Field(..., description="Page property type")
    webFonts: List[TemplateWebFont] = Field(
        ..., description="Web fonts used in template"
    )


class TemplateJsonData(BaseModel):
    """
    Complete template configuration data.
    Contains all styling, structure, and content definitions.
    """

    page: TemplatePageProperties = Field(..., description="Page properties and styling")
    description: str = Field("", description="Template description")
    rows: List[Dict[str, Any]] = Field(..., description="Template row definitions")
    template: Dict[str, str] = Field(..., description="Template metadata")
    title: str = Field("", description="Template title")


class TemplateRequest(BaseModel):
    """
    Structured request for template generation.
    Contains parameters that guide the template creation process.
    """

    industry: str = Field(
        ...,
        description="Industry or business sector (e.g., 'Technology', 'Healthcare')",
    )
    brand_name: str = Field(..., description="Name of the brand")
    campaign_type: str = Field(
        ...,
        description="Type of email campaign (e.g., 'Newsletter', 'Sales Outreach', 'Product Launch')",
    )
    target_audience: str = Field(..., description="Specific audience segment to target")
    tone: str = Field(
        ...,
        description="Desired tone of the email (e.g., 'Professional', 'Casual', 'Urgent')",
    )
    objective: str = Field(
        ...,
        description="Primary goal of the email (e.g., 'Book Demo', 'Drive Sales', 'Increase Engagement')",
    )
    key_features: Optional[List[str]] = Field(
        default=None, description="Key product/service features to highlight"
    )
    custom_variables: Optional[List[str]] = Field(
        default=None, description="Custom personalization variables"
    )
    additional_context: Optional[str] = Field(
        default=None, description="Any additional context or requirements"
    )
    creative_mode: bool = Field(
        default=False, description="Whether to use creative mode"
    )


class EmailTemplateMetadata(BaseModel):
    """
    Final template format for storage and rendering.
    This is the complete schema that includes all styling, structure, and metadata
    needed for template storage and delivery.

    This schema matches the JSON structure in the template store and includes:
    - Template metadata (categories, descriptions, etc.)
    - Designer information
    - Complete HTML content
    - Styling configuration (TemplateJsonData)
    - Asset URLs (thumbnails, etc.)
    """

    categories: List[str] = Field(..., description="Categories the template belongs to")
    collections: str = Field("", description="Collections the template belongs to")
    description: str = Field(..., description="Detailed description of the template")
    short_description: str = Field(..., description="Brief description of the template")
    designer: Designer = Field(
        ..., description="Information about the template designer"
    )
    html_data: str = Field(..., description="Raw HTML content of the template")
    html_url: HttpUrl = Field(..., description="URL to the template's HTML file")
    id: str = Field(..., description="Unique identifier for the template")
    json_data: TemplateJsonData = Field(..., description="Template configuration data")
    order: str = Field(..., description="Template ordering value")
    published_at: str = Field(..., description="Publication date")
    tags: List[str] = Field(..., description="Tags associated with the template")
    template_type: str = Field(..., description="Type of template (e.g., 'email')")
    thumbnail_large: HttpUrl = Field(..., description="URL to large thumbnail image")
    thumbnail: HttpUrl = Field(..., description="URL to standard thumbnail image")
    title: str = Field(..., description="Template title")
