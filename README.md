# Mailwright - Agentic Marketing Email Platform

---

## 📋 Table of Contents

1. [Quick Start Checklist](#quick-start-checklist)
2. [Environment Setup](#environment-setup)
3. [Project Architecture Deep Dive](#project-architecture-deep-dive)
4. [Development Workflow](#development-workflow)
5. [Testing & Debugging](#testing--debugging)
6. [Common Issues & Solutions](#common-issues--solutions)
7. [Bug Fixing Methodology](#bug-fixing-methodology)
8. [Code Patterns & Conventions](#code-patterns--conventions)
9. [External Dependencies](#external-dependencies)
10. [Useful Commands & Scripts](#useful-commands--scripts)

---

## 🚀 Quick Start Checklist

**Goal: Get the application running locally in 30 minutes**

### Prerequisites Installation

- [ ] **Python 3.10+** installed (`python --version`)
- [ ] **Node.js & npm** installed for MJML CLI (`node --version`, `npm --version`)
- [ ] **PostgreSQL** installed and running locally

### Repository Setup

```bash
# 1. Clone and navigate
git clone <repository-url>
cd Mailwright-Templates

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install MJML CLI globally
npm install -g mjml

# 5. Verify MJML installation
mjml --version
```

### Environment Configuration

```bash
# Create environment file (no .env.example exists, create from scratch)
touch .env

# Edit .env file with your API keys (based on actual mailwright/config.py)
# Add the following content to .env:
```

### Required Environment Variables (.env file)

**⚠️ CRITICAL**: Based on `mailwright/config.py`, you need **at least one** LLM API key:

```bash
# Application Configuration
APP_NAME="Mailwright - Agentic Marketing Email Platform"
DEBUG=true  # Set to true for development

# LLM API Keys (you need at least ONE of these)
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here

# LLM Provider Configuration
DEFAULT_LLM_PROVIDER=openai  # or "anthropic"

# Task-specific LLM Configurations
BRIEF_ANALYZER_PROVIDER=openai
BRIEF_ANALYZER_OPENAI_MODEL=gpt-4-turbo-preview
BRIEF_ANALYZER_ANTHROPIC_MODEL=claude-3-opus-20240229

MJML_GENERATION_PROVIDER=openai
MJML_GENERATION_OPENAI_MODEL=gpt-4-turbo-preview
MJML_GENERATION_ANTHROPIC_MODEL=claude-3-opus-20240229

FEEDBACK_ENGINE_PROVIDER=openai
FEEDBACK_ENGINE_OPENAI_MODEL=gpt-4-turbo-preview
FEEDBACK_ENGINE_ANTHROPIC_MODEL=claude-3-sonnet-20240229

# Image Generation
IMAGE_GENERATION_PROVIDER=openai
IMAGE_GENERATION_OPENAI_DALLE_MODEL=dall-e-3

# Database Configuration (PostgreSQL)
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/mailwright_db
LANGGRAPH_CHECKPOINTER_DB_URL=postgresql://postgres:password@localhost:5432/mailwright_db

# MJML CLI Path
MJML_CLI_PATH=mjml  # Should be 'mjml' if installed globally
```

### Database Setup

```bash
# Create PostgreSQL database
createdb mailwright_db

# Run database migrations
alembic upgrade head
```

### Verification

```bash
# Run the development server
uvicorn mailwright.main:app --reload --host 0.0.0.0 --port 8000

# Test basic functionality
curl http://localhost:8000/apihealth  # Should return {"status": "healthy"}

# View SwaggerUI
open http://localhost:8000/docs
```

### Quick Test

```bash
# Run a subset of tests to verify setup
pytest tests/unit/test_brief_analyzer_service.py -v
```

### 3. Test Template Creation (Basic)

```bash
curl -X POST http://localhost:8000/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{
    "user_brief": {
      "subject": "Welcome to Our Platform", 
      "body_copy": "Thanks for joining us! Here are some exciting features to explore.",
      "cta_text": "Get Started"
    }
  }'
```

This should return a response with a `template_id` and status.

---

## ⚙️ Environment Setup

### API Key Setup Guide

#### OpenAI API Key

1. Visit https://platform.openai.com/api-keys
2. Create new secret key
3. Copy key to `OPENAI_API_KEY` in `.env`

#### Anthropic API Key

1. Visit https://console.anthropic.com/account/keys
2. Create new key
3. Copy key to `ANTHROPIC_API_KEY` in `.env`

### Development Tools Setup

#### PyCharm Configuration

- Enable FastAPI run configuration
- Configure pytest as test runner
- Set up database connection to PostgreSQL

---

## 🏗️ Project Architecture Deep Dive

### High-Level Architecture

```
User Request → FastAPI → LangGraph Workflow → External Services → Database Storage
              ↓              ↓                    ↓                    ↓
         API Routes    State Machine       LLMs/DALL-E         PostgreSQL
```

### Core Workflows

This project supports two distinct template generation workflows that run in parallel:

1.  **From-Scratch MJML Generation (Legacy):**
    *   **Input:** A user's creative brief.
    *   **Process:** A LangGraph state machine orchestrates LLM calls to generate MJML (a responsive email framework) from scratch based on the brief.
    *   **Output:** A new MJML design and its compiled HTML.

2.  **RAG-Based HTML Generation (New - Sprint 5):**
    *   **Input:** A user's creative brief and a selected template from an existing corpus.
    *   **Process:** This workflow retrieves a pre-existing template and uses an LLM to modify its content to fit the user's brief.
    *   **Output:** A final, responsive HTML file. **This process generates HTML directly and does not use MJML.**

### Directory Structure Explained

```
Mailwright-Templates/
├── .env.example                   # Example environment variables
├── .gitignore                     # Specifies intentionally untracked files that Git should ignore
├── alembic.ini                    # Configuration file for Alembic database migrations
├── cursor.rules                   # Rules for Cursor AI
├── pyproject.toml                 # Build system and project metadata (PEP 518, PEP 621)
├── README.md                      # Project overview and setup instructions
├── requirements.txt               # Project dependencies
├── temp_output.html               # Temporary HTML output, likely for testing
│
├── alembic/                       # Alembic database migration scripts
│   ├── env.py                     # Alembic environment configuration
│   ├── README                     # Alembic README
│   ├── script.py.mako             # Alembic migration script template
│   └── versions/                  # Alembic migration versions
│       └── c1e1c3e07a5e_create_template_versions_table.py # Specific migration
│
├── archive/                       # Archived code or documentation
│   ├── cuda-test.py
│   ├── legacy_code/
│   │   ├── __init__.py
│   │   ├── content.py
│   │   ├── generator.py
│   │   ├── schema.py
│   │   ├── store.py
│   │   └── templates_api.py
│   └── templates/                 # (Likely another version of legacy or example templates)
│       ├── __init__.py
│       ├── content.py
│       ├── generator.py
│       ├── schema.py
│       └── store.py
│
├── docs/                          # Project documentation
│   ├── Dev_Guide.md               # Developer onboarding guide (this file)
│   ├── archive/                   # Archived documentation
│   │   ├── ankur_instructions.md
│   │   ├── llm_abstraction_plan.md
│   │   ├── plan_langgraph.md
│   │   ├── plan_review_langgraph.md
│   │   ├── sprint_1_plan_tasks.md
│   │   ├── sprint_plan_langgraph.md
│   │   └── legacy_systems/
│   │       ├── generator.md
│   │       ├── html_generator_overview.md
│   │       ├── plan.md
│   │       ├── SPRINT_PLAN.md
│   │       └── template_indexing_overview.md
│   └── working_context/           # Current working documents for sprints, context
│       ├── primary_context.md
│       ├── sprint_2_plan_tasks.md
│       └── sprint_2_test_debugging_notes.md
│
├── scripts/                       # Utility scripts
│   └── test_openai_access.py      # Script to test OpenAI API access
│
├── tests/                         # Test suite
│   ├── conftest.py                # Pytest configuration and fixtures
│   ├── Mailwright API - TemplateGen Tests.postman_collection.json # Postman collection for API tests
│   ├── api/v1/                    # API endpoint tests (specific to v1)
│   │   └── test_template_routes.py
│   ├── beefreetester/             # (Likely related to a specific HTML/email editor testing)
│   │   ├── Blob.js
│   │   ├── fileSaver.js
│   │   └── index.html
│   ├── integration/               # End-to-end workflow tests
│   │   └── test_template_generation_graph.py
│   └── unit/                      # Component/unit tests
│       ├── test_brief_analyzer_service.py
│       ├── test_image_generator_service.py
│       ├── test_llm_factory.py
│       ├── test_mjml_service.py
│       └── graphs/
│           └── test_checkpointer.py
│
└── mailwright/                          # Main application package
    ├── __init__.py
    ├── config.py                  # Settings & environment variables
    ├── main.py                    # FastAPI app entry point
    ├── templates_api.py           # (Potentially older or specific template API logic)
    │
    ├── api/                       # API modules
    │   ├── __init__.py
    │   └── v1/                    # Version 1 of the API
    │       ├── __init__.py
    │       ├── router.py          # API router for v1
    │       └── template_routes.py # Template generation endpoints
    │
    ├── core_services/             # Business logic services
    │   ├── brief_analyzer_service.py    # Analyzes user briefs
    │   ├── image_generator_service.py  # Image generation (e.g., DALL-E)
    │   ├── llm_factory.py              # LLM client factory
    │   └── mjml_service.py             # MJML generation & validation
    │
    ├── db/                        # Database layer
    │   ├── __init__.py
    │   ├── models.py              # SQLAlchemy models
    │   └── template_store.py      # Database operations for templates
    │
    ├── graphs/                    # LangGraph workflow definitions
    │   ├── __init__.py
    │   ├── checkpointer.py             # State persistence for graphs
    │   ├── state.py                    # Workflow state schema
    │   └── template_generation_graph.py # Main template generation workflow
    │
    └── schemas/                   # API request/response Pydantic models
        ├── __init__.py
        └── template_schemas.py    # Schemas for template operations
```

### LangGraph Workflow Architecture

**LangGraph** is the core orchestration engine. Think of it as a state machine that manages the template generation process through multiple steps.

#### Key Nodes in the Workflow:

1. **LG_Start**: Entry point, receives user brief. May route to feedback engine if feedback is present.
2. **LG_BriefAnalyzer**: Analyzes brief for clarity, may request clarifications (if not in feedback loop).
3. **LG_WaitForAmendedBrief**: Pauses workflow waiting for user input if clarifications were requested.
4. **LG_ImageGeneration**: Generates images (e.g., using DALL-E) based on prompts derived from the brief. Stores generated image URLs in the graph state.
5. **LG_MJMLGeneration**: Creates MJML template using LLM, incorporating any generated image URLs.
6. **LG_MJMLValidateCompile**: Validates MJML syntax and compiles it to HTML. This node is used for both initial generation and revised MJML.
7. **LG_StoreV0**: Stores the successfully generated and validated template (MJML, HTML, brief, image assets) as the initial version (v0) in the PostgreSQL database.
8. **LG_FeedbackEngineNode**: (Sprint 3) Processes user feedback against an existing MJML version to produce a revised MJML candidate.
9. **LG_StoreVNextNode**: (Sprint 3) Stores a successfully validated revised MJML template as a new version (e.g., v_rev_1, v_rev_2) in the database.

#### State Flow Example:

A simplified representation including the feedback loop:

```mermaid
graph TD
    subgraph Initial Generation
        direction LR
        A1[POST /templates] --> N_Start((LG_StartNode))
        N_Start --> R_InitialOrFeedback{route_initial_or_feedback}
        R_InitialOrFeedback -- No Feedback --> N_BriefAnalyzer((LG_BriefAnalyzer))
        N_BriefAnalyzer --> R_Clarify{should_request_clarification}
        R_Clarify -- Clarification Needed --> N_WaitForAmend((LG_WaitForAmendedBrief))
        N_WaitForAmend --> N_BriefAnalyzer 
        R_Clarify -- Brief OK --> N_ImageGen((LG_ImageGeneration))
        N_ImageGen --> N_MJMLGen((LG_MJMLGeneration))
        N_MJMLGen --> N_ValidateCompile((LG_MJMLValidateCompile))
        N_ValidateCompile --> R_StoreV0OrNext{should_route_after_validation}
        R_StoreV0OrNext -- Initial Flow & Valid --> N_StoreV0((LG_StoreV0))
        N_StoreV0 --> E_EndV0((END Initial))
        R_StoreV0OrNext -- Invalid --> E_EndErr((END Error))
    end

    subgraph Feedback Loop
        direction LR
        B1[POST /feedback for V_N] --> UpdateState[Update State w/ Feedback]
        UpdateState --> N_Start_Feedback((LG_StartNode)) 
        N_Start_Feedback --> R_InitialOrFeedback_F{route_initial_or_feedback}
        R_InitialOrFeedback_F -- Has Feedback --> N_FeedbackEngine((LG_FeedbackEngineNode))
        N_FeedbackEngine --> N_ValidateCompile_F((LG_MJMLValidateCompile))
        N_ValidateCompile_F --> R_StoreV0OrNext_F{should_route_after_validation}
        R_StoreV0OrNext_F -- Revision Flow & Valid --> N_StoreVNext((LG_StoreVNextNode))
        N_StoreVNext --> E_EndVNext((END Revised))
        R_StoreV0OrNext_F -- Invalid --> E_EndErr_F((END Error))
    end

    C1[User Approves Version] --> D1[POST /approve]
    D1 --> DB_Update[DB: Mark Approved]

    classDef node fill:# вкус,stroke:#333,stroke-width:2px;
    classDef decision fill:#E8A27D,stroke:#333,stroke-width:2px;
    class N_Start,N_BriefAnalyzer,N_WaitForAmend,N_ImageGen,N_MJMLGen,N_ValidateCompile,N_StoreV0,N_FeedbackEngine,N_ValidateCompile_F,N_StoreVNext,N_Start_Feedback node;
    class R_InitialOrFeedback,R_Clarify,R_StoreV0OrNext,R_InitialOrFeedback_F,R_StoreV0OrNext_F decision;
    class A1,B1,C1,UpdateState,DB_Update,E_EndV0,E_EndErr,E_EndVNext,E_EndErr_F external;
```

*Note: The feedback loop is re-entrant via API calls that update state and re-invoke the graph, leveraging the `route_initial_or_feedback` conditional node.*

### Key Concepts to Understand

#### 1. Graph State (`mailwright/graphs/state.py`)

```python
class GraphState(BaseModel):
    user_brief_data: Optional[Dict[str, Any]] = None
    clarification_questions: Optional[list[str]] = None
    amended_brief_data: Optional[Dict[str, Any]] = None
    current_mjml: Optional[str] = None
    compiled_html: Optional[str] = None
    mjml_validation_status: Optional[str] = None
    image_prompts: Optional[list[str]] = None
    generated_image_urls: Optional[list[str]] = None
    error_message: Optional[str] = None
    last_operation_status: Optional[str] = None
    stored_version_info: Optional[Dict[str, Any]] = None
    current_version_id_stored: Optional[str] = None
    # Sprint 3 additions for feedback loop
    user_feedback_content: Optional[str] = None
    version_id_for_feedback: Optional[str] = None
    revised_mjml_candidate: Optional[str] = None
    # ... more fields
```

The state is the "memory" of the workflow, passed between nodes and persisted to the database.

#### 2. Checkpointer (`mailwright/graphs/checkpointer.py`)

- Saves workflow state to PostgreSQL
- Enables workflow resumption after interruptions
- Critical for handling user clarifications

#### 3. Service Layer Pattern

Each core service follows this pattern:

```python
class ServiceClass:
    def __init__(self):
        self.llm_client = get_configured_chat_model(...)
  
    async def service_method(self, input_data) -> Result:
        # Implementation with error handling
        pass
```

---

## 🔄 Development Workflow

### Sprint 2 Status (Completed)

**✅ ALL SPRINT 2 FEATURES COMPLETED:**

- Image generation integration (DALL-E)
- PostgreSQL template versioning (including `GET /templates/{template_id}/versions` API)
- Production PostgreSQL checkpointer for LangGraph state
- StoreV0Node for initial template version persistence in PostgreSQL
- HTML preview service endpoints (`GET /templates/{id}/versions/{v_id}/html` and `/mjml`)
- Enhanced status reporting (e.g., `current_version_id` in status responses)
- Standardized logging implemented across the application
- Comprehensive unit tests for new services and nodes (Image Generation, TemplateStoreDB)
- Integration tests for error handling scenarios in the template generation graph

**✔️ RESOLVED/MITIGATED ISSUES from Sprint 2 Development:**

- Test mocking difficulties with `mjml_service` methods: Resolved through careful mock placement and fixture management. All relevant tests are passing.
- Graph compilation timing issues with mocks: Addressed by ensuring mocks are applied before graph compilation.
- Asyncio event loop conflicts in tests: Resolved by standardizing pytest-asyncio configuration (`asyncio_default_fixture_loop_scope = "function"`, `asyncio_default_test_loop_scope = "function"`) and fixture scopes.

### Sprint 3 Status (Completed)

**✅ ALL SPRINT 3 PRIMARY FEATURES COMPLETED:**

- **Feedback Submission API & State Updates:**
    - Implemented `POST /api/v1/templates/{template_id}/versions/{version_id}/feedback` endpoint.
    - Defined `FeedbackRequestSchema` and updated `GraphState` for feedback data.
- **LangGraph Feedback & Revision Loop:**
    - Implemented `LG_FeedbackEngineNode` and `feedback_engine_service.py` for AI-driven MJML revision.
    - Adapted `LG_MJMLValidateCompileNode` to handle revised MJML.
    - Implemented `LG_StoreVNextNode` to save revised versions.
    - Updated graph routing logic (`route_initial_or_feedback`, `should_route_after_validation`) to support the feedback cycle.
- **Template Approval Workflow:**
    - Implemented `POST /api/v1/templates/{template_id}/versions/{version_id}/approve` endpoint and `ApprovalResponseSchema`.
    - Added database logic (`approve_template_version`) to manage `is_approved` status uniquely per template.
    - Updated `GET /status` endpoint and `TemplateStatusSchema` to reflect approval status, prioritizing it over graph state if a version is approved.
    - Ensured `GET /versions` correctly reflects the `is_approved` flag for each version.
- **Comprehensive Integration Tests:**
    - Added integration tests for the full feedback and revision loop (V0 -> V_Rev1, V0 -> V_Rev1 -> V_Rev2, feedback leading to invalid MJML).
    - Added integration tests for feedback on an approved version.
    - Unit tests for new services and DB functions were also added.

**✔️ RESOLVED/MITIGATED ISSUES from Sprint 3 Development:**

- Resolved various `pytest` test failures through careful debugging of mocks, state handling in LangGraph, and test assertion logic.
- Addressed all `ruff` linter errors identified during the sprint.

### Git Workflow

```bash
# Always work on feature branches
git checkout -b feature/your-feature-name

# Make commits with descriptive messages
git commit -m "feat: add HTML preview endpoint for template versions"

# Push and create PR
git push origin feature/your-feature-name
```

### 🧪 Testing, Debugging, Linting

#### Linting

```bash
# Ruff (Python linting)
ruff check .
ruff format .

# Type checking with mypy (if configured)
mypy mailwright/
```

#### Ruff Configuration

Ruff is configured in the [`pyproject.toml`](pyproject.toml:32) file. Key settings include:

- **Line Length**: 88 characters.
- **Selected Linters**: Includes standard pycodestyle errors (E), Pyflakes (F), plus `flake8-bugbear` (B), `flake8-comprehensions` (C4), and `flake8-simplify` (SIM) for more thorough checks.
- **Ignored Rules**: `E501` (line too long) is currently ignored, but aim to adhere to the line length where practical.
- **Auto-fix**: Ruff can auto-fix many issues (e.g., `ruff check . --fix` or `ruff format .`).
- **Exclusions**: Certain directories like `.venv`, `build`, `dist`, `mailwright/legacy_code`, and `mailwright/templates` are excluded from linting.

Refer to the `[tool.ruff]` and `[tool.ruff.lint]` sections in [`pyproject.toml`](pyproject.toml:32) for the complete and up-to-date configuration.

### Test Structure Overview

```
tests/
├── unit/                          # Fast, isolated component tests
│   ├── test_brief_analyzer_service.py
│   ├── test_mjml_service.py
│   ├── test_image_generator_service.py
│   └── graphs/test_checkpointer.py
├── integration/                   # End-to-end workflow tests
│   └── test_template_generation_graph.py
└── api/v1/                       # HTTP endpoint tests
    └── test_template_routes.py
```

### Pytest Configuration

Pytest is configured in the [`pyproject.toml`](pyproject.toml:81) file. A key setting for this project is:

- **Asyncio Mode**: `asyncio_mode = "auto"` is set. This enables `pytest-asyncio` to automatically handle `async` tests, which is crucial for testing the asynchronous components of Mailwright-Templates.

All test execution commands shown below utilize `pytest`.

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_brief_analyzer_service.py -v

# Run with coverage
pytest --cov=Mailwright --cov-report=html

# Run only failed tests
pytest --lf

# Run tests matching pattern
pytest -k "test_brief" -v

# Run tests with detailed output
pytest -v -s
```

### Key Test Files to Understand

#### 1. `tests/integration/test_template_generation_graph.py`

**Most Important for Bug Fixing** - Tests the complete workflow:

```python
async def test_graph_flow_brief_ok():
    """Tests the 'brief is clear' path through the entire workflow"""
    # This test mocks external services and verifies state transitions
```

#### 2. `tests/api/v1/test_template_routes.py`

Tests HTTP endpoints end-to-end:

```python
def test_create_template_success():
    """Tests POST /api/v1/templates endpoint"""
  
def test_get_template_status():
    """Tests GET /api/v1/templates/{id}/status endpoint"""
```

### Debugging Techniques

#### 1. Using the Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()
```

#### 2. LangGraph State Debugging

```python
# Add logging to graph nodes
import logging
logger = logging.getLogger(__name__)

async def your_node(state: GraphState, config: dict) -> GraphState:
    logger.info(f"Node state: {state.dict()}")
    logger.info(f"Config: {config}")
    # ... node logic
```

#### 3. Database State Inspection

```bash
# Connect to PostgreSQL
psql -d mailwright_db

# Check workflow checkpoints
SELECT * FROM checkpoints ORDER BY created_at DESC LIMIT 5;

# Check template versions
SELECT template_id, version_id, created_at FROM template_versions;
```

#### 4. API Debugging with curl/Postman

```bash
# Test template creation
curl -X POST http://localhost:8000/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{"user_brief": {"subject": "", "body_copy": ""}}'

# Check status
curl http://localhost:8000/api/v1/templates/{template_id}/status
```

## 📝 Code Patterns & Conventions

### 1. Async Service Pattern

```python
class ServiceClass:
    def __init__(self):
        self.llm_client = get_configured_chat_model(
            task_provider_config_value=settings.TASK_PROVIDER,
            # ... other config
        )
  
    async def async_method(self, input_data: InputType) -> OutputType:
        try:
            # Service logic here
            result = await self.external_call(input_data)
            return OutputType(data=result)
        except Exception as e:
            logger.error(f"Service error: {e}")
            raise ServiceException(f"Failed to process: {e}")
```

### 2. LangGraph Node Pattern

```python
async def node_function(state: GraphState, config: dict) -> GraphState:
    """
    Standard pattern for LangGraph nodes.
  
    Args:
        state: Current workflow state
        config: Graph configuration (includes thread_id)
  
    Returns:
        Updated GraphState
    """
    try:
        # Validate inputs
        if not state.user_brief_data:
            state.error_message = "User brief is required"
            state.last_operation_status = "error"
            return state
  
        # Perform node logic
        service = SomeService()
        result = await service.process(state.user_brief_data)
  
        # Update state
        state.some_field = result
        state.last_operation_status = "success"
        return state
  
    except Exception as e:
        logger.error(f"Node {node_function.__name__} failed: {e}")
        state.error_message = f"Node error: {e}"
        state.last_operation_status = "error"
        return state
```

### 3. Database Operations Pattern

```python
async def database_operation(input_data: CreateSchema) -> ModelType:
    async with AsyncSessionLocal() as db_session:
        try:
            # Create model instance
            db_obj = ModelType(**input_data.dict())
  
            # Add to session
            db_session.add(db_obj)
            await db_session.commit()
            await db_session.refresh(db_obj)
  
            return db_obj
  
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Database operation failed: {e}")
            raise DatabaseException(f"Failed to create: {e}")
```

### 4. API Endpoint Pattern

```python
@router.post("/templates", response_model=TemplateCreationResponseSchema)
async def create_template(
    request: UserBriefSchema,
    background_tasks: BackgroundTasks
) -> TemplateCreationResponseSchema:
    """
    Standard FastAPI endpoint pattern.
    """
    try:
        # Validate input
        if not request.user_brief:
            raise HTTPException(
                status_code=400, 
                detail="User brief is required"
            )
  
        # Process request
        template_id = str(uuid.uuid4())
  
        # Start background task
        background_tasks.add_task(start_workflow, template_id, request)
  
        # Return response
        return TemplateCreationResponseSchema(
            template_id=template_id,
            status="pending_brief_analysis",
            message="Template creation initiated"
        )
  
    except Exception as e:
        logger.error(f"Template creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 5. Testing Patterns

#### Unit Test Pattern

```python
@pytest.mark.asyncio
async def test_service_method():
    """Test service method with mocked dependencies."""
  
    # Arrange
    service = ServiceClass()
    input_data = InputType(field="test_value")
  
    # Mock external dependencies
    with patch.object(service, 'external_call') as mock_call:
        mock_call.return_value = {"result": "success"}
  
        # Act
        result = await service.async_method(input_data)
  
        # Assert
        assert result.data == {"result": "success"}
        mock_call.assert_called_once_with(input_data)
```

#### Integration Test Pattern

```python
@pytest.mark.asyncio
async def test_complete_workflow(compiled_graph_with_memory_saver):
    """Test complete workflow with mocked external services."""
  
    # Arrange
    graph, checkpointer = compiled_graph_with_memory_saver
    config = {"configurable": {"thread_id": "test-thread"}}
  
    # Mock external services
    with patch('module.external_service') as mock_service:
        mock_service.return_value = "mocked_result"
  
        # Act
        result = await graph.ainvoke(initial_state, config)
  
        # Assert
        assert result["last_operation_status"] == "success"
        mock_service.assert_called_once()
```

---

## 🔗 External Dependencies

### LLM Providers

#### OpenAI

- **Models Used**: GPT-4o, DALL-E 3
- **Error Handling**: Handle rate limits and quota exceeded

#### Anthropic Claude

- **Models Used**: Claude-3/4 variants
- **Alternative to OpenAI**: Can be used as fallback
- **Configuration**: Same pattern as OpenAI in `llm_factory.py`

### MJML CLI

- **Purpose**: Validates and compiles MJML to HTML
- **Installation**: `npm install -g mjml`
- **Usage**: Called via subprocess in `mjml_service.py`
- **Error Handling**: Handle CLI errors gracefully

### PostgreSQL

- **Purpose**: Template versioning and LangGraph state persistence
- **Schema**: Managed via Alembic migrations
- **Performance**: Use async drivers (asyncpg)
- **Monitoring**: Monitor connection pool and query performance

### LangGraph

- **Purpose**: Workflow orchestration
- **State Management**: Critical for resumable workflows
- **Debugging**: Use built-in visualization tools
- **Updates**: Pin version to avoid breaking changes

---

## 💻 Useful Commands & Scripts

### Development Commands

```bash
# Start development server with auto-reload
uvicorn mailwright.main:app --reload --host 0.0.0.0 --port 8000

# Run with debugger
python -m debugpy --listen 5678 --wait-for-client -m uvicorn mailwright.main:app --reload

# Check application health
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs
```

### Database Commands

```bash
# Create new migration
alembic revision --autogenerate -m "description of changes"

# Apply migrations
alembic upgrade head

# Downgrade migrations
alembic downgrade -1

# Check current migration status
alembic current

# View migration history
alembic history --verbose
```

### Testing Commands

```bash
# Run all tests with coverage
pytest --cov=Mailwright --cov-report=html --cov-report=term

# Run specific test patterns
pytest -k "test_brief" -v
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/api/ -v

# Run failed tests only
pytest --lf

# Run tests with specific markers
pytest -m "slow" -v
pytest -m "not slow" -v
```

### Debugging Commands

```bash
# Check Python environment
python -c "import sys; print(sys.executable)"
pip list

# Check MJML installation
mjml --version
which mjml

# Check PostgreSQL connection
psql -d mailwright_db -c "SELECT version();"

# Check environment variables
env | grep -E "(OPENAI|ANTHROPIC|DATABASE)"
```

### Git Commands for Bug Fixes

```bash
# Create bug fix branch
git checkout -b bugfix/issue-description

# Check what files changed recently
git log --oneline --since="1 week ago" --name-only

# Find when a bug was introduced
git bisect start
git bisect bad HEAD
git bisect good <known-good-commit>

# Check blame for specific lines
git blame mailwright/api/v1/template_routes.py

# Revert specific commit
git revert <commit-hash>
```

### Code Quality Commands

```bash
# Run linter
ruff check .
ruff check . --fix

# Format code
ruff format .

# Type checking (if mypy configured)
mypy mailwright/

# Security check
bandit -r mailwright/
```

## 📚 Docs Reading Order

1. **This guide** (you're here!) - Complete overview
2. **`docs/working_context/sprint_3_plan_tasks.md`** - Detailed plan for the current Sprint 3.
3. **`docs/working_context/sprint_2_plan_tasks.md`** - Detailed plan and outcomes of the completed Sprint 2.
4. **`docs/working_context/sprint_2_test_debugging_notes.md`** - Notes on issues encountered and resolved during Sprint 2 testing.
5. **`mailwright/graphs/state.py`** - Understand the core data model
6. **`mailwright/graphs/template_generation_graph.py`** - Core workflow
7. **`tests/integration/test_template_generation_graph.py`** - How everything works together
8. **`mailwright/api/v1/template_routes.py`** - API interface
9. **`docs/archive/plan_langgraph.md`** - Deep architectural understanding