
## Template Generation
### Key Components

- **TemplateGenerator**: Core module that orchestrates the template generation process
- **TemplateExamples**: Provides relevant template examples using content analysis
- **TemplateStore**: Stores and retrieves templates using vector similarity
- **Content**: Analyzes template content and creates embeddings
- **OpenAI**: External service used for generating template content and styling 


```mermaid
sequenceDiagram
    actor Client
    participant TemplateGenerator
    participant TemplateExamples
    participant TemplateStore
    participant Content
    participant OpenAI
    
    Client->>TemplateGenerator: create_template(request)
    
    %% Step 1: Find example templates
    TemplateGenerator->>TemplateExamples: get_example(campaign_type, industry)
    TemplateExamples->>Content: analyze_template(search_text)
    Content-->>TemplateExamples: embedding, _
    TemplateExamples->>TemplateStore: find_similar(embedding)
    TemplateStore-->>TemplateExamples: examples
    TemplateExamples-->>TemplateGenerator: examples
    
    %% Step 2: Create system prompt
    TemplateGenerator->>TemplateGenerator: create_system_prompt(request)
    
    %% Step 3: Generate content with OpenAI
    TemplateGenerator->>OpenAI: chat.completions.create(...)
    OpenAI-->>TemplateGenerator: template_dict (JSON response)
    TemplateGenerator->>TemplateGenerator: EmailTemplate.model_validate_json(template_dict)
    
    %% Step 4: Transform content to full template
    TemplateGenerator->>TemplateGenerator: transform_to_metadata(content, request)
    
    %% Sub-steps of transform_to_metadata
    alt creative_mode=True
        TemplateGenerator->>OpenAI: generate_creative_html_content(template)
        OpenAI-->>TemplateGenerator: html_content
        TemplateGenerator->>OpenAI: generate_creative_template_styling()
        OpenAI-->>TemplateGenerator: template_json
    else creative_mode=False
        TemplateGenerator->>TemplateGenerator: generate_html_content(template)
        TemplateGenerator->>TemplateGenerator: generate_template_styling()
    end
    
    %% Asset generation
    TemplateGenerator->>TemplateGenerator: generate_template_assets(template)
    
    %% Final template creation
    TemplateGenerator->>TemplateGenerator: EmailTemplateMetadata(...)
    
    TemplateGenerator-->>Client: EmailTemplateMetadata
```

## Process Breakdown

1. **Request Intake**: Client submits a `TemplateRequest` with parameters like industry, campaign type, tone, and target audience.

2. **Example Identification**:
   - The system searches for relevant template examples based on campaign type and industry
   - Content analysis is performed to find semantic matches
   - Similar templates are retrieved from the TemplateStore (a pgvector database)

3. **Content Generation**:
   - A system prompt is created incorporating example templates
   - OpenAI's API is called to generate the email template content
   - The response is validated and parsed into an `EmailTemplate` object

4. **Template Transformation**:
   - The content is transformed into a complete template with styling and structure
   - If creative mode is enabled, AI generates more personalized HTML and styling
   - Otherwise, standard templating functions are used

5. **Asset Generation**:
   - Template assets (HTML file, thumbnails) are generated
   - A unique template ID is created

6. **Template Return**:
   - A complete `EmailTemplateMetadata` object is returned to the client

