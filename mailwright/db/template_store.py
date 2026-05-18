from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, List
from sqlalchemy import desc, update
from sqlalchemy.orm import sessionmaker
from fastapi import Request

from mailwright.db.models import TemplateVersion
from mailwright.schemas.template_schemas import (
    TemplateVersionCreate,
)


async def get_db_session(request: Request) -> AsyncSession:
    """
    Dependency to get an async database session using the engine from app.state.
    Ensures the session is closed after use.
    """
    # Get engine from app.state
    engine = request.app.state.db_engine

    # Create a new sessionmaker instance bound to this engine, or use the engine directly if preferred for single sessions
    # For consistency with typical session management, creating a session factory per request or using one on app.state is common.
    # Here, we'll create a session directly from the engine for simplicity within the dependency.
    async_session_factory = sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_factory() as session:
        yield session


async def create_template_version(
    db: AsyncSession, version_data: TemplateVersionCreate
) -> TemplateVersion:
    """
    Creates a new template version in the database.
    """
    db_version = TemplateVersion(
        template_id=version_data.template_id,
        version_id=version_data.version_id,
        mjml_source=version_data.mjml_source,
        compiled_html=version_data.compiled_html,
        user_brief_snapshot=version_data.user_brief_snapshot,
        image_assets=version_data.image_assets,
        change_trigger=version_data.change_trigger,
        is_approved=version_data.is_approved,
        # created_at is handled by server_default
    )
    db.add(db_version)
    await db.commit()
    await db.refresh(db_version)
    return db_version


async def get_template_version(
    db: AsyncSession, template_id: str, version_id: str
) -> Optional[TemplateVersion]:
    """
    Retrieves a specific template version from the database.
    """
    result = await db.execute(
        select(TemplateVersion).filter_by(
            template_id=template_id, version_id=version_id
        )
    )
    return result.scalars().first()


async def get_all_template_versions_for_template_id(
    db: AsyncSession, template_id: str
) -> List[TemplateVersion]:
    """
    Retrieves all template versions for a given template_id, ordered by creation date (newest first).
    """
    stmt = (
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(desc(TemplateVersion.created_at))
    )
    result = await db.execute(stmt)
    versions = result.scalars().all()
    return list(versions)


# --- Sprint 3: Approval Logic ---
async def approve_template_version(
    db: AsyncSession, template_id: str, version_id_to_approve: str
) -> Optional[TemplateVersion]:
    """
    Approves a specific template version and unapproves all other versions for the same template_id.

    Args:
        db: The AsyncSession for database operations.
        template_id: The ID of the template.
        version_id_to_approve: The ID of the version to approve.

    Returns:
        The approved TemplateVersion object if successful, None otherwise.
    """
    # First, ensure the target version exists
    version_to_approve = await get_template_version(
        db, template_id, version_id_to_approve
    )
    if not version_to_approve:
        return None  # Or raise an exception, e.g., HTTPException(status_code=404, detail="Version not found")

    try:
        # Step 1: Unapprove all other versions for this template_id
        await db.execute(
            update(TemplateVersion)
            .where(TemplateVersion.template_id == template_id)
            .values(is_approved=False)
        )

        # Step 2: Approve the target version
        # (The version_to_approve object fetched earlier is now stale due to the previous update)
        # So, we execute another update or re-fetch and update the object.
        # Direct update is cleaner here.
        await db.execute(
            update(TemplateVersion)
            .where(
                TemplateVersion.template_id == template_id,
                TemplateVersion.version_id == version_id_to_approve,
            )
            .values(is_approved=True)
        )

        await db.commit()

        # Re-fetch the approved version to return the updated object
        approved_version = await get_template_version(
            db, template_id, version_id_to_approve
        )
        return approved_version

    except Exception:
        await db.rollback()  # Rollback in case of any error during the transaction
        # Optionally log the error e.g., logger.error(f"Error approving version: {e}")
        raise  # Re-raise the exception to be handled by the caller or FastAPI error handling


async def get_approved_template_version_for_template(
    db: AsyncSession, template_id: str
) -> Optional[TemplateVersion]:
    """
    Retrieves the single approved template version for a given template_id, if one exists.
    """
    stmt = select(TemplateVersion).where(
        TemplateVersion.template_id == template_id,
        TemplateVersion.is_approved.is_(True),
    )
    result = await db.execute(stmt)
    approved_version = result.scalars().first()  # Should be at most one
    return approved_version


# We can add more functions here later:
# - get_all_versions_for_template(db: AsyncSession, template_id: str)
# - update_template_version_approval(db: AsyncSession, template_id: str, version_id: str, is_approved: bool)
# - etc.
