# Sprint 3: Iterative Refinement & Approval Workflow

**Overall Project Goal (Recap):** Develop an AI-powered agent for generating professional-grade, responsive email templates, featuring iterative refinement and eventual integration with Beefree. Sprints 1 & 2 established core generation, versioning, and preview.

**Sprint 3 Goal:** Implement the full iterative refinement loop, allowing users to provide feedback on a generated template version and have the MJML revised by AI. Crucially, this sprint will also introduce the functionality for a user to formally approve a specific template version, designating it as the canonical version ready for subsequent (Sprint 4) actions like Beefree import.

```mermaid
graph TD
    A[Start Sprint 3] --> B{1. Feedback Submission API};
    B --> B1[1.1 Implement POST /templates/{id}/versions/{v_id}/feedback Endpoint];
    B --> B2[1.2 Define Feedback Schemas (Request/Response)];
    B --> B3[1.3 Update GraphState for Feedback Data];

    A --> C{2. LangGraph Feedback & Revision Loop};
    C --> C1[2.1 Implement LG_FeedbackEngine Node & Service (`feedback_engine_service.py`)];
    C1 --> C1a[2.1.1 LLM Call to Analyze Feedback & Revise MJML];
    C1 --> C1b[2.1.2 Robust Prompt Engineering];
    C --> C2[2.2 Reuse/Adapt LG_MJMLValidateCompile Node (as LG_MJMLValidateCompileRevised)];
    C --> C3[2.3 Implement LG_StoreVNextNode (Saves New Unapproved Version)];
    C3 --> C3a[2.3.1 Generate New UUID for version_id];
    C3 --> C3b[2.3.2 Store Feedback in change_trigger];
    C --> C4[2.4 Clarify Graph End/Loop Logic (Re-trigger via API)];

    A --> D{3. Template Approval Workflow};
    D --> D1[3.1 Implement POST /templates/{id}/versions/{v_id}/approve Endpoint];
    D1 --> D1a[3.1.1 Log Placeholder for Beefree Import on Success];
    D --> D2[3.2 DB Logic for Approval (Set target true, others false for same template_id)];
    D --> D3[3.3 Update GET /status to Reflect 'approved_pending_import'];
    D --> D4[3.4 Ensure GET /versions Reflects 'is_approved' Correctly];

    A --> E{4. Advanced MJML Validation (Research - Secondary)};
    E --> E1[4.1 Research Sophisticated MJML Validation Beyond CLI];
    E --> E2[4.2 Consider LLM Self-Critique for MJML Output];

    A --> F{5. UX for Feedback (Considerations - Secondary)};
    F --> F1[5.1 Define Strategy for Vague Feedback (LLM identification)];

    A --> G{6. Integration Tests};
    G --> G1[6.1 Tests for Full Feedback & Revision Loop];
    G --> G2[6.2 Tests for Approval Workflow (DB changes, API status)];
    G --> G3[6.3 Tests for Feedback on Approved Version];

    B & C & D & E & F & G --> H[End Sprint 3];

    subgraph "Key File Areas"
        direction LR
        FA1[API: template_routes.py]
        FA2[Schemas: template_schemas.py]
        FA3[Graph: template_generation_graph.py, state.py]
        FA4[Services: feedback_engine_service.py (New), mjml_service.py]
        FA5[DB: template_store.py, models.py]
        FA6[Tests: integration & unit tests]
    end
```

---

## Detailed Task Breakdown

### 1. Feedback Submission API & State Updates
*Goal: Allow users to submit feedback for a specific template version to initiate a revision cycle.*

1.  **Implement `POST /api/v1/templates/{template_id}/versions/{version_id}/feedback` Endpoint:** `[DONE]`
    *   **File:** `xyra/api/v1/template_routes.py`
    *   **Details:**
        *   Accepts user feedback (e.g., natural language text) for a specified `template_id` and `version_id`.
        *   Validate `template_id` and `version_id` (ensure version exists).
        *   Update `GraphState` with the feedback content and the `version_id` the feedback applies to.
        *   Invoke/resume the LangGraph workflow, guiding it towards the `LG_FeedbackEngineNode`.
        *   Return `202 Accepted` response.
2.  **Define Feedback Schemas:** `[DONE]`
    *   **File:** `xyra/schemas/template_schemas.py`
    *   **Details:**
        *   Create `FeedbackRequestSchema` (e.g., fields: `feedback_text: str`).
        *   (Optional) `FeedbackResponseSchema` if more than a simple confirmation is needed.
3.  **Update `GraphState` for Feedback Data:** `[DONE]`
    *   **File:** `xyra/graphs/state.py`
    *   **Details:** Add new fields to `GraphState`, e.g.:
        *   `user_feedback_content: Optional[str]`
        *   `version_id_for_feedback: Optional[str]`
        *   `revised_mjml_candidate: Optional[str]` (output of feedback engine)

---

