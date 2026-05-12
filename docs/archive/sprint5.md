# Sprint 5: RAG-Based Template Generation

**Overall Goal:** Implement a new "retrieve-and-modify" workflow that leverages a corpus of existing HTML templates to generate marketing emails. This will be a parallel workflow to the existing from-scratch MJML generation system. **This new workflow will generate HTML directly, bypassing MJML entirely.**

**Key Context:**
*   **Current Branch:** `sprint5` 
*   **Existing System:** LangGraph-based MJML generation workflow with PostgreSQL persistence
*   **Template Corpus:** 1600+ JSON templates in `/templates` directory with structure: `{description, categories, tags, json_data, html_data}`
*   **Database:** PostgreSQL with existing `template_versions` and `checkpoints` tables
*   **Embedding Model:** `text-embedding-3-small` (1536 dimensions)
*   **Vector DB:** `pgvector` extension within existing PostgreSQL instance

---

## Phase 1: Foundation - The Corpus Ingestion System
*Goal: Create a fully indexed and searchable vector store of the existing 1600+ templates, ready for use by the application.*

**Tasks:**

1.  **Database Setup & Migration:**
    *   **1.1. Create `RAGTemplate` Model:** [DONE] First, define the new `RAGTemplate` model in `mailwright/db/models.py` with:
        *   `template_id` (String, Primary Key) - matches filename without .json extension
        *   `layout_vector` (Vector(1536)) - for structural/layout similarity
        *   `content_vector` (Vector(1536)) - for content/semantic similarity  
        *   `structural_fingerprint` (Text) - human-readable layout description
        *   `content_description` (Text) - stores original template description
        *   `placeholder_json` (JSONB) - modified json_data with placeholders
        *   `original_categories` (JSONB) - stores categories array from template
        *   `original_tags` (JSONB) - stores tags array from template
    *   **1.2. Generate Alembic Migration:** [DONE] Run `alembic revision --autogenerate -m "Add RAG templates table and modify template_versions"` to auto-generate migration
    *   **1.3. Modify Migration:** [DONE] Edit the generated migration to:
        *   Add `op.execute("CREATE EXTENSION IF NOT EXISTS vector;")` at the top
        *   Ensure `template_versions.mjml_source` is altered to `nullable=True`
    *   **1.4. Apply Migration:** [DONE] Run `alembic upgrade head` to apply changes

2.  **Configuration:**
    *   **2.1. Update `mailwright/config.py`:** [DONE] Add a new setting: `EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"`.

3.  **Corpus Pre-processing & Ingestion Script:**
    *   **3.1. Create Ingestion Service:** [DONE] Develop `mailwright/core_services/corpus_ingestion_service.py` with:
        *   [DONE] `CorpusIngestionService` class with dependency injection for database and OpenAI client
        *   [DONE] Method to generate structural fingerprint from `json_data` (analyze layout structure)
        *   [DONE] Method to create placeholder JSON (replace text/images with `{{placeholder_name}}`)
        *   Method to generate embeddings using OpenAI's `text-embedding-3-small`
        *   Method to batch insert processed templates into `rag_templates` table
    *   **3.2. Structural Fingerprint Logic (EXPANDED SCOPE):** [DONE] The implementation must go beyond simple element counting. It must parse the `json_data` to understand the template's high-level structure and element hierarchy.
        *   **Goal:** Generate a human-readable but structurally significant string.
        *   **Example Output:** `"[header-section] [hero-image] [2-col-product-feature] [cta-button] [footer-social]"`
        *   **Implementation:** This will require recursively walking the JSON tree and mapping common structural patterns (e.g., a row with a single image module) to semantic section labels.
    *   **3.3. Placeholder Generation Logic (EXPANDED SCOPE):** [DONE] The implementation must generate intelligent, semantic placeholders instead of generic, numbered ones.
        *   **Goal:** Provide the downstream LLM with clear context about what kind of content to generate for each placeholder.
        *   **Example Output:** `{{headline_hero}}`, `{{product_image_1}}`, `{{cta_button_text}}`, `{{footer_disclaimer_text}}`
        *   **Implementation:** This will require analyzing the styling and context of each text or image element within the JSON (e.g., font size, weight, parent module type) to infer its semantic purpose.
    *   **3.4. Embedding Logic:** Generate vectors for:
        *   **Layout Vector:** Embed the new, more sophisticated structural fingerprint text.
        *   **Content Vector:** Embed the original template description.
    *   **3.5. Main Ingestion Script:** Create `scripts/ingest_corpus.py` that:
        *   Connects to database using existing connection patterns
        *   Iterates through all `.json` files in `/templates` directory
        *   For each template: loads JSON, processes via IngestionService, stores in database
        *   Includes progress logging and error handling
        *   Can be run multiple times safely (upsert behavior)

