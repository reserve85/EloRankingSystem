"""add_player_entry_date

Adds the per-player "entry date" (member-since) column used by historical
rankings (Fix #3 II).

A player is only a competitor from their entry date onwards, and every
non-disabled player entered by a date counts on that date (ranked by their
Elo as of that date). Existing rows are backfilled with their previous
effective entry = min(creation date, first recorded match date), so current
statistics do not change until the club corrects the member-since dates.

Revision ID: f5a6b7c8d9e0
Revises: e3f0b5d6c7a8
Create Date: 2026-09-09
"""

import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e3f0b5d6c7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entry_date", sa.Date(), nullable=True))

    # Backfill existing rows with the previous effective entry: the earlier of
    # the creation date and the first recorded match date. Doing it in Python
    # keeps the migration dialect-agnostic (works on SQLite / Postgres / MySQL).
    bind = op.get_bind()

    def _to_date(value) -> datetime.date:
        """Coerce date / datetime / ISO-string from raw SQL into a date."""
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return datetime.datetime.fromisoformat(str(value)).date()

    first_match: dict[int, datetime.date] = {}
    players_rows = bind.execute(sa.text("SELECT id, created_at FROM players")).mappings()
    for row in players_rows:
        first_match.setdefault(row["id"], _to_date(row["created_at"]))

    match_rows = bind.execute(
        sa.text(
            "SELECT player_a_id AS pid, MIN(date) AS d FROM matches GROUP BY player_a_id "
            "UNION ALL "
            "SELECT player_b_id AS pid, MIN(date) AS d FROM matches GROUP BY player_b_id"
        )
    ).mappings()
    for row in match_rows:
        pid = row["pid"]
        if pid is None:
            continue
        d = _to_date(row["d"])
        if d is not None and d < first_match.get(pid, d):
            first_match[pid] = d

    for pid, entry in first_match.items():
        bind.execute(
            sa.text("UPDATE players SET entry_date = :entry WHERE id = :pid"),
            {"entry": entry, "pid": pid},
        )


def downgrade() -> None:
    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.drop_column("entry_date")
