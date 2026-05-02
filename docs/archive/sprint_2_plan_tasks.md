# Sprint 2: Image Generation, Versioning & Production Persistence

**Overall Project Goal (Recap from [`docs/working_context/plan_langgraph.md`](docs/working_context/plan_langgraph.md))**

To develop an AI-powered agent capable of generating professional-grade, responsive email templates in MJML format, including image generation, iterative refinement, and integration with Beefree. This phase leverages LangGraph for workflow orchestration. Sprint 1 established the core infrastructure. Sprint 2 focuses on adding image generation, robust data persistence for versions, and production-ready state management.

**Sprint 2 Goal**

Integrate image generation capabilities into the MJML workflow, establish a robust template versioning system using PostgreSQL for persistence, implement a production-grade LangGraph checkpointer (replacing the Sprint 1 SQLite solution), enhance error handling and logging, and provide HTML preview functionality.

```mermaid
graph TD
    A[Start Sprint 2] --> B{1. Image Generation Module};
    B --> B1[1.1 Implement Image Generation Node (`image_generator_service.py`)];
    B1 --> B1a[1.1.1 Integrate DALL-E 3 / Alternative];
    B1 --> B1b[1.1.2 Handle Image Prompts & Asset URLs];
    B --> B2[1.2 Integrate `LG_ImageGen` Node into LangGraph Flow (before `LG_MJMLGen`)];
    B --> B3[1.3 Update MJML Generation Prompt for Images];

    A --> C{2. Template Versioning & Storage (`TemplateStoreDB` - PostgreSQL)};
    C --> C1[2.1 Setup PostgreSQL Database & Configuration];
    C --> C2[2.2 Define SQLAlchemy Models (`xyra/db/models.py`)];
    C --> C3[2.3 Implement DB Interaction Logic (`xyra/db/template_store.py`)];
    C --> C4[2.4 Implement `StoreV0Node` in LangGraph (Saves to `TemplateStoreDB`)];
    C --> C5[2.5 Update `GET /status` for `ready_for_preview` & Version Info];

    A --> D{3. HTML Preview Service};
    D --> D1[3.1 Implement `GET /templates/{id}/versions/{v_id}/html` Endpoint];
    D --> D2[3.2 Implement `GET /templates/{id}/versions/{v_id}/mjml` Endpoint];

    A --> E{4. LangGraph State Persistence Finalization (Production Checkpointer)};
    E --> E1[4.1 Decide: PostgreSQL or Redis for Production Checkpointer (replaces SQLite)];
    E --> E2[4.2 Implement & Configure Chosen Production Checkpointer];
    E --> E3[4.3 Test Resumability of Graph Executions];

    A --> F{5. Enhanced Error Handling & Logging};
    F --> F1[5.1 Implement Robust Error Handling in LangGraph Nodes (Build on Sprint 1)];
    F --> F2[5.2 Standardize Logging Across Services & Nodes];

    A --> G{6. Unit & Integration Tests};
    G --> G1[6.1 Tests for Image Generation];
    G --> G2[6.2 Tests for Versioning & DB Interactions];
    G --> G3[6.3 Tests for Preview Service Endpoints];
    G --> G4[6.4 Tests for Production Checkpointer & Resumability];

    B & C & D & E & F & G --> H[End Sprint 2];

    subgraph "Considerations from Review (Throughout Sprint)"
        direction LR
        R1[Refine Error Handling & Propagation Strategies<br/>(plan_review_langgraph.md Point 1)]
        R2[Address Image Generation Consistency & Prompt Derivation<br/>(plan_review_langgraph.md Point 4)]
    end
    B1 --> R2;
    F1 --> R1;
```

---

## Relevant Project File Structure (Focus for Sprint 2)

The overall project structure is defined in [`docs/working_context/plan_langgraph.md:438-507`](docs/working_context/plan_langgraph.md:438-507). Sprint 2 will primarily involve creating or significantly modifying the following:

