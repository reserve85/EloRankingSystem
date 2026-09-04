"""add_k_factor_to_match

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-03 12:00:00.000000

"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "15087aee213e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add k_factor column with server_default for existing rows
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("k_factor", sa.Float(), server_default="32.0", nullable=False)
        )

    # Backfill with current K_FACTOR from env if set, otherwise keep default 32.0
    k_factor_env = os.environ.get("K_FACTOR")
    if k_factor_env is not None:
        try:
            k_value = float(k_factor_env)
            op.execute(f"UPDATE matches SET k_factor = {k_value}")
        except (ValueError, TypeError):
            pass  # Invalid env var, keep the default 32.0


def downgrade() -> None:
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.drop_column("k_factor")