**Phase 1 - Definition of Done:**
*   A new Alembic migration is created and applied.
*   The `rag_templates` table exists in the database and is populated with data for all 1600+ templates.
*   The ingestion script is reusable and checked into the repository.
*   The `template_versions` table schema is updated.

---

## Phase 2: Application - The RAG Workflow
*Goal: Build the new LangGraph workflow and API endpoints that use the ingested corpus to generate templates based on user selection.*

**Tasks:**

1.  **Template Retrieval Service:**
    *   **1.1. Create `TemplateRetrieverService`:** Develop `mailwright/core_services/template_retriever_service.py`.
    *   **1.2. Implement Hybrid Search:** The service will contain the logic to take a user brief, embed it, and perform a hybrid search against the `rag_templates` table using `pgvector`. It will filter on metadata and then perform vector similarity search on the appropriate vector (`layout_vector` or `content_vector`).

2.  **New API Endpoints & Schemas:**
    *   **2.1. Define Schemas:** In `mailwright/schemas/template_schemas.py`, create new Pydantic models:
        *   `LayoutRetrievalResponse`: A list of candidate templates (id, description, thumbnail).
        *   `LayoutSelectionRequest`: The ID of the template the user selected.
    *   **2.2. Create New Router:** Create a new file `mailwright/api/v1/layout_routes.py`.
    *   **2.3. `POST /api/v1/layouts/retrieve` Endpoint:** This endpoint will take a `UserBriefSchema`, use the `TemplateRetrieverService` to find top matching layouts, and return them. This does *not* start a graph.

3.  **New LangGraph Workflow (RAG Branch):**
    *   **3.1. Create `rag_generation_graph.py`:** Create a new graph definition file.
    *   **3.2. `POST /api/v1/layouts/generate` Endpoint:** This endpoint will take a `LayoutSelectionRequest`. It will initiate the new RAG graph, passing the selected template ID and original user brief into the initial `GraphState`.
    *   **3.3. Define New Graph Nodes:**
        *   `LG_LoadSelectedTemplateNode`: Fetches the `placeholder_json` for the selected template from the DB and loads it into the state.
        *   `LG_ContentModificationNode`: Prompts an LLM to fill the placeholders in the JSON based on the user brief. **Crucially, the LLM will be prompted to output a JSON diff/object of the changes, not the entire modified JSON.** A Python function will then apply this diff to the `placeholder_json` in the state.
        *   `LG_HTMLCompilationNode`: Takes the modified `json_data` and uses an LLM to compile it into **final, responsive HTML, without an intermediate MJML step.** The prompt will include an example from the original template's `json_data` and `html_data` for few-shot learning.
        *   `LG_StoreRAGVersionNode`: An adapted version of `LG_StoreV0Node`. It saves the final generated HTML to the `template_versions` table. The `mjml_source` column for this entry will be `NULL`.

**Phase 2 - Definition of Done:**
*   User can submit a brief to a new endpoint and receive a list of relevant layouts.
*   User can select a layout to trigger a new LangGraph workflow.
*   The workflow successfully modifies the selected template's content based on the brief and compiles it to HTML.
*   The final HTML is versioned and stored in the database, viewable via the existing preview endpoints.
*   The new workflow is covered by integration tests.

---

## Test-Driven Development Plan

**Current Test Structure Analysis:**
*   **API Tests:** `tests/api/v1/test_template_routes.py` (1154 lines) - Comprehensive coverage of existing template generation endpoints
*   **Unit Tests:** Individual service tests for all core services (brief analyzer, image generator, MJML service, etc.)
*   **Integration Tests:** `tests/integration/test_template_generation_graph.py` (1507 lines) - Full graph workflow testing
*   **Test Configuration:** `conftest.py` with proper database setup, migrations, and cleanup

**Testing Requirements for Sprint 5:**

### Phase 1 Testing:
1.  **Database Migration Tests:**
    *   **New Test:** `tests/unit/test_migrations.py` - Test that the new migration creates `rag_templates` table correctly and enables `pgvector` extension
    *   **Update Required:** `conftest.py` - Add `rag_templates` to the `tables_to_clear` list in `clear_tables_between_tests`

