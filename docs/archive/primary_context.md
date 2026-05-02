# Xyra Marketing Content Agent - Cursor Rules

## Project Overview

Xyra is an AI-powered backend service for generating responsive MJML email templates using LangGraph for workflow orchestration. The system provides API endpoints for template generation, clarification handling, and iterative refinement through natural language feedback.

**Current Status**: Sprint 1: Core infrastructure, LangGraph workflow, basic MJML generation

- Sprint 2: Image generation, PostgreSQL versioning, production checkpointer, HTML preview **COMPLETED**

## Sprint 2 Summary & Outcomes

Sprint 2 has been successfully completed, delivering all planned features and enhancements. Key outcomes include:

- **Image Generation:** Fully integrated DALL-E 3 for image generation within the template workflow.
- **PostgreSQL Template Versioning:** Robust versioning of templates (MJML, HTML, metadata) implemented using PostgreSQL, including the `GET /templates/{template_id}/versions` API endpoint for listing all version metadata.
- **Production Checkpointer:** LangGraph state persistence upgraded to use PostgreSQL for production environments, ensuring resumability.
- **HTML/MJML Preview Endpoints:** API endpoints for retrieving HTML and MJML content of specific template versions are functional.
- **Standardized Logging:** Logging has been standardized across the application for improved traceability and debugging.
- **Unit Test Completion:**
  - Unit tests for the `image_generation_node` have been implemented and are passing.
  - Unit tests for `TemplateStoreDB` database interaction logic (including version listing) are complete and passing.
  - The unit test `test_generate_mjml_node_llm_exception` in `tests/unit/test_mjml_service.py` was successfully fixed and is passing.
- **Integration Test Completion:**
  - Comprehensive integration tests for various error handling scenarios within the `template_generation_graph` have been implemented and are passing.
- **Overall Test Status:** All unit and integration tests related to Sprint 2 functionalities are consistently passing.

## Architecture & Technology Stack

### Core Technologies

- **Backend**: Python 3.10+, FastAPI (async API gateway)
- **Workflow**: LangGraph (stateful multi-step workflow orchestration)
- **Database**: PostgreSQL (template versioning, LangGraph state persistence)
- **LLMs**: OpenAI GPT-4-turbo, Anthropic Claude (configurable via LangChain)
- **Image Generation**: DALL-E 3 (OpenAI)
- **Email Templates**: MJML (responsive email markup language)
- **Validation**: mjml CLI (MJML validation and HTML compilation)
- **Testing**: pytest, pytest-asyncio
- **Migrations**: Alembic (SQLAlchemy)
- **Linting**: Ruff

### Project Structure

