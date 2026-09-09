"""prune_zero_day_disable_periods

Removes disable-period rows that do not exclude a player from a single real
day, cleaning up two kinds of legacy junk after the same-day reactivation
behaviour was corrected:

- ``disabled_to < disabled_from``  - "empty" windows written by an interim
  fix version for disable + immediate re-enable on the same day.
- ``disabled_to == disabled_from`` - same-day windows written by the
  original Fix #5 code, which closed a same-day toggle with ``disabled_to =
  today``. With inclusive window semantics that single row excluded the
  player from the whole re-enable day - the exact bug causing re-enabled
  players to vanish.

Only rows where the disable is provably shorter than one full day are
removed. Real multi-day windows (``disabled_to > disabled_from``) and open
intervals (``disabled_to IS NULL`` = still disabled) are kept untouched.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM player_disable_periods "
            "WHERE disabled_to IS NOT NULL AND disabled_to <= disabled_from"
        )
    )


def downgrade() -> None:
    # The pruned rows cannot be reconstructed (the player is not disabled any
    # more, and an empty/same-day window carries no information worth
    # restoring). Downgrade is intentionally a no-op.
    pass
