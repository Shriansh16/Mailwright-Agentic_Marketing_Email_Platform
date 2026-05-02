"""create_new_rag_corpus_table

Revision ID: b42c672b7a7e
Revises: c1e1c3e07a5e
Create Date: 2025-07-03 13:15:21.383178

"""

import os
from typing import Sequence, Union
from pathlib import Path

from dotenv import load_dotenv
from alembic import op
import sqlalchemy as sa

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

# revision identifiers, used by Alembic.
revision: str = "b42c672b7a7e"
down_revision: Union[str, None] = "c1e1c3e07a5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RAG_ENABLED = os.getenv("RAG_ENABLED", "true").strip().lower() not in ("false", "0", "no")


def upgrade() -> None:
    """Upgrade schema."""
    if not _RAG_ENABLED:
        op.execute("SELECT 1")  # no-op to satisfy Alembic's transaction requirement
        return

    from pgvector.sqlalchemy import Vector  # only import when actually needed

    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.create_table(
        "rag_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_name", sa.Text(), nullable=False),
        sa.Column("processed_html", sa.Text(), nullable=False),
        sa.Column("fingerprint_embedding", Vector(1536), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    if not _RAG_ENABLED:
        return

    op.drop_table("rag_templates")
