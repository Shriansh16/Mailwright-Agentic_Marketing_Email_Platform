# Sprint 5 Plan: RAG-Based HTML Generation

## 1. Overview & Core Goal

This sprint introduces a significant new capability to the template generation agent: a Retrieval-Augmented Generation (RAG) workflow. The primary goal is to shift from generating MJML from scratch to intelligently selecting and populating existing HTML templates from a corpus. This allows for greater control over the final output's structure and accelerates the generation process.

This new RAG system will coexist with the legacy MJML generation flow, selectable via a new API flag.

### Key Principles for This Sprint:
- **Preserve Existing Architecture:** We will integrate the new workflow into the existing LangGraph state machine, preserving the asynchronous API, PostgreSQL checkpointer, and as many existing nodes as possible.
- **HTML-First:** This workflow will bypass MJML entirely, working directly with and producing raw HTML.
- **Assume "Perfect Brief":** For this sprint, we assume the user provides a detailed, structured, plain-text brief that contains all necessary information and requires no clarification cycles.

---

## 2. Technical Implementation Plan

The work is broken down into the following tasks, designed to build the new system from the database layer up to the API.

### Task 0: Decommission Previous RAG Implementation (Rip and Replace)

**Status:** ✅ Complete

Before any new development, we will remove the artifacts from the initial, more complex RAG implementation to create a clean slate. This is the first and most critical step.

- **Action 1:** Create and apply a new Alembic migration to reverse the changes from revision `3d8eba472621`. This will drop the `rag_templates` table entirely.
- **Action 2:** Delete the `RAGTemplate` SQLAlchemy model from `xyra/db/models.py`.
- **Action 3:** Delete the conflicting service file `xyra/core_services/corpus_ingestion_service.py`.
- **Action 4:** Run the full test suite (`pytest -v`) to confirm that the removal of these components has not broken any existing, unrelated functionality.
- **Action 5:** Delete the `RAGTemplateBase`, `RAGTemplateCreate`, and `RAGTemplate` Pydantic models from `xyra/schemas/template_schemas.py`.

### Task 1: Database Schema for RAG Corpus

**Status:** ✅ Complete

We will create a new table to store the processed and vectorized template corpus. This requires a database migration.

- **Action:** Create a new Alembic migration script.
- **Details:**
    - The migration will create a new table named `rag_templates`.
    - **Required Columns:**
        - `id`: Primary Key (Integer/UUID).
        - `template_name`: The original filename or identifier (e.g., "halloween-movie-premier").
        - `processed_html`: The raw HTML of the template after being processed to include placeholders (TEXT).
        - `fingerprint_embedding`: The vector embedding of the template's structural fingerprint (VECTOR).
    - **Dependency:** This requires the `pgvector` extension to be enabled in the PostgreSQL database.

### Task 2: Corpus Ingestion & Processing Service

**Status:** ✅ Complete

A one-time script is needed to populate the `rag_templates` table. This script will form the basis of our corpus management.

- **Action:** Create a new utility script `scripts/ingest_rag_corpus.py`.
- **Functionality:**
    1.  **Iterate:** Scan the `ingest/` directory for all `*.json` source files.
    2.  **Extract:** For each file, parse the JSON and extract the `html_data` string.
    3.  **Process HTML:** Implement a new HTML processing function that:
        - Parses the HTML (e.g., with BeautifulSoup).
        - Replaces media-specific `<img>` tags and video blocks with standardized, size-aware placeholders (e.g., `https://placehold.co/...` or a placeholder `<div>`).
        - **Crucially, it must ignore and preserve UI/branding images** (e.g., social media icons).
        - **Justification for HTML-First:** We are explicitly choosing to work with the raw `html_data` instead of the `json_data` for two key reasons: 1) It allows all media processing (like creating image placeholders) to happen in one place, keeping the database schema simple and clean. 2) The detailed information within the JSON is unnecessary for this RAG workflow and would introduce significant downstream complexity.
    4.  **Generate Fingerprint:** Use an LLM with the pre-defined "fingerprint prompt" to convert the processed HTML into a concise, one-line structural summary.
    5.  **Generate Embedding:** Send the fingerprint string to the OpenAI `text-embedding-3-small` model to create a vector.
    6.  **Store in Database:** Insert the `template_name`, `processed_html`, and `fingerprint_embedding` into the `rag_templates` table.

