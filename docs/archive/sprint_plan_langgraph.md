# Mailwright - Agentic Marketing Email Platform - Phase 1: 4-Sprint Plan (LangGraph Architecture)

This document breaks down the Phase 1 development of the Mailwright - Agentic Marketing Email Platform, as detailed in [`docs/plan_langgraph.md`](docs/plan_langgraph.md) and incorporating feedback from [`docs/plan_review_langgraph.md`](docs/plan_review_langgraph.md), into four manageable sprints. Each sprint will have a primary goal and key deliverables.

## Sprint 1: Core Infrastructure & Initial Generation Path `[COMPLETED]`

**Goal:** Establish the foundational FastAPI application, LangGraph setup, and the initial path for MJML generation from a user brief, including AI-driven clarification.

**Key Deliverables:** `[ALL DELIVERABLES COMPLETED]`

1.  **Project Setup & CI/CD Basics:**
    *   Initialize project structure ([`docs/plan_langgraph.md:431-491`](docs/plan_langgraph.md:431-491)).
    *   Set up `requirements.txt` with core dependencies ([`docs/plan_langgraph.md:403-416`](docs/plan_langgraph.md:403-416)).
    *   Basic CI pipeline (linting, initial tests).
    *   Setup `config.py` for application settings and secure secret management strategy.
2.  **FastAPI Application Shell:**
    *   Implement `main.py` with FastAPI app instance ([`docs/plan_langgraph.md:446`](docs/plan_langgraph.md:446)).
    *   Basic API router setup (`mailwright/api/v1/router.py`).
    *   Implement `POST /templates` endpoint to initiate LangGraph execution ([`docs/plan_langgraph.md:254-267`](docs/plan_langgraph.md:254-267)).
    *   Implement `GET /templates/{template_id}/status` endpoint (initial version for polling LangGraph state) ([`docs/plan_langgraph.md:284-310`](docs/plan_langgraph.md:284-310)).
3.  **LangGraph Core Setup:**
    *   Define initial LangGraph state schema (`mailwright/graphs/state.py`) ([`docs/plan_langgraph.md:458`](docs/plan_langgraph.md:458)).
    *   Implement basic LangGraph checkpointer using `langgraph.checkpoint.aiosqlite.AsyncSqliteSaver` for initial development (due to its async compatibility and file-based persistence). The decision on a production checkpointer will be revisited for later phases (see [`docs/plan_review_langgraph.md`](docs/plan_review_langgraph.md) Point 2).
    *   Define the initial `template_generation_graph.py` ([`docs/plan_langgraph.md:457`](docs/plan_langgraph.md:457)).
4.  **Brief Analysis & Clarification Flow:**
    *   Implement `Brief Analyzer Node` (`mailwright/core_services/brief_analyzer_service.py`) ([`docs/plan_langgraph.md:175-182`](docs/plan_langgraph.md:175-182)).
        *   Integrate LLM call for brief analysis and question generation.
        *   Define prompt for clarification.
    *   Implement LangGraph flow: `LG_Start` -> `LG_BriefAnalyzer` -> `LG_ClarificationDecision`.
    *   Implement `LG_WaitForAmendedBrief` node.
    *   Implement `PUT /templates/{template_id}/brief` endpoint to submit amended brief ([`docs/plan_langgraph.md:269-282`](docs/plan_langgraph.md:269-282)).
5.  **Initial MJML Generation (No Images Yet):**
    *   Implement `MJML Generation Node` (`mailwright/core_services/mjml_service.py` - initial version) ([`docs/plan_langgraph.md:183-190`](docs/plan_langgraph.md:183-190)).
        *   Integrate LLM call for MJML generation from a clarified brief.
        *   Develop initial prompt for MJML generation.
    *   Implement LangGraph flow: `LG_ClarificationDecision` (No) -> `LG_MJMLGen`.
