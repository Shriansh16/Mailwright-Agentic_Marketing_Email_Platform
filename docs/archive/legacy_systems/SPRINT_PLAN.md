# Project Breakdown: Mailwright - Agentic Marketing Email Platform - Phase 1

We'll organize the work into logical sprints, each focusing on delivering a key set of functionalities.

---

### **Sprint 1: Foundation & Core API Infrastructure**

*   **Goal:** Establish the foundational FastAPI application, asynchronous task management, core API endpoints for initiating template generation and polling status, and the database schema for template versioning.
*   **Key Components from [`plan.md`](plan.md:1):** Basic FastAPI setup, Asynchronous Task Management (conceptual), initial API endpoints (POST /templates, GET /templates/{template_id}/status), `Template Versioning and Storage` (Schema setup).

**Epics & Tasks:**

1.  **Epic: Project Setup & FastAPI Core**
    *   Task: Initialize FastAPI project based on the "Proposed Project File Structure" in [`plan.md`](plan.md:1) (Section 9).
    *   Task: Implement basic application configuration (`mailwright/config.py`).
    *   Task: Set up `mailwright/main.py` with FastAPI app instance.
    *   Task: Define initial Pydantic schemas for API requests/responses and common statuses (`mailwright/schemas/`).
    *   Task: Implement basic logging setup.

