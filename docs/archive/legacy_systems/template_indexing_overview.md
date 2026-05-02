# Template Indexing Process


1. **Data Preparation**: The system reads the JSON file, extracts the template ID from the filename, and prepares the template data structure.

2. **Text Analysis**:
   - Extracts named entities from the template text
   - Classifies the emotional tone of the text
   - Generates text embeddings that represent the semantic content

3. **Image Analysis**:
   - Finds images related to the extracted entities
   - Generates embeddings for each related image
   - Combines multiple image embeddings if necessary

4. **Embedding Combination**: The system combines text and image embeddings to create a unified representation of the template.

5. **Storage**: Finally, the template is stored in the `TemplateStore` with its:
   - Template ID
   - Combined embedding
   - Metadata (including entities, tone analysis, and related image paths)

This indexing process enables powerful template searching and matching capabilities based on both textual and visual content. 


```mermaid
sequenceDiagram
    participant User
    participant Content
    participant TemplateStore
    participant NLP
    participant Images
    
    User->>Content: load_template_from_file(template_path)
    activate Content
    Content->>Content: Read JSON file
    Content->>Content: Extract template_id from filename
    Content->>Content: Prepare template data (subject, body, etc.)
    
    Content->>Content: add_template(template_id, template_data)
    Content->>Content: analyze_template(text, templates_dir)
    
    Content->>NLP: analyze_text(text)
    activate NLP
    NLP->>NLP: extract_entities(text)
    NLP->>NLP: classify_tone(text)
    NLP->>NLP: generate_embedding(text, entities, tone)
    NLP-->>Content: Return text analysis (entities, tone, embedding)
    deactivate NLP
    
    Content->>Images: analyze_images(entities, templates_dir)
    activate Images
    Images->>Images: find_related_images(entities, templates_dir)
    loop For each image
        Images->>Images: generate_embedding(image_path)
    end
    Images-->>Content: Return image analysis results
    deactivate Images
    
    Content->>Content: Combine text and image embeddings
    Content->>Content: Prepare metadata
    
    Content->>TemplateStore: add_template(template_id, embedding, metadata)
    activate TemplateStore
    TemplateStore->>TemplateStore: Store template data
    TemplateStore-->>Content: Template stored confirmation
    deactivate TemplateStore
    
    Content-->>User: Template indexing complete
    deactivate Content

```
