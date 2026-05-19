# Mailwright — Agentic Marketing Email Platform

Mailwright turns a marketing brief into a responsive marketing email. You describe the campaign (subject, copy, CTA, images); LangGraph orchestrates LLM and tool steps to produce MJML, compile it to HTML, store versioned templates in PostgreSQL, and support chat-based review, feedback, and approval.

**Stack:** FastAPI · LangGraph · PostgreSQL · MJML CLI · OpenAI / Anthropic · Gradio UI

---

## What it does

| Capability | Description |
|------------|-------------|
| **Brief → email** | Analyze brief, generate images (optional), write MJML, validate and compile to HTML |
| **Versioning** | Each generation is stored as `v0`, `v_rev_1`, … with MJML, HTML, and brief snapshot |
| **Feedback loop** | Natural-language revisions re-run the feedback engine and store a new version |
| **Chat UI** | Gradio client talks to `/api/v1/chat/` for gathering requirements, generate, revise, approve |
| **REST API** | Direct template creation, status, preview, feedback, and approve without chat |
| **RAG path (optional)** | When `RAG_ENABLED=true`, retrieve a corpus HTML template and populate content instead of MJML-from-scratch |

---

## Workflows

### Chat UI (recommended)

Gradio (`ui/app.py`) → `POST /api/v1/chat/` → **Chat LangGraph** (`mailwright/graphs/chat_graph.py`).

Phases: `gathering` → `review` → `approved`

```mermaid
flowchart TD
    A[User in Gradio UI] --> B[POST /api/v1/chat/]
    B --> C[Chat LangGraph]
    C --> D[LG_Chat_Conversation]

    D -->|reply only| E[END]
    D -->|start_generation| F[LG_Chat_Generate]
    D -->|submit_feedback| G[LG_Chat_Feedback]
    D -->|approve| H[LG_Chat_Approve]

    F --> TG[Template Generation Graph]
    H --> J[Mark version approved in DB]

    TG --> K[Brief Analyzer]
    K -->|BRIEF_OK| M[Image Generation]
    M --> N[MJML Generation]
    N --> O[MJML Validate + Compile]
    O --> P[Store v0]
    P --> Q[Review + preview URL]

    G --> R[Feedback Engine]
    R --> O2[Validate + Compile]
    O2 --> S[Store v_next]
    S --> Q

    E --> T[PostgreSQL checkpointer]
    Q --> T
    J --> T
```

### Template generation (REST or invoked from chat)

Two pipelines, selected by `rag_flow` / `RAG_ENABLED`:

| Path | When | Steps |
|------|------|--------|
| **MJML (default)** | `RAG_ENABLED=false` | Brief analyzer → images → MJML LLM → MJML CLI → store |
| **RAG** | `RAG_ENABLED=true` | Fingerprint → vector search → populate HTML → store |

LangGraph checkpoint tables are created at app startup (`checkpointer.setup()`). Application tables (`template_versions`, optional `rag_templates`) are managed with **Alembic**.

---

## Quick start

### Prerequisites

- Python 3.10+
- PostgreSQL
- Node.js (for MJML CLI)
- OpenAI and/or Anthropic API key

### Setup

```bash
git clone <repository-url>
cd <project-root>

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
npm install -g mjml
```

Create `.env` in the project root (see `mailwright/config.py` for all options):

```bash
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/mailwright_db
LANGGRAPH_CHECKPOINTER_DB_URL=postgresql://postgres:password@localhost:5432/mailwright_db
MJML_CLI_PATH=mjml
RAG_ENABLED=false
```

```bash
createdb mailwright_db
alembic upgrade head
```

### Run

```bash
# API (port 8000)
uvicorn mailwright.main:app --reload --host 0.0.0.0 --port 8000

# Chat UI (port 7860)
python ui/app.py
```

- API docs: http://localhost:8000/docs  
- Health: http://localhost:8000/api/v1/health  

### Optional: RAG corpus

```bash
# Only when RAG_ENABLED=true
python scripts/ingest_rag_corpus.py
```

---

## Project layout

```
mailwright/
├── main.py                    # FastAPI entry, checkpointer setup
├── config.py                  # Settings from .env
├── api/v1/
│   ├── template_routes.py     # Template CRUD, feedback, approve, preview
│   └── chat_routes.py         # Conversational endpoint
├── graphs/
│   ├── chat_graph.py          # Chat orchestration
│   ├── template_generation_graph.py
│   └── checkpointer.py
├── core_services/             # Brief analyzer, MJML, images, feedback, RAG
├── db/                        # SQLAlchemy models + template store
└── schemas/
ui/app.py                      # Gradio chat UI
alembic/                       # DB migrations (template_versions, rag_templates)
tests/
```

---

## API overview

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/v1/templates` | Start generation from a brief |
| `GET` | `/api/v1/templates/{id}/status` | Workflow status |
| `GET` | `/api/v1/templates/{id}/versions/{v}/html` | Preview HTML |
| `POST` | `/api/v1/templates/{id}/versions/{v}/feedback` | Submit revision feedback |
| `POST` | `/api/v1/templates/{id}/versions/{v}/approve` | Approve a version |
| `POST` | `/api/v1/chat/` | Chat turn (used by Gradio) |

---

## Development

```bash
pytest
ruff check .
ruff format .
alembic upgrade head
```

For deeper onboarding and module reference, see `ONBOARDING.md` and `MODULE_REFERENCE.md`.
