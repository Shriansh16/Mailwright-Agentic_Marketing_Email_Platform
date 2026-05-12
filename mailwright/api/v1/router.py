from fastapi import APIRouter

from . import chat_routes, template_routes

router = APIRouter()


@router.get("/health", tags=["Status"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "message": "API v1 is healthy"}


router.include_router(template_routes.router, prefix="/templates", tags=["Templates"])
router.include_router(chat_routes.router, prefix="/chat", tags=["Chat"])
