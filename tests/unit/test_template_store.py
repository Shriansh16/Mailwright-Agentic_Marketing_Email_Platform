from dotenv import load_dotenv

load_dotenv()

import pytest
import pytest_asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from mailwright.db.template_store import (
    get_all_template_versions_for_template_id,
    create_template_version,
    approve_template_version,
    get_template_version,
)
from mailwright.schemas.template_schemas import TemplateVersionCreate


@pytest_asyncio.fixture
async def db_session(async_db_engine) -> AsyncSession:
    """
    Provides a clean database session for each test, using the shared
    session-scoped async_db_engine from conftest.py.
    """
    # Create a sessionmaker bound to the shared engine
    TestAsyncSessionLocal = sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with TestAsyncSessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_get_all_template_versions_no_versions(db_session: AsyncSession):
    """
    Test retrieving versions for a template_id that has no versions.
    Should return an empty list.
    """
    test_template_id = str(uuid4())
    versions = await get_all_template_versions_for_template_id(
        db_session, test_template_id
    )
    assert versions == []


@pytest.mark.asyncio
async def test_get_all_template_versions_multiple_versions_ordered(
    db_session: AsyncSession,
):
    """
    Test retrieving multiple versions for a template_id.
    Should return them ordered by creation date (newest first).
    """
    test_template_id = str(uuid4())

    # Version 1 (oldest)
    v1_data = TemplateVersionCreate(
        template_id=test_template_id,
        version_id="v1",
        mjml_source="<mjml>v1</mjml>",
        compiled_html="<html>v1</html>",
    )
    await create_template_version(db_session, v1_data)

    # Version 2 (middle)
    # To ensure a slight time difference for created_at if the DB resolution is very fast
    # await asyncio.sleep(0.01) # Small delay, usually not needed with real DB like PostgreSQL
    v2_data = TemplateVersionCreate(
        template_id=test_template_id,
        version_id="v2",
        mjml_source="<mjml>v2</mjml>",
        compiled_html="<html>v2</html>",
    )
    await create_template_version(db_session, v2_data)

    # Version 3 (newest)
    # await asyncio.sleep(0.01)
    v3_data = TemplateVersionCreate(
        template_id=test_template_id,
        version_id="v3",
        mjml_source="<mjml>v3</mjml>",
        compiled_html="<html>v3</html>",
    )
    await create_template_version(db_session, v3_data)

    versions_retrieved = await get_all_template_versions_for_template_id(
        db_session, test_template_id
    )

    assert len(versions_retrieved) == 3
    # Verify order: v3 (newest), then v2, then v1 (oldest)
    # This depends on create_template_version committing and func.now() resolving with enough difference.
    assert versions_retrieved[0].version_id == "v3"
    assert versions_retrieved[1].version_id == "v2"
    assert versions_retrieved[2].version_id == "v1"

    assert versions_retrieved[0].mjml_source == "<mjml>v3</mjml>"
    assert versions_retrieved[1].mjml_source == "<mjml>v2</mjml>"
    assert versions_retrieved[2].mjml_source == "<mjml>v1</mjml>"

    # Check another template_id to ensure isolation
    other_template_id = str(uuid4())
    other_versions = await get_all_template_versions_for_template_id(
        db_session, other_template_id
    )
    assert other_versions == []


# --- Tests for Sprint 3: Approval Logic ---


@pytest.mark.asyncio
async def test_approve_template_version_success(db_session: AsyncSession):
    """Test successfully approving a version, ensuring others are unapproved."""
    template_id_1 = str(uuid4())

    # Create versions for template_id_1
    v1_t1_data = TemplateVersionCreate(
        template_id=template_id_1,
        version_id="v1",
        mjml_source="<mjml>t1v1</mjml>",
        compiled_html="",
    )
    v2_t1_data = TemplateVersionCreate(
        template_id=template_id_1,
        version_id="v2",
        mjml_source="<mjml>t1v2</mjml>",
        compiled_html="",
        is_approved=False,
    )  # Explicitly false
    v3_t1_data = TemplateVersionCreate(
        template_id=template_id_1,
        version_id="v3",
        mjml_source="<mjml>t1v3</mjml>",
        compiled_html="",
    )
    await create_template_version(db_session, v1_t1_data)
    await create_template_version(db_session, v2_t1_data)
    await create_template_version(db_session, v3_t1_data)

    # Approve v2 for template_id_1
    approved_v2 = await approve_template_version(db_session, template_id_1, "v2")
    assert approved_v2 is not None
    assert approved_v2.version_id == "v2"
    assert approved_v2.is_approved is True

    # Verify statuses of all versions for template_id_1
    v1_t1_db = await get_template_version(db_session, template_id_1, "v1")
    v2_t1_db = await get_template_version(
        db_session, template_id_1, "v2"
    )  # Re-fetch to confirm commit
    v3_t1_db = await get_template_version(db_session, template_id_1, "v3")

    assert v1_t1_db.is_approved is False
    assert v2_t1_db.is_approved is True
    assert v3_t1_db.is_approved is False

    # Now, approve v3 for template_id_1 and check again
    approved_v3 = await approve_template_version(db_session, template_id_1, "v3")
    assert approved_v3 is not None
    assert approved_v3.version_id == "v3"
    assert approved_v3.is_approved is True

    v1_t1_db_after = await get_template_version(db_session, template_id_1, "v1")
    v2_t1_db_after = await get_template_version(db_session, template_id_1, "v2")
    v3_t1_db_after = await get_template_version(db_session, template_id_1, "v3")

    assert v1_t1_db_after.is_approved is False
    assert v2_t1_db_after.is_approved is False  # Should be false now
    assert v3_t1_db_after.is_approved is True

    # Check isolation with another template
    template_id_2 = str(uuid4())
    vA_t2_data = TemplateVersionCreate(
        template_id=template_id_2,
        version_id="vA",
        mjml_source="<mjml>t2vA</mjml>",
        compiled_html="",
        is_approved=True,
    )
    await create_template_version(db_session, vA_t2_data)
    vA_t2_db = await get_template_version(db_session, template_id_2, "vA")
    assert vA_t2_db.is_approved is True  # Should remain true


@pytest.mark.asyncio
async def test_approve_non_existent_version(db_session: AsyncSession):
    """Test approving a version that does not exist for a given template_id."""
    template_id = str(uuid4())
    # Create one version to ensure the template_id exists contextually, but not the one we try to approve
    await create_template_version(
        db_session,
        TemplateVersionCreate(
            template_id=template_id,
            version_id="v_real",
            mjml_source="...",
            compiled_html="",
        ),
    )

    result = await approve_template_version(db_session, template_id, "v_non_existent")
    assert result is None


@pytest.mark.asyncio
async def test_approve_version_for_non_existent_template(db_session: AsyncSession):
    """Test approving a version for a template_id that does not exist."""
    non_existent_template_id = str(uuid4())
    result = await approve_template_version(db_session, non_existent_template_id, "v1")
    assert result is None
