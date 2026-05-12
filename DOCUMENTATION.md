# Mailwright - Agentic Marketing Email Platform — Complete Project Documentation

> **Who is this for?** Anyone — developer, contributor, or evaluator — who wants to fully understand what Mailwright is, how it is built, and how to run, extend, or test it. No prior knowledge of the codebase is assumed.

---

## Table of Contents

1. [What Is Mailwright?](#1-what-is-Mailwright)
2. [Tech Stack](#2-tech-stack)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Repository Structure](#4-repository-structure)
5. [Core Concepts](#5-core-concepts)
   - 5a. [LangGraph State Machine](#5a-langgraph-state-machine)
   - 5b. [GraphState — Shared Workflow Memory](#5b-graphstate--shared-workflow-memory)
   - 5c. [Checkpointer — Persistence & Resumability](#5c-checkpointer--persistence--resumability)
   - 5d. [LLM Factory — Provider Abstraction](#5d-llm-factory--provider-abstraction)
6. [Two Core Workflows](#6-two-core-workflows)
   - 6a. [MJML Generation Workflow (Legacy / from-scratch)](#6a-mjml-generation-workflow-legacy--from-scratch)
   - 6b. [RAG-Based HTML Generation Workflow (Fast Path)](#6b-rag-based-html-generation-workflow-fast-path)
7. [LangGraph Nodes Reference](#7-langgraph-nodes-reference)
8. [API Endpoints Reference](#8-api-endpoints-reference)
9. [Chat Endpoint & Chat Graph](#9-chat-endpoint--chat-graph)
   - 9a. [ChatState](#9a-chatstate)
   - 9b. [Chat Graph Nodes](#9b-chat-graph-nodes)
   - 9c. [Conversation Phases & Routing](#9c-conversation-phases--routing)
   - 9d. [Rolling Summarization in the Chat Graph](#9d-rolling-summarization-in-the-chat-graph)
   - 9e. [Chat API Schema](#9e-chat-api-schema)
   - 9f. [Chat Walkthrough Example](#9f-chat-walkthrough-example)
10. [Database Layer](#10-database-layer)
    - 10a. [ORM Models](#10a-orm-models)
    - 10b. [Alembic Migrations](#10b-alembic-migrations)
11. [Core Services](#11-core-services)
12. [Configuration Reference](#12-configuration-reference)
13. [Local Setup — Step by Step](#13-local-setup--step-by-step)
14. [Running the Application](#14-running-the-application)
15. [Gradio UI](#15-gradio-ui)
16. [End-to-End API Walkthrough](#16-end-to-end-api-walkthrough)
17. [Testing Guide](#17-testing-guide)
18. [Code Patterns & Conventions](#18-code-patterns--conventions)
19. [Context Engineering](#19-context-engineering)
    - 19a. [What Is Context Engineering?](#19a-what-is-context-engineering)
    - 19b. [The Context Window Mental Model](#19b-the-context-window-mental-model)
    - 19c. [Memory Management Strategies](#19c-memory-management-strategies)
    - 19d. [Prompt Engineering within Context Engineering](#19d-prompt-engineering-within-context-engineering)
    - 19e. [RAG — Retrieval-Augmented Generation](#19e-rag--retrieval-augmented-generation)
    - 19f. [Tool and State Injection](#19f-tool-and-state-injection)
    - 19g. [Token Budget Management](#19g-token-budget-management)
    - 19h. [How Mailwright Applies These Principles](#19h-how-Mailwright-applies-these-principles)
20. [CI / CD](#20-ci--cd)
21. [Sprint History](#21-sprint-history)
22. [Common Issues & Debugging](#22-common-issues--debugging)
23. [Key Files Quick Reference](#23-key-files-quick-reference)
24. [Glossary](#24-glossary)

---

## 1. What Is Mailwright?

**Mailwright (Mailwright - Agentic Marketing Email Platform)** is a **Python microservice** that generates production-ready, responsive **marketing email templates** using AI.

A user provides a short creative brief describing the email goal, messaging, and visual ideas. Mailwright then:

1. Analyses the brief for completeness — and asks follow-up questions if it is ambiguous.
2. Optionally generates images using **DALL-E 3**.
3. Generates a responsive **MJML** email template using a large language model (GPT-4 or Claude).
4. Compiles MJML to standard **HTML** via the MJML CLI tool.
5. Saves every generated version in **PostgreSQL** with full history.
6. Accepts user **feedback** and produces a revised version in a loop.
7. Allows the user to **approve** a version as the final deliverable.

Alternatively, Mailwright can skip the from-scratch generation path entirely and instead use a **RAG (Retrieval-Augmented Generation)** pipeline: it embeds the user's brief, finds the most structurally similar email from a pre-indexed corpus of approximately 1,600 real templates, and uses an LLM to fill in the user's specific content — producing HTML in seconds.

Both modes are available through the same REST API.

---

## 2. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Language** | Python 3.10+ | All application code |
| **API Server** | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | REST API, async request handling |
| **Workflow Orchestration** | [LangGraph](https://langchain-ai.github.io/langgraph/) | Stateful, resumable AI workflow engine |
| **LLM Framework** | [LangChain](https://python.langchain.com/) | LLM abstraction, message formatting |
| **LLM Providers** | [OpenAI](https://platform.openai.com/) (GPT-4, DALL-E 3) · [Anthropic](https://www.anthropic.com/) (Claude) | Text and image generation |
| **Email Markup** | [MJML](https://mjml.io/) CLI (Node.js) | Responsive email template compilation to HTML |
| **Database** | [PostgreSQL](https://www.postgresql.org/) | Template versioning, LangGraph state persistence |
| **Async DB Driver** | [asyncpg](https://magicstack.github.io/asyncpg/) | Non-blocking PostgreSQL access |
| **ORM** | [SQLAlchemy](https://www.sqlalchemy.org/) (async) | Object-relational mapping |
| **DB Migrations** | [Alembic](https://alembic.sqlalchemy.org/) | Schema version management |
| **Vector Search (RAG)** | [pgvector](https://github.com/pgvector/pgvector) PostgreSQL extension | Cosine similarity search over template embeddings |
| **Embeddings (RAG)** | [sentence-transformers](https://www.sbert.net/) · OpenAI embedding models | Vectorising briefs and templates |
| **HTML Parsing (RAG)** | [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | Extracting content from corpus HTML |
| **Settings Management** | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Typed `.env` configuration |
| **Data Validation** | [Pydantic v2](https://docs.pydantic.dev/) | API schemas, graph state typing |
| **Linting / Formatting** | [Ruff](https://docs.astral.sh/ruff/) | Code quality |
| **Testing** | [pytest](https://pytest.org/) + [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) | Unit, integration, and API tests |
| **UI (optional)** | [Gradio](https://www.gradio.app/) | Web chat interface for manual testing |
| **CI** | GitHub Actions | Automated linting on push/PR |

---

## 3. High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    CLIENT / API CONSUMER                  │
│  (curl · Postman · Gradio UI · your application)         │
└───────────────────────┬──────────────────────────────────┘
                        │  HTTP REST
                        ▼
┌──────────────────────────────────────────────────────────┐
│              FastAPI  (mailwright/main.py)                      │
│              Mounted at: /api/v1                          │
│              ┌──────────────────────────────────────┐    │
│              │  template_routes.py   chat_routes.py  │    │
│              └────────────┬─────────────────────────┘    │
└───────────────────────────┼──────────────────────────────┘
                            │  graph.ainvoke() / aupdate_state()
                            ▼
┌──────────────────────────────────────────────────────────┐
│         LangGraph State Machine  (mailwright/graphs/)           │
│                                                          │
│  Nodes call core_services:                               │
│  • BriefAnalyzerService        (LLM call)                │
│  • MJMLService                 (LLM + CLI subprocess)     │
│  • ImageGeneratorService       (DALL-E API)              │
│  • FeedbackEngineService       (LLM call)                │
│  • RAGTemplateService          (embed + vector search)   │
│                                                          │
│  State is persisted after every node via Checkpointer    │
└────────────┬──────────────────────────┬─────────────────┘
             │ SQLAlchemy async         │ Checkpoint save/load
             ▼                          ▼
┌──────────────────────┐   ┌──────────────────────────────┐
│  External LLMs       │   │        PostgreSQL              │
│  • OpenAI GPT-4      │   │  • template_versions table   │
│  • Anthropic Claude  │   │  • rag_templates table       │
│  • OpenAI DALL-E 3   │   │  • LangGraph checkpoint tbls │
└──────────────────────┘   └──────────────────────────────┘
             │
             ▼
┌──────────────────────┐
│  MJML CLI (Node.js)  │
│  mjml --input ...    │
└──────────────────────┘
```

**Key design insight:** The `template_id` UUID returned on every `POST /templates` call doubles as LangGraph's `thread_id`. Every subsequent API call for the same template (feedback, status, approval) reloads the exact same persisted graph state, enabling resumable multi-turn workflows.

---

## 4. Repository Structure

```
Mailwright-Agentic_Marketing_Email_Platform/
│
├── mailwright/                               # Main Python application package
│   ├── __init__.py
│   ├── main.py                         # FastAPI app creation; lifespan (DB engine setup)
│   ├── config.py                       # All settings via pydantic-settings (.env)
│   ├── logging_config.py               # Structured logging setup
│   ├── templates_api.py                # ⚠ Legacy / broken — references missing package
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── router.py               # Assembles all v1 routes + /health endpoint
│   │       ├── template_routes.py      # All template HTTP endpoint handlers
│   │       └── chat_routes.py          # Conversational chat endpoint handlers
│   │
│   ├── graphs/
│   │   ├── state.py                    # GraphState Pydantic model (workflow memory)
│   │   ├── checkpointer.py             # Factory: Postgres saver or SQLite fallback
│   │   ├── template_generation_graph.py # All LangGraph nodes, edges, conditional routing
│   │   └── chat_graph.py               # ChatState, rolling summarisation, chat flow
│   │
│   ├── core_services/
│   │   ├── brief_analyzer_service.py   # LLM: is the brief clear enough?
│   │   ├── mjml_service.py             # LLM generates MJML; calls MJML CLI to compile
│   │   ├── image_generator_service.py  # Calls DALL-E 3 to generate images
│   │   ├── feedback_engine_service.py  # LLM revises existing MJML from user feedback
│   │   ├── rag_template_service.py     # Embedding, vector search, HTML content fill
│   │   └── llm_factory.py             # Provider-agnostic LLM client factory
│   │
│   ├── db/
│   │   ├── models.py                   # SQLAlchemy ORM models (TemplateVersion, RAGTemplate)
│   │   └── template_store.py           # CRUD helpers: create/get/approve versions
│   │
│   └── schemas/
│       ├── template_schemas.py         # Pydantic request/response models for templates API
│       └── chat_schemas.py             # Pydantic models for chat API
│
├── alembic/                            # Database migration scripts
│   ├── env.py                          # Alembic environment config (loads .env)
│   ├── script.py.mako                  # Migration script template
│   └── versions/
│       ├── c1e1c3e07a5e_create_template_versions_table.py
│       ├── b42c672b7a7e_create_new_rag_corpus_table.py
│       └── 26fb755ba38b_add_raw_html_to_rag_templates.py
│
├── templates/                          # ~1,600 Bee-style JSON email templates
│                                       # Source corpus for RAG ingestion
│
├── scripts/
│   ├── ingest_rag_corpus.py            # Load templates/ JSON files into rag_templates DB
│   ├── clear_rag_db.py                 # Wipe the rag_templates table
│   ├── diagnose_schema.py              # Inspect DB schema for debugging
│   ├── extract_html.py                 # Extract HTML from corpus JSON files
│   ├── replace_media.py                # Replace media URLs in templates
│   ├── manual_test_ingestion.py        # Manual ingestion test script
│   └── test_openai_access.py           # Verify OpenAI API key works
│
├── tests/
│   ├── conftest.py                     # Shared fixtures; sets DB env, runs alembic migrations
│   ├── unit/
│   │   ├── test_brief_analyzer_service.py
│   │   ├── test_mjml_service.py
│   │   ├── test_image_generator_service.py
│   │   ├── test_llm_factory.py
│   │   └── graphs/test_checkpointer.py
│   ├── integration/
│   │   └── test_template_generation_graph.py
│   ├── api/v1/
│   │   └── test_template_routes.py
│   └── beefreetester/                  # Static HTML/JS helpers (not production UI)
│
├── ui/
│   ├── app.py                          # Gradio chat UI (connects to localhost:8000)
│   └── requirements.txt                # gradio>=6.14.0, requests>=2.31.0
│
├── docs/
│   ├── working_context/                # Active sprint plans and notes
│   └── archive/                        # Historical sprint and architecture docs
│
├── archive/                            # Legacy code (excluded from packaging + linting)
│   ├── legacy_code/
│   └── templates/
│
├── output/                             # Sample/diagnostic HTML outputs
│
├── .env.example                        # Template for the required .env file
├── .gitignore
├── alembic.ini                         # Alembic configuration
├── pyproject.toml                      # Build system, Ruff config, pytest config
├── requirements.txt                    # All Python runtime dependencies
├── README.md                           # Original developer guide
├── ONBOARDING.md                       # Comprehensive onboarding guide
├── MODULE_REFERENCE.md                 # Per-module technical reference
└── context_engineering.md             # RAG and memory architecture notes
```

---

## 5. Core Concepts

### 5a. LangGraph State Machine

[LangGraph](https://langchain-ai.github.io/langgraph/) is the heart of Mailwright's processing pipeline. It turns the multi-step email generation process into a **directed graph** where:

- Each **node** is an async Python function that performs one step (e.g., analyse the brief, generate MJML, store to DB).
- Each **edge** is a transition between nodes, which can be conditional (a router function inspects the state and decides the next node).
- The entire graph state is **serialised and saved** to PostgreSQL (or SQLite) after every node, making the workflow resumable across HTTP calls.

This is what enables the clarification loop and the feedback revision loop: the API call returns immediately, the graph saves its state, and when the user provides more information the graph picks up exactly where it left off.

### 5b. GraphState — Shared Workflow Memory

Every node in the graph receives a `GraphState` object, reads what it needs, and returns a dictionary of updated fields. This object is the single source of truth for everything that has happened in a workflow run.

```python
# mailwright/graphs/state.py (simplified)
class GraphState(BaseModel):
    # --- Workflow routing ---
    rag_flow: bool = False                    # True → RAG path; False → MJML path

    # --- MJML workflow inputs ---
    user_brief_data: Optional[Dict]           # Structured brief (subject, CTA, etc.)

    # --- RAG workflow inputs ---
    plain_text_brief: Optional[str]           # Free-form text brief for RAG
    use_placeholders: bool = False

    # --- Brief analysis ---
    clarification_questions: Optional[List[str]]
    clarification_rounds_count: int = 0
    amended_brief_data: Optional[Dict]

    # --- Image generation ---
    image_prompts: Optional[List[str]]
    generated_image_urls: Optional[List[str]]
    image_urls_map: Optional[Dict]

    # --- MJML/HTML outputs ---
    current_mjml: Optional[str]
    compiled_html: Optional[str]
    mjml_validation_status: Optional[str]    # "VALID" | "INVALID" | "ERROR"

    # --- Storage ---
    stored_version_info: Optional[Dict]
    current_version_id_stored: Optional[str]

    # --- Feedback loop ---
    user_feedback_content: Optional[str]
    version_id_for_feedback: Optional[str]
    revised_mjml_candidate: Optional[str]

    # --- RAG internals ---
    brief_fingerprint: Optional[str]
    brief_embedding: Optional[List[float]]
    retrieved_template_html: Optional[str]
    final_html_content: Optional[str]

    # --- Status tracking ---
    last_operation_status: Optional[str]
    error_message: Optional[str]
```

### 5c. Checkpointer — Persistence & Resumability

`mailwright/graphs/checkpointer.py` is a factory that returns either:

- **`AsyncPostgresSaver`** — production mode; requires `LANGGRAPH_CHECKPOINTER_DB_URL` in `.env`; saves state to dedicated tables in PostgreSQL.
- **`AsyncSqliteSaver`** — fallback for development; saves state to a local SQLite file at `data/langgraph_checkpoints.sqlite`.

The checkpointer is initialised once during FastAPI startup and passed to every `graph.ainvoke()` call.

### 5d. LLM Factory — Provider Abstraction

`mailwright/core_services/llm_factory.py` provides a single function `get_configured_chat_model(...)` that returns a LangChain `BaseChatModel` for either OpenAI (`ChatOpenAI`) or Anthropic (`ChatAnthropic`) based on environment configuration.

Each core service calls this factory with its own provider/model settings, so individual tasks (brief analysis, MJML generation, feedback revision) can each use a different provider or model without changing the service code.

---

## 6. Two Core Workflows

### 6a. MJML Generation Workflow (Legacy / from-scratch)

**Use this when:** you want a brand-new email design generated entirely by AI from a structured brief.

**Trigger:** `POST /api/v1/templates` with a `user_brief` object (no `rag_flow: true`).

**Step-by-step flow:**

```
POST /api/v1/templates
  └─► [LG_Start]
        Initialises GraphState with user_brief_data.
        Route → route_rag_or_legacy → LEGACY path

  └─► [LG_BriefAnalyzer]
        Calls LLM: "Is this brief clear enough to produce a great email?"
        ├── Brief OK     → last_operation_status = BRIEF_OK
        └── Too vague   → sets clarification_questions in state

        Route → should_request_clarification

  └─► [LG_WaitForAmendedBrief]   ← INTERRUPT POINT
        Graph pauses here.
        Client polls status, sees WAITING_FOR_AMENDED_BRIEF + clarification_questions.
        Client calls PUT /{id}/brief with answers.
        Graph resumes → back to LG_BriefAnalyzer.

  └─► [LG_ImageGeneration]
        For each image_suggestion in the brief, calls DALL-E 3.
        Stores generated image URLs in state.

  └─► [LG_MJMLGeneration]
        Calls LLM to write a full MJML template.
        Brief data + image URLs are injected into the prompt.
        Stores MJML source in state.

  └─► [LG_MJMLValidateCompile]
        Calls MJML CLI (subprocess): mjml --input - --output -
        If VALID → compiled_html stored in state.
        If INVALID → last_operation_status = ERROR → END

  └─► [LG_StoreV0]
        Writes to template_versions table.
        version_id = "v0"
        → END  (last_operation_status = SUCCESS_STORED_V0)
```

**Feedback revision loop:**

```
POST /api/v1/templates/{id}/versions/{ver}/feedback
  └─► Updates state: user_feedback_content, version_id_for_feedback
  └─► Re-invokes graph

[LG_Start] → route_initial_or_feedback → HAS FEEDBACK

  └─► [LG_FeedbackEngineNode]
        Calls LLM: "Revise this MJML to address the feedback."
        Stores revised MJML as revised_mjml_candidate.

  └─► [LG_MJMLValidateCompile]
        Same validation step, applied to the revised MJML.

  └─► [LG_StoreVNextNode]
        Writes new version as v_rev_<short-uuid>.
        → END
```

**Approval:**

```
POST /api/v1/templates/{id}/versions/{ver}/approve
  └─► Sets is_approved = true in template_versions for this version.
      Clears is_approved on all other versions of this template.
      Status becomes approved_pending_import.
```

---

### 6b. RAG-Based HTML Generation Workflow (Fast Path)

**Use this when:** you want a fast, high-quality result by adapting a real template from the corpus rather than generating from scratch.

**Trigger:** `POST /api/v1/templates` with `rag_flow: true` and `plain_text_brief`.

**Prerequisites:** The RAG corpus must be ingested first — run `python scripts/ingest_rag_corpus.py`. This reads all JSON files from `templates/`, extracts HTML, generates embeddings, and inserts ~1,600 rows into the `rag_templates` table.

**Step-by-step flow:**

```
POST /api/v1/templates  (rag_flow: true)
  └─► [LG_Start]
        Route → route_rag_or_legacy → RAG path

  └─► [LG_RAG_GenerateBriefFingerprint]
        LLM extracts a structural fingerprint from the plain-text brief.
        Example: "product launch, single product, discount CTA, 2-column layout"
        Generates a vector embedding of this fingerprint.

  └─► [LG_RAG_FindMatchingTemplate]
        Queries rag_templates using pgvector cosine similarity.
        Returns the HTML of the structurally closest template.

  └─► [LG_RAG_PopulateContent]
        LLM receives: retrieved HTML template + plain_text_brief.
        Fills in all headlines, body text, CTAs with user's content.
        Returns final_html_content.

  └─► [LG_StoreV0]
        Stores final HTML in template_versions.
        mjml_source = "" (RAG flow produces no MJML).
        → END
```

**Result:** A ready-to-use HTML email in seconds, with no MJML compilation and no image generation needed.

---

## 7. LangGraph Nodes Reference

| Node | Trigger / Condition | What It Does |
|------|---------------------|-------------|
| `LG_Start` | Entry point for every invocation | Initialises state; routes to legacy or RAG path |
| `LG_BriefAnalyzer` | Legacy path, initial run | LLM evaluates brief clarity; sets `clarification_questions` if needed |
| `LG_WaitForAmendedBrief` | Brief is ambiguous | Interrupt point; pauses graph until `PUT /{id}/brief` is called |
| `LG_ImageGeneration` | Brief is clear (legacy) | Calls DALL-E for each image suggestion; stores URLs |
| `LG_MJMLGeneration` | After image generation | LLM generates full MJML source |
| `LG_MJMLValidateCompile` | After MJML generation or feedback revision | Calls MJML CLI; validates and compiles to HTML |
| `LG_StoreV0` | MJML valid (initial) or RAG flow complete | Writes first version (`v0`) to `template_versions` |
| `LG_FeedbackEngineNode` | Feedback submitted | LLM revises existing MJML based on feedback text |
| `LG_StoreVNextNode` | Revised MJML valid | Writes revised version (`v_rev_*`) to `template_versions` |
| `LG_RAG_GenerateBriefFingerprint` | RAG path entry | LLM extracts structural description; generates embedding |
| `LG_RAG_FindMatchingTemplate` | After fingerprinting | pgvector cosine similarity search over `rag_templates` |
| `LG_RAG_PopulateContent` | After template retrieval | LLM fills retrieved HTML with user's specific content |

**Conditional routing functions:**

| Router | Location in Graph | Possible Outputs |
|--------|------------------|-----------------|
| `route_rag_or_legacy` | After `LG_Start` | `rag` → RAG path; `legacy` → brief analysis |
| `should_request_clarification` | After `LG_BriefAnalyzer` | `wait_for_brief` or `proceed_to_image_gen` |
| `route_initial_or_feedback` | After `LG_Start` (re-invocations) | `feedback` or `initial` |
| `should_route_after_validation` | After `LG_MJMLValidateCompile` | `store_v0`, `store_vnext`, or `end_error` |

---

## 8. API Endpoints Reference

**Base URL:** `http://localhost:8000/api/v1`

**Interactive Swagger UI:** `http://localhost:8000/docs`

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `GET` | `/health` | — | `{"status": "healthy"}` | Liveness check |
| `POST` | `/templates` | `TemplateCreationRequest` | `TemplateCreationResponse` (202) | Start a new template generation job |
| `GET` | `/templates/{id}/status` | — | `TemplateStatusSchema` | Poll workflow status and get preview URLs |
| `PUT` | `/templates/{id}/brief` | `UserBriefSchema` | `TemplateStatusSchema` | Submit an amended brief after clarification |
| `GET` | `/templates/{id}/versions` | — | `VersionListSchema` | List all versions with metadata |
| `GET` | `/templates/{id}/versions/{ver}/html` | — | HTML text | Download compiled HTML for a specific version |
| `GET` | `/templates/{id}/versions/{ver}/mjml` | — | MJML text | Download MJML source for a specific version |
| `POST` | `/templates/{id}/versions/{ver}/feedback` | `FeedbackRequestSchema` | `202 Accepted` | Submit feedback; triggers AI revision |
| `POST` | `/templates/{id}/versions/{ver}/approve` | — | `ApprovalResponseSchema` | Approve a version as the final deliverable |
| `POST` | `/chat/` | `ChatRequest` | `ChatResponse` | Conversational interface (chat graph) |

### Request & Response Schemas (summary)

**`TemplateCreationRequest`** — choose one of three modes:
```json
// Mode 1: MJML workflow (structured brief)
{
  "user_brief": {
    "subject": "Summer Sale — 50% Off!",
    "body_copy": "Shop our biggest sale...",
    "cta_text": "Shop Now",
    "cta_url": "https://example.com/sale",
    "image_suggestions": ["bright beach scene"]
  }
}

// Mode 2: RAG workflow (free-text brief)
{
  "rag_flow": true,
  "plain_text_brief": "Product launch email for new headphones. Target: millennials. Include 20% discount.",
  "use_placeholders": false
}
```

**`TemplateStatusSchema`** — returned by `GET /{id}/status`:
```json
{
  "template_id": "3f8a1234-...",
  "status": "READY_FOR_PREVIEW",
  "current_version_id": "v0",
  "html_preview_url": "/api/v1/templates/3f8a1234-.../versions/v0/html",
  "mjml_source_url": "/api/v1/templates/3f8a1234-.../versions/v0/mjml",
  "clarification_questions": null,
  "error_message": null
}
```

**Status values** you will see in `last_operation_status` / `status`:

| Status | Meaning |
|--------|---------|
| `PENDING_BRIEF_ANALYSIS` | Job created, analysis not started |
| `BRIEF_OK` | Brief is clear, proceeding to generation |
| `WAITING_FOR_AMENDED_BRIEF` | Graph paused; client must submit a clearer brief |
| `GENERATING_IMAGES` | DALL-E calls in progress |
| `GENERATING_MJML` | LLM generating MJML |
| `COMPILING_MJML` | MJML CLI running |
| `SUCCESS_STORED_V0` | Initial version `v0` saved |
| `READY_FOR_PREVIEW` | Template ready (alias for above in status endpoint) |
| `REVISION_IN_PROGRESS` | Feedback submitted; revision running |
| `approved_pending_import` | A version has been approved |
| `ERROR_*` | Node-specific error; see `error_message` for details |

---

## 9. Chat Endpoint & Chat Graph

The chat interface is a **fully conversational alternative** to the raw REST template API. Instead of calling individual endpoints yourself, you have a natural-language conversation with an AI assistant (Mailwright) that gathers your requirements, triggers generation, handles revision requests, and approves the final template — all through a single endpoint.

**Endpoint:** `POST /api/v1/chat/`  
**File:** `mailwright/api/v1/chat_routes.py` and `mailwright/graphs/chat_graph.py`  
**LLM:** OpenAI (`ChatOpenAI`), requires `OPENAI_API_KEY`

---

### 9a. ChatState

The chat graph has its own independent state model — separate from the template `GraphState`. It is persisted to the same checkpointer backend (Postgres or SQLite), keyed by `chat_{thread_id}`.

```python
class ChatState(BaseModel):
    # Full conversation history as dicts: [{"role": "user"|"assistant", "content": "..."}]
    messages: List[Dict[str, str]] = []

    # Current phase of the conversation
    phase: str = "gathering"   # gathering | review | approved | error

    # Brief fields collected conversationally
    brief_subject: Optional[str] = None
    brief_body_copy: Optional[str] = None
    brief_cta_text: Optional[str] = None
    brief_cta_url: Optional[str] = None
    brief_image_suggestions: Optional[List[str]] = None

    # Set once a template is successfully generated
    template_id: Optional[str] = None
    current_version_id: Optional[str] = None

    # Intra-turn action signals (set by conversation node, consumed by routing)
    pending_action: Optional[str] = None      # start_generation | submit_feedback | approve
    pending_feedback_text: Optional[str] = None

    # The reply text to return to the caller this turn
    assistant_reply: Optional[str] = None
    error_message: Optional[str] = None
```

---

### 9b. Chat Graph Nodes

The chat graph has four nodes:

| Node | LangGraph name | What it does |
|------|---------------|-------------|
| **Conversation** | `LG_Chat_Conversation` | Main LLM node. Reads message history, chooses a response, and decides what action to take next. Uses structured output (`ChatLLMDecision`) so routing is deterministic. |
| **Generate** | `LG_Chat_Generate` | Compiles and invokes the full `template_generation_graph` as a sub-graph (same graph used by the REST API). Passes collected brief fields. Sets `phase = "review"` on success. |
| **Feedback** | `LG_Chat_Feedback` | Loads the current MJML from the DB, re-invokes the template graph with `user_feedback_content` injected, so the `LG_FeedbackEngineNode` runs. Updates `current_version_id` with the new revision. |
| **Approve** | `LG_Chat_Approve` | Calls `approve_template_version()` in the DB directly. Sets `phase = "approved"`. |

**Structured LLM output — `ChatLLMDecision`:**

Each turn the LLM returns a typed object (not a free-form string), which makes routing reliable:

```python
class ChatLLMDecision(BaseModel):
    reply_to_user: str                                    # Text shown to the user
    action: Optional[Literal[
        "start_generation",
        "submit_feedback",
        "approve"
    ]] = None                                             # Routing signal
    # Populated when action == "start_generation":
    subject: Optional[str] = None
    body_copy: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    image_suggestions: Optional[List[str]] = None
    # Populated when action == "submit_feedback":
    feedback_text: Optional[str] = None
```

---

### 9c. Conversation Phases & Routing

The conversation moves through four phases, each governed by a different system prompt:

**Phase 1 — `gathering`**

The assistant uses `_GATHERING_SYSTEM_PROMPT`. It collects five things in order:
1. `subject` — email subject line
2. `body_copy` — main email message
3. `cta_text` — button label (e.g. "Shop Now")
4. `cta_url` — button URL
5. `image_suggestions` — *always* asks once whether images are wanted

Rules enforced in the prompt:
- Ask 1–2 questions at a time (never dump a form)
- The image question is **mandatory** before confirming generation
- Strictly scoped to email templates only — any off-topic question gets redirected

Once all fields are gathered and the user confirms, the LLM sets `action = "start_generation"`.

**Phase 2 — `generating` (node, not a state)**

The `LG_Chat_Generate` node invokes the template sub-graph with `clarification_rounds_count=1` (so `LG_BriefAnalyzer` is lenient — requirements were already gathered through conversation). On success, phase transitions to `review`.

**Phase 3 — `review`**

The assistant uses `_REVIEW_SYSTEM_PROMPT`. It shows preview/MJML URLs and handles three cases:
- **Change request** → `action = "submit_feedback"` with detailed `feedback_text`
- **Approval** → `action = "approve"` (triggered by phrases like "looks good", "approve it", "perfect")
- **Question** → conversational reply, `action = null`
- **Off-topic** → redirect, `action = null`

**Phase 4 — `approved`**

Template is finalised. Status, template ID, version ID, and final HTML URL are returned to the user.

**Graph routing (conditional edges):**

```
START → LG_Chat_Conversation
            │
            ├── action == "start_generation"  → LG_Chat_Generate → END
            ├── action == "submit_feedback"   → LG_Chat_Feedback → END
            ├── action == "approve"           → LG_Chat_Approve  → END
            └── action == null                → END
```

Every turn starts at `LG_Chat_Conversation` — the graph is re-invoked on each HTTP request.

---

### 9d. Rolling Summarization in the Chat Graph

The chat graph implements **Rolling Summarization** (Strategy 2 from `context_engineering.md`) to keep the context window lean as conversations grow.

**How it works:**

- After every turn, the route handler calls `apply_rolling_summary(messages)`.
- **Trigger:** if total message count exceeds `_SUMMARY_THRESHOLD` (default: 10 messages ≈ 5 turns).
- **Preserved:** the last `_KEEP_RECENT` (default: 6) messages are kept verbatim.
- **Compressed:** everything older is sent to the LLM with this summarization instruction:

```
"Produce a concise summary (max 180 words) that preserves EVERY confirmed decision:
  • email subject, body copy, CTA text, CTA URL
  • image descriptions (if any)
  • template ID and version IDs (if generated)
  • any approved or pending changes
Use bullet points. Do not include greetings or filler."
```

- The summary replaces old messages as a single `assistant` message:  
  `"[CONVERSATION SUMMARY — earlier turns]\n<summary text>"`

- The compressed list is persisted to the checkpointer so the next turn starts with it.

**Graceful fallback:** If the summarization LLM call fails, the full message history is kept unchanged — no history is ever silently lost.

**Why this matters:**

Without summarization, a 50-turn conversation could send 40,000+ tokens to the LLM every single turn. With rolling summarization, the context stays roughly constant (~4–6 turns in full + one compact summary block), keeping both latency and API costs low.

---

### 9e. Chat API Schema

**Request:**

```json
{
  "message": "I want to create a summer sale email",
  "thread_id": null
}
```

- `message` — the user's text input (required)
- `thread_id` — omit or set to `null` to start a new conversation; pass the value returned in the previous response to continue

**Response:**

```json
{
  "reply": "Great! Let's create your summer sale email. What's the subject line you have in mind?",
  "thread_id": "a1b2c3d4-...",
  "phase": "gathering",
  "template_id": null,
  "current_version_id": null,
  "html_preview_url": null
}
```

Once a template is generated:

```json
{
  "reply": "Your email template is ready! 🎉\n\nPreview: /api/v1/templates/3f8a.../versions/v0/html\n\nTell me if you'd like any changes or say 'approve' when you're happy.",
  "thread_id": "a1b2c3d4-...",
  "phase": "review",
  "template_id": "3f8a1234-...",
  "current_version_id": "v0",
  "html_preview_url": "/api/v1/templates/3f8a1234-.../versions/v0/html"
}
```

---

### 9f. Chat Walkthrough Example

```bash
# Turn 1 — Start a new conversation
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "I need to create an email for our summer sale"}'

# Response: {"reply": "Great! What is the subject line for your email?", "thread_id": "a1b2...", "phase": "gathering", ...}

# Turn 2 — Provide subject
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Summer Sale — Up to 50% Off Everything", "thread_id": "a1b2..."}'

# Response: {"reply": "Perfect subject line! What should the main body copy say?", "phase": "gathering", ...}

# Turn 3 — Provide body copy
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Huge discounts across all product lines. Shop now before stock runs out.", "thread_id": "a1b2..."}'

# Response: {"reply": "Got it! What text should the call-to-action button say?", ...}

# ... (turns 4-6: CTA text, CTA URL, image question)

# Final gathering turn — confirm generation
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Yes, go ahead and generate it!", "thread_id": "a1b2..."}'

# Response: {"reply": "Your email template is ready! ...", "phase": "review", "template_id": "3f8a...", "current_version_id": "v0", "html_preview_url": "..."}

# Review turn — request a change
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Looks great but can you make the CTA button red?", "thread_id": "a1b2..."}'

# Response: {"reply": "Done! Here is the revised template ...", "current_version_id": "v_rev_...", ...}

# Approval turn
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Perfect, approve it.", "thread_id": "a1b2..."}'

# Response: {"reply": "Your email template has been approved! ...", "phase": "approved", ...}
```

---

## 10. Database Layer

### 10a. ORM Models

**`TemplateVersion`** (`template_versions` table) — every generated version of every email:

| Column | Type | Notes |
|--------|------|-------|
| `template_id` | UUID | Groups all versions of one job; composite PK with `version_id` |
| `version_id` | string | `"v0"`, `"v_rev_a1b2c3d4"`, etc.; composite PK |
| `mjml_source` | text | Full MJML source; empty string for RAG flow |
| `compiled_html` | text | Final responsive HTML |
| `user_brief_snapshot` | JSONB | Snapshot of the brief at generation time |
| `image_assets` | JSONB | List of generated image URLs |
| `change_trigger` | JSONB | What caused this version (initial, feedback, etc.) |
| `is_approved` | boolean | Only one approved version per `template_id` at a time |
| `created_at` | timestamp | Auto-set on insert |

**`RAGTemplate`** (`rag_templates` table) — pre-indexed email corpus:

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `source_file` | string | Original JSON filename from `templates/` |
| `raw_html` | text | Unprocessed HTML from source JSON |
| `processed_html` | text | Cleaned HTML used for content population |
| `fingerprint` | text | Structural description string |
| `fingerprint_embedding` | vector(1536) | pgvector embedding for cosine similarity |
| `metadata` | JSONB | Additional info from source JSON |

### 10b. Alembic Migrations

Migrations are in `alembic/versions/` and apply in the following order:

1. **`c1e1c3e07a5e`** — creates the `template_versions` table.
2. **`b42c672b7a7e`** — creates the `rag_templates` table and enables the `pgvector` extension (gated by `RAG_ENABLED` env var).
3. **`26fb755ba38b`** — adds the `raw_html` column to `rag_templates` (also gated by `RAG_ENABLED`).

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Check current state
alembic current

# Create a new migration after changing models.py
alembic revision --autogenerate -m "add column xyz"
```

**Important:** `alembic/env.py` reads the database URL from `DATABASE_URL` in the environment, stripping the `+asyncpg` driver prefix for Alembic's synchronous operations. It falls back to the URL in `alembic.ini` if the env var is not set.

---

## 11. Core Services

All services live in `mailwright/core_services/`. Each follows the same pattern: constructor creates an LLM client via `llm_factory`, and each async method invokes that client with a carefully crafted prompt.

| Service | File | What It Does |
|---------|------|-------------|
| **BriefAnalyzerService** | `brief_analyzer_service.py` | Sends the user brief to an LLM with instructions to evaluate completeness. Returns status `BRIEF_OK` or a list of `clarification_questions`. |
| **MJMLService** | `mjml_service.py` | (1) Calls LLM to generate MJML source incorporating the brief and image URLs. (2) Calls the MJML CLI subprocess to compile MJML → HTML and validate. |
| **ImageGeneratorService** | `image_generator_service.py` | Calls DALL-E 3 for each image prompt extracted from the brief. Returns a list of image URLs. |
| **FeedbackEngineService** | `feedback_engine_service.py` | Takes the existing MJML version and the user's feedback text, instructs an LLM to revise the MJML accordingly, returns the revised MJML source. |
| **RAGTemplateService** | `rag_template_service.py` | (1) Embeds the brief fingerprint. (2) Runs pgvector cosine similarity query against `rag_templates`. (3) Sends the retrieved HTML + brief to an LLM to fill content. |
| **LLM Factory** | `llm_factory.py` | `get_configured_chat_model(task_provider_config_value, openai_model, anthropic_model)` → returns `ChatOpenAI` or `ChatAnthropic`. |

---

## 12. Configuration Reference

All configuration is managed by `mailwright/config.py` using `pydantic-settings`. Values are loaded from the `.env` file in the project root.

Copy `.env.example` to `.env` and fill in your values before running the app.

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `APP_NAME` | `"Mailwright - Agentic Marketing Email Platform"` | No | Display name |
| `DEBUG` | `false` | No | Enables FastAPI debug mode |
| `LOG_LEVEL` | `INFO` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `OPENAI_API_KEY` | None | At least one LLM key | OpenAI GPT-4 and DALL-E |
| `ANTHROPIC_API_KEY` | None | At least one LLM key | Anthropic Claude models |
| `GOOGLE_API_KEY` | None | Only for Google image gen | Google Gemini image generation |
| `DEFAULT_LLM_PROVIDER` | `anthropic` | No | `openai` or `anthropic` |
| `BRIEF_ANALYZER_PROVIDER` | `anthropic` | No | LLM provider for brief analysis |
| `BRIEF_ANALYZER_OPENAI_MODEL` | `gpt-4-turbo-preview` | No | OpenAI model for brief analysis |
| `BRIEF_ANALYZER_ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | No | Anthropic model for brief analysis |
| `MJML_GENERATION_PROVIDER` | `anthropic` | No | LLM provider for MJML generation |
| `MJML_GENERATION_OPENAI_MODEL` | `gpt-4-turbo-preview` | No | OpenAI model for MJML |
| `MJML_GENERATION_ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | No | Anthropic model for MJML |
| `FEEDBACK_ENGINE_PROVIDER` | `anthropic` | No | LLM provider for feedback revision |
| `FEEDBACK_ENGINE_OPENAI_MODEL` | `gpt-4-turbo-preview` | No | OpenAI model for feedback |
| `FEEDBACK_ENGINE_ANTHROPIC_MODEL` | `claude-3-sonnet-20240229` | No | Anthropic model for feedback |
| `IMAGE_GENERATION_PROVIDER` | `openai` | No | Must be `openai` (DALL-E) |
| `IMAGE_GENERATION_OPENAI_DALLE_MODEL` | `dall-e-3` | No | DALL-E model |
| `IMAGE_GENERATION_GOOGLE_MODEL` | `gemini-3.1-flash-image-preview` | No | Google image model (experimental) |
| `RAG_GENERATION_PROVIDER` | `openai` | No | LLM provider for RAG content fill |
| `RAG_GENERATION_OPENAI_MODEL` | `gpt-4o` | No | OpenAI model for RAG |
| `EMBEDDING_MODEL_NAME` | `text-embedding-3-small` | No | OpenAI embedding model |
| `RAG_ENABLED` | `true` | No | Controls RAG migrations |
| `DATABASE_URL` | None | Yes | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `LANGGRAPH_CHECKPOINTER_DB_URL` | None | Yes (for Postgres checkpointer) | `postgresql://user:pass@host:5432/dbname` |
| `SQLITE_CHECKPOINTER_DB_FILE` | `data/langgraph_checkpoints.sqlite` | No | SQLite fallback path |
| `MJML_CLI_PATH` | `mjml` | Yes | Path to MJML CLI binary |

---

## 13. Local Setup — Step by Step

### Prerequisites

- **Python 3.10+** — `python --version`
- **Node.js & npm** — `node --version`, `npm --version`
- **PostgreSQL** — running locally, accessible via `psql`

### Step 1 — Clone and create a virtual environment

```bash
git clone <repository-url>
cd Mailwright-Agentic_Marketing_Email_Platform

python -m venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Linux / macOS)
source .venv/bin/activate
```

### Step 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Install the MJML CLI

MJML is a Node.js tool. Install it globally so it is on your `PATH`:

```bash
npm install -g mjml
mjml --version   # Should print a version number
```

### Step 4 — Create the PostgreSQL database

```bash
createdb mailwright_db
```

### Step 5 — Configure environment variables

```bash
# Copy the example file
copy .env.example .env     # Windows
cp .env.example .env       # Linux / macOS
```

Edit `.env` with your real values. Minimum required configuration:

```bash
# At least one LLM API key
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Choose your default provider
DEFAULT_LLM_PROVIDER=anthropic

# Database (replace credentials with your PostgreSQL setup)
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/mailwright_db
LANGGRAPH_CHECKPOINTER_DB_URL=postgresql://postgres:password@localhost:5432/mailwright_db

# MJML CLI
MJML_CLI_PATH=mjml

# Optional: enable verbose logs during development
DEBUG=true
LOG_LEVEL=DEBUG
```

### Step 6 — Run database migrations

```bash
alembic upgrade head
```

This creates the `template_versions` and `rag_templates` tables plus the LangGraph checkpoint tables.

### Step 7 — (Optional) Ingest the RAG corpus

Only needed if you want to use `rag_flow: true` mode:

```bash
python scripts/ingest_rag_corpus.py
```

This reads all ~1,600 JSON files from `templates/`, extracts HTML, generates embeddings, and inserts them into the `rag_templates` table. This can take several minutes depending on your API rate limits.

---

## 14. Running the Application

```bash
# Development server with hot reload
uvicorn mailwright.main:app --reload --host 0.0.0.0 --port 8000
```

Verify the app is running:

```bash
curl http://localhost:8000/api/v1/health
# → {"status": "healthy"}
```

Open interactive API documentation (Swagger UI):

```
http://localhost:8000/docs
```

The `ReDoc` alternative is available at:

```
http://localhost:8000/redoc
```

---

## 15. Gradio UI

An optional web chat interface is included in `ui/app.py`. It connects to the running backend and lets you send briefs and read responses without using `curl`.

### Running the UI

```bash
# Install UI-specific dependencies
pip install -r ui/requirements.txt

# Start the Gradio server
python ui/app.py
```

Open `http://localhost:7860` in your browser.

The UI provides:
- A chat input to send briefs as natural language
- A configurable API base URL (default: `http://localhost:8000`)
- A sidebar showing the current thread ID, template ID, and version ID

The Gradio UI communicates with the backend via the `POST /api/v1/chat/` endpoint using the conversational chat graph.

---

## 16. End-to-End API Walkthrough

### Scenario A: Generate a Welcome Email (MJML workflow)

**Step 1 — Submit the brief**

```bash
curl -X POST http://localhost:8000/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{
    "user_brief": {
      "subject": "Welcome to StyleHub!",
      "body_copy": "Thanks for joining us. Explore our curated collections and enjoy 15% off your first order.",
      "cta_text": "Start Shopping",
      "cta_url": "https://stylehub.com/shop",
      "image_suggestions": ["stylish fashion model in summer outfit"]
    }
  }'
```

Response (HTTP 202):
```json
{
  "template_id": "3f8a1234-abcd-...",
  "task_id": "3f8a1234-abcd-...",
  "status": "PENDING_BRIEF_ANALYSIS",
  "status_poll_url": "/api/v1/templates/3f8a1234-abcd-.../status"
}
```

**Step 2 — Poll status until ready**

```bash
curl http://localhost:8000/api/v1/templates/3f8a1234-abcd-.../status
```

When done:
```json
{
  "template_id": "3f8a1234-abcd-...",
  "status": "READY_FOR_PREVIEW",
  "current_version_id": "v0",
  "html_preview_url": "/api/v1/templates/3f8a1234-abcd-.../versions/v0/html"
}
```

**Step 3 — Preview the HTML**

```bash
curl http://localhost:8000/api/v1/templates/3f8a1234-abcd-.../versions/v0/html
# Returns a full responsive HTML email
```

**Step 4 — Submit feedback**

```bash
curl -X POST http://localhost:8000/api/v1/templates/3f8a1234-abcd-.../versions/v0/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "feedback_text": "The header font is too large. Change the CTA button to dark navy and make the body text more concise."
  }'
```

Response (HTTP 202): `{ "message": "Feedback received and revision process initiated." }`

**Step 5 — List versions**

```bash
curl http://localhost:8000/api/v1/templates/3f8a1234-abcd-.../versions
```

```json
{
  "versions": [
    { "version_id": "v0", "is_approved": false, "created_at": "..." },
    { "version_id": "v_rev_a1b2c3d4", "is_approved": false, "created_at": "..." }
  ]
}
```

**Step 6 — Approve the revised version**

```bash
curl -X POST http://localhost:8000/api/v1/templates/3f8a1234-abcd-.../versions/v_rev_a1b2c3d4/approve
```

```json
{
  "template_id": "3f8a1234-abcd-...",
  "approved_version_id": "v_rev_a1b2c3d4",
  "status": "approved"
}
```

---

### Scenario B: RAG-Based Email (fast path)

```bash
curl -X POST http://localhost:8000/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{
    "rag_flow": true,
    "plain_text_brief": "Product launch for new noise-cancelling headphones. Target: tech-savvy millennials. Tone: energetic. 20% launch discount. CTA: Shop Now.",
    "use_placeholders": false
  }'
```

The response arrives much faster. Same polling / preview / approval flow applies.

---

### Scenario C: Clarification Loop

If the brief is too vague, the graph pauses:

```bash
# Submit vague brief
curl -X POST http://localhost:8000/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{"user_brief": {"subject": "Email", "body_copy": "Buy stuff."}}'
```

Status response:
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

Submit the amended brief:

```bash
curl -X PUT http://localhost:8000/api/v1/templates/<id>/brief \
  -H "Content-Type: application/json" \
  -d '{
    "user_brief": {
      "subject": "Flash Sale: 40% Off Electronics Today Only",
      "body_copy": "Shop our biggest electronics sale. All laptops, phones, and headphones 40% off — today only.",
      "cta_text": "Shop Flash Sale",
      "cta_url": "https://example.com/flash"
    }
  }'
```

The graph resumes from the interrupt point and continues to image generation → MJML → storage.

---

## 17. Testing Guide

### Running Tests

```bash
# All tests
pytest

# Unit tests only (no database required)
pytest tests/unit/ -v

# Integration tests (PostgreSQL required)
pytest tests/integration/ -v

# API endpoint tests
pytest tests/api/ -v

# Specific file
pytest tests/unit/test_brief_analyzer_service.py -v

# With coverage report
pytest --cov=Mailwright --cov-report=html --cov-report=term

# Re-run only the last failures
pytest --lf

# Match tests by name pattern
pytest -k "test_brief" -v
```

### Test Structure

```
tests/
├── conftest.py                               # Shared fixtures; runs alembic upgrade head
│
├── unit/                                     # Fast, isolated; all external calls are mocked
│   ├── test_brief_analyzer_service.py        # BriefAnalyzerService with mocked LLM
│   ├── test_mjml_service.py                  # MJMLService with mocked LLM and CLI
│   ├── test_image_generator_service.py       # ImageGeneratorService with mocked DALL-E
│   ├── test_llm_factory.py                   # Factory returns correct client type
│   └── graphs/test_checkpointer.py           # Checkpointer factory logic
│
├── integration/                              # Full graph with MemorySaver (no real DB writes)
│   └── test_template_generation_graph.py     # End-to-end workflow paths + feedback loop
│
└── api/v1/                                   # HTTP layer with FastAPI TestClient
    └── test_template_routes.py               # HTTP request/response shape tests
```

A Postman collection is also available at `tests/Mailwright API - TemplateGen Tests.postman_collection.json` for manual API testing.

### Asyncio Configuration

The project sets `asyncio_mode = "auto"` in `pyproject.toml`. This means all `async def test_*` functions are automatically treated as async tests — you do **not** need to add `@pytest.mark.asyncio` decorators.

### Unit Test Example

```python
async def test_brief_analysis_clear():
    service = BriefAnalyzerService()
    with patch.object(service.llm_client, 'ainvoke') as mock_llm:
        mock_llm.return_value = MockMessage(content='{"status": "BRIEF_OK", "questions": []}')
        result = await service.analyze(sample_brief)
    assert result.status == "BRIEF_OK"
```

### Integration Test Example

```python
async def test_full_workflow_brief_ok(compiled_graph_with_memory_saver):
    graph, _ = compiled_graph_with_memory_saver
    config = {"configurable": {"thread_id": "test-123"}}

    with patch('mailwright.core_services.mjml_service.MJMLService.compile_mjml') as mock_compile:
        mock_compile.return_value = ("<html>...</html>", "VALID")
        result = await graph.ainvoke(initial_state, config)

    assert result["last_operation_status"] == "SUCCESS_STORED_V0"
```

### Linting

```bash
ruff check .            # Report issues
ruff check . --fix      # Auto-fix where possible
ruff format .           # Format code (like Black)
```

Ruff is configured in `pyproject.toml`:
- Line length: 88
- Rules: `E`, `F`, `B` (bugbear), `C4` (comprehensions), `SIM` (simplify)
- `E501` (line too long) is ignored
- Excluded: `.venv`, `build`, `dist`, `mailwright/legacy_code`, `archive/`

---

## 18. Code Patterns & Conventions

### Service Pattern

```python
class MyService:
    def __init__(self):
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

### LangGraph Node Pattern

```python
async def my_node(state: GraphState, config: dict) -> Dict[str, Any]:
    """Node docstring explains what this step does."""
    logger.info("--- Executing MyNode ---")

    if not state.some_required_field:
        return {
            "error_message": "Required field missing",
            "last_operation_status": "ERROR_MY_NODE"
        }

    try:
        result = await some_service.process(state.some_required_field)
        return {
            "output_field": result,
            "last_operation_status": "SUCCESS_MY_NODE",
            "error_message": None,
        }
    except Exception as e:
        logger.exception("MyNode failed")
        return {
            "error_message": str(e),
            "last_operation_status": "ERROR_MY_NODE",
        }
```

Key rules for nodes:
- Always return a **dict** of state field updates (never the full state object).
- Never raise from a node — capture exceptions and set `error_message`.
- Always update `last_operation_status`.
- Log entry and exit for traceability.

### Database Operation Pattern

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

### API Endpoint Pattern

```python
@router.post("/templates", response_model=TemplateCreationResponseSchema, status_code=202)
async def create_template(
    request: TemplateCreationRequest,
    background_tasks: BackgroundTasks,
) -> TemplateCreationResponseSchema:
    try:
        template_id = str(uuid.uuid4())
        background_tasks.add_task(run_graph_workflow, template_id, request)
        return TemplateCreationResponseSchema(
            template_id=template_id,
            status="PENDING_BRIEF_ANALYSIS",
        )
    except Exception as e:
        logger.error(f"Template creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### Error Handling Convention

| Layer | Rule |
|-------|------|
| **LangGraph nodes** | Catch all exceptions; return partial dict with `error_message` and `ERROR_*` status |
| **Core services** | Raise typed service exceptions (`MyServiceError`) |
| **API routes** | Catch everything; convert to `HTTPException` |
| **Routing functions** | Check `last_operation_status`; route to `END` on errors |

---

## 19. Context Engineering

> *"Context engineering is the delicate art and science of filling the context window with just the right information for the LLM to accomplish the task."*
> — Andrej Karpathy

Context engineering is a first-class architectural concern in mailwright. The `context_engineering.md` file in the repo documents the full theory and practice. This section summarises the key concepts and maps them directly to Mailwright's code.

---

### 19a. What Is Context Engineering?

Context engineering is **not** the same as prompt engineering.

| Aspect | Prompt Engineering | Context Engineering |
|--------|-------------------|-------------------|
| Focus | How you *word* the instruction | *What information* goes in the context window |
| Nature | Mostly static | Dynamic — changes every turn |
| Scope | System prompt wording, few-shot examples | Memory, history, retrieved docs, injected state |
| When it matters | At design time | At runtime, every request |

It is the discipline of deciding:
- **What** history to keep or drop
- **How** to compress long conversations
- **When** to fetch external knowledge (RAG)
- **How much** of the token budget to allocate to each piece of context

Mailwright uses context engineering in five specific ways:

```
┌──────────────────────────────────────────────────────────────┐
│                    CONTEXT ENGINEERING                       │
│                                                              │
│   1. Memory Management       — What history to keep/drop     │
│   2. Prompt Engineering      — How to structure instructions │
│   3. RAG                     — Fetching relevant knowledge   │
│   4. Tool / State Injection  — Structured data into context  │
│   5. Token Budget Management — Fitting within the limit      │
└──────────────────────────────────────────────────────────────┘
```

---

### 19b. The Context Window Mental Model

Everything the LLM "knows" for a given request fits inside one box:

```
┌─────────────────────────────────────────────────────────┐
│                   CONTEXT WINDOW                        │
│                  (e.g. 128k tokens)                     │
│                                                         │
│  [ System Prompt        ]  ~3,000 tokens  (fixed)       │
│  [ Long-term Memories   ]  ~500  tokens  (retrieved)    │
│  [ Conversation History ]  varies        (managed)      │
│  [ Retrieved Documents  ]  varies        (RAG)          │
│  [ Injected State       ]  varies        (tools/state)  │
│  [ Current User Message ]  ~100  tokens  (new)          │
│                                                         │
│  TOTAL must stay under the model's limit                │
└─────────────────────────────────────────────────────────┘
```

When the total exceeds the limit → the model truncates silently, forgets context, hallucinates, or throws an error. Managing this box intelligently is the entire point of context engineering.

---

### 19c. Memory Management Strategies

#### Strategy 1 — Message Window (Sliding Window)

Keep only the last N messages. Everything before is dropped permanently.

```python
from langchain_core.messages import trim_messages

trimmed = trim_messages(
    state["messages"],
    max_tokens=8000,
    token_counter=llm,       # uses the LLM's tokenizer
    strategy="last",         # keep the most recent messages
    include_system=True,     # always keep system prompt
    start_on="human"         # always start with a human message
)
```

**Pros:** Simple, 5-line fix, guaranteed token safety  
**Cons:** Early context is permanently lost — agent forgets original goals

---

#### Strategy 2 — Rolling Summarization ✅ Used in Mailwright's chat graph

Instead of dropping old messages, compress them into a summary that preserves key facts.

```
Turns 1-10 (old) ──► LLM summarizes ──► "User is creating a summer sale email.
                                          Subject: 'Summer Sale – 50% Off'.
                                          CTA: 'Shop Now' → https://example.com/sale.
                                          Template ID: 3f8a... Version: v0."
                                          [~80 tokens instead of ~2000]

Turns 11-16 (recent) → kept in full
Turn 17 (new)        → user types here
```

**Implementation in mailwright** (`mailwright/graphs/chat_graph.py`):

```python
_SUMMARY_THRESHOLD = 10   # compress when total messages exceed this
_KEEP_RECENT = 6          # always keep the 6 most-recent messages verbatim

async def apply_rolling_summary(messages, threshold=10, keep_recent=6):
    if len(messages) <= threshold:
        return messages  # nothing to do yet

    old_messages  = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Ask LLM to compress old messages (max 180 words, bullet points)
    response = await llm.ainvoke([
        SystemMessage(content=_ROLLING_SUMMARY_SYSTEM),
        HumanMessage(content=format_messages(old_messages)),
    ])

    summary_message = {
        "role": "assistant",
        "content": f"[CONVERSATION SUMMARY — earlier turns]\n{response.content}",
    }
    return [summary_message] + recent_messages
```

The route handler (`chat_routes.py`) calls this after every turn and persists the compressed list to the checkpointer.

**Pros:** Retains full intent across long conversations, token-safe, graceful fallback  
**Cons:** Two LLM calls per summarization step; subtle nuances can occasionally be lost

---

#### Strategy 3 — Structured State as Memory ✅ Used in Mailwright's template graph

For domain-specific applications that build structured state over time, **the state itself is the memory** — you do not need the raw conversation history.

```
❌ NAIVE — send raw message history:
   Turn 1 + Turn 2 + ... + Turn 10 messages → LLM

✅ Mailwright — send the accumulated GraphState:
   [GraphState: current_mjml, compiled_html, version_id, brief_data]
   [Last LLM prompt + response]
   [New input]
   → LLM
```

In Mailwright's template graph, the `GraphState` object IS the memory. After each node, the state is saved by the checkpointer. When the graph is resumed (e.g. after the user submits feedback), the full state is reloaded and the LLM only needs to see the current MJML + the feedback text — not a replay of the entire conversation.

**Token usage becomes roughly constant regardless of how many revision cycles have occurred.**

---

#### Strategy 4 — Two-Tier Hot/Cold Memory

A pattern described in `context_engineering.md` for production systems:

```
┌────────────────────────────────────────┐
│  HOT MEMORY (inside context window)    │
│  - Last 4-6 turns                      │
│  - Current state summary               │
│  - Key facts extracted from history    │
└───────────────────┬────────────────────┘
                    │ retrieved on demand
┌───────────────────▼────────────────────┐
│  COLD MEMORY (database / vector store) │
│  - Full conversation history           │
│  - All checkpoint snapshots            │
│  - Historical versions of state        │
└────────────────────────────────────────┘
```

In Mailwright, PostgreSQL (via the LangGraph checkpointer) serves as cold memory, and the `ChatState.messages` list (after rolling summarization) serves as hot memory.

---

### 19d. Prompt Engineering within Context Engineering

System prompts in Mailwright follow a structured approach. The chat graph uses two role-specific system prompts:

**`_GATHERING_SYSTEM_PROMPT`** — scoped strictly to collecting brief information:

```
Structure:
  ROLE        — "You are Mailwright, a dedicated email marketing template creation assistant."
  SCOPE RULE  — strictly enforced; off-topic questions are redirected
  GOAL        — gather 5 fields in order (subject, body_copy, cta_text, cta_url, images)
  RULES       — ask 1-2 questions at a time; image question is mandatory; confirm before generating
  CONTEXT     — dynamically injects what has been collected so far (subject: ..., body_copy: ...)
  OUTPUT      — structured ChatLLMDecision (not free-form text)
```

**`_REVIEW_SYSTEM_PROMPT`** — scoped to reviewing and refining the generated template:

```
Structure:
  ROLE        — same scope enforcement
  CONTEXT     — injects template_id and version_id for preview URLs
  CASES       — handles change request / approval / question / out-of-scope as explicit branches
  OUTPUT      — structured ChatLLMDecision with action field
```

Key prompt engineering principles applied:
- **Structured output** over free-form text — routes are determined by `action` field, not string parsing
- **Labeled sections** keep long prompts navigable for the model
- **Dynamic context injection** — `collected_info` is built at runtime and injected into the prompt each turn
- **Guard rails** are explicit and scoped: the "SCOPE RULE" section appears first in both prompts

---

### 19e. RAG — Retrieval-Augmented Generation

RAG is used in Mailwright's template generation fast path (section 6b). The principle:

```
User brief (plain text)
        ↓
LLM extracts structural fingerprint
        ↓
Embed fingerprint as a vector (text-embedding-3-small)
        ↓
pgvector cosine similarity search over rag_templates table
        ↓
Retrieve HTML of the most structurally similar template
        ↓
LLM fills retrieved HTML with user's specific content
        ↓
Final HTML email (produced in seconds)
```

**Why RAG instead of fine-tuning for this use case:**

| | RAG | Fine-Tuning |
|--|-----|------------|
| Update knowledge | Real-time — just re-ingest corpus | Requires retraining |
| Cost | Low (vector search) | High (GPU training time) |
| Best for | Structural patterns from real templates | Style and behavior changes |
| Hallucination risk | Lower — grounded in retrieved HTML | Higher without grounding |

The corpus of ~1,600 real email templates gives the LLM access to proven, tested email structures rather than generating layouts from scratch (which often produces non-standard HTML that breaks in email clients).

---

### 19f. Tool and State Injection

Mailwright injects structured domain state into every LLM call rather than relying on raw conversation history:

**In the chat graph — gathering phase:**

```python
# Injected at runtime into the system prompt each turn:
collected_info = """
  subject      : Summer Sale — 50% Off
  body_copy    : Huge discounts across all...
  cta_text     : Shop Now
  cta_url      : (not collected yet)
  images       : (not asked yet)
"""
system_content = _GATHERING_SYSTEM_PROMPT.format(collected_info=collected_info)
```

This means the LLM never needs to re-read 6 turns of conversation to know what has been collected — it is told explicitly every turn.

**In the template graph — feedback node:**

```python
# Only the relevant state fields are injected into the LLM call:
{
    "current_mjml": version.mjml_source,        # what to revise
    "user_feedback_content": feedback_text,      # what to change
    "version_id_for_feedback": current_version,  # which version
}
```

The LLM does not need full generation history — it only needs the current MJML and the change request.

---

### 19g. Token Budget Management

Without token management, a long chat conversation sends an unbounded number of tokens to the LLM on every turn:

```
Turn 1 :  system prompt + 1 msg        = ~3,100 tokens
Turn 10:  system prompt + 19 msgs      = ~8,000 tokens
Turn 30:  system prompt + 59 msgs      = ~25,000 tokens  ← expensive
Turn 50:  system prompt + 99 msgs      = ~40,000+ tokens ← crash risk
```

At GPT-4o pricing ($2.50 / 1M input tokens), 1,000 requests/day at turn 30 ≈ **$62/day** just in input tokens.

With rolling summarization (Strategy 2), the effective context stays roughly constant:

```
What goes to LLM per turn:           Tokens (approx)
─────────────────────────────────    ───────────────
System prompt (fixed)                ~3,000
Rolling summary (replaces old turns) ~200
Last 6 messages verbatim             ~1,200
New user message                     ~100
─────────────────────────────────    ───────────────
TOTAL (roughly constant)             ~4,500
```

Same 1,000 requests/day at ~4,500 tokens ≈ **$11/day** — approximately an 82% cost reduction.

For production use, `context_engineering.md` also documents a `tiktoken`-based pre-call budget check pattern:

```python
import tiktoken

def check_token_budget(messages: list, model: str = "gpt-4o") -> dict:
    enc = tiktoken.encoding_for_model(model)
    total = sum(len(enc.encode(m.content)) + 4 for m in messages) + 2
    return {
        "total_tokens": total,
        "within_budget": total < 100_000,
        "headroom": 100_000 - total,
    }
```

**Token allocation priority (from `context_engineering.md`):**

```
Priority 1 (always include):  system prompt, current state summary, user message
Priority 2 (if budget allows): recent conversation turns (newest first)
Priority 3 (if budget allows): retrieved RAG documents
Priority 4 (drop first):       verbose AI responses from old turns, raw JSON blobs
```

---

### 19h. How Mailwright Applies These Principles

| Principle | How Mailwright Uses It |
|-----------|----------------|
| **Rolling summarization** | `apply_rolling_summary()` in `chat_graph.py`; compresses after 10 messages, keeps last 6 verbatim; called by `chat_routes.py` after every turn |
| **Structured state as memory** | `GraphState` in `template_generation_graph.py`; LLM only sees relevant state fields per node, not full history |
| **Dynamic state injection** | `_GATHERING_SYSTEM_PROMPT` injects `collected_info` live each turn; feedback node injects only `current_mjml` + `feedback_text` |
| **Structured output** | `ChatLLMDecision` Pydantic model; LLM returns typed JSON not free-form text — routing is deterministic |
| **RAG grounding** | `rag_template_service.py`; pgvector cosine search on `rag_templates`; fills real templates instead of hallucinating layouts |
| **Scoped system prompts** | Separate prompts for gathering vs review phases; explicit scope rule redirects off-topic requests |
| **Graceful fallback** | `apply_rolling_summary` returns original messages unchanged if summarization LLM call fails |

---

## 20. CI / CD

GitHub Actions is configured in `.github/workflows/ci.yml`.

**Triggers:** Push or PR to `sprint1` or `main` branches.

**Jobs:**

| Job | Steps |
|-----|-------|
| `lint` | Checkout → set up Python 3.10 → `pip install ruff` → `ruff check . --output-format=github` |

**Not yet in CI:**
- `pytest` — tests require a live PostgreSQL instance; integration into CI is a planned improvement.
- Docker build — no Dockerfile exists currently.

---

## 21. Sprint History

| Sprint | Status | Key Deliverables |
|--------|--------|-----------------|
| Sprint 1 | Complete | Basic FastAPI + LangGraph skeleton; SQLite checkpointer; initial brief analysis node |
| Sprint 2 | Complete | DALL-E image generation; PostgreSQL versioning (`TemplateVersion` table); `LG_StoreV0` node; HTML/MJML preview endpoints; production Postgres checkpointer; standardised logging |
| Sprint 3 | Complete | Feedback loop (`LG_FeedbackEngineNode` → `LG_StoreVNextNode`); approval endpoint; comprehensive integration tests for feedback and approval scenarios |
| Sprint 5 | Complete | Full RAG pipeline (fingerprint → embedding → pgvector search → content population); ~1,600-template corpus ingestion; `rag_templates` DB table; `RAGTemplateService` |

---

## 22. Common Issues & Debugging

### "Failed to initialize checkpointer" on startup

- Verify `LANGGRAPH_CHECKPOINTER_DB_URL` is set in `.env` and points to a running PostgreSQL instance.
- Test connectivity: `pg_isready -d mailwright_db`
- For SQLite fallback during development, create the directory: `mkdir -p data`

### "MJML CLI not found" or compilation errors

- Ensure MJML is installed globally: `npm install -g mjml`
- Test it: `mjml --version`
- If installed locally (not globally), set the full path: `MJML_CLI_PATH=/path/to/node_modules/.bin/mjml`

### "No suitable template found in the RAG corpus"

- The RAG corpus has not been ingested yet. Run: `python scripts/ingest_rag_corpus.py`
- Verify row count: `psql -d mailwright_db -c "SELECT COUNT(*) FROM rag_templates;"`

### Template status stuck at "WAITING_FOR_AMENDED_BRIEF"

- Call `GET /api/v1/templates/{id}/status` — the `clarification_questions` array tells you what questions to answer.
- Call `PUT /api/v1/templates/{id}/brief` with a more detailed brief to resume the graph.

### Inspecting the database for debugging

```bash
psql -d mailwright_db

-- Most recent LangGraph checkpoints
SELECT thread_id, checkpoint_id, created_at
FROM checkpoints
ORDER BY created_at DESC LIMIT 10;

-- All template versions
SELECT template_id, version_id, is_approved, created_at
FROM template_versions
ORDER BY created_at DESC LIMIT 20;

-- RAG corpus size
SELECT COUNT(*) FROM rag_templates;
```

### Adding logging to trace a specific node

```python
import logging
logger = logging.getLogger(__name__)

async def my_node(state: GraphState) -> Dict:
    logger.debug(f"State entering my_node: {state.model_dump()}")
    # node logic ...
```

Set `LOG_LEVEL=DEBUG` in `.env` to see all node-level logs in the console output.

### Test failures due to asyncio conflicts

Ensure `pyproject.toml` contains:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
asyncio_default_test_loop_scope = "function"
```

All test fixtures that use async resources (DB sessions, graph instances) must use `scope="function"` to avoid event loop sharing across tests.

---

## 23. Key Files Quick Reference

| File | When to look here |
|------|------------------|
| `mailwright/config.py` | Adding a new environment variable or changing a default model |
| `mailwright/main.py` | App startup, middleware, adding a new router group |
| `mailwright/api/v1/router.py` | Registering a new route group or prefix |
| `mailwright/api/v1/template_routes.py` | Adding or modifying HTTP endpoints |
| `mailwright/api/v1/chat_routes.py` | Chat endpoint logic |
| `mailwright/graphs/state.py` | Adding new fields to the workflow state |
| `mailwright/graphs/template_generation_graph.py` | Adding/modifying nodes or routing logic |
| `mailwright/graphs/checkpointer.py` | Checkpointer connection or fallback issues |
| `mailwright/graphs/chat_graph.py` | Chat workflow with rolling summarisation |
| `mailwright/core_services/brief_analyzer_service.py` | Tuning brief analysis prompts |
| `mailwright/core_services/mjml_service.py` | MJML generation prompts; CLI interaction |
| `mailwright/core_services/feedback_engine_service.py` | Feedback revision prompts |
| `mailwright/core_services/rag_template_service.py` | RAG similarity search; content population prompts |
| `mailwright/core_services/llm_factory.py` | Adding support for a new LLM provider |
| `mailwright/db/models.py` | Adding a new database table or column |
| `mailwright/db/template_store.py` | Adding a new database query function |
| `mailwright/schemas/template_schemas.py` | Changing API request/response shapes |
| `mailwright/schemas/chat_schemas.py` | Changing chat API shapes |
| `alembic/versions/` | Migration history; writing new migrations |
| `scripts/ingest_rag_corpus.py` | RAG corpus ingestion pipeline |
| `tests/conftest.py` | Shared test fixtures; DB setup |
| `tests/integration/test_template_generation_graph.py` | Understanding full workflow behaviour end-to-end |
| `.env.example` | Reference for all required environment variables |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **MJML** | A framework for writing responsive email templates in an XML-like language. The MJML CLI compiles it to standard HTML that renders correctly across email clients. |
| **LangGraph** | A library (part of the LangChain ecosystem) for building stateful, resumable AI agent workflows modelled as directed graphs. |
| **GraphState** | The single Pydantic model that carries all data through the LangGraph workflow. Every node reads from it and returns a dict of updates to it. |
| **Checkpointer** | A LangGraph component that serialises and saves `GraphState` to a database after every node. Enables the graph to be paused and resumed across separate HTTP requests. |
| **Thread ID** | LangGraph's key for identifying which saved state to load. In Mailwright, the `template_id` UUID also serves as the `thread_id`. |
| **RAG** | Retrieval-Augmented Generation — a technique where, instead of generating content from scratch, an LLM is given a retrieved document (here, an existing template) to base its output on. |
| **pgvector** | A PostgreSQL extension that adds a `vector` column type and cosine/L2 similarity operators, enabling efficient nearest-neighbour search over embeddings. |
| **Fingerprint** | A concise structural description of an email template (e.g., "product launch, 2-column layout, single CTA"). Used as the embedding input for RAG similarity search. |
| **Version** | One saved output of a template generation or revision run. `v0` is always the first version; `v_rev_*` versions are created by the feedback loop. |
| **Brief** | The user's input describing the desired email: subject, body copy, CTA text/URL, and optional image suggestions. |
| **Feedback Loop** | The cycle of `POST /feedback` → AI revision → new version → user reviews → repeat until satisfied. |
| **Alembic** | A database schema migration tool for SQLAlchemy. Manages incremental, versioned changes to the PostgreSQL schema. |
| **pydantic-settings** | A Pydantic extension that reads configuration from environment variables and `.env` files into typed Python objects. |
| **Ruff** | A fast Python linter and formatter written in Rust; used here as a drop-in replacement for flake8 + Black. |

---

*Last updated: May 2026. Based on full codebase analysis of the Mailwright-Agentic_Marketing_Email_Platform-main project.*
