import logging  # Added for standardized logging
from sqlalchemy import Column, Text, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import (
    sessionmaker,
    declarative_base,
)  # declarative_base was already here but good to group
from sqlalchemy.sql import func  # For server-side default timestamp
from pgvector.sqlalchemy import Vector

from xyra.config import settings  # To get DATABASE_URL

logger = logging.getLogger(__name__)  # Added for standardized logging

# Define the base for declarative models
Base = declarative_base()


class TemplateVersion(Base):
    __tablename__ = "template_versions"

    template_id = Column(Text, primary_key=True, index=True)
    version_id = Column(
        Text, primary_key=True, index=True
    )  # Composite primary key with template_id

    mjml_source = Column(Text, nullable=False)
    compiled_html = Column(Text, nullable=False)

    user_brief_snapshot = Column(JSONB)
    image_assets = Column(JSONB)  # Store URLs or identifiers for images
    change_trigger = Column(JSONB)  # Info about what triggered this version

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_approved = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<TemplateVersion(template_id='{self.template_id}', version_id='{self.version_id}')>"


class RAGTemplate(Base):
    __tablename__ = "rag_templates"

    id = Column(Integer, primary_key=True)
    template_name = Column(Text, nullable=False)
    raw_html = Column(Text, nullable=False)  # Added field for original HTML
    processed_html = Column(Text, nullable=False)
    fingerprint_embedding = Column(Vector(1536), nullable=False)

    def __repr__(self):
        return f"<RAGTemplate(id={self.id}, template_name='{self.template_name}')>"


# Database setup (engine and session)
# This part is often in a separate db.py or session.py, but can be here for simplicity initially
# We will need to ensure DATABASE_URL is set in the environment or config
if settings.DATABASE_URL:
    async_engine = create_async_engine(
        settings.DATABASE_URL, echo=settings.DEBUG
    )  # Added echo for debugging if DEBUG is True
    AsyncSessionLocal = sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,  # Explicitly False for async
        autoflush=False,  # Explicitly False for async
    )
else:
    # Handle the case where DATABASE_URL is not set, e.g., raise an error or use a fallback
    # For now, we'll print a warning, but in a real app, this should be more robust.
    logger.warning(
        "DATABASE_URL not set. Async database features will not be available."
    )
    async_engine = None
    AsyncSessionLocal = None

# The create_db_tables function and the if __name__ == "__main__": block
# are removed as Alembic now handles synchronous table creation.
# For asynchronous applications, direct table creation like this with an async engine
# needs to be handled carefully (e.g., in an async startup event if not using Alembic).
# Since we have Alembic, it's the preferred way.