```text
xyra/
├── __init__.py
├── main.py                 # FastAPI app instance
├── config.py               # Application settings (updated for DB, new API keys)
├── core_services/
│   ├── __init__.py
│   ├── image_generator_service.py # NEW: For DALL-E/image generation logic
│   ├── mjml_service.py       # MODIFIED: To handle image URLs/placeholders
│   └── ...                   # Existing services from Sprint 1
├── graphs/
│   ├── __init__.py
│   ├── template_generation_graph.py # MODIFIED: Integrate LG_ImageGen, StoreV0Node, update checkpointer
│   ├── state.py              # MODIFIED: Potentially update state schema for image assets, version info
│   └── checkpointer.py       # MODIFIED: To implement production checkpointer (PostgreSQL/Redis)
├── api/
│   └── v1/
│       ├── __init__.py
│       ├── router.py
│       └── template_routes.py # MODIFIED: Update /status, Add /versions/... endpoints
├── db/
│   ├── __init__.py
│   ├── template_store.py     # NEW: For TemplateStoreDB (MJML versions) interaction logic
│   ├── models.py           # NEW: SQLAlchemy models for TemplateStoreDB
│   └── langgraph_checkpointer.py # POTENTIALLY NEW/MODIFIED: If custom DB checkpointer logic is extensive
├── schemas/
│   ├── __init__.py
│   ├── template_schemas.py   # MODIFIED: Schemas for version info, image assets in API responses
│   └── ...
tests/
├── unit/
│   ├── test_image_generator_service.py # NEW
│   └── test_template_store.py        # NEW
│   └── graphs/
│       └── test_checkpointer.py      # MODIFIED/EXPANDED for production checkpointer
├── integration/
│   └── test_template_generation_graph_sprint2.py # NEW: For S2 specific flows
```

---

## Detailed Task Breakdown

This breakdown is based on the deliverables outlined in [`docs/working_context/sprint_plan_langgraph.md:53-79`](docs/working_context/sprint_plan_langgraph.md:53-79). Sprint 1 successfully established the core application, initial LangGraph flow with `AsyncSqliteSaver` (SQLite-based), and basic MJML generation/validation ([`docs/working_context/sprint_1_plan_tasks.md:165-168`](docs/working_context/sprint_1_plan_tasks.md:165-168)).

### 1. Image Generation Module
*Goal: Integrate AI-driven image generation into the template creation process.*
**Status: COMPLETED (with temporary test override in `brief_analyzer_node` for `run_graph` testing during development of this task)**

1.  **Implement `Image Generation Node`** in the new file [`xyra/core_services/image_generator_service.py`](xyra/core_services/image_generator_service.py)
    *   References: [`docs/working_context/plan_langgraph.md:191-195`](docs/working_context/plan_langgraph.md:191-195)
    1.  **Integrate DALL-E 3** (or the chosen alternative image generation API).
        *   Ensure secure API key management via [`xyra/config.py`](xyra/config.py).
    2.  **Handle image prompts** derived from the user's brief (managed in LangGraph state, defined in [`xyra/graphs/state.py`](xyra/graphs/state.py)).
    3.  **Manage image asset URLs** returned by the generation service. These URLs will be stored and used in the MJML.
    4.  Address strategies for **visual consistency** and **prompt refinement** as highlighted in [`docs/working_context/plan_review_langgraph.md:33-36`](docs/working_context/plan_review_langgraph.md:33-36).
2.  **Integrate `LG_ImageGen` node into the LangGraph flow** within [`xyra/graphs/template_generation_graph.py`](xyra/graphs/template_generation_graph.py).
    *   This node should execute *before* the `LG_MJMLGen` node.
    *   The LangGraph state will pass image asset information (e.g., URLs) to the MJML generation step.
3.  **Update MJML Generation Prompt & Logic.**
    *   The prompt for `LG_MJMLGen` node (logic within [`xyra/core_services/mjml_service.py`](xyra/core_services/mjml_service.py)) must be updated to instruct the LLM on how to incorporate image placeholders or actual image URLs into the MJML structure.

### 2. Template Versioning & Storage (`TemplateStoreDB` - PostgreSQL)
*Goal: Establish a persistent store for generated template versions, including MJML, HTML, and associated metadata.*
**Status: IN PROGRESS**
1.  **Set up PostgreSQL Database.** **Status: COMPLETED**
    *   Install and configure a PostgreSQL server instance.
    *   Update [`xyra/config.py`](xyra/config.py) with database connection details.
2.  **Define SQLAlchemy Models** in the new file [`xyra/db/models.py`](xyra/db/models.py). **Status: COMPLETED**
    *   Based on schema in [`docs/working_context/plan_langgraph.md:234-243`](docs/working_context/plan_langgraph.md:234-243) (template_id, version_id, mjml_source, compiled_html, user_brief_snapshot, image_assets, etc.).
    *   Set up Alembic for database migrations.
