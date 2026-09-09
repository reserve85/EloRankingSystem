"""add_player_disable_periods

Adds a per-player history of "disabled from .. until" intervals used by the
rankings (Fix #5): a player is only excluded from a ranking on dates inside
a recorded disable period - never retroactively from the beginning. The
``players.disabled`` boolean stays the current-state flag.

Existing rows that are currently disabled have no recorded history yet, so
they are backfilled with an open interval starting on the migration date.
That keeps their pre-migration history fully visible (nothing is retro-
actively rewritten); the club can later tweak those start dates directly in
the database if a player was removed earlier.

Revision ID: f6a7b8c9d0e1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-09
"""

import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_disable_periods",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "player_id",
            sa.Integer(),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("disabled_from", sa.Date(), nullable=False),
        # NULL = the player is still disabled (open interval).
        sa.Column("disabled_to", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_player_disable_periods_player_id",
        "player_disable_periods",
        ["player_id"],
    )

    # Backfill: every currently disabled player gets one open interval that
    # starts at the migration date (we cannot reconstruct the real start).
    bind = op.get_bind()
    today = datetime.date.today()
    rows = bind.execute(sa.text("SELECT id FROM players WHERE disabled = 1")).mappings()
    for row in rows:
        bind.execute(
            sa.text(
                "INSERT INTO player_disable_periods (player_id, disabled_from, disabled_to) "
                "VALUES (:pid, :from, NULL)"
            ),
            {"pid": row["id"], "from": today},
        )


def downgrade() -> None:
    op.drop_index("ix_player_disable_periods_player_id", table_name="player_disable_periods")
    op.drop_table("player_disable_periods")
