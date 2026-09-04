"""add_matches_timeline_index

Revision ID: e3f0b5d6c7a8
Revises: d1e2f3a4b5c6
Create Date: 2026-09-04

Backs the deterministic timeline ordering ``(date ASC, created_at ASC, id ASC)``
used by ``get_all`` / ``get_from_match`` / ``get_by_player`` (Fix L10). Without
it, SQLite re-sorts the full matches table on every ranking/history query; the
composite index keeps those ORDER BY clauses cheap as history grows.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e3f0b5d6c7a8"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.create_index("ix_matches_date_created_id", ["date", "created_at", "id"])


def downgrade() -> None:
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.drop_index("ix_matches_date_created_id")