```
Xyra-Templates/
├── README.md                       # Main project documentation
├── requirements.txt                # Python dependencies
├── pyproject.toml                  # Project configuration and build settings
├── .gitignore                      # Git ignore patterns
├── alembic.ini                     # Alembic database migration configuration
├── temp_output.html                # Temporary HTML output file
│
├── .env.example                    # Environment variables template (not tracked)
├── .env                            # Local environment variables (not tracked)
│
├── xyra/                           # Main application package
│   ├── __init__.py                 # Package initialization
│   ├── main.py                     # FastAPI app entry point
│   ├── config.py                   # Application settings (env vars, API keys)
│   ├── templates_api.py            # Legacy API module
│   │
│   ├── core_services/              # Business logic services
│   │   ├── __init__.py
│   │   ├── brief_analyzer_service.py    # LLM-based brief analysis
│   │   ├── mjml_service.py             # MJML generation & validation
│   │   ├── image_generator_service.py  # DALL-E image generation
│   │   └── llm_factory.py              # LLM client factory (OpenAI/Anthropic)
│   │
│   ├── graphs/                     # LangGraph workflow definitions
│   │   ├── __init__.py
│   │   ├── template_generation_graph.py # Main workflow graph
│   │   ├── state.py                    # Graph state schema
│   │   └── checkpointer.py             # State persistence (SQLite/PostgreSQL)
│   │
│   ├── api/                        # FastAPI endpoints
│   │   ├── __init__.py
│   │   └── v1/                     # API version 1
│   │       ├── __init__.py
│   │       ├── router.py                # API router setup
│   │       └── template_routes.py       # Template generation endpoints
│   │
│   ├── db/                         # Database layer
│   │   ├── __init__.py
│   │   ├── models.py                   # SQLAlchemy models
│   │   └── template_store.py           # Database operations
│   │
│   ├── schemas/                    # Pydantic data models
│   │   ├── __init__.py
│   │   └── template_schemas.py         # API request/response schemas
│   │
│   ├── utils/                      # Utility functions
│   │   └── __init__.py
│   │
│   └── tasks/                      # Task-related modules
│       └── __init__.py
│
├── tests/                          # Test suite
│   ├── unit/                       # Unit tests for individual components
│   │   ├── __init__.py
│   │   ├── test_brief_analyzer_service.py  # Brief analysis logic tests
│   │   ├── test_mjml_service.py           # MJML generation & validation tests
│   │   ├── test_image_generator_service.py # Image generation service tests
│   │   ├── test_llm_factory.py            # LLM client factory tests
│   │   └── graphs/                        # Graph-specific unit tests
│   │       └── test_checkpointer.py       # Checkpointer logic tests
│   │
│   ├── integration/                # End-to-end workflow tests
│   │   ├── __init__.py
│   │   └── test_template_generation_graph.py # Complete LangGraph flows
│   │
│   ├── api/                        # API endpoint tests
│   │   └── v1/
│   │       └── test_template_routes.py    # FastAPI endpoint validation
│   │
│   ├── test_data/                  # Test data files
│   │   └── (various test data files)
│   │
│   ├── beefreetester/              # Beefree integration testing
│   │   └── (HTML/JS files for Beefree testing)
│   │
│   └── Xyra API - TemplateGen Tests.postman_collection.json # Postman API tests
│
├── docs/                           # Documentation
│   ├── working_context/            # Current sprint documentation
│   │   ├── sprint_2_plan_tasks.md          # Sprint 2 task breakdown
│   │   └── sprint_2_test_debugging_notes.md # Testing notes and issues
│   │
│   └── archive/                    # Historical documentation
│       ├── sprint_1_plan_tasks.md          # Sprint 1 planning
│       ├── plan_langgraph.md               # LangGraph architecture plan
│       ├── sprint_plan_langgraph.md        # Sprint planning for LangGraph
│       ├── plan_review_langgraph.md        # Architecture review document
│       ├── llm_abstraction_plan.md         # LLM abstraction design
│       ├── ankur_instructions.md           # Developer instructions
│       └── legacy_systems/                 # Legacy system documentation
│           └── (legacy documentation files)
│
├── alembic/                        # Database migration system
│   ├── env.py                      # Alembic environment configuration
│   ├── script.py.mako              # Migration script template
│   ├── README                      # Alembic documentation
│   └── versions/                   # Database migration files
│       └── (timestamped migration files)
│
├── data/                           # Local data storage (not tracked)
│   └── (SQLite databases, temporary files)
│
├── scripts/                        # Utility scripts
│   └── (development and deployment scripts)
│
├── archive/                        # Archived project files
│   └── (legacy code and documentation)
│
├── xyra.egg-info/                  # Package metadata (generated)
│   └── (setuptools metadata files)
│
├── node_modules/                   # Node.js dependencies (for MJML CLI)
│   └── (npm packages)
│
├── .venv/                          # Python virtual environment (not tracked)
│   └── (Python packages and dependencies)
│
├── .git/                           # Git repository metadata (not tracked)
│   └── (Git internal files)
│
├── .pytest_cache/                  # Pytest cache (not tracked)
│   └── (pytest temporary files)
│
├── .ruff_cache/                    # Ruff linter cache (not tracked)
│   └── (ruff temporary files)
│
└── cursor.rules                    # Cursor IDE configuration (this file)
```

## LangGraph Workflow Architecture

### Core Workflow Nodes

1. **LG_Start**: Initial entry point, receives user brief
2. **LG_BriefAnalyzer**: LLM analysis for clarification needs
3. **LG_WaitForAmendedBrief**: Pauses for user clarification input
4. **LG_ImageGeneration**: DALL-E image generation from prompts
5. **LG_MJMLGeneration**: LLM-based MJML template generation
6. **LG_MJMLValidateCompile**: MJML validation and HTML compilation
7. **LG_StoreV0**: Persist initial template version to database

### State Management

- **GraphState**: Pydantic model defining workflow state
- **Checkpointer**: PostgreSQL (production) or SQLite (development)
- **Persistence**: Async state management with resumability

### Conditional Logic

- **should_request_clarification()**: Routes based on brief analysis
- **should_store_or_end_after_validation()**: Handles MJML validation results

## API Design Patterns

### Asynchronous Request/Response Pattern

- **POST /api/v1/templates**: Initiate generation (202 Accepted)
- **GET /api/v1/templates/{id}/status**: Poll for status updates
- **PUT /api/v1/templates/{id}/brief**: Submit amended brief