### 2. LangGraph Feedback & Revision Loop Implementation `[DONE]`
*Goal: Process user feedback using an LLM to revise MJML, validate it, and store it as a new version.*

1.  **Implement `LG_FeedbackEngineNode` and `feedback_engine_service.py`:** `[DONE]`
    *   **Files:** `xyra/graphs/template_generation_graph.py` (add node), `xyra/core_services/feedback_engine_service.py` (new file).
    *   **Details (Service):**
        *   Takes `user_feedback_content` and the MJML of `version_id_for_feedback` (fetched from DB or passed in state) as input.
        *   Uses an LLM (configured via `FEEDBACK_ENGINE_PROVIDER` settings) to analyze feedback against current MJML.
        *   **Prompt Engineering:** Develop a robust prompt for the LLM to generate a *revised MJML content string*.
        *   Returns the revised MJML.
    *   **Details (Node):**
        *   Calls the `FeedbackEngineService`.
        *   Updates `GraphState.revised_mjml_candidate` with the result.
        *   Handles potential errors from the service/LLM.
2.  **Reuse/Adapt `LG_MJMLValidateCompileNode` (as `LG_MJMLValidateCompileRevised`):** `[DONE]`
    *   **Files:** `xyra/graphs/template_generation_graph.py`, `xyra/core_services/mjml_service.py`.
    *   **Details:**
        *   This node takes `GraphState.revised_mjml_candidate` as input.
        *   Uses the existing `MJMLService` to validate the revised MJML and compile it to HTML.
        *   Updates `GraphState.current_mjml`, `GraphState.compiled_html`, and `GraphState.mjml_validation_status`.
3.  **Implement `LG_StoreVNextNode`:** `[DONE]`
    *   **Files:** `xyra/graphs/template_generation_graph.py`, `xyra/db/template_store.py`.
    *   **Details (Node & DB Logic):**
        *   If `LG_MJMLValidateCompileRevised` is successful:
            *   Generate a new unique `version_id` (e.g., UUID).
            *   Prepare `TemplateVersionCreate` data:
                *   `template_id` from current context.
                *   New `version_id`.
                *   `mjml_source = GraphState.current_mjml` (the revised one).
                *   `compiled_html = GraphState.compiled_html` (the revised one).
                *   `user_brief_snapshot` (can be copied from the version being revised or V0).
                *   `image_assets` (likely copied, as feedback focuses on MJML for this sprint).
                *   `change_trigger`: Store context, e.g., `{ "event": "feedback_revision", "source_version_id": state.version_id_for_feedback, "feedback": state.user_feedback_content }`.
                *   `is_approved = False` (new versions from feedback are drafts).
            *   Call a function in `template_store.py` to save this new version.
            *   Update `GraphState` with info about this newly stored version (e.g., `current_version_id_stored`, `last_operation_status = "SUCCESS_STORED_V_NEXT"`).
4.  **Clarify Graph End/Loop Logic:** `[DONE]`
    *   **Files:** `xyra/graphs/template_generation_graph.py`.
    *   **Details:** Added `route_initial_or_feedback` and `should_route_after_validation` conditional edges.

---

### 3. Template Approval Workflow `[DONE]`
*Goal: Allow users to formally approve a template version, marking it as the final one for that iteration cycle and ready for subsequent (Sprint 4) actions.*

1.  **Implement `POST /api/v1/templates/{template_id}/versions/{version_id}/approve` Endpoint:** `[DONE]`
    *   **File:** `xyra/api/v1/template_routes.py`.
    *   **Details:**
        *   User specifies `template_id` and `version_id` to approve.
        *   Validate existence of the template and version.
        *   Call database logic (see 3.2) to update approval status.
        *   **On successful DB update, log a message: "Template [template_id], Version [version_id] approved. Placeholder: Beefree import would be initiated here."**
        *   Return a success response, possibly including the new status (`approved_pending_import`) and details of the approved version.
    *   **Schema:** Define `ApprovalResponseSchema` in `xyra/schemas/template_schemas.py`.
2.  **Database Logic for Approval:** `[DONE]`
    *   **File:** `xyra/db/template_store.py`.
    *   **Details:** Implemented `approve_template_version` function.
3.  **Update `GET /status` to Reflect Approval:** `[DONE]`
    *   **File:** `xyra/api/v1/template_routes.py` (update `get_template_task_status` logic).
    *   **File:** `xyra/schemas/template_schemas.py` (update `TemplateStatusSchema`).
    *   **Details:**
        *   The `get_template_task_status` function will:
            *   First, check the database: if any version for the given `template_id` has `is_approved = True`.
            *   If yes, set `status = "approved_pending_import"` (or similar) and include `approved_version_id`. This DB-derived status takes precedence.
            *   If no version is approved in DB, then proceed to query LangGraph checkpointer for the current graph execution state as it does now.
        *   Update `TemplateStatusSchema` to include `approved_version_id: Optional[str]` and ensure `status` field can accommodate `approved_pending_import`.