6.  **Basic MJML Validation & Compilation:**
    *   Implement `MJML Validator and HTML Compiler Node` (`mailwright/core_services/mjml_service.py` - initial version) ([`docs/plan_langgraph.md:197-206`](docs/plan_langgraph.md:197-206)).
        *   Integrate `mjml` CLI via subprocess for validation and compilation.
    *   Implement LangGraph flow: `LG_MJMLGen` -> `LG_MJMLValidateCompile`.
    *   Basic error handling for invalid MJML (log error, update graph state).
7.  **Unit Tests:** For all new services and critical API endpoints.

**Considerations from Review:**
*   Initial thoughts on error handling within nodes ([`docs/plan_review_langgraph.md`](docs/plan_review_langgraph.md) Point 1).
*   Initial LangGraph checkpointer chosen: `AsyncSqliteSaver` (see [`docs/plan_review_langgraph.md`](docs/plan_review_langgraph.md) Point 2 for original consideration).
*   Initial security considerations for API endpoints and secret management ([`docs/plan_review_langgraph.md`](docs/plan_review_langgraph.md) Point 6).

## Sprint 2: Image Generation, Versioning & State Persistence `[COMPLETED]`

**Goal:** Integrate image generation capabilities, establish the template versioning system with database persistence, and solidify LangGraph state persistence.

**Key Deliverables:** `[ALL DELIVERABLES COMPLETED]`

1.  **Image Generation Module:**
    *   Implement `Image Generation Node` (`mailwright/core_services/image_generator_service.py`) ([`docs/plan_langgraph.md:191-195`](docs/plan_langgraph.md:191-195)).
        *   Integrate DALL-E 3 (or chosen alternative).
        *   Handle image prompts from the brief.
        *   Manage asset URLs.
    *   Integrate `LG_ImageGen` node into the LangGraph flow before `LG_MJMLGen`.
    *   Update MJML generation prompt to incorporate image placeholders/URLs.
2.  **Template Versioning & Storage (`TemplateStoreDB`):**
    *   Set up PostgreSQL database.
    *   Define SQLAlchemy models (`mailwright/db/models.py`) for template versions ([`docs/plan_langgraph.md:234-243`](docs/plan_langgraph.md:234-243)).
    *   Implement database interaction logic (`mailwright/db/template_store.py`) ([`docs/plan_langgraph.md:468`](docs/plan_langgraph.md:468)).
    *   Implement `StoreV0Node` in LangGraph to save the first generated version to `TemplateStoreDB` ([`docs/plan_langgraph.md:154`](docs/plan_langgraph.md:154)).
    *   Update `GET /templates/{template_id}/status` to reflect `ready_for_preview` and provide version info ([`docs/plan_langgraph.md:299-308`](docs/plan_langgraph.md:299-308)).
3.  **HTML Preview Service:**
    *   Implement FastAPI endpoints to serve versioned content:
        *   `GET /templates/{template_id}/versions/{version_id}/html` ([`docs/plan_langgraph.md:314`](docs/plan_langgraph.md:314))
        *   `GET /templates/{template_id}/versions/{version_id}/mjml` (as per [`docs/plan_langgraph.md:306`](docs/plan_langgraph.md:306))
4.  **LangGraph State Persistence Finalization:**
    *   Implement and configure the chosen production-ready LangGraph checkpointer (e.g., PostgreSQL or Redis based on decision from Sprint 1) ([`docs/plan_langgraph.md:469`](docs/plan_langgraph.md:469)).
    *   Test resumability of graph executions.
5.  **Enhanced Error Handling & Logging:**
    *   Implement more robust error handling within LangGraph nodes (building on Sprint 1).
    *   Standardize logging across services and LangGraph nodes.
6.  **Unit & Integration Tests:** For image generation, versioning, and preview services.

**Considerations from Review:**
*   Refine error handling and propagation strategies ([`docs/plan_review_langgraph.md`](docs/plan_review_langgraph.md) Point 1).
*   Address image generation consistency and prompt derivation ([`docs/plan_review_langgraph.md`](docs/plan_review_langgraph.md) Point 4).

## Sprint 3: Iterative Refinement Loop, Approval & Advanced Validation `[COMPLETED - Primary Goals]`