### Status Flow

1. `pending_brief_analysis` → Brief being analyzed
2. `clarification_needed` → Waiting for user input
3. `pending_initial_generation` → Generating template
4. `ready_for_preview` → Template available for preview
5. Error states: `error_...` with descriptive messages

### Response Schemas

- **TemplateCreationResponseSchema**: Initial creation response
- **TemplateStatusSchema**: Status polling response
- **UserBriefSchema**: User input validation
- **TemplateVersionResponse**: Versioned template data

## Database Schema

### TemplateVersion Model

```python
class TemplateVersion(Base):
    __tablename__ = "template_versions"
  
    template_id = Column(Text, primary_key=True, index=True)
    version_id = Column(Text, primary_key=True, index=True)
    mjml_source = Column(Text, nullable=False)
    compiled_html = Column(Text, nullable=False)
    user_brief_snapshot = Column(JSONB)
    image_assets = Column(JSONB)
    change_trigger = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_approved = Column(Boolean, default=False)
```

### Database Configuration

- **Primary DB**: PostgreSQL for template versioning
- **LangGraph State**: PostgreSQL checkpointer (production) or SQLite (dev)
- **Async Operations**: asyncpg driver with SQLAlchemy async sessions

## Configuration Management

### Environment Variables (.env)

```bash
# Application
APP_NAME="Xyra Marketing Content Agent"
DEBUG=false

# LLM APIs
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
DEFAULT_LLM_PROVIDER=openai

# Task-specific LLM configs
BRIEF_ANALYZER_PROVIDER=openai
BRIEF_ANALYZER_OPENAI_MODEL=gpt-4o
MJML_GENERATION_PROVIDER=openai
MJML_GENERATION_OPENAI_MODEL=gpt-4o

# Image Generation
IMAGE_GENERATION_PROVIDER=openai
IMAGE_GENERATION_OPENAI_DALLE_MODEL=dall-e-3

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/xyra_db
LANGGRAPH_CHECKPOINTER_DB_URL=postgresql://user:pass@localhost:5432/xyra_db

# MJML CLI
MJML_CLI_PATH=mjml
```

### Provider Configuration

- **LLM Factory**: Configurable OpenAI/Anthropic selection per task
- **Temperature Settings**: Task-specific LLM temperature controls
- **Model Selection**: Per-task model configuration (GPT-4, Claude-3)

## Testing Strategy

### Test Categories

1. **Unit Tests**: Individual service/component testing

   - `test_brief_analyzer_service.py`: Brief analysis logic
   - `test_mjml_service.py`: MJML generation and validation
   - `test_image_generator_service.py`: Image generation service
   - `test_llm_factory.py`: LLM client factory
2. **Integration Tests**: End-to-end workflow testing

   - `test_template_generation_graph.py`: Complete LangGraph flows
   - Mock external services (LLMs, DALL-E)
   - State persistence and resumability
3. **API Tests**: HTTP endpoint testing

   - `test_template_routes.py`: FastAPI endpoint validation
   - Request/response schema validation
   - Error handling scenarios

### Testing Patterns

- **Async Testing**: pytest-asyncio for async operations
- **Mocking**: Mock external LLM and image generation calls
- **State Testing**: LangGraph state transitions and persistence
- **Database Testing**: Async SQLAlchemy operations

## Development Guidelines

### Code Style

- **Linting**: Ruff with line length 88
- **Type Hints**: Full type annotation coverage
- **Async/Await**: Consistent async patterns throughout
- **Error Handling**: Comprehensive exception handling with logging

### LangGraph Node Development

```python
async def node_function(state: GraphState, config: dict) -> GraphState:
    """
    LangGraph node function pattern.
  
    Args:
        state: Current graph state
        config: Graph configuration (includes thread_id)
  
    Returns:
        Updated GraphState or dict with state updates
    """
    try:
        # Node logic here
        state.last_operation_status = "success"
        return state
    except Exception as e:
        state.error_message = f"Node error: {e}"
        state.last_operation_status = "error"
        return state
```

### Service Layer Patterns

```python
class ServiceClass:
    def __init__(self):
        self.llm_client = get_configured_chat_model(
            task_provider_config_value=settings.TASK_PROVIDER,
            task_openai_model_config_value=settings.TASK_OPENAI_MODEL,
            task_anthropic_model_config_value=settings.TASK_ANTHROPIC_MODEL,
            temperature=0.7
        )
  
    async def service_method(self, input_data) -> ServiceResult:
        # Service implementation
        pass
```

### Database Operations

