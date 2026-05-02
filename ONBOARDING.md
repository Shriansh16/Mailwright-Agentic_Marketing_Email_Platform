# Xyra — Complete Onboarding Guide

> **Purpose of this document:** A ground-up walkthrough for anyone new to this project. By the end you should understand what Xyra does, how every piece fits together, how to run it locally, and how to develop and test confidently.

---

## Table of Contents

1. [What Is Xyra?](#1-what-is-xyra)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Tech Stack at a Glance](#3-tech-stack-at-a-glance)
4. [Repository Structure](#4-repository-structure)
5. [Two Core Workflows Explained](#5-two-core-workflows-explained)
   - 5a. Legacy MJML Generation Workflow
   - 5b. RAG-Based HTML Generation Workflow
6. [LangGraph — The Orchestration Engine](#6-langgraph--the-orchestration-engine)
7. [API Endpoints Reference](#7-api-endpoints-reference)
8. [Database Layer](#8-database-layer)
9. [Configuration Reference](#9-configuration-reference)
10. [Local Setup — Step by Step](#10-local-setup--step-by-step)
11. [Running the Application](#11-running-the-application)
12. [End-to-End Use Case Walkthrough](#12-end-to-end-use-case-walkthrough)
13. [Testing](#13-testing)
14. [Code Patterns & Conventions](#14-code-patterns--conventions)
15. [Sprint History & Current State](#15-sprint-history--current-state)
16. [Common Issues & Debugging Tips](#16-common-issues--debugging-tips)
17. [Key Files Quick Reference](#17-key-files-quick-reference)

---

## 1. What Is Xyra?

**Xyra (Xyra Marketing Content Agent)** is a **FastAPI microservice** that generates production-ready marketing **email templates** using AI.

A user provides a creative brief — describing what the email should say, its call-to-action, and visual ideas. Xyra then:

- Analyses the brief for clarity (asking follow-up questions if it is ambiguous).
- Optionally generates images via DALL-E.
- Generates an MJML email template using an LLM (GPT-4 or Claude).
- Compiles the MJML to responsive HTML.
- Stores versioned results in PostgreSQL.
- Allows the user to iterate via a feedback loop.
- Lets the user approve a final version when satisfied.

Alternatively, Xyra can skip the MJML path entirely and use a **RAG (Retrieval-Augmented Generation)** pipeline: it finds the most structurally similar template from a pre-indexed corpus of ~1,600 real email templates and uses an LLM to fill in the user's content — producing HTML directly and very quickly.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT / API CONSUMER                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  HTTP (REST)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     FastAPI  (xyra/main.py)                           │
│                     Prefix: /api/v1                                   │
│                     Routes: xyra/api/v1/template_routes.py            │
└──────────┬───────────────────────────────────────┬───────────────────┘
           │                                       │
           │ LangGraph graph.ainvoke()             │ SQLAlchemy async
           ▼                                       ▼
┌────────────────────────┐              ┌──────────────────────────────┐
│  LangGraph State       │              │        PostgreSQL              │
│  Machine               │              │                               │
│  (graphs/)             │◄────────────►│  • template_versions table    │
│                        │  checkpoint  │  • rag_templates table        │
│  Nodes call:           │  save/load   │  • LangGraph checkpoints      │
│  • brief_analyzer_svc  │              └──────────────────────────────┘
│  • mjml_service        │
│  • image_generator_svc │              ┌──────────────────────────────┐
│  • feedback_engine_svc │─────────────►│  External LLM Providers       │
│  • rag_template_svc    │              │  • OpenAI (GPT-4, DALL-E 3)   │
└────────────────────────┘              │  • Anthropic (Claude)         │
                                        └──────────────────────────────┘
                                        ┌──────────────────────────────┐
                                        │  MJML CLI (Node.js)           │
                                        │  subprocess via mjml_service  │
                                        └──────────────────────────────┘
```

**Key insight:** the `template_id` (a UUID) doubles as LangGraph's `thread_id`. Every API call for the same template reuses the same persisted graph state.

---

## 3. Tech Stack at a Glance

| Layer | Technology |
|-------|-----------|
| API server | **FastAPI** + **Uvicorn** |
| Workflow orchestration | **LangGraph** (stateful state machine) |
| LLM providers | **OpenAI** (GPT-4, DALL-E 3) and/or **Anthropic** (Claude) |
| Email markup | **MJML** (compiled via CLI subprocess) |
| Database | **PostgreSQL** with `asyncpg` driver |
| ORM / migrations | **SQLAlchemy** (async) + **Alembic** |
| Vector search (RAG) | **pgvector** + **sentence-transformers** |
| HTML parsing (RAG) | **BeautifulSoup4** |
| Settings | **pydantic-settings** (`.env` file) |
| Linting | **Ruff** |
| Testing | **pytest** + **pytest-asyncio** |
| Language | **Python 3.10+** |

---

## 4. Repository Structure

```
Xyra_Templates/
│
├── xyra/                          # Main Python package — all application code
│   ├── main.py                    # FastAPI app creation and lifespan setup
│   ├── config.py                  # pydantic-settings: all env vars live here
│   ├── templates_api.py           # ⚠ Legacy / orphan — not used by main.py
│   │
│   ├── api/v1/
│   │   ├── router.py              # Mounts /templates routes + /health
│   │   └── template_routes.py    # All HTTP endpoint handlers
│   │
│   ├── graphs/
│   │   ├── state.py               # GraphState Pydantic model (workflow memory)
│   │   ├── checkpointer.py        # Postgres or SQLite checkpointer factory
│   │   └── template_generation_graph.py  # All LangGraph nodes, edges, routing
│   │
│   ├── core_services/
│   │   ├── brief_analyzer_service.py     # LLM call: is the brief clear?
│   │   ├── mjml_service.py               # LLM generates MJML; CLI compiles it
│   │   ├── image_generator_service.py    # DALL-E image generation
│   │   ├── feedback_engine_service.py    # LLM revises MJML from user feedback
│   │   ├── rag_template_service.py       # Embedding, vector search, HTML fill
│   │   └── llm_factory.py               # Provider-agnostic LLM client factory
│   │
│   ├── db/
│   │   ├── models.py              # SQLAlchemy ORM models
│   │   └── template_store.py      # CRUD helpers (create, get, approve, etc.)
│   │
│   └── schemas/
│       └── template_schemas.py    # Pydantic request/response models for API
│
├── alembic/                       # Database migration scripts
│   └── versions/                  # Individual migration files
│
├── templates/                     # ~1,599 Bee-style JSON email templates
│                                  # Used as the RAG corpus (ingested by scripts)
│
├── scripts/
│   ├── ingest_rag_corpus.py       # Load templates/ into rag_templates DB table
│   ├── clear_rag_db.py            # Wipe the RAG table
│   └── ...                        # Other utility and diagnostic scripts
│
├── tests/
│   ├── unit/                      # Isolated service/component tests
│   ├── integration/               # Full graph workflow tests
│   └── api/v1/                    # HTTP endpoint tests
│
├── docs/                          # Sprint notes and architecture documents
├── archive/                       # Legacy code (excluded from packaging)
│
├── pyproject.toml                 # Build config, Ruff, pytest settings
├── requirements.txt               # All runtime dependencies
├── alembic.ini                    # Alembic configuration
└── README.md                      # Original developer guide
```

---

## 5. Two Core Workflows Explained

### 5a. Legacy MJML Generation Workflow

**When to use:** Client wants a brand-new, fully custom email design generated from scratch.

**Input:**
```json
{
  "user_brief": {
    "subject": "Summer Sale — 50% Off Everything!",
    "body_copy": "Huge discounts across all product lines. Shop now before stock runs out.",
    "cta_text": "Shop the Sale",
    "cta_url": "https://example.com/sale",
    "image_suggestions": ["bright summer beach scene", "product collage"]
  }
}
```

**What happens internally:**

```
POST /api/v1/templates
        │
        ▼
[LG_Start] — initialises state with user_brief_data
        │
        ▼ (route_rag_or_legacy → legacy path)
[LG_BriefAnalyzer]
  • Calls LLM: "Is this brief clear enough to generate a great email?"
  • If ambiguous → sets clarification_questions in state
  • If clear → status = BRIEF_OK
        │
        ├── BRIEF_OK ──────────────────────────────────────────────────┐
        │                                                               │
        └── CLARIFICATION_NEEDED                                        │
                │                                                       │
        [LG_WaitForAmendedBrief]   ← INTERRUPT POINT                   │
          • Graph pauses here                                           │
          • Client calls PUT /{id}/brief with answers                  │
          • Graph resumes → back to LG_BriefAnalyzer                   │
                                                                        │
                                                          [LG_ImageGeneration]
                                                            • For each image suggestion
                                                              calls DALL-E 3
                                                            • Stores URLs in state
                                                                        │
                                                          [LG_MJMLGeneration]
                                                            • LLM generates full
                                                              MJML source using brief
                                                              + image URLs
                                                                        │
                                                          [LG_MJMLValidateCompile]
                                                            • Calls MJML CLI subprocess
                                                            • Validates MJML syntax
                                                            • Compiles to HTML
                                                                        │
                                                    ┌──────── VALID ────┤
                                                    │                   └── INVALID → END (error)
                                          [LG_StoreV0]
                                            • Writes to template_versions table
                                            • version_id = "v0"
                                                    │
                                                   END
```

**Result:** `template_id` with status `SUCCESS_STORED_V0`. Client can then call `GET /{id}/versions/v0/html` to preview.

---

### 5b. RAG-Based HTML Generation Workflow

**When to use:** Client wants a fast result based on an existing template style. No MJML, no image generation.

**Input:**
```json
{
  "rag_flow": true,
  "plain_text_brief": "Create a product launch email for our new wireless headphones. Target audience: tech-savvy millennials. Tone: energetic. Include a 20% discount offer.",
  "use_placeholders": false
}
```

**What happens internally:**

```
POST /api/v1/templates
        │
        ▼ (route_rag_or_legacy → RAG path)
[LG_RAG_GenerateBriefFingerprint]
  • LLM extracts structural fingerprint from plain_text_brief
    e.g. "product launch, single product, discount CTA, 2-column layout"
  • Generates vector embedding of the fingerprint
        │
        ▼
[LG_RAG_FindMatchingTemplate]
  • Queries rag_templates table using pgvector cosine similarity
  • Returns the HTML of the closest matching template from corpus
        │
        ▼
[LG_RAG_PopulateContent]
  • LLM receives: retrieved template HTML + user's plain_text_brief
  • Fills in all editable text, headlines, CTAs with user's content
  • Returns final_html_content
        │
        ▼
[LG_StoreV0]
  • Stores final HTML in template_versions
  • mjml_source = "" (none for RAG flow)
        │
       END
```

**Result:** A ready-to-use HTML email, generated in seconds by adapting a real template.

> **Note:** Before RAG works, you must ingest the corpus: `python scripts/ingest_rag_corpus.py`

---

## 6. LangGraph — The Orchestration Engine

LangGraph is the heart of Xyra. Think of it as a **resumable state machine**.

### GraphState — the shared memory

Every node reads from and writes to a single `GraphState` object. It is persisted to PostgreSQL (or SQLite as fallback) after every node execution.

```python
# xyra/graphs/state.py (simplified)
class GraphState(BaseModel):
    # Input
    user_brief_data: Optional[Dict]          # MJML workflow input
    plain_text_brief: Optional[str]          # RAG workflow input
    rag_flow: bool = False                   # Which workflow to use

    # Brief analysis
    clarification_questions: Optional[list[str]]
    clarification_rounds_count: int = 0
    amended_brief_data: Optional[Dict]

    # Image generation
    image_prompts: Optional[list[str]]
    generated_image_urls: Optional[list[str]]
    image_urls_map: Optional[Dict]

    # MJML outputs
    current_mjml: Optional[str]
    compiled_html: Optional[str]
    mjml_validation_status: Optional[str]    # "VALID" | "INVALID" | "ERROR"

    # Storage
    stored_version_info: Optional[Dict]
    current_version_id_stored: Optional[str]

    # Feedback loop (Sprint 3)
    user_feedback_content: Optional[str]
    version_id_for_feedback: Optional[str]
    revised_mjml_candidate: Optional[str]

    # RAG workflow (Sprint 5)
    brief_fingerprint: Optional[str]
    brief_embedding: Optional[list[float]]
    retrieved_template_html: Optional[str]
    final_html_content: Optional[str]
    use_placeholders: bool = False

    # Status tracking
    last_operation_status: Optional[str]
    error_message: Optional[str]
```

### Checkpointer — persistence and resumability

The checkpointer saves state between API calls. When a user submits feedback or an amended brief, the graph loads the previously saved state and continues exactly where it left off.

- **Production:** `AsyncPostgresSaver` (set `LANGGRAPH_CHECKPOINTER_DB_URL`)
- **Dev/fallback:** `AsyncSqliteSaver` (file at `data/langgraph_checkpoints.sqlite`)

### Thread ID = Template ID

Every HTTP request includes `config = {"configurable": {"thread_id": str(template_id)}}`. This is how LangGraph knows which saved state to load and update.

---

## 7. API Endpoints Reference

Base URL: `http://localhost:8000/api/v1`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/templates` | Start template generation (MJML or RAG) |
| `GET` | `/templates/{id}/status` | Poll current status & get preview URLs |
| `PUT` | `/templates/{id}/brief` | Submit amended brief (after clarification) |
| `GET` | `/templates/{id}/versions` | List all versions with metadata |
| `GET` | `/templates/{id}/versions/{ver}/html` | Get compiled HTML for a version |
| `GET` | `/templates/{id}/versions/{ver}/mjml` | Get MJML source for a version |
| `POST` | `/templates/{id}/versions/{ver}/feedback` | Submit feedback → triggers revision |
| `POST` | `/templates/{id}/versions/{ver}/approve` | Approve a version as final |

**Interactive docs:** http://localhost:8000/docs (Swagger UI)

---

## 8. Database Layer

### Tables

**`template_versions`** — every generated version of every template
| Column | Type | Notes |
|--------|------|-------|
| `template_id` | UUID | Groups all versions of one job |
| `version_id` | string | `"v0"`, `"v_rev_a1b2c3d4"`, etc. |
| `mjml_source` | text | Empty string for RAG flow |
| `compiled_html` | text | Final email HTML |
| `user_brief_snapshot` | JSONB | Snapshot of brief at time of generation |
| `image_assets` | JSONB | List of generated image URLs |
| `change_trigger` | JSONB | What caused this version |
| `is_approved` | boolean | Only one approved version per template |
| `created_at` | timestamp | Auto-set |

**`rag_templates`** — pre-indexed email template corpus
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | |
| `source_file` | string | Original JSON filename |
| `html_content` | text | Processed template HTML |
| `fingerprint` | text | Structural description string |
| `embedding` | vector(1536) | pgvector embedding for similarity search |
| `metadata` | JSONB | Extra info from source JSON |

### Migrations

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration after changing models.py
alembic revision --autogenerate -m "add column xyz"

# Check status
alembic current
```

---

## 9. Configuration Reference

All settings live in `xyra/config.py` as a `pydantic-settings` `Settings` class. They are populated from the `.env` file.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | None | Required for OpenAI LLMs + DALL-E |
| `ANTHROPIC_API_KEY` | None | Required for Anthropic models |
| `DEFAULT_LLM_PROVIDER` | `anthropic` | Global fallback provider |
| `BRIEF_ANALYZER_PROVIDER` | `anthropic` | Provider for brief analysis task |
| `BRIEF_ANALYZER_ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Model for brief analysis |
| `MJML_GENERATION_PROVIDER` | `anthropic` | Provider for MJML generation task |
| `MJML_GENERATION_ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Model for MJML generation |
| `FEEDBACK_ENGINE_PROVIDER` | `anthropic` | Provider for feedback revision |
| `IMAGE_GENERATION_PROVIDER` | `openai` | Must be openai (DALL-E) |
| `IMAGE_GENERATION_OPENAI_DALLE_MODEL` | `dall-e-3` | DALL-E model version |
| `RAG_GENERATION_PROVIDER` | `openai` | Provider for RAG content filling |
| `RAG_GENERATION_OPENAI_MODEL` | `gpt-4o` | Model for RAG content population |
| `EMBEDDING_MODEL_NAME` | `text-embedding-3-small` | OpenAI embedding model for RAG |
| `DATABASE_URL` | None | `postgresql+asyncpg://...` for template store |
| `LANGGRAPH_CHECKPOINTER_DB_URL` | None | `postgresql://...` for LangGraph state |
| `SQLITE_CHECKPOINTER_DB_FILE` | `data/langgraph_checkpoints.sqlite` | SQLite fallback path |
| `MJML_CLI_PATH` | `mjml` | Path or command name for MJML CLI |
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## 10. Local Setup — Step by Step

### Prerequisites

- Python 3.10+
- Node.js + npm (for MJML CLI)
- PostgreSQL running locally

### 1. Clone and create virtual environment

```bash
git clone <repository-url>
cd Xyra_Templates

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install MJML CLI

```bash
npm install -g mjml
mjml --version   # Should print version number
```

### 4. Create PostgreSQL database

```bash
createdb xyra_db
```

### 5. Create `.env` file

Create `Xyra_Templates/.env` with:

```bash
# LLM Keys — need at least one
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Provider selection (anthropic is default)
DEFAULT_LLM_PROVIDER=anthropic

# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/xyra_db
LANGGRAPH_CHECKPOINTER_DB_URL=postgresql://postgres:password@localhost:5432/xyra_db

# MJML CLI
MJML_CLI_PATH=mjml

# Debug
DEBUG=true
LOG_LEVEL=DEBUG
```

### 6. Run database migrations

```bash
alembic upgrade head
```

### 7. (Optional) Ingest RAG corpus

Only needed if you plan to use the `rag_flow=true` mode:

```bash
python scripts/ingest_rag_corpus.py
```

---

## 11. Running the Application

```bash
# Development with auto-reload
uvicorn xyra.main:app --reload --host 0.0.0.0 --port 8000

# Verify health
curl http://localhost:8000/api/v1/health

# Open Swagger UI
# http://localhost:8000/docs
```

---

## 12. End-to-End Use Case Walkthrough

### Use Case: Generate a Welcome Email (MJML workflow)

**Step 1 — Create a template job**

```bash
curl -X POST http://localhost:8000/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{
    "user_brief": {
      "subject": "Welcome to StyleHub!",
      "body_copy": "Thanks for joining us. Explore our curated fashion collections and enjoy 15% off your first order.",
      "cta_text": "Start Shopping",
      "cta_url": "https://stylehub.com/shop",
      "image_suggestions": ["stylish fashion model in summer outfit"]
    }
  }'
```

Response (HTTP 202):
```json
{
  "template_id": "3f8a1234-...",
  "task_id": "3f8a1234-...",
  "status": "SUCCESS_STORED_V0",
  "status_poll_url": "/api/v1/templates/3f8a1234-.../status"
}
```

**Step 2 — Check status**

```bash
curl http://localhost:8000/api/v1/templates/3f8a1234-.../status
```

Response when ready:
```json
{
  "template_id": "3f8a1234-...",
  "status": "READY_FOR_PREVIEW",
  "current_version_id": "v0",
  "html_preview_url": "/api/v1/templates/3f8a1234-.../versions/v0/html",
  "mjml_source_url": "/api/v1/templates/3f8a1234-.../versions/v0/mjml"
}
```

**Step 3 — Preview the HTML**

```bash
curl http://localhost:8000/api/v1/templates/3f8a1234-.../versions/v0/html
# Returns full responsive HTML email
```

**Step 4 — Submit feedback for a revision**

```bash
curl -X POST http://localhost:8000/api/v1/templates/3f8a1234-.../versions/v0/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "feedback_text": "The header font looks too large. Also please change the CTA button color to dark navy and make the body text more concise."
  }'
```

Response (HTTP 202):
```json
{ "message": "Feedback received and revision process initiated." }
```

Behind the scenes, the graph:
1. Loads the saved state for `template_id`
2. Injects `user_feedback_content` and `version_id_for_feedback = "v0"`
3. Routes to `LG_FeedbackEngine` → LLM revises MJML
4. Validates & compiles revised MJML
5. Stores new version as `v_rev_a1b2c3d4`

**Step 5 — Check for revised version**

```bash
curl http://localhost:8000/api/v1/templates/3f8a1234-.../versions
```

```json
{
  "versions": [
    { "version_id": "v0", "is_approved": false, ... },
    { "version_id": "v_rev_a1b2c3d4", "is_approved": false, ... }
  ]
}
```

**Step 6 — Approve the revised version**

```bash
curl -X POST http://localhost:8000/api/v1/templates/3f8a1234-.../versions/v_rev_a1b2c3d4/approve
```

```json
{
  "template_id": "3f8a1234-...",
  "approved_version_id": "v_rev_a1b2c3d4",
  "status": "approved"
}
```

The status endpoint will now return `"approved_pending_import"` for this template.

---

### Use Case: RAG-Based Email (fast path)

```bash
curl -X POST http://localhost:8000/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{
    "rag_flow": true,
    "plain_text_brief": "Product launch email for our new noise-cancelling headphones. Target: millennials. Tone: exciting. Include 20% launch discount. CTA: Shop Now.",
    "use_placeholders": false
  }'
```

The response arrives much faster because no MJML is generated — the system finds the best-matching template from the corpus and fills it in with AI.

---

### Use Case: Clarification Loop

If the brief is too vague:

```bash
# Step 1 — Submit vague brief
curl -X POST http://localhost:8000/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{"user_brief": {"subject": "Email", "body_copy": "Buy stuff."}}'
```

Status will be `WAITING_FOR_AMENDED_BRIEF` with:
```json
{
  "status": "WAITING_FOR_AMENDED_BRIEF",
  "clarification_questions": [
    "What product or service are you promoting?",
    "Who is your target audience?",
    "What action should the reader take?"
  ]
}
```

```bash
# Step 2 — Submit amended brief
curl -X PUT http://localhost:8000/api/v1/templates/<id>/brief \
  -H "Content-Type: application/json" \
  -d '{
    "user_brief": {
      "subject": "Flash Sale: 40% Off Electronics Today Only",
      "body_copy": "Shop our biggest electronics sale of the year. Laptops, phones, headphones all 40% off — today only.",
      "cta_text": "Shop Flash Sale",
      "cta_url": "https://example.com/flash"
    }
  }'
```

The graph resumes and continues to image generation → MJML → storage.

---

## 13. Testing

### Running tests

```bash
# All tests
pytest

# Unit tests only (no DB required)
pytest tests/unit/ -v

# Integration tests (requires PostgreSQL)
pytest tests/integration/ -v

# API endpoint tests
pytest tests/api/ -v

# Specific file
pytest tests/unit/test_brief_analyzer_service.py -v

# With coverage
pytest --cov=xyra --cov-report=html

# Re-run only last failures
pytest --lf
```

### Test structure

```
tests/
├── conftest.py                      # Shared fixtures; sets DB env vars, runs alembic migrations
├── unit/
│   ├── test_brief_analyzer_service.py    # Tests LLM brief analysis (mocked)
│   ├── test_mjml_service.py              # Tests MJML generation + CLI compilation (mocked)
│   ├── test_image_generator_service.py   # Tests DALL-E calls (mocked)
│   └── graphs/test_checkpointer.py       # Tests checkpointer factory
├── integration/
│   └── test_template_generation_graph.py # Full workflow with MemorySaver (no real DB)
└── api/v1/
    └── test_template_routes.py           # HTTP endpoint tests with TestClient
```

### Important: asyncio configuration

The project uses `asyncio_mode = "auto"` in `pyproject.toml`. This means all `async def test_*` functions are automatically treated as async tests — you do **not** need to add `@pytest.mark.asyncio` decorators.

### Test patterns

**Unit test (mocked external services):**
```python
async def test_brief_analysis_ok():
    service = BriefAnalyzerService()
    with patch.object(service.llm_client, 'ainvoke') as mock_llm:
        mock_llm.return_value = MockMessage(content='{"status": "BRIEF_OK"}')
        result = await service.analyze(sample_brief)
    assert result.status == "BRIEF_OK"
```

**Integration test (full graph with MemorySaver):**
```python
async def test_full_workflow_brief_ok(compiled_graph_with_memory_saver):
    graph, _ = compiled_graph_with_memory_saver
    config = {"configurable": {"thread_id": "test-123"}}
    with patch('xyra.core_services.mjml_service.MJMLService.generate_mjml_node') as mock_gen:
        mock_gen.return_value = {"current_mjml": "<mjml>...</mjml>"}
        result = await graph.ainvoke(initial_state, config)
    assert result["last_operation_status"] == "SUCCESS_STORED_V0"
```

### Linting

```bash
ruff check .          # Check for issues
ruff check . --fix    # Auto-fix issues
ruff format .         # Format code
```

---

## 14. Code Patterns & Conventions

### Service pattern

All `core_services` follow this structure:

```python
class MyService:
    def __init__(self):
        # Get configured LLM client (provider selected from env)
        self.llm = get_configured_chat_model(
            task_provider_config_value=settings.MY_PROVIDER,
            openai_model=settings.MY_OPENAI_MODEL,
            anthropic_model=settings.MY_ANTHROPIC_MODEL,
        )

    async def do_something(self, input_data: InputType) -> OutputType:
        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return parse(response.content)
        except Exception as e:
            logger.error(f"MyService failed: {e}")
            raise MyServiceError(str(e))
```

### LangGraph node pattern

```python
async def my_node(state: GraphState, config: dict) -> Dict[str, Any]:
    """Node docstring explains what this step does."""
    logger.info("--- Executing MyNode ---")
    updates = {}

    if not state.some_required_field:
        return {
            "error_message": "Required field missing",
            "last_operation_status": "ERROR_MY_NODE"
        }

    try:
        result = await some_service.process(state.some_required_field)
        updates["output_field"] = result
        updates["last_operation_status"] = "SUCCESS_MY_NODE"
        updates["error_message"] = None
    except Exception as e:
        logger.exception("MyNode failed")
        updates["error_message"] = str(e)
        updates["last_operation_status"] = "ERROR_MY_NODE"

    return updates
```

### Database operation pattern

```python
async def create_something(db: AsyncSession, data: CreateSchema) -> Model:
    obj = Model(**data.model_dump())
    db.add(obj)
    try:
        await db.commit()
        await db.refresh(obj)
        return obj
    except Exception as e:
        await db.rollback()
        logger.error(f"DB error: {e}")
        raise
```

### Error handling

- Nodes return partial state updates as dicts (never raise from nodes)
- Service classes raise typed exceptions (`MyServiceError`)
- API routes catch all exceptions and convert to `HTTPException`
- Conditional edge functions check `last_operation_status` to route to `END` on errors

---

## 15. Sprint History & Current State

| Sprint | Status | Key Deliverables |
|--------|--------|-----------------|
| Sprint 1 | ✅ Complete | Basic FastAPI + LangGraph skeleton, SQLite checkpointer, initial brief analysis |
| Sprint 2 | ✅ Complete | DALL-E image generation, PostgreSQL versioning, StoreV0Node, HTML/MJML preview endpoints, production checkpointer |
| Sprint 3 | ✅ Complete | Feedback loop (LG_FeedbackEngine → LG_StoreVNext), approval endpoint, comprehensive integration tests |
| Sprint 5 | ✅ Complete | RAG pipeline (fingerprint → embedding → vector search → content population), ~1,599 template corpus |

**Current branch for active development:** check `git branch` — features are developed on `feature/*` branches, merged to `main`.

**CI:** GitHub Actions runs `ruff check .` on push/PR to `sprint1` and `main`. Pytest is not enforced in CI yet.

---

## 16. Common Issues & Debugging Tips

### "Failed to initialize checkpointer"

- Check that `LANGGRAPH_CHECKPOINTER_DB_URL` is set in `.env`
- Verify PostgreSQL is running: `pg_isready`
- If using SQLite fallback, ensure the `data/` directory exists: `mkdir -p data`

### "MJML CLI not found"

- Install globally: `npm install -g mjml`
- Verify: `mjml --version`
- If installed locally, set `MJML_CLI_PATH=/absolute/path/to/node_modules/.bin/mjml`

### "No suitable template found in the RAG corpus"

- The RAG corpus hasn't been ingested yet. Run: `python scripts/ingest_rag_corpus.py`
- Check `rag_templates` table: `psql -d xyra_db -c "SELECT COUNT(*) FROM rag_templates;"`

### "Status is CLARIFICATION_NEEDED but I never see questions"

- Call `GET /{id}/status` — the `clarification_questions` field in the response contains the questions
- Then call `PUT /{id}/brief` with a more detailed brief

### Inspecting graph state in the database

```bash
psql -d xyra_db
-- LangGraph checkpoints
SELECT thread_id, checkpoint_id, created_at FROM checkpoints ORDER BY created_at DESC LIMIT 10;

-- Template versions
SELECT template_id, version_id, is_approved, created_at FROM template_versions ORDER BY created_at DESC LIMIT 20;
```

### Adding logging to trace graph execution

```python
import logging
logger = logging.getLogger(__name__)

async def my_node(state: GraphState) -> Dict:
    logger.debug(f"State entering my_node: {state.model_dump()}")
    # ...
```

Set `LOG_LEVEL=DEBUG` in `.env` to see all node-level logging.

---

## 17. Key Files Quick Reference

| File | What to look at when... |
|------|------------------------|
| `xyra/config.py` | Adding a new setting or changing a default model |
| `xyra/main.py` | Changing app startup, adding middleware, new router |
| `xyra/api/v1/router.py` | Adding a new route group |
| `xyra/api/v1/template_routes.py` | Changing or adding HTTP endpoints |
| `xyra/graphs/state.py` | Adding new fields to workflow state |
| `xyra/graphs/template_generation_graph.py` | Adding/modifying nodes or routing logic |
| `xyra/graphs/checkpointer.py` | Checkpointer connection issues |
| `xyra/core_services/brief_analyzer_service.py` | Tweaking brief analysis prompts |
| `xyra/core_services/mjml_service.py` | MJML generation prompts, CLI interaction |
| `xyra/core_services/feedback_engine_service.py` | Feedback revision prompts |
| `xyra/core_services/rag_template_service.py` | RAG similarity search, content population |
| `xyra/core_services/llm_factory.py` | Adding a new LLM provider |
| `xyra/db/models.py` | Adding a new database table or column |
| `xyra/db/template_store.py` | Adding a new database query |
| `xyra/schemas/template_schemas.py` | Changing API request/response shapes |
| `alembic/versions/` | Database migration history |
| `scripts/ingest_rag_corpus.py` | RAG corpus ingestion pipeline |
| `tests/integration/test_template_generation_graph.py` | Understanding full workflow behaviour |

---

*This document was auto-generated based on a full codebase analysis. Last updated: April 2026.*
