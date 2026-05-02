from fastapi import FastAPI
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine
from xyra.api.v1.router import router as api_v1_router
from xyra.config import settings
from xyra.logging_config import setup_logging

# Call logging setup early, after all imports but before app instantiation
setup_logging()

# We will import API routers here later, e.g.:


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create engine instance
    engine = create_async_engine(
        settings.DATABASE_URL,
        # echo=settings.DEBUG,  # Optional: echo SQL queries if in debug mode
        pool_pre_ping=True,
    )
    app.state.db_engine = engine
    try:
        yield
    finally:
        await app.state.db_engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
    # You can add other FastAPI parameters like version, description, etc.
    # version="0.1.0",
    # description="Xyra Marketing Content Agent API",
)

# Placeholder for including API routers
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME}"}


# Placeholder for startup/shutdown events if needed later
# @app.on_event("startup")
# async def startup_event():
#     # Initialize database connections, etc.
#     print("Application startup...")

# @app.on_event("shutdown")
# async def shutdown_event():
#     # Clean up resources
#     print("Application shutdown...")

if __name__ == "__main__":
    import uvicorn

    # This is for direct execution, e.g., python xyra/main.py
    # For production, you'd typically use: uvicorn xyra.main:app --reload (for dev)
    uvicorn.run(app, host="0.0.0.0", port=8000)