**Goal:** Implement the full iterative refinement loop (feedback and revision) and template approval workflow. Defer advanced/research tasks.

**Key Deliverables (Actual for Sprint 3):**

1.  **Feedback Submission API:** `[DONE]`
    *   Implement `POST /templates/{template_id}/versions/{version_id}/feedback` endpoint.
2.  **LangGraph Feedback Loop Implementation:** `[DONE]`
    *   Implement `LG_FeedbackEngineNode` and `feedback_engine_service.py`.
    *   Adapt `LG_MJMLValidateCompileNode` for revised MJML.
    *   Implement `LG_StoreVNextNode` to save revised versions.
    *   Updated graph routing logic for feedback (`route_initial_or_feedback`, `should_route_after_validation`).
3.  **Approval Workflow:** `[DONE]` (Moved from original Sprint 4 plan and completed)
    *   Implement `POST /templates/{template_id}/versions/{version_id}/approve` endpoint.
    *   Implement database logic to manage `is_approved` status for versions.
    *   Update `GET /status` to reflect approved status.
4.  **Integration Tests:** For the complete feedback loop and approval workflow. `[DONE]`

**Deferred to Sprint 4 / Future:**
*   **Advanced MJML Validation & Structuring:** `[DEFERRED TO SPRINT 4]`
    *   Research sophisticated MJML validation beyond basic CLI checks.
    *   Consider LLM Self-Critique for MJML output.
*   **User Experience for Feedback & Clarification (Advanced):** `[DEFERRED TO SPRINT 4]`
    *   Strategies for vague feedback (LLM identification).
*   **Idempotency Review for APIs:** `[DEFERRED TO SPRINT 4 / RE-EVALUATE]`

## Sprint 4: Beefree Integration, Deferred Tasks, Final Polish

**Goal:** Integrate with the Beefree HTML Importer API, address deferred research tasks from Sprint 3, conduct final end-to-end testing, and prepare documentation.

**Key Deliverables:**

1.  **Beefree HTML Importer API Integration:**
    *   Implement `BeefreeImportNode` (`mailwright/core_services/beefree_service.py`).
    *   Develop Python client for Beefree API.
    *   Retrieve approved HTML from `TemplateStoreDB`.
    *   Handle API responses and errors from Beefree.
    *   Integrate `LG_BeefreeImport` node into the LangGraph flow after approval.
    *   Update `GET /templates/{template_id}/status` to reflect Beefree import status.
2.  **Advanced MJML Validation & Structuring (Deferred from Sprint 3):**
    *   Research and implement more sophisticated MJML validation beyond basic CLI checks if useful.
    *   Consider safeguards/LLM self-critique for LLM revisions to maintain MJML integrity.
3.  **User Experience for Feedback & Clarification (Advanced - Deferred from Sprint 3):**
    *   Define and implement strategies for handling vague feedback (e.g., LLM identification and prompting for more details).
4.  **Idempotency Review (Deferred from Sprint 3):**
    *   Review and implement idempotency for key API endpoints where necessary.
5.  **End-to-End Testing (Overall System):**
    *   Develop comprehensive end-to-end test scenarios covering all major user flows including Beefree integration.
    *   Perform testing, including error conditions and edge cases.
6.  **Security Hardening:**
    *   Final review of security measures (authentication, authorization, input validation, prompt injection mitigation).
7.  **Performance Optimization:**
    *   Identify and address any performance bottlenecks.
8.  **Documentation:**
    *   API documentation (e.g., OpenAPI spec generated from FastAPI).
    *   User guide snippets for key features.
    *   Deployment and operational notes.
9.  **Observability Hooks:**
    *   Ensure nodes emit sufficient logs/metrics for future observability.
10. **Code Cleanup & Refactoring:** Final pass on code quality.

**Considerations from Review:**
*   Resilient error handling for Beefree API integration.
*   Final security review.

This sprint plan provides a structured approach to delivering Phase 1. Flexibility will be needed, and priorities may shift based on discoveries during development. Regular review against the original plan and the review document is recommended.