2.  **Epic: Asynchronous Task Management Setup**
    *   Task: Choose and configure an asynchronous task queue (e.g., Celery with a broker like Redis/RabbitMQ, or FastAPI's built-in BackgroundTasks for simpler initial setup, to be decided based on scalability needs).
    *   Task: Define basic structure for task definitions (`mailwright/tasks/`).

3.  **Epic: Initial API Endpoints (Generation & Status)**
    *   Task: Implement `POST /templates` endpoint (as per [`plan.md`](plan.md:1) Section 3.9.1):
        *   Accepts `MJMLTemplateRequest` (initial version).
        *   Returns `202 Accepted` with `template_id`, `task_id`, `status_poll_url`.
        *   Triggers a placeholder asynchronous task for now (e.g., "brief_analysis_pending").
    *   Task: Implement `GET /templates/{template_id}/status` endpoint (as per [`plan.md`](plan.md:1) Section 3.9.3):
        *   Retrieves and returns the current status of the generation task.
        *   Implement initial status states (e.g., `pending_brief_analysis`).

4.  **Epic: Template Versioning & Storage (Database Setup)**
    *   Task: Define database models (`mailwright/db/models.py`) for the `TemplateStore` schema outlined in [`plan.md`](plan.md:1) (Section 3.7: `template_id`, `version_id`, `mjml_source`, `compiled_html`, etc.).
    *   Task: Set up database connection and basic CRUD operations for `TemplateStore` (`mailwright/db/template_store.py`).
    *   Task: Implement database migrations (if using a tool like Alembic).

---

### **Sprint 2: Initial Generation Flow (Brief to First MJML/HTML Version)**

*   **Goal:** Implement the `Brief Analyzer`, initial `MJML Generation Module`, `Image Generation Module`, and `MJML Validator/Compiler`. Integrate with `Template Versioning and Storage` to store the first generated version (v0).
*   **Key Components from [`plan.md`](plan.md:1):** `Brief Analyzer`, `MJML Generation Module` (initial generation), `Image Generation Module`, `MJML Validator and HTML Compiler`, `Template Versioning and Storage` (storing v0).

**Epics & Tasks:**

1.  **Epic: Brief Analyzer Service**
    *   Task: Implement `Brief Analyzer` service (`mailwright/core_services/brief_analyzer_service.py`).
    *   Task: Develop prompt for LLM to analyze brief and ask clarification questions (as per [`plan.md`](plan.md:1) Section 3.1).
    *   Task: Integrate LLM call within an asynchronous task.
    *   Task: Update `POST /templates` to trigger the `Brief Analyzer` async task.
    *   Task: Implement `PUT /templates/{template_id}/brief` endpoint for submitting amended briefs (as per [`plan.md`](plan.md:1) Section 3.9.2).
    *   Task: Update status polling to reflect `clarification_needed` or `pending_initial_generation`.

2.  **Epic: Image Generation Service**
    *   Task: Implement `Image Generation` service (`mailwright/core_services/image_generator_service.py`).
    *   Task: Integrate with DALL-E 3 (or chosen alternative) API via an asynchronous task.
    *   Task: Handle image prompt input and manage generated image asset URLs/storage.

3.  **Epic: MJML Generation Service (Initial Version)**
    *   Task: Implement `MJML Generation` service (`mailwright/core_services/mjml_service.py`) for initial generation.
    *   Task: Develop prompt for LLM to generate MJML from a clarified brief and image URLs (as per [`plan.md`](plan.md:1) Section 3.2).
    *   Task: Integrate LLM call within an asynchronous task.
    *   Task: Coordinate with `Image Generation` service if image prompts are part of the brief.

4.  **Epic: MJML Validation & Compilation Service**
    *   Task: Implement `MJML Validator and HTML Compiler` service (can be part of `mailwright/core_services/mjml_service.py` or `mailwright/utils/mjml_cli_utils.py`).
    *   Task: Integrate `mjml` CLI for validation and compilation to HTML (with inlined CSS) via a subprocess call within an asynchronous task.
    *   Task: Handle validation errors and update task status.

5.  **Epic: End-to-End Initial Generation & Storage**
    *   Task: Orchestrate the flow: Brief Analysis -> (Image Gen + MJML Gen) -> Validation/Compilation.
    *   Task: Upon successful compilation, store the initial MJML, compiled HTML, and image assets as v0 in `Template Versioning and Storage`.
    *   Task: Update task status to `ready_for_preview` and include `html_preview_url` and `mjml_source_url` (as per [`plan.md`](plan.md:1) Section 3.9.3).

---

### **Sprint 3: Iterative Refinement Loop**

*   **Goal:** Implement the `Feedback Engine`, enable the `MJML Generation Module` to handle revisions based on structured feedback, and provide the HTML preview mechanism.
*   **Key Components from [`plan.md`](plan.md:1):** `Feedback Engine`, `MJML Generation Module` (revisions), HTML Preview Service, `Template Versioning and Storage` (storing new versions).

**Epics & Tasks:**

1.  **Epic: HTML Preview Service**
    *   Task: Implement `GET /templates/{template_id}/versions/{version_id}/html` endpoint to serve compiled HTML from storage (as per [`plan.md`](plan.md:1) Section 3.9.4).
    *   Task: Implement `GET /templates/{template_id}/versions/{version_id}` endpoint to serve version details (MJML, assets, etc.).

2.  **Epic: Feedback Engine Service**
    *   Task: Implement `Feedback Engine` service (`mailwright/core_services/feedback_engine_service.py`).
    *   Task: Develop prompt for LLM to translate natural language feedback into structured change instructions (as per [`plan.md`](plan.md:1) Section 3.6).
    *   Task: Integrate LLM call within an asynchronous task.
    *   Task: Implement `POST /templates/{template_id}/feedback` endpoint (as per [`plan.md`](plan.md:1) Section 3.9.5).

3.  **Epic: MJML Generation Service (Revisions)**
    *   Task: Extend `MJML Generation` service to accept current MJML and structured change instructions.
    *   Task: Develop prompt for LLM to apply structured changes to existing MJML (as per [`plan.md`](plan.md:1) Section 3.2).
    *   Task: Integrate this revision capability into an asynchronous task.

4.  **Epic: End-to-End Refinement Loop & Versioning**
    *   Task: Orchestrate the flow: User Feedback -> Feedback Engine -> MJML Revision -> Validation/Compilation.
    *   Task: Upon successful revision and compilation, store the new MJML, HTML, and any new/updated image assets as a new version in `Template Versioning and Storage`.
    *   Task: Update task status to `ready_for_preview` for the new version.

---

### **Sprint 4: Approval & Beefree Integration (Phase 1.1)**

*   **Goal:** Implement the template approval mechanism and integrate with the Beefree HTML Importer API.
*   **Key Components from [`plan.md`](plan.md:1):** Beefree HTML Importer API Integration, Approval endpoint.

**Epics & Tasks:**

1.  **Epic: Template Approval Workflow**
    *   Task: Implement `POST /templates/{template_id}/versions/{version_id}/approve` endpoint (as per [`plan.md`](plan.md:1) Section 3.9.6).
    *   Task: Update the `is_approved` flag in `Template Versioning and Storage` for the approved version.

2.  **Epic: Beefree Importer Service**
    *   Task: Implement `Beefree Importer` service (`mailwright/core_services/beefree_service.py`).
    *   Task: Develop a Python client for the Beefree HTML Importer API.
    *   Task: Integrate API call within an asynchronous task, triggered upon template approval.
    *   Task: Handle API responses and update task status (e.g., `pending_beefree_import`, `import_to_beefree_complete`, `error_beefree_import`).

3.  **Epic: Documentation & Testing**
    *   Task: Write API documentation for all endpoints.
    *   Task: Develop unit and integration tests for all new services and workflows.
    *   Task: Update [`README.md`](README.md:1) to reflect the v2 system.