2.  **Corpus Ingestion Service Tests:**
    *   **New Test:** `tests/unit/test_corpus_ingestion_service.py` - Unit tests for:
        *   Structural fingerprint generation
        *   Placeholder generation logic
        *   Embedding generation
        *   Database insertion logic
    *   **New Test:** `tests/integration/test_corpus_ingestion.py` - Integration test for the full ingestion script

3.  **Template Retriever Service Tests:**
    *   **New Test:** `tests/unit/test_template_retriever_service.py` - Unit tests for:
        *   Vector similarity search
        *   Hybrid search functionality
        *   Query embedding and matching

### Phase 2 Testing:
1.  **New API Endpoint Tests:**
    *   **New Test:** `tests/api/v1/test_layout_routes.py` - Test the new RAG endpoints:
        *   `POST /api/v1/layouts/retrieve` - Template retrieval
        *   `POST /api/v1/layouts/generate` - RAG workflow initiation
        *   Status checking for RAG workflows

2.  **RAG Graph Integration Tests:**
    *   **New Test:** `tests/integration/test_rag_generation_graph.py` - Full RAG workflow testing:
        *   Template loading from database
        *   Content modification based on user brief
        *   HTML compilation
        *   Storage in `template_versions` with `mjml_source=NULL`
        *   Error handling and edge cases

3.  **Modified Existing Tests:**
    *   **Update Required:** `tests/unit/test_template_store.py` - Update tests to handle nullable `mjml_source` column
    *   **Update Required:** `tests/api/v1/test_template_routes.py` - Ensure existing tests still pass with modified database schema

### Test Data Requirements:
*   **New Test Data:** Sample JSON templates for testing ingestion and retrieval
*   **New Fixtures:** RAG-specific fixtures for template selection and modification testing
*   **Mock Data:** Embedding vectors and similarity scores for predictable test results

### Testing Strategy Notes:
*   All new services must have unit tests before integration
*   Database operations must be tested with both success and failure scenarios
*   RAG workflow must be tested with various template types and user briefs
*   Performance testing for vector similarity search (optional for MVP)
*   Backward compatibility testing to ensure existing MJML workflow remains unaffected

### **MANDATORY QUALITY GATES:**
**🚨 CRITICAL: After completing each task, the following commands MUST be run and MUST pass before proceeding to the next task:**

1. **Code Quality Check:**
   ```bash
   ruff check .
   ruff format .
   ```

2. **Test Suite Execution:**
   ```bash
   pytest -v
   ```

**NO TASK IS CONSIDERED COMPLETE UNTIL BOTH RUFF AND PYTEST PASS WITHOUT ERRORS.**

**Quality Gate Workflow:**
- Complete task implementation
- Run `ruff check .` and `ruff format .` - fix any issues
- Run `pytest -v` - ensure all tests pass
- Only then proceed to next task

**If either ruff or pytest fails:**
- Fix all issues immediately
- Re-run both commands
- Do not proceed until both pass completely

---

## Important Implementation Notes:

### Database Connection Patterns:
*   Follow existing patterns in `mailwright/db/template_store.py` for async database operations
*   Use `AsyncSessionLocal` from `mailwright/db/models.py` for database sessions
*   Import `settings` from `mailwright/config.py` for configuration values

### Service Architecture:
*   Follow existing service patterns (see `mailwright/core_services/brief_analyzer_service.py`)
*   Use dependency injection for database sessions and external clients
*   Implement proper error handling and logging using `mailwright/logging_config.py`

### LangGraph Integration:
*   Study existing graph structure in `mailwright/graphs/template_generation_graph.py`
*   Use existing `GraphState` class in `mailwright/graphs/state.py` as reference
*   Follow existing node naming conventions: `LG_NodeName_NODE_NAME`

### API Patterns:
*   Follow existing router structure in `mailwright/api/v1/template_routes.py`
*   Use existing schema patterns in `mailwright/schemas/template_schemas.py`
*   Maintain consistent error handling and response formats

### File Locations Reference:
*   **Models:** `mailwright/db/models.py`
*   **Services:** `mailwright/core_services/`
*   **API Routes:** `mailwright/api/v1/`
*   **Schemas:** `mailwright/schemas/`
*   **Config:** `mailwright/config.py`
*   **Scripts:** `scripts/`
*   **Tests:** `tests/` (unit, integration, api subdirectories) 