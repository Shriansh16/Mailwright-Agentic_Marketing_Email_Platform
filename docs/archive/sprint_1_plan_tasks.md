# Sprint 1: Core Infrastructure & Initial Generation Path

**Overall Goal**

Establish the foundational FastAPI application, LangGraph setup, and the initial path for MJML generation from a user brief, including AI‑driven clarification.

```mermaid
graph TD
    A[Start Sprint 1] --> B{1. Project Setup & CI/CD};
    B --> B1[1.1 Initialize Project Structure];
    B --> B2[1.2 Setup requirements.txt];
    B --> B3[1.3 Basic CI Pipeline (Linting, Initial Tests)];
    B --> B4[1.4 Setup config.py & Secret Management Strategy];
    
    B --> C{2. FastAPI Application Shell};
    C --> C1[2.1 Implement main.py with FastAPI instance];
    C --> C2[2.2 Basic API Router Setup (xyra/api/v1/router.py)];
    C --> C3[2.3 Implement POST /templates Endpoint];
    C --> C4[2.4 Implement GET /templates/{template_id}/status Endpoint (Initial)];
    
    C --> D{3. LangGraph Core Setup};
    D --> D1[3.1 Define Initial LangGraph State Schema (xyra/graphs/state.py)];
    D --> D2[3.2 Decide & Implement Basic LangGraph Checkpointer (e.g., SqliteSaver/InMemorySaver)];
    D --> D3[3.3 Define Initial template_generation_graph.py];

    D --> E{4. Brief Analysis & Clarification Flow};
    E --> E1[4.1 Implement Brief Analyzer Node (xyra/core_services/brief_analyzer_service.py)];
    E1 --> E1a[4.1.1 Integrate LLM for Brief Analysis & Question Generation];
    E1 --> E1b[4.1.2 Define Clarification Prompt];
    E --> E2[4.2 Implement LangGraph Flow: Start -> BriefAnalyzer -> ClarificationDecision];
    E --> E3[4.3 Implement LG_WaitForAmendedBrief Node];
    E --> E4[4.4 Implement PUT /templates/{template_id}/brief Endpoint];

    E --> F{5. Initial MJML Generation (No Images)};
    F --> F1[5.1 Implement MJML Generation Node (xyra/core_services/mjml_service.py - initial)];
    F1 --> F1a[5.1.1 Integrate LLM for MJML Generation (from clarified brief)];
    F1 --> F1b[5.1.2 Develop Initial MJML Generation Prompt];
    F --> F2[5.2 Implement LangGraph Flow: ClarificationDecision (No) -> MJMLGen];

    F --> G{6. Basic MJML Validation & Compilation};
    G --> G1[6.1 Implement MJML Validator & HTML Compiler Node (xyra/core_services/mjml_service.py - initial)];
    G1 --> G1a[6.1.1 Integrate mjml CLI (subprocess) for Validation & Compilation];
    G --> G2[6.2 Implement LangGraph Flow: MJMLGen -> MJMLValidateCompile];
    G --> G3[6.3 Basic Error Handling for Invalid MJML (Log, Update Graph State)];

    G --> H{7. Unit Tests};
    H --> H1[7.1 Write Unit Tests for New Services];
    H --> H2[7.2 Write Unit Tests for Critical API Endpoints];

    H --> I[End Sprint 1];

    subgraph "Considerations from Review (Throughout Sprint)"
        direction LR
        R1[Initial Error Handling Strategy in Nodes]
        R2[Decision on Initial LangGraph Checkpointer]
        R3[Initial API Security & Secret Management]
    end
    B4 --> R3;
    D2 --> R2;
    E1 & F1 & G1 --> R1;
    G3 --> R1;
```

---

## Detailed Task Breakdown

### 1. Project Setup & CI/CD Basics