### Task 3: API Schema and Endpoint Updates

**Status:** ✅ Complete

To enable the new workflow, we need to modify the primary template creation endpoint.

- **Action:** Modify `xyra/schemas/template_schemas.py`.
- **Schema Changes:**
    - `TemplateCreationRequest`:
        - The existing `user_brief: UserBriefSchema` field will be made `Optional`.
        - Add a new field: `rag_flow: bool = False`. This flag will determine the workflow.
        - Add a new field: `plain_text_brief: Optional[str]`. This will hold the unstructured brief for the RAG flow.
        - A Pydantic validator will be added to ensure that if `rag_flow` is `True`, then `plain_text_brief` must be provided, and if `False`, `user_brief` must be provided.
- **Endpoint Behavior:** The `POST /api/v1/templates` endpoint will now inspect the `rag` flag to determine which workflow to initiate in the background.

### Task 4: LangGraph Workflow Implementation

This is the core logic, integrating the RAG pipeline into our existing state machine.

- **Action 1: Update Graph State**
    - **Status:** ✅ Complete
    - Modify `GraphState` in `xyra/graphs/state.py` to track the new workflow's data.
    - **New Fields:** `rag_flow: bool`, `plain_text_brief: Optional[str]`, `brief_fingerprint: Optional[str]`, `retrieved_template_html: Optional[str]`, `final_html_content: Optional[str]`.

- **Action 2: Create RAG Core Service**
    - Create a new service file: `xyra/core_services/rag_template_service.py`.
    - This service will encapsulate the key RAG logic:
        - `generate_fingerprint_for_brief(brief: str) -> str`
        - `find_best_matching_template(embedding: list[float]) -> str` (returns processed HTML)
        - `populate_template_with_brief(template_html: str, brief: str) -> str` (returns final HTML)

- **Action 3: Implement New Graph Nodes**
    - In `xyra/graphs/template_generation_graph.py`, add new node functions that utilize the `rag_template_service`.
    - **New Nodes:**
        - `LG_RAG_GenerateBriefFingerprint`
        - `LG_RAG_FindMatchingTemplate`
        - `LG_RAG_PopulateContent`

- **Action 4: Update Graph Routing**
    - Modify the graph's entry point to include a new, top-level conditional edge function, `route_rag_or_legacy`.
    - Based on `state.rag_flow`, this new router will direct execution:
        - If `True`, the graph will route to the `LG_RAG_GenerateBriefFingerprint` node.
        - If `False`, it will delegate to the existing `route_initial_or_feedback` function to preserve the legacy MJML workflow.

- **Action 5: Adapt Final Storage Node**
    - Modify the `LG_StoreV0` node to be fully flexible. It will inspect `state.rag_flow`:
        - If `True`, it will use `state.final_html_content` to populate the `compiled_html` field in the database and explicitly store `mjml_source` as `None`.
        - If `False`, it will use the existing logic, saving `state.current_mjml` and `state.compiled_html`.

- **Action 6: Enforce State Hygiene**
    - The new RAG-specific nodes (`LG_RAG_...`) are responsible for writing only to RAG-specific fields in the `GraphState` (e.g., `brief_fingerprint`, `final_html_content`).
    - These nodes must not populate or modify any fields related to the MJML or feedback flows (e.g., `current_mjml`, `clarification_questions`, `revised_mjml_candidate`) to prevent state pollution and simplify debugging.

### Task 5: Testing Strategy

- **Unit Tests:**
    - Test the `ingest_rag_corpus.py` script's logic with mocked DB and LLM calls.
    - Write unit tests for all new methods in `rag_template_service.py`.