```python
async def database_operation(db: AsyncSession, data: CreateSchema) -> Model:
    async with AsyncSessionLocal() as db_session:
        try:
            # Database operations
            await db_session.commit()
            return result
        except Exception as e:
            await db_session.rollback()
            raise
```

## Current Sprint 2 Status

### Completed Features

- ✅ Image generation integration (DALL-E)
- ✅ PostgreSQL template versioning system (Core V0 storage)
- ✅ Production PostgreSQL checkpointer
- ✅ StoreV0Node for initial version persistence
- ✅ HTML preview service endpoints (GET /versions/.../html & /mjml)
- ✅ Enhanced status reporting with version info (in GET /status for preview readiness)
- ✅ Integration tests for core successful workflow paths and resumability

### In Progress

- 🔄 Template versioning API endpoints: Implement `GET /api/v1/templates/{template_id}/versions` to list version metadata (including preview URLs), as the next step beyond V0 storage and basic retrieval.
- 🔄 Enhanced error handling (improving coverage and sophistication)
- 🔄 Standardized logging (migrating all logging to use the `logging` module consistently)
- 🔄 Unit Tests:
  - ✅ For `Image Generation Node` (graph node specific logic) - COMPLETED
  - ✅ For `TemplateStoreDB` interaction logic (`tests/unit/test_template_store.py`) - COMPLETED
- 🔄 Integration Tests:
  - ✅ For HTML Preview Service endpoint functionality (testing content retrieval via GET /versions, and versioned HTML/MJML endpoints) - COMPLETED
  - For additional error handling scenarios across various graph nodes

### Known Issues

- **Test Mocking**: Difficulty mocking `mjml_service` methods in integration tests
- **Graph Compilation**: Mocks must be applied before graph compilation
- **State Persistence**: Checkpointer context management complexity

## Security Considerations

### API Security

- Input validation via Pydantic schemas
- SQL injection prevention via SQLAlchemy ORM
- Environment variable management for secrets
- Prompt injection mitigation for user inputs

### External Service Security

- Secure API key management
- Rate limiting considerations for LLM/image APIs
- Error message sanitization to prevent information leakage

## Performance Considerations

### Async Operations

- Non-blocking LLM API calls
- Async database operations
- Concurrent image generation when possible
- Efficient state persistence

### Cost Management

- Configurable LLM model selection
- Image generation optimization
- Database query optimization
- Monitoring and logging for cost tracking

## Future Enhancements (Post-Sprint 2)

### Planned Features

- Iterative refinement loop with user feedback
- Beefree.io editor integration
- RAG (Retrieval Augmented Generation) for brand guidelines
- Advanced template versioning with approval workflows
- Multi-channel marketing content generation

### Scalability Considerations

- Horizontal scaling with stateless API design
- Database sharding for high-volume template storage
- Caching strategies for frequently accessed templates
- Load balancing for LLM API calls

## Debugging and Monitoring

### Logging Strategy

- **Centralized Configuration**: Logging is configured via `xyra/logging_config.py`, initialized in `xyra/main.py`.
- **Standard Format**: Uses a consistent format: `%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s`.
- **Log Level Control**: The log level can be set using the `LOG_LEVEL` environment variable or the `LOG_LEVEL` setting in `xyra/config.py` (defaults to `INFO`).
- **Structured Logging**: Python's `logging` module is used throughout the application.
- **Output**: Logs are currently directed to the console (StreamHandler).
- Per-node logging in LangGraph workflows.
- External service call logging.
- Error tracking and alerting (future consideration).

### Development Tools

- **Local Development**: uvicorn with reload
- **Database Migrations**: Alembic for schema changes
- **API Documentation**: FastAPI automatic OpenAPI docs
- **Testing**: pytest with coverage reporting

## Dependencies and Requirements

### Core Dependencies

```
fastapi
uvicorn[standard]
langchain
langgraph
langgraph-checkpoint-postgres
pydantic>=2.0.0
pydantic-settings
python-dotenv>=1.0.0
openai>=1.12.0
langchain-openai
langchain-anthropic
psycopg2-binary
asyncpg
alembic
pytest
pytest-asyncio
ruff
```

### External Requirements

- **MJML CLI**: `npm install -g mjml`
- **PostgreSQL**: Database server for persistence
- **API Keys**: OpenAI and/or Anthropic API access

This cursor.rules file provides comprehensive context for the Xyra Marketing Content Agent project, covering architecture, implementation patterns, current status, and development guidelines. Use this as a reference for understanding the codebase structure, making consistent changes, and maintaining the project's architectural integrity.
