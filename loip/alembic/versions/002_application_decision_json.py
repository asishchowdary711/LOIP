"""Add review_flags + full decision/explainability JSON to applications.

Lets the review console rehydrate complete case detail after a restart.

Revision ID: 002
Revises: 001
Create Date: 2026-06-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("review_flags", sa.JSON, nullable=True))
    op.add_column("applications", sa.Column("decision_json", sa.JSON, nullable=True))
    op.add_column("applications", sa.Column("explainability_json", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "explainability_json")
    op.drop_column("applications", "decision_json")
    op.drop_column("applications", "review_flags")