3.  **Implement Database Interaction Logic** in the new file [`xyra/db/template_store.py`](xyra/db/template_store.py). **Status: COMPLETED** (Initial async functions for create/get implemented)
    *   Functions for creating, retrieving, and updating template versions.
    *   Ensure asynchronous operations.
4.  **Implement `StoreV0Node` in LangGraph** within [`xyra/graphs/template_generation_graph.py`](xyra/graphs/template_generation_graph.py). **Status: COMPLETED** (and integration tested)
    *   This new node will save the first successfully generated version to `TemplateStoreDB`.
    *   References: [`docs/working_context/plan_langgraph.md:154`](docs/working_context/plan_langgraph.md:154).
    *   This node will run after `LG_MJMLValidateCompile` is successful.
5.  **Update `GET /api/v1/templates/{template_id}/status` Endpoint** in [`xyra/api/v1/template_routes.py`](xyra/api/v1/template_routes.py). **Status: COMPLETED**
    *   Indicate `ready_for_preview` status.
    *   Include `current_version_id` and preview URLs.
    *   References: [`docs/working_context/plan_langgraph.md:299-308`](docs/working_context/plan_langgraph.md:299-308).
6.  **Implement API Endpoint to List Template Versions.** **Status: PENDING**
    *   **Endpoint:** `GET /api/v1/templates/{template_id}/versions`.
    *   **Functionality:** Return a list of metadata for all stored versions of a given template_id (e.g., version_id, created_at, change_trigger, is_approved), including dynamically generated `preview_urls` (for HTML and MJML content) for each version.
    *   **Components:**
        *   Define Pydantic response schemas in `xyra/schemas/template_schemas.py`.
        *   Add database logic in `xyra/db/template_store.py` to fetch all versions for a template.
        *   Implement the endpoint logic in `xyra/api/v1/template_routes.py`.

### 3. HTML Preview Service
*Goal: Allow users to preview the generated HTML and MJML for a specific template version.*
**Status: COMPLETED**
1.  **Implement FastAPI endpoint: `GET /api/v1/templates/{template_id}/versions/{version_id}/html`** in [`xyra/api/v1/template_routes.py`](xyra/api/v1/template_routes.py). **Status: COMPLETED**
    *   Retrieves compiled HTML for the specified version from `TemplateStoreDB`.
    *   References: [`docs/working_context/plan_langgraph.md:314`](docs/working_context/plan_langgraph.md:314).
2.  **Implement FastAPI endpoint: `GET /api/v1/templates/{template_id}/versions/{version_id}/mjml`** in [`xyra/api/v1/template_routes.py`](xyra/api/v1/template_routes.py). **Status: COMPLETED**
    *   Retrieves MJML source for the specified version from `TemplateStoreDB`.
    *   References: [`docs/working_context/plan_langgraph.md:306`](docs/working_context/plan_langgraph.md:306).

### 4. LangGraph State Persistence Finalization (Production Checkpointer)
*Goal: Transition from `AsyncSqliteSaver` (SQLite-based, used in Sprint 1) to a production-ready checkpointer for LangGraph state.*
**Status: COMPLETED** (Core implementation and testing done)
1.  **Decide on Production Checkpointer:** PostgreSQL or Redis. **Status: DECISION MADE: PostgreSQL**
    *   This decision was deferred to later phases in [`docs/working_context/plan_review_langgraph.md:25-28`](docs/working_context/plan_review_langgraph.md:25-28). Sprint 2 is the time to make and implement this, replacing the Sprint 1 SQLite solution.
2.  **Implement and Configure Chosen Production Checkpointer.** **Status: COMPLETED** (`checkpointer.py` updated for `AsyncPostgresSaver`, used in API routes)
    *   Update LangGraph initialization in [`xyra/graphs/template_generation_graph.py`](xyra/graphs/template_generation_graph.py) and/or [`xyra/graphs/checkpointer.py`](xyra/graphs/checkpointer.py).
    *   References: [`docs/working_context/plan_langgraph.md:469`](docs/working_context/plan_langgraph.md:469).
3.  **Test Resumability of Graph Executions.** **Status: COMPLETED**
    *   Verify correct resumption from persisted state using the new production checkpointer.
    *   A new integration test (`test_graph_resumability_after_clarification_postgres`) was added to explicitly test resumability after brief clarification using the PostgreSQL checkpointer.

### 5. Enhanced Error Handling & Logging
*Goal: Improve system robustness.*
**Status: COMPLETED**