- **Integration Tests:**
    - Create a new integration test for the end-to-end RAG workflow. This test will:
        - Initiate the graph with `rag: true`.
        - Mock the external LLM/embedding calls.
        - Verify correct state transitions through the new RAG nodes.
        - Assert that `LG_StoreV0` saves the final HTML correctly.
    - Run existing integration tests with `rag: false` to ensure the legacy MJML path is not broken.
    - Add API tests for the new request schema.

---

## Sprint 5 Summary & Outcomes

**Sprint Status: ✅ Completed**

This sprint was a success, delivering the full end-to-end RAG-based HTML generation workflow. All primary implementation tasks (Tasks 1-4) were completed, and the new pipeline was validated through a comprehensive manual testing process.

### Key Accomplishments:

1.  **Corpus Ingestion & Processing (Task 2):**
    - The `scripts/ingest_rag_corpus.py` script was successfully implemented.
    - Through an iterative debugging process, the HTML processing logic was made robust, correctly handling image dimension fetching (via `Pillow` and `httpx`) and video placeholder centering to create visually accurate, structurally sound placeholder templates.

2.  **API & State Integration (Task 3 & 4):**
    - The API (`/api/v1/templates`) and `GraphState` were successfully updated to support the dual-workflow system.
    - The `RAGTemplateService` was implemented with the logic for fingerprinting, database vector search, and LLM-based content population.
    - All new RAG nodes were integrated into the `LangGraph` and the top-level routing logic was implemented and debugged to correctly delegate between the RAG and legacy MJML workflows.

3.  **End-to-End Validation:**
    - A manual `curl` test successfully triggered the RAG workflow.
    - We diagnosed and fixed several critical bugs that were not initially anticipated:
        - **Configuration Error:** Added the `PROMPT_GENERATION_MODEL` to the central `xyra/config.py` settings.
        - **Unsupported Parameter:** Corrected the LLM calls to remove the `temperature` parameter, which was unsupported by the target model.
        - **Asyncio Client Bug:** Refactored the `RAGTemplateService` to use the correct `AsyncOpenAI` client, resolving a `TypeError`.
        - **Resource Management Stall:** Debugged and fixed a stall in the diagnostic script by refactoring how the `AsyncOpenAI` client and `SQLAlchemy` sessions were managed, preventing event loop conflicts.
    - The final populated HTML was successfully retrieved and visually verified.

### Final Status:
The new RAG pipeline is fully functional and integrated alongside the existing MJML generation system. The project is now ready for the final automated testing phase as originally planned.

---

## 3. Mandatory Quality Gates

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

**NO TASK IS CONSIDERED COMPLETE UNTIL BOTH RUFF AND PYTEST PASS WITHOUT ERRORS.** The sprint plan document will be updated to reflect progress after each task passes these gates.

---

## 4. Out of Scope for Sprint 5

To ensure focus, the following items are explicitly not part of this sprint:

- **Dynamic Image Generation:** Placeholders in the final HTML will *not* be replaced with DALL-E generated images. The output will be valid HTML with placeholder links.
- **RAG Brief Clarification & Feedback:** The "perfect brief" assumption removes the need for clarification. The existing feedback loop will not be adapted for the RAG flow at this time.

---

## 5. Success Criteria

The sprint will be considered a success when:
- ✅ **Task 0 Complete:** The previous RAG implementation is successfully removed, and all tests pass.
- ✅ The corpus ingestion script successfully populates the *new*, simplified `rag_templates` table in PostgreSQL.
- ✅ A `POST` request to `/api/v1/templates` with `rag_flow: true` and a `plain_text_brief` triggers the new workflow.
- ✅ The system successfully finds a template, populates it, and stores the final HTML in the database as version `v0`.
- ✅ The legacy MJML flow (`rag: false`) remains fully functional and unaffected.
- ☐ All new logic is covered by a combination of passing unit and integration tests, with all quality gates passing at each step. 