4.  **Ensure `GET /versions` Reflects `is_approved` Correctly:** `[DONE]`
    *   **File:** `xyra/api/v1/template_routes.py` (logic for `list_template_versions`).
    *   **File:** `xyra/schemas/template_schemas.py` (`VersionMetadataSchema`).
    *   **Details:** Verified by extending `test_approve_version_success` API test.

---

### 4. Advanced MJML Validation (Research & Initial Implementation - Secondary Goal) `[DEFERRED TO SPRINT 4]`
*Goal: Explore improvements to MJML validation beyond current capabilities.*

1.  **Research Sophisticated MJML Validation Beyond CLI:** `[DEFERRED TO SPRINT 4]`
    *   Investigate MJML linters, Python libraries, or advanced CLI options for more granular validation (semantic correctness, best practices).
2.  **Consider LLM Self-Critique for MJML Output:** `[DEFERRED TO SPRINT 4]`
    *   Explore prompting the `FeedbackEngineNode`'s LLM (or a separate validation LLM call) to review its own generated MJML for issues.
    *   **Focus:** This is a research task. Implementation only if a clear, stable, and high-impact improvement is found that fits within Sprint 3.

---

### 5. User Experience for Feedback (Considerations - Secondary Goal) `[DEFERRED TO SPRINT 4]`
*Goal: Think about improving how the system handles potentially problematic user feedback.*

1.  **Define Strategy for Vague Feedback (LLM Identification):** `[DEFERRED TO SPRINT 4]`
    *   Consider prompting the `FeedbackEngineNode`'s LLM to identify when user feedback is too vague to be actionable.
    *   If vague, the LLM could suggest what information is missing, and this could be passed back to the user via `GraphState.error_message` or a dedicated field.
    *   **Focus:** Initial consideration and prompt experimentation. Full implementation is a stretch goal.

---

### 6. Integration Tests `[DONE]`
*Goal: Ensure the new feedback and approval workflows are robust and function end-to-end.*

1.  **Tests for Full Feedback & Revision Loop:**
    *   **File:** `tests/integration/test_template_generation_graph.py` (and potentially new unit tests for `feedback_engine_service.py`).
    *   **Scenarios:**
        *   V0 created -> Submit feedback -> V1 created, reflecting changes. `[DONE]`
        *   V1 created -> Submit further feedback -> V2 created.
        *   Feedback leading to (mocked) invalid MJML from Feedback Engine -> Ensure graph handles error and doesn't store V_Next.
2.  **Tests for Approval Workflow:**
    *   **Files:** `tests/api/v1/test_template_routes.py`, `tests/integration/test_template_generation_graph.py` (if graph state is affected by approval).
    *   **Scenarios:**
        *   Create V0 -> Approve V0. Verify DB state (`is_approved`), API response from `/approve`, and `GET /status` shows `approved_pending_import`. Verify placeholder log message.
        *   Approve V0 -> Create V1 (via feedback) -> Approve V1. Verify V0 becomes `is_approved = False` and V1 becomes `is_approved = True`.
        *   Verify `GET /versions` correctly lists approval status for all versions.
3.  **Tests for Feedback on Approved Version:**
    *   **File:** `tests/integration/test_template_generation_graph.py`.
    *   **Scenario:** Approve V0 -> Submit feedback for V0 -> New unapproved version V1 is created. V0 remains approved.

---

**Sprint 3 Concluded:** All primary objectives (Tasks 1, 2, 3, and 6) are complete. Secondary research tasks (4 & 5) are deferred to Sprint 4.

### Key Files & Estimated Impact for Sprint 3:

*   **High Impact (Significant Changes/New):**
    *   `xyra/api/v1/template_routes.py` (new endpoints, modified status logic)
    *   `xyra/graphs/template_generation_graph.py` (new nodes, new logic for feedback path)
    *   `xyra/core_services/feedback_engine_service.py` (NEW)
    *   `xyra/db/template_store.py` (new DB functions for approval, adapting version creation)
    *   `xyra/schemas/template_schemas.py` (new schemas, modified `TemplateStatusSchema`)
    *   `xyra/graphs/state.py` (new fields for feedback)
    *   `tests/integration/test_template_generation_graph.py` (new complex test cases)
    *   `tests/api/v1/test_template_routes.py` (new API test cases)
*   **Medium Impact (Minor Additions/Modifications):**
    *   `xyra/core_services/mjml_service.py` (if any adaptation needed for revised MJML validation beyond reuse)
    *   `tests/unit/` (new unit tests for `feedback_engine_service.py`)
*   **Low Impact (Review/Confirmation):**
    *   `xyra/db/models.py` (confirm existing fields are suitable)
    *   `xyra/config.py` (confirm LLM config for feedback engine)

This Sprint 3 plan aims to deliver a robust iterative refinement and approval system, setting a clear path towards Sprint 4's final integration and deployment tasks. 