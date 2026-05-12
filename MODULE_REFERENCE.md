# Mailwright — Complete Module & Script Reference

> **Purpose of this document:** A file-by-file breakdown of every module and script in the project. For each file you will find: what it does, what it contains, how it connects to the rest of the system, and what to change/touch when adding a new feature.

---

## Table of Contents

1. [Application Entry & Routing](#1-application-entry--routing)
   - `mailwright/main.py`
   - `mailwright/api/v1/router.py`
   - `mailwright/api/v1/template_routes.py`
2. [Configuration](#2-configuration)
   - `mailwright/config.py`
   - `mailwright/logging_config.py`
3. [Schemas (Data Contracts)](#3-schemas-data-contracts)
   - `mailwright/schemas/template_schemas.py`
4. [LangGraph — The Workflow Engine](#4-langgraph--the-workflow-engine)
   - `mailwright/graphs/state.py`
   - `mailwright/graphs/checkpointer.py`
   - `mailwright/graphs/template_generation_graph.py`
5. [Core Services](#5-core-services)
   - `mailwright/core_services/llm_factory.py`
   - `mailwright/core_services/brief_analyzer_service.py`
   - `mailwright/core_services/mjml_service.py`
   - `mailwright/core_services/image_generator_service.py`
   - `mailwright/core_services/feedback_engine_service.py`
   - `mailwright/core_services/rag_template_service.py`
6. [Database Layer](#6-database-layer)
   - `mailwright/db/models.py`
   - `mailwright/db/template_store.py`
7. [Scripts — Operational Utilities](#7-scripts--operational-utilities)
   - `scripts/ingest_rag_corpus.py`
   - `scripts/clear_rag_db.py`
   - `scripts/extract_html.py`
   - `scripts/replace_media.py`
   - `scripts/manual_test_ingestion.py`
   - `scripts/diagnose_schema.py`
   - `scripts/test_openai_access.py`
8. [How Everything Connects — Dependency Map](#8-how-everything-connects--dependency-map)
9. [Adding New Features — Where to Touch What](#9-adding-new-features--where-to-touch-what)

---

## 1. Application Entry & Routing

### `mailwright/main.py`

**What it is:** The single entry point for the entire FastAPI application.

**What it does:**
- Creates the `FastAPI` app instance (`app`) with title and debug flag from `settings`
- Defines a `lifespan` context manager (runs at startup/shutdown):
  - **Startup:** creates an async SQLAlchemy engine and stores it on `app.state.db_engine`
  - **Shutdown:** disposes the engine cleanly, closing all DB connections
- Mounts the v1 API router under the `/api/v1` prefix
- Exposes a root `GET /` health greeting

**Key imports:** `settings` (config), `api_v1_router` (all routes), `setup_logging` (logging init)

**How to run it:**
```bash
uvicorn mailwright.main:app --reload --host 0.0.0.0 --port 8000
```

**When to edit this file:**
- Adding new top-level API version routers (e.g. `v2`)
- Adding global middleware (CORS, authentication, rate-limiting)
- Adding more startup logic (e.g. pre-warming a model, running checks)
- Changing app metadata (title, version, description shown in Swagger)

> **Important design note:** The DB engine is stored on `app.state.db_engine` and is picked up by `get_db_session` in `template_store.py`. If you change how the engine is created, update both files.

---

### `mailwright/api/v1/router.py`

**What it is:** The API v1 router — the switchboard that assembles all v1 endpoints.

**What it does:**
- Creates an `APIRouter` instance
- Registers a simple `GET /health` endpoint (returns `{"status": "ok"}`)
- Includes `template_routes.router` under the `/templates` prefix with the `"Templates"` tag

**Effective URL structure after mounting in `main.py`:**
```
/api/v1/health
/api/v1/templates/...
```

**When to edit this file:**
- Adding a new endpoint group (e.g. `GET /api/v1/users` → create `user_routes.py` and include it here)
- Changing the prefix or tags for the templates group

---

### `mailwright/api/v1/template_routes.py`

**What it is:** The core HTTP API layer. All user-facing endpoints live here.

**What it does — endpoint by endpoint:**

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `POST /templates` | `create_template_generation_task` | Validates request, generates a `template_id` UUID, builds initial `GraphState`, compiles and invokes the LangGraph, returns `template_id` + status |
| `GET /templates/{id}/status` | `get_template_task_status` | Checks DB for an approved version first; if none, loads LangGraph state snapshot and returns current status, preview URLs, clarification questions |
| `PUT /templates/{id}/brief` | `update_template_brief` | Injects an amended brief into the paused graph state via `aupdate_state`, then resumes execution with `ainvoke` |
| `GET /templates/{id}/versions` | `list_template_versions` | Queries DB for all `TemplateVersion` rows for the template, returns list with metadata and preview URLs |
| `GET /templates/{id}/versions/{ver}/html` | `get_template_version_html` | Fetches compiled HTML from DB and returns it as `HTMLResponse` |
| `GET /templates/{id}/versions/{ver}/mjml` | `get_template_version_mjml` | Fetches MJML source from DB and returns it as JSON |
| `POST /templates/{id}/versions/{ver}/feedback` | `submit_template_feedback` | Validates the version exists, injects feedback + MJML-of-version-being-revised into graph state, re-invokes graph (routes to feedback engine) |
| `POST /templates/{id}/versions/{ver}/approve` | `approve_specific_template_version` | Calls `approve_template_version` DB function which sets exactly one version's `is_approved = True` |

**Key patterns:**
- Every route that touches LangGraph uses `async with get_checkpointer_context_manager() as checkpointer:` — the graph is compiled fresh per request inside this context
- Every route that touches the DB uses `db: Annotated[AsyncSession, Depends(get_db_session)]` — FastAPI injects the session
- `template_id` and LangGraph `thread_id` are always the same UUID string

**When to edit this file:**
- Adding a new API endpoint for templates
- Changing request validation rules
- Changing what the status response includes
- Adding new interrupt points in the graph flow

---

## 2. Configuration

### `mailwright/config.py`

**What it is:** The single source of truth for all runtime configuration. **Read this before anything else.**

**What it does:**
- Uses `pydantic-settings` to define a `Settings` class
- All fields can be overridden by environment variables (case-insensitive) or by the `.env` file at project root
- The `settings` singleton is imported by every other module that needs configuration

**Complete field reference:**

| Field | Default | Purpose |
|-------|---------|---------|
| `APP_NAME` | `"Mailwright - Agentic Marketing Email Platform"` | Shown in Swagger UI |
| `DEBUG` | `False` | Enables SQLAlchemy SQL echo |
| `LOG_LEVEL` | `"INFO"` | Controls logging verbosity |
| `OPENAI_API_KEY` | `None` | Required for GPT models and DALL-E |
| `ANTHROPIC_API_KEY` | `None` | Required for Claude models |
| `DEFAULT_LLM_PROVIDER` | `"anthropic"` | Global fallback (not used by task-specific settings) |
| `BRIEF_ANALYZER_PROVIDER` | `"anthropic"` | Which LLM to use for brief analysis |
| `BRIEF_ANALYZER_OPENAI_MODEL` | `"gpt-4-turbo-preview"` | OpenAI model if provider = openai |
| `BRIEF_ANALYZER_ANTHROPIC_MODEL` | `"claude-sonnet-4-20250514"` | Anthropic model if provider = anthropic |
| `MJML_GENERATION_PROVIDER` | `"anthropic"` | Which LLM to use for MJML generation |
| `MJML_GENERATION_OPENAI_MODEL` | `"gpt-4-turbo-preview"` | — |
| `MJML_GENERATION_ANTHROPIC_MODEL` | `"claude-sonnet-4-20250514"` | — |
| `FEEDBACK_ENGINE_PROVIDER` | `"anthropic"` | Which LLM for feedback/revision |
| `FEEDBACK_ENGINE_OPENAI_MODEL` | `"gpt-4-turbo-preview"` | — |
| `FEEDBACK_ENGINE_ANTHROPIC_MODEL` | `"claude-sonnet-4-20250514"` | — |
| `IMAGE_GENERATION_PROVIDER` | `"openai"` | Must be `openai` (only DALL-E supported) |
| `IMAGE_GENERATION_OPENAI_DALLE_MODEL` | `"dall-e-3"` | DALL-E model version |
| `RAG_GENERATION_PROVIDER` | `"openai"` | LLM for RAG content population |
| `RAG_GENERATION_OPENAI_MODEL` | `"gpt-4o"` | — |
| `RAG_GENERATION_ANTHROPIC_MODEL` | `"claude-3-sonnet-20240229"` | — |
| `EMBEDDING_MODEL_NAME` | `"text-embedding-3-small"` | OpenAI embeddings model for RAG |
| `PROMPT_GENERATION_MODEL` | `"gpt-4o"` | Used by ingest script for fingerprint generation |
| `MJML_CLI_PATH` | `"mjml"` | Command or full path to the MJML CLI binary |
| `DATABASE_URL` | `None` | Async SQLAlchemy URL: `postgresql+asyncpg://...` |
| `LANGGRAPH_CHECKPOINTER_DB_URL` | `None` | Sync PostgreSQL URL for LangGraph checkpointer |
| `SQLITE_CHECKPOINTER_DB_FILE` | `data/langgraph_checkpoints.sqlite` | SQLite fallback path for checkpointer |

**When to edit this file:**
- Adding a new API key (e.g. for a new image provider)
- Adding a new per-task LLM configuration
- Adding any new environment-driven setting
- Changing default model names

> **Rule:** Never hardcode API keys or model names in any other file. Always add them here and import `settings`.

---

### `mailwright/logging_config.py`

**What it is:** Centralised logging setup — called once at startup.

**What it does:**
- `setup_logging()` reads `LOG_LEVEL` from environment / settings
- Calls `logging.basicConfig` with a detailed format string including timestamp, module, function name, and line number
- All logs go to `stdout` (console) — suitable for containerised/cloud deployments

**Log format:**
```
2026-04-29 18:00:00 - mailwright.api.v1.template_routes - INFO - template_routes.create_template_generation_task:48 - Starting...
```

**When to edit this file:**
- Adding a file-based log handler
- Adding structured JSON logging (for log aggregation systems)
- Silencing overly verbose third-party library loggers (add a `setLevel(WARNING)` call at the bottom)

**How to use in any module:**
```python
import logging
logger = logging.getLogger(__name__)
logger.info("My message")
```

---

## 3. Schemas (Data Contracts)

### `mailwright/schemas/template_schemas.py`

**What it is:** All Pydantic models that define the shape of API request and response bodies.

**Complete schema inventory:**

| Schema | Direction | Used by | Purpose |
|--------|-----------|---------|---------|
| `UserBriefSchema` | Request input | `TemplateCreationRequest`, `brief_analyzer_service` | Structured brief: subject, body_copy, image_suggestions, cta_text, cta_url |
| `TemplateCreationRequest` | Request | `POST /templates` | Wraps `user_brief` OR `plain_text_brief`; includes `rag_flow` flag; has a `model_validator` that enforces mutual exclusivity |
| `TemplateCreationResponseSchema` | Response | `POST /templates` | Returns `template_id`, `task_id`, `status`, `message`, `status_poll_url` |
| `TemplateStatusSchema` | Response | `GET /templates/{id}/status` | Full status including version ID, preview URLs, clarification questions, MJML/HTML content, approval status |
| `AmendedBriefRequest` | Request | `PUT /templates/{id}/brief` | Wraps a new `UserBriefSchema` plus an optional `brief_token` |
| `TemplateVersionBase` | Internal base | — | Shared fields for versioning schemas |
| `TemplateVersionCreate` | Internal | `template_store.create_template_version`, graph nodes | Used by nodes to build the DB record |
| `TemplateVersionResponse` | Response | — | DB version with `created_at` for ORM-mode serialisation |
| `VersionPreviewURLsSchema` | Nested response | `list_template_versions` | `{ "html": "...", "mjml": "..." }` |
| `VersionMetadataSchema` | Nested response | `list_template_versions` | One version's metadata: id, created_at, change_trigger, is_approved, preview_urls |
| `TemplateVersionListSchema` | Response | `GET /templates/{id}/versions` | Wraps a list of `VersionMetadataSchema` |
| `FeedbackRequestSchema` | Request | `POST /templates/{id}/versions/{ver}/feedback` | Single field: `feedback_text` |
| `ApprovalResponseSchema` | Response | `POST /templates/{id}/versions/{ver}/approve` | `template_id`, `approved_version_id`, `status`, `message` |

**When to edit this file:**
- Adding a new field to any API request or response
- Adding a new endpoint that needs new request/response shapes
- Adding validation rules (e.g. min/max length, regex patterns) to existing fields
- The `model_validator` in `TemplateCreationRequest` — touch this when adding a third workflow type

---

## 4. LangGraph — The Workflow Engine

### `mailwright/graphs/state.py`

**What it is:** The single shared memory object that flows between all graph nodes.

**What it does:**
Defines `GraphState` — a Pydantic model. Every LangGraph node receives a `GraphState` instance and returns either an updated `GraphState` or a dict of field updates. The checkpointer serialises this after every node.

**Field groups and their owners:**

| Group | Fields | Set by |
|-------|--------|--------|
| MJML workflow input | `user_brief_data`, `amended_brief_data`, `clarification_questions`, `clarification_rounds_count` | `brief_analyzer_node`, `wait_for_amended_brief_node`, API route |
| RAG workflow input | `rag_flow`, `plain_text_brief`, `use_placeholders` | API route |
| RAG intermediate | `brief_fingerprint`, `brief_embedding`, `retrieved_template_html`, `final_html_content` | RAG graph nodes |
| Image generation | `image_prompts`, `generated_image_urls`, `image_urls_map` | `image_generation_node` |
| MJML output | `current_mjml`, `compiled_html`, `mjml_validation_status` | `mjml_service` nodes |
| Storage | `stored_version_info`, `current_version_id_stored` | `store_v0_node`, `store_v_next_node` |
| Feedback loop | `user_feedback_content`, `version_id_for_feedback`, `revised_mjml_candidate` | API route, `feedback_engine_node` |
| Status | `last_operation_status`, `error_message` | Every node |
| Testing | `is_test_forcing_brief_ok` | Test fixtures only |

**When to edit this file:**
- Adding a new piece of data that needs to flow between nodes (add a new `Optional` field with a default)
- Every new node you create will need fields here for its outputs
- If you add fields, also update the Alembic migration if that data needs to be persisted to the DB

---

### `mailwright/graphs/checkpointer.py`

**What it is:** The factory that provides the persistence layer for LangGraph state.

**What it does:**
- Exports `get_checkpointer_context_manager()` — a function that returns an async context manager
- **If `LANGGRAPH_CHECKPOINTER_DB_URL` is set:** returns `AsyncPostgresSaver` (production mode)
- **Otherwise:** returns `AsyncSqliteSaver` (development/fallback mode)
- Handles the URL format difference: SQLAlchemy uses `postgresql+asyncpg://` but LangGraph's psycopg checkpointer needs `postgresql://` — the conversion is done here automatically

**Why this matters:**
Without the checkpointer, every API call would start the graph from scratch and the graph could not be paused and resumed. The checkpointer is what makes `PUT /brief` and `POST /feedback` work — they resume an existing paused run.

**Thread ID = Template ID:** The `thread_id` in LangGraph `config` is always set to `str(template_id)`. This ties a specific API resource to a specific checkpoint history.

**When to edit this file:**
- Switching to a different checkpointer backend (e.g. Redis)
- Tuning PostgreSQL connection pool settings
- If the LangGraph library changes its checkpointer API

---

### `mailwright/graphs/template_generation_graph.py`

**What it is:** The heart of the application. Defines every node, every edge, and every routing decision in the LangGraph workflow.

**Structure overview:**

```
CONSTANTS        — Node name strings (e.g. LG_START_NODE_NAME = "LG_Start")
SERVICE INSTANCES — module-level singletons: mjml_service, image_generator_service, feedback_service
NODE FUNCTIONS   — one async function per graph node
ROUTING FUNCTIONS — conditional edge functions (return the name of next node)
create_graph_builder() — assembles the StateGraph and returns the builder
run_graph()       — standalone test runner (not used by API)
RAG NODES        — three async functions for the RAG path (at bottom of file)
```

**Node-by-node breakdown:**

| Node function | Node name constant | What it does |
|---------------|-------------------|-------------|
| `start_node` | `LG_Start` | No-op pass-through; entry point for the MJML path |
| `brief_analyzer_node` | `LG_BriefAnalyzer` | Calls `analyze_brief_for_clarifications()`; sets `clarification_questions` or `BRIEF_OK` |
| `wait_for_amended_brief_node` | `LG_WaitForAmendedBrief` | Sets status to `WAITING_FOR_AMENDED_BRIEF`; this is the **interrupt point** — graph pauses here |
| `image_generation_node` | `LG_ImageGeneration` | Iterates `state.image_prompts`; calls `ImageGeneratorService.generate_image()` per prompt; accumulates URLs |
| `mjml_service.generate_mjml_node` | `LG_MJMLGeneration` | Calls LLM with brief + image URLs; strips markdown fences from response; validates `<mjml>...</mjml>` present |
| `mjml_service.validate_and_compile_mjml_node` | `LG_MJMLValidateCompile` | Writes MJML to temp file; spawns `mjml` CLI subprocess; parses return code + stderr; deletes temp file |
| `store_v0_node` | `LG_StoreV0` | Builds `TemplateVersionCreate`; calls `create_template_version()`; works for both MJML and RAG flows |
| `feedback_engine_node` | `LG_FeedbackEngine` | Calls `FeedbackEngineService.revise_mjml_based_on_feedback()`; stores result in `revised_mjml_candidate` |
| `store_v_next_node` | `LG_StoreVNext` | Same as StoreV0 but generates version ID `v_rev_{uuid[:8]}`; clears feedback fields after storing |
| `lg_rag_generate_brief_fingerprint_node` | `LG_RAG_GenerateBriefFingerprint` | Calls `RAGTemplateService.generate_fingerprint_for_brief()` then `.generate_embedding()` |
| `lg_rag_find_matching_template_node` | `LG_RAG_FindMatchingTemplate` | Calls `RAGTemplateService.find_best_matching_template()` with pgvector L2 distance search |
| `lg_rag_populate_content_node` | `LG_RAG_PopulateContent` | Calls `RAGTemplateService.populate_template_with_brief()` — extract/modify/inject pipeline |

**Routing functions (conditional edges):**

| Function | Decision point | Routes to |
|----------|---------------|-----------|
| `route_rag_or_legacy` | Entry from `START` | RAG fingerprint node OR MJML/feedback path |
| `route_initial_or_feedback` | Legacy path entry | `LG_FeedbackEngine` if feedback present, else `LG_BriefAnalyzer` |
| `should_request_clarification` | After brief analysis | `LG_WaitForAmendedBrief` if unclear, `LG_ImageGeneration` if OK, `END` on error |
| `did_mjml_generation_fail` | After MJML generation | `END` on failure, `LG_MJMLValidateCompile` on success |
| `should_route_after_validation` | After MJML validation | `LG_StoreVNext` if feedback loop, `LG_StoreV0` if initial, `END` on invalid/error |

**`create_graph_builder()` — the assembly function:**
Builds a `StateGraph(GraphState)`, adds all nodes, adds all edges (fixed and conditional), and returns the builder. **Every API route calls this and then `.compile(checkpointer=...)` before invoking.**

**When to edit this file:**
- Adding a new processing step → add a node function + add it to `create_graph_builder()`
- Changing routing logic → edit the relevant routing function
- Adding a new workflow path → add new node name constants, node functions, and wire them in `create_graph_builder()`
- Changing what is stored in a version → edit `store_v0_node` or `store_v_next_node`

---

## 5. Core Services

### `mailwright/core_services/llm_factory.py`

**What it is:** A single function factory that hides the difference between OpenAI and Anthropic clients.

**What it does:**
- `get_configured_chat_model(task_provider_config_value, task_openai_model_config_value, task_anthropic_model_config_value, temperature, **kwargs)` 
- Reads the `provider` string (`"openai"` or `"anthropic"`)
- Returns a `ChatOpenAI` or `ChatAnthropic` LangChain model instance
- Validates that the required API key is set (raises `ValueError` if not)
- For Anthropic, hardcodes `max_tokens=16384` — important for long HTML generation tasks

**Key design principle:** Every service passes its own task-specific provider + model settings. This means you can run brief analysis on Claude and MJML generation on GPT-4 simultaneously, configured entirely through `.env`.

**When to edit this file:**
- Adding support for a new LLM provider (e.g. Google Gemini):
  1. Add `elif provider == "google":` branch
  2. Add corresponding API key and model settings to `config.py`
  3. No other files need to change — all services will automatically pick up the new provider

---

### `mailwright/core_services/brief_analyzer_service.py`

**What it is:** The service that decides whether a user's email brief is clear enough to proceed.

**What it does:**
- Defines `BriefAnalysisResult` — a Pydantic model with `status`, `clarification_questions`, `error_message`
- `analyze_brief_for_clarifications(brief: UserBriefSchema, clarification_round: int)` — the main function:
  1. Gets an LLM via `get_configured_chat_model` using `BRIEF_ANALYZER_*` settings
  2. Builds a LangChain prompt chain with `LC_BRIEF_ANALYZER_PROMPT`
  3. **First round:** asks for 1–3 specific questions if anything is unclear
  4. **Subsequent rounds (`clarification_round >= 1`):** much more lenient — asks at most 1 question, proceeds with `BRIEF_OK` if close enough
  5. Parses the LLM's JSON response into a `BriefAnalysisResult`

**The prompt:** System: "Respond only in JSON." Human: provides the brief fields, asks LLM to return `{"status": "BRIEF_OK"}` or `{"clarification_questions": [...]}`.

**Return values:**
- `BriefAnalysisResult(status="BRIEF_OK")` — proceed with generation
- `BriefAnalysisResult(status="CLARIFICATION_NEEDED", clarification_questions=[...])` — pause and ask user
- `BriefAnalysisResult(status="ERROR", error_message="...")` — something went wrong

**When to edit this file:**
- Changing the clarification threshold (how aggressive it is at asking questions)
- Editing the prompt to ask about different brief qualities
- Adding new brief fields to the prompt (e.g. brand tone, target audience)
- Changing the number of clarification rounds allowed

---

### `mailwright/core_services/mjml_service.py`

**What it is:** A class (`MJMLService`) that owns two LangGraph nodes for MJML generation and compilation.

**What it does:**

**`generate_mjml_node(state: GraphState) → Dict`**
1. Picks the brief to use: `amended_brief_data` if set, else `user_brief_data`
2. Extracts `subject`, `body`, `call_to_action` from the brief dict
3. Formats any generated image URLs into a numbered list for the prompt
4. Invokes the LLM with `MJML_GENERATION_PROMPT_TEMPLATE` (the LLM is told to output only MJML from `<mjml>` to `</mjml>`)
5. Strips markdown code fences from LLM response (LLMs often wrap code in ` ```mjml `)
6. Basic validation: checks the response contains `<mjml>` and `</mjml>`
7. Returns `{"current_mjml": ..., "last_operation_status": "success"}` or an error dict

**`validate_and_compile_mjml_node(state: GraphState) → Dict`**
1. Checks for `revised_mjml_candidate` first (feedback path); falls back to `current_mjml` (initial path)
2. Writes the MJML to a temporary `.mjml` file
3. Runs `mjml <file> --config.validationLevel=strict` as a subprocess (async, non-blocking)
4. Parses exit code and stderr for errors
5. Returns compiled HTML on success, error info on failure
6. **Always** deletes the temp file in a `finally` block
7. **Always** clears `revised_mjml_candidate` after processing (so it doesn't persist to the next cycle)

**When to edit this file:**
- Changing the MJML generation prompt (`MJML_GENERATION_PROMPT_TEMPLATE`)
- Adding brand guidelines, layout preferences, or design system tokens to the prompt
- Changing MJML CLI flags (e.g. removing strict validation for development)
- Adding MJML-to-HTML post-processing (e.g. inlining CSS with another tool)

---

### `mailwright/core_services/image_generator_service.py`

**What it is:** A class (`ImageGeneratorService`) that wraps the OpenAI DALL-E image generation API.

**What it does:**
- `__init__`: Validates `OPENAI_API_KEY` is set; initialises `OpenAI` client synchronously; raises `NotImplementedError` for non-OpenAI providers (extension point)
- `generate_image(prompt, size, quality, n) → str | None`:
  1. Guards against empty prompts
  2. Calls `client.images.generate()` via `asyncio.to_thread()` — wraps the synchronous SDK in an async call
  3. Returns the URL of the first generated image
  4. Handles `RateLimitError` and `APIError` separately (returns `None` instead of crashing)

**Default parameters:** `size="1024x1024"`, `quality="standard"`, `n=1`

**Note:** DALL-E 3 only supports `n=1`. If you want multiple images, the graph's `image_generation_node` iterates over the list of `image_prompts` and calls this service once per prompt.

**When to edit this file:**
- Switching to a different image generation provider (Midjourney, Stability AI, etc.)
- Adding retry logic for rate limit errors
- Supporting HD quality: change `quality="hd"` in `generate_image()` call
- Supporting different aspect ratios: change the `size` parameter

---

### `mailwright/core_services/feedback_engine_service.py`

**What it is:** A class (`FeedbackEngineService`) that takes existing MJML + user feedback and produces revised MJML.

**What it does:**
- `__init__`: Gets an LLM via the factory using `FEEDBACK_ENGINE_*` settings; raises `FeedbackEngineServiceError` if init fails
- `revise_mjml_based_on_feedback(current_mjml: str, feedback_text: str) → str`:
  1. Guards against empty inputs
  2. Builds a prompt: "You are an expert MJML designer. Here is the original MJML. Here is the feedback. Output only the revised MJML."
  3. Calls `llm_client.ainvoke(formatted_prompt)` directly (not a chain)
  4. Strips markdown code fences from the response
  5. Returns the cleaned revised MJML string
  6. Raises `FeedbackEngineServiceError` on failure (the calling node catches this)

**Custom exception:** `FeedbackEngineServiceError(Exception)` — allows callers to catch feedback-specific errors separately from general exceptions.

**When to edit this file:**
- Tuning the feedback revision prompt (e.g. adding rules like "preserve the layout structure")
- Adding context about the brand or design system to the prompt
- Adding a check to ensure the revised MJML still contains the original CTA URL (anti-hallucination guard)
- Adding multi-step revision (e.g. ask for diff first, then apply)

---

### `mailwright/core_services/rag_template_service.py`

**What it is:** The most complex service — handles the entire RAG workflow from fingerprinting to content injection.

**What it does — function by function:**

**`_extract_editable_content(soup) → dict` (module-level helper)**
- Walks the BeautifulSoup tree to find all editable text nodes and CSS colour values
- Tags each element with a temporary `data-Mailwright-temp-id` attribute for later injection
- Returns a `content_map` dict: `{"text_elements": [...], "style_elements": [...]}`
- Text elements: `{"id": "Mailwright-text-0", "tag": "p", "current_text": "..."}`
- Style elements (from `<style>` blocks): `{"id": "Mailwright-style-0", "selector": ".btn", "property": "background-color", "current_value": "#123456"}`
- Style elements (inline): `{"id": "Mailwright-style-inline-0", "selector": "inline-td-0", "property": "color", "current_value": "..."}`

**`_inject_content(soup, updated_content_map) → str` (module-level helper)**
- Receives the LLM's updated content map (with `new_text` and `new_value` fields added)
- Finds each element by its `data-Mailwright-temp-id` attribute and replaces text / updates styles
- Handles both `<style>` block updates (regex-based CSS property replacement) and inline style updates
- Cleans up all temporary `data-Mailwright-temp-id` attributes before returning final HTML string

**`RAGTemplateService` class:**

| Method | What it does |
|--------|-------------|
| `generate_fingerprint_for_brief(brief)` | LLM converts plain-text brief to a structured fingerprint string (same format as ingested templates) using a detailed system prompt with controlled vocabulary |
| `generate_embedding(text)` | Calls OpenAI Embeddings API (`text-embedding-3-small`) to get a 1536-float vector |
| `find_best_matching_template(embedding, use_placeholders)` | pgvector L2 distance query on `rag_templates` table; returns `processed_html` (placeholders) or `raw_html` |
| `populate_template_with_brief(template_html, brief)` | **Primary method:** Extract content map → LLM modifies content map → inject back into HTML. Falls back to legacy method on failure |
| `populate_template_with_brief_legacy(template_html, brief)` | **Fallback:** Sends the entire HTML + brief to LLM and asks it to populate directly. Less precise, kept as safety net |

**The two-step population approach (primary method):**
```
HTML → _extract_editable_content() → content_map (JSON, small)
                                           ↓
                                    LLM adds new_text/new_value fields
                                           ↓
HTML + updated content_map → _inject_content() → final populated HTML
```
This is more reliable than sending the whole HTML to the LLM because:
1. The LLM only modifies a small JSON payload, not raw HTML
2. The HTML structure is never at risk of LLM hallucination
3. Faster and cheaper (smaller input/output)

**When to edit this file:**
- Changing the fingerprint vocabulary (the controlled vocabulary in both `generate_fingerprint_for_brief` and `ingest_rag_corpus.py` must match)
- Tuning the content population prompt (improving how well the LLM maps brief content to template slots)
- Adding support for populating image alt-text or links (currently only text and colours are updated)
- Switching from L2 distance to cosine distance in `find_best_matching_template` (change `.l2_distance` to `.cosine_distance`)

---

## 6. Database Layer

### `mailwright/db/models.py`

**What it is:** SQLAlchemy ORM model definitions + async engine/session factory.

**Models:**

**`TemplateVersion`** (`template_versions` table)

| Column | Type | Notes |
|--------|------|-------|
| `template_id` | Text (PK) | UUID as string; shared with LangGraph thread_id |
| `version_id` | Text (PK) | `"v0"`, `"v_rev_a1b2c3d4"` etc.; composite PK with template_id |
| `mjml_source` | Text | Empty string for RAG flow versions |
| `compiled_html` | Text | The final HTML sent to the user |
| `user_brief_snapshot` | JSONB | Snapshot of the brief at generation time |
| `image_assets` | JSONB | `{"urls": ["https://..."]}` |
| `change_trigger` | JSONB | `{"event": "initial_generation"}` or `{"event": "feedback_revision", "source_version_id": "v0"}` |
| `created_at` | DateTime | Server-side default `NOW()` |
| `is_approved` | Boolean | At most one `True` per `template_id` |

**`RAGTemplate`** (`rag_templates` table)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-increment |
| `template_name` | Text | Filename without extension |
| `raw_html` | Text | Original HTML from the JSON source file |
| `processed_html` | Text | HTML with placeholder images |
| `fingerprint_embedding` | Vector(1536) | pgvector column for similarity search |

**Engine / session setup (at module level):**
- If `settings.DATABASE_URL` is set: creates `async_engine` and `AsyncSessionLocal` sessionmaker
- If not set: logs a warning and sets both to `None`
- `AsyncSessionLocal` is imported directly by graph nodes (`store_v0_node`, `store_v_next_node`, RAG nodes) for DB operations within the graph

**When to edit this file:**
- Adding a new column to `TemplateVersion` → add the `Column` here AND create an Alembic migration
- Adding a new DB table → define a new class inheriting `Base` here AND create an Alembic migration
- Do not run `Base.metadata.create_all()` manually — Alembic owns migrations

---

### `mailwright/db/template_store.py`

**What it is:** All database query functions (CRUD operations) for the `template_versions` table.

**Functions:**

| Function | What it does |
|----------|-------------|
| `get_db_session(request)` | FastAPI dependency — creates a session from `app.state.db_engine`; yields it; auto-closes after request |
| `create_template_version(db, version_data)` | INSERTs a new `TemplateVersion` row; commits; refreshes; returns the ORM object |
| `get_template_version(db, template_id, version_id)` | SELECT by composite PK; returns `Optional[TemplateVersion]` |
| `get_all_template_versions_for_template_id(db, template_id)` | SELECT all versions for a template; ordered by `created_at DESC` (newest first) |
| `approve_template_version(db, template_id, version_id_to_approve)` | Two-step atomic transaction: (1) UPDATE all versions for template → `is_approved=False`, (2) UPDATE target version → `is_approved=True`; rollbacks on error |
| `get_approved_template_version_for_template(db, template_id)` | SELECT the single version where `is_approved IS TRUE`; returns `None` if none approved |

**Two session patterns in use:**

1. **API routes** use `Depends(get_db_session)` — the session comes from `app.state.db_engine`
2. **Graph nodes** use `async with AsyncSessionLocal() as session:` — the session comes from the module-level sessionmaker in `models.py`

This is a known inconsistency. Both work, but if you ever want to change the DB connection, you need to update both.

**When to edit this file:**
- Adding a new DB query (e.g. `search_versions_by_date_range`, `get_version_count_for_template`)
- Adding soft-delete, archive, or export functionality
- Adding pagination to `get_all_template_versions_for_template_id`

---

## 7. Scripts — Operational Utilities

These scripts are standalone tools run from the command line. They are **not** part of the API.

---

### `scripts/ingest_rag_corpus.py`

**Purpose:** One-time (or on-demand) script to populate the `rag_templates` database table from a directory of JSON template files.

**Reads from:** `ingest/` directory (create it and copy/symlink your JSON files there)

**What it does — in order:**
1. Validates `OPENAI_API_KEY` and `DATABASE_URL` are set
2. Scans `ingest/` for `*.json` files
3. For each file:
   - Extracts `html_data` (the raw email HTML)
   - **`process_html(raw_html)`:** downloads each `<img>` src, gets real pixel dimensions, replaces src with `placehold.co/{W}x{H}` placeholder; replaces `<a class="video-preview">` blocks with plain placeholder divs
   - **`generate_fingerprint_and_embedding(llm_client, processed_html, template_metadata)`:** calls GPT-4o with a detailed structural analysis prompt; then calls OpenAI Embeddings API on the fingerprint string; returns a 1536-float vector
   - Creates a `RAGTemplate` ORM object and stages it with `session.add()`
4. Commits all staged records in a single transaction at the end

**How to run:**
```bash
mkdir ingest
cp templates/*.json ingest/   # or just a subset to test
python scripts/ingest_rag_corpus.py
```

**Important:** The structural fingerprint vocabulary in this script and in `rag_template_service.py` must stay identical. If you update one, update the other.

**When to edit this file:**
- Adding new template sources (different JSON format → update HTML extraction)
- Changing the fingerprint format (also update `rag_template_service.py`)
- Adding batch size control (currently commits all at once)
- Adding a check to skip already-ingested templates (no de-duplication currently)

---

### `scripts/clear_rag_db.py`

**Purpose:** Wipe all records from the `rag_templates` table. Use before re-ingesting from scratch.

**Important:** The `DATABASE_URL` is **hardcoded** in this script as `postgresql+asyncpg://postgres:postgres@localhost:5432/Mailwright`. Edit it before running if your DB is different.

**How to run:**
```bash
python scripts/clear_rag_db.py
```

**What it does:** Executes `DELETE FROM rag_templates` inside a transaction and commits.

**When to edit this file:**
- Changing the hardcoded `DATABASE_URL` to read from `.env` instead (improvement opportunity)
- Adding a confirmation prompt before deletion (safety improvement)

---

### `scripts/extract_html.py`

**Purpose:** Debugging tool — fetches the `processed_html` for a specific template from the `rag_templates` DB table and saves it to a file.

**What it does:**
- Reads `DATABASE_URL` from `.env`
- Connects via `psycopg2` (synchronous)
- Queries `SELECT processed_html FROM rag_templates WHERE template_name = %s`
- Saves the HTML to `output/{template_name}.html`

**Usage:** Edit the `TEMPLATE_NAME` variable at the bottom of the file, then run:
```bash
python scripts/extract_html.py
```

**When to use it:**
- You want to visually inspect what a stored template looks like
- You want to test the placeholder replacement visually before running the full RAG pipeline
- Debugging why a particular template is or isn't being matched

---

### `scripts/replace_media.py`

**Purpose:** Advanced post-processing tool — takes an HTML file with `placehold.co` placeholder images and replaces them with real AI-generated DALL-E images that are contextually appropriate.

**What it does:**
1. Reads an HTML file from `output/test-movie-premier.html` (hardcoded, edit before use)
2. **`generate_global_context(html_content)`:** sends all text content to GPT-4o to get a one-sentence theme summary of the whole email
3. For each `placehold.co` image:
   - Extracts the dimensions from the URL (e.g. `600x400`)
   - Determines the best DALL-E size: `1792x1024` (landscape), `1024x1792` (portrait), or `1024x1024` (square)
   - **`generate_detailed_image_prompt(global_context, local_html_snippet, image_attrs)`:** sends the surrounding HTML `<td>` or `<div>` as context + the global theme to GPT-4o; gets back a specific DALL-E prompt
   - Calls `ImageGeneratorService.generate_image()` with the contextual prompt
   - Replaces `img["src"]` with the new DALL-E URL
4. Saves result to `output/test-movie-premier-replaced.html`

**When to use it:** When you want to go from a placeholder-based RAG result to a fully designed email with real images. This is a semi-automated image replacement pipeline.

**When to edit this file:**
- Changing `INPUT_HTML_PATH` / `OUTPUT_HTML_PATH` to different templates
- This script demonstrates a pattern that could be integrated directly into the API as a post-processing step

---

### `scripts/manual_test_ingestion.py`

**Purpose:** Debugging tool — tests the old JSON-based structural fingerprint logic against a real template file. Does not use the LLM or database.

**What it does:**
- Reads `templates/abandoned-cart.json`
- Walks the `json_data.page.rows` structure (the Bee editor's JSON schema)
- Maps each module type to a tag (e.g. `paragraph → [text]`, `button → [button]`)
- Prints a fingerprint string like `[1-col][text][button] [2-col][image][text]`
- Logs every step verbosely with `print()` statements (intentional for debugging)

**Note:** This represents an **older fingerprint approach** based on the Bee JSON structure rather than the current HTML-based LLM approach. It is not used in the live pipeline. Useful as a reference for understanding the template JSON schema.

**When to use it:** When inspecting the raw JSON structure of a template to understand what data is available for fingerprinting.

---

### `scripts/diagnose_schema.py`

**Purpose:** Deep diagnostic tool — recursively finds and pretty-prints all `columns` arrays anywhere in a template's JSON structure.

**What it does:**
- Reads `templates/abandoned-cart.json`
- Recursively walks every dict and list
- Whenever it finds a key named `"columns"`, prints the path and the column contents
- Helps you understand exactly where the column/module data is nested in the Bee JSON schema

**When to use it:** When you're confused about the structure of a template JSON file and want to see all the column data at once.

---

### `scripts/test_openai_access.py`

**Purpose:** Quick connectivity test — verifies that your `OPENAI_API_KEY` is valid and can reach the API.

**What it does:**
1. Reads `OPENAI_API_KEY` from settings
2. **Test 1:** Calls `aclient.models.list()` and prints the first 5 models
3. **Test 2:** Sends `"Hello, world! This is a test."` to the configured model with `max_tokens=50`
4. Prints the response

**Note:** This script references `settings.OPENAI_MODEL_NAME` which does not appear to exist in the current `config.py`. If you run this and get an `AttributeError`, add `OPENAI_MODEL_NAME: str = "gpt-4o"` to `config.py`, or replace the reference directly in the script.

**How to run:**
```bash
python scripts/test_openai_access.py
```

**When to use it:** First thing to run when setting up a new environment to confirm your API key works.

---

## 8. How Everything Connects — Dependency Map

```
main.py
  └─► api/v1/router.py
        └─► api/v1/template_routes.py
              ├─► schemas/template_schemas.py         (request/response types)
              ├─► graphs/template_generation_graph.py (invoke the graph)
              │     ├─► graphs/state.py               (shared memory)
              │     ├─► graphs/checkpointer.py        (state persistence)
              │     ├─► core_services/brief_analyzer_service.py
              │     │     └─► core_services/llm_factory.py
              │     ├─► core_services/mjml_service.py
              │     │     └─► core_services/llm_factory.py
              │     ├─► core_services/image_generator_service.py
              │     ├─► core_services/feedback_engine_service.py
              │     │     └─► core_services/llm_factory.py
              │     ├─► core_services/rag_template_service.py
              │     │     ├─► core_services/llm_factory.py
              │     │     └─► db/models.py             (RAGTemplate ORM)
              │     └─► db/models.py                   (AsyncSessionLocal)
              │           └─► db/template_store.py
              └─► db/template_store.py                (DB queries via Depends)
                    └─► db/models.py

config.py      ←── imported by almost everything (settings singleton)
logging_config.py ←── called once in main.py; logger = getLogger(__name__) everywhere else
```

**Scripts are standalone — they import from `mailwright.*` but are not imported by `mailwright.*`:**
```
scripts/ingest_rag_corpus.py → mailwright/config.py, mailwright/db/models.py, mailwright/logging_config.py
scripts/clear_rag_db.py      → standalone (hardcoded DB URL)
scripts/extract_html.py      → mailwright/config.py (via .env)
scripts/replace_media.py     → mailwright/config.py, mailwright/core_services/image_generator_service.py
scripts/test_openai_access.py → mailwright/config.py, mailwright/logging_config.py
```

---

## 9. Adding New Features — Where to Touch What

### Add a new LLM task (e.g. "Subject Line Generator")

1. **`mailwright/config.py`** — add `SUBJECT_LINE_PROVIDER`, `SUBJECT_LINE_OPENAI_MODEL`, `SUBJECT_LINE_ANTHROPIC_MODEL`
2. **`mailwright/core_services/`** — create `subject_line_service.py` with a class that calls `get_configured_chat_model(...)`
3. **`mailwright/graphs/state.py`** — add `generated_subject_line: Optional[str]` field
4. **`mailwright/graphs/template_generation_graph.py`** — add node function + add it to `create_graph_builder()`
5. **`mailwright/schemas/template_schemas.py`** — add field to response schema if you want to expose it via API

---

### Add a new API endpoint (e.g. `GET /templates/{id}/export`)

1. **`mailwright/api/v1/template_routes.py`** — add the route handler function
2. **`mailwright/schemas/template_schemas.py`** — add request/response schemas if needed
3. **`mailwright/db/template_store.py`** — add a new DB query function if the endpoint reads from DB

---

### Add a new LLM provider (e.g. Google Gemini)

1. **`requirements.txt`** — add `langchain-google-genai`
2. **`mailwright/config.py`** — add `GOOGLE_API_KEY` and per-task `*_GOOGLE_MODEL` settings
3. **`mailwright/core_services/llm_factory.py`** — add `elif provider == "google":` branch
4. No other files need to change

---

### Add a new image generation provider (e.g. Stability AI)

1. **`requirements.txt`** — add the SDK
2. **`mailwright/config.py`** — add API key and model settings
3. **`mailwright/core_services/image_generator_service.py`** — add `elif provider == "stability":` branch in `__init__` and `generate_image`

---

### Add a new database column to template_versions

1. **`mailwright/db/models.py`** — add the `Column(...)` definition
2. **Terminal:** `alembic revision --autogenerate -m "add column xyz"` — creates the migration file
3. **Terminal:** `alembic upgrade head` — applies it
4. **`mailwright/schemas/template_schemas.py`** — add the field to `TemplateVersionBase` if you want it exposed via API
5. **`mailwright/db/template_store.py`** — update `create_template_version` if the new column needs to be set explicitly

---

### Add a new RAG corpus source (different JSON format)

1. **`scripts/ingest_rag_corpus.py`** — update the HTML extraction logic (currently reads `template_data.get("html_data")`)
2. Possibly update `process_html()` if the new format has different media types
3. The rest of the pipeline (fingerprinting, embedding, storage) requires no changes

---

*This document was generated based on full source code analysis. Last updated: April 2026.*
