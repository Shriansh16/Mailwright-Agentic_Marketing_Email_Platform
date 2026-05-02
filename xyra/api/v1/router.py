from fastapi import APIRouter

from . import template_routes  # . indicates relative import from the same package

router = APIRouter()


@router.get("/health", tags=["Status"])
async def health_check():
    """
    Simple health check endpoint.
    """
    return {"status": "ok", "message": "API v1 is healthy"}


# We will add template_routes here later
router.include_router(template_routes.router, prefix="/templates", tags=["Templates"])