1. **Initialize project directory structure** as outlined in [`docs/plan_langgraph.md`](docs/plan_langgraph.md#L431-L491).
2. \*\*Create and populate \*\***`requirements.txt`** with core dependencies.
   *Update*: Added `langchain-openai`, `langchain-anthropic`, `pytest`, `pytest-asyncio`.
3. **Set up a basic CI pipeline**

   1. Implement linting (e.g. Flake8 or Ruff).
   2. Configure the pipeline to run initial placeholder tests.
4. **Create ********************************************`xyra/config.py`******************************************** for application settings**

   1. Implement a strategy for secure management of secrets (API keys, database credentials).
   2. *Update*: Enhanced `config.py` to support flexible LLM provider selection (OpenAI, Anthropic).

### 2. FastAPI Application Shell

1. \*\*Implement \*\***`xyra/main.py`** to initialize the FastAPI application instance.
2. **Set up basic API routing** in `xyra/api/v1/router.py` and include it in the main FastAPI app.
3. **Implement ********************************************`POST /api/v1/templates`******************************************** endpoint** (`xyra/api/v1/template_routes.py`).

   1. Define request schema (`UserBriefSchema`).
   2. Initiate a LangGraph execution.
   3. Return `202 Accepted` with `template_id` and `status_poll_url`.
4. **Implement ********************************************`GET /api/v1/templates/{template_id}/status`******************************************** endpoint**

   1. Poll the LangGraph state.
   2. Return status information.

### 3. LangGraph Core Setup

1. **Define the initial LangGraph state schema** in `xyra/graphs/state.py`.
2. **Decide on and implement a checkpointer**

   1. Decision: `langgraph.checkpoint.aiosqlite.AsyncSqliteSaver` for async compatibility.
   2. Implement the chosen checkpointer.
3. **Define the initial graph structure** in `xyra/graphs/template_generation_graph.py`.

### 4. Brief Analysis & Clarification Flow

1. **Implement the Brief Analyzer node** (`xyra/core_services/brief_analyzer_service.py`).

   1. Integrate an LLM call for brief analysis & question generation.
   2. Develop and refine the clarification prompt.
   3. Update graph state with clarification questions or OK status.
2. **Add** `LG_Start`, `LG_BriefAnalyzer`, and the `LG_ClarificationDecision` conditional edge to the graph.
3. **Implement ********************************************`LG_WaitForAmendedBrief`******************************************** node**.
4. **Implement ********************************************`PUT /api/v1/templates/{template_id}/brief`******************************************** endpoint**

   1. Define request schema for the amended brief.
   2. Send amended brief to the waiting LangGraph execution.
   3. Return `202 Accepted`.

### 5. Initial MJML Generation (No Images)

1. **Implement the MJML Generation node** (`xyra/core_services/mjml_service.py`).

   1. Integrate an LLM call to generate MJML from the clarified brief.
   2. Develop and refine the MJML generation prompt.
   3. Update graph state with generated MJML.
2. **Add ********************************************`LG_MJMLGen`******************************************** node** to the graph (ClarificationDecision → MJMLGen).

### 6. Basic MJML Validation & Compilation

1. **Implement the MJML Validator & HTML Compiler node** (`xyra/core_services/mjml_service.py`).

   1. Integrate the `mjml` CLI via `subprocess` for validation & compilation.
   2. Update graph state with compiled HTML and validation status.
2. **Add ********************************************`LG_MJMLValidateCompile`******************************************** node** to the graph (MJMLGen → MJMLValidateCompile).
3. **Implement basic error handling** for invalid MJML (log, update graph state).

### 7. Unit Tests

1. Write unit tests for new services (`xyra/core_services`).
2. Write unit tests for critical API endpoints (`POST /templates`, `GET /status`, `PUT /brief`).

---

## Ongoing Considerations (Throughout Sprint 1)

* Error‑handling strategy within LangGraph nodes.
* Decision on the initial LangGraph checkpointer.
* API security and secret‑management best practices.

---

## Sprint 1 Progress Analysis (as of 2025‑05‑22)

### Completed Task Groups

* **Project Setup & CI/CD Basics**
* **FastAPI Application Shell**
* **LangGraph Core Setup**
* **Brief Analysis & Clarification Flow**
* **Initial MJML Generation (No Images)**
* **Basic MJML Validation & Compilation**
* **Unit Tests**

### Current Status

All planned tasks for Sprint 1 are complete. The FastAPI application includes the initial LangGraph flow for brief analysis, clarification, MJML generation, and validation. Unit tests for core services and API endpoints are passing, `excluding test_graph_flow_brief_ok` (expected at this point)

---

*End of Sprint 1*