1.  **Implement More Robust Error Handling within LangGraph Nodes.** **Status: COMPLETED**
    *   Building on Sprint 1 ([`docs/working_context/sprint_1_plan_tasks.md:136`](docs/working_context/sprint_1_plan_tasks.md:136)).
    *   Address error management from external services and propagation.
    *   Define retry strategies and critical failure updates to graph state.
    *   Consider points from [`docs/working_context/plan_review_langgraph.md:19-24`](docs/working_context/plan_review_langgraph.md:19-24).
2.  **Standardize Logging Across Services and LangGraph Nodes.** **Status: COMPLETED**
    *   Implement structured logging with consistent formatting using Python's `logging` module.
    *   Centralized configuration in `xyra/logging_config.py`.
    *   Log level controlled by `LOG_LEVEL` environment variable or `xyra/config.py` setting.
    *   Removed `print()` statements and ad-hoc `logging.basicConfig()` calls.
    *   Detailed plan and execution steps are documented in `docs/working_context/logging_standardization_plan.md`.
    *   Ensure detailed logs for debugging and tracing.

### 6. Unit & Integration Tests
*Goal: Ensure quality and correctness.* **Status: COMPLETED**

1.  **Write Unit Tests for:**
    *   `Image Generation Node` logic (new file [`tests/unit/test_image_generator_service.py`](tests/unit/test_image_generator_service.py)). **Status: COMPLETED** (Unit tests for the node are in `tests/unit/graphs/test_image_generation_node.py`)
    *   `TemplateStoreDB` interaction logic (new file [`tests/unit/test_template_store.py`](tests/unit/test_template_store.py)), including logic for listing all versions. **Status: COMPLETED**
    *   New/updated LangGraph nodes. **Status: COMPLETED** (`StoreV0Node` and main graph flow tested via integration tests, `ImageGenerationNode` unit tested, `MJMLService` unit test `test_generate_mjml_node_llm_exception` fixed and passing)
    *   Production checkpointer logic (updates to [`tests/unit/graphs/test_checkpointer.py`](tests/unit/graphs/test_checkpointer.py)). **Status: COMPLETED** (tests fixed for new checkpointer logic, and `AsyncPostgresSaver` used successfully in integration tests)
2.  **Write Integration Tests for:**
    *   End-to-end LangGraph flows including image generation, versioning, and HTML preview services (new file [`tests/integration/test_template_generation_graph_sprint2.py`](tests/integration/test_template_generation_graph_sprint2.py) or augment existing). **Status: COMPLETED**
    *   Production checkpointer resumability (covered by existing and new integration tests). **Status: COMPLETED**
    *   Error handling scenarios in the template generation graph. **Status: COMPLETED** (Implemented in `tests/integration/test_template_generation_graph.py`)

**Sprint 2 Test Conclusion:** All planned unit and integration tests for Sprint 2 features have been successfully implemented and are passing. This includes specific tests for error handling scenarios and the resolution of the previously failing `test_generate_mjml_node_llm_exception` unit test in `tests/unit/test_mjml_service.py`. The codebase is stable with respect to Sprint 2 objectives.

### 7. Documentation & Review
*Goal: Ensure comprehensive and accurate documentation for the implemented features and processes.*
**Status: IN PROGRESS**

1.  **Update Sprint 2 Documentation:**
    *   Add detailed descriptions and diagrams for each task.
    *   Document key decisions and rationale for each implementation choice.
    *   Include screenshots or examples of the final product.
2.  **Conduct Sprint Review:**
    *   Gather feedback from stakeholders and team members.
    *   Identify areas for improvement and document them for future iterations.
    *   Prepare a summary report for the project team.

---

## Ongoing Considerations (Throughout Sprint 2)

*   **Error Handling and Propagation in LangGraph:** Continuously refine, referencing [`docs/working_context/plan_review_langgraph.md:19-24`](docs/working_context/plan_review_langgraph.md:19-24).
*   **Image Generation Details:** Focus on visual consistency and prompt derivation, per [`docs/working_context/plan_review_langgraph.md:33-36`](docs/working_context/plan_review_langgraph.md:33-36).
*   **Database Schema Migrations:** Use Alembic for `TemplateStoreDB` schema changes.
*   **Security:** Apply best practices for DB access and new API integrations.
*   **Configuration Management:** Manage new configurations securely via [`xyra/config.py`](xyra/config.py) and `.env` files.

---