"""add_raw_html_to_rag_templates

Revision ID: 26fb755ba38b
Revises: b42c672b7a7e
Create Date: 2025-07-26 12:47:38.257444

"""
import os
from typing import Sequence, Union
from pathlib import Path

from dotenv import load_dotenv
from alembic import op
import sqlalchemy as sa

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

# revision identifiers, used by Alembic.
revision: str = "26fb755ba38b"
down_revision: Union[str, None] = "b42c672b7a7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RAG_ENABLED = os.getenv("RAG_ENABLED", "true").strip().lower() not in ("false", "0", "no")


def upgrade() -> None:
    """Add raw_html column to rag_templates and backfill it."""
    if not _RAG_ENABLED:
        return

    op.add_column(
        "rag_templates", sa.Column("raw_html", sa.Text(), nullable=True)
    )
    op.execute(
        """
        UPDATE rag_templates
        SET raw_html = processed_html
        """
    )
    op.alter_column("rag_templates", "raw_html", nullable=False)


def downgrade() -> None:
    """Remove raw_html column from rag_templates."""
    if not _RAG_ENABLED:
        return

    op.drop_column("rag_templates", "raw_html")
