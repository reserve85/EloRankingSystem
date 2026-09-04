"""drop_unused_club_settings_columns

Revision ID: f1e2d3c4b5a6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-04

The ``club_settings`` columns ``default_elo``, ``k_factor`` and
``inactivity_months`` are dead: every consumer reads the env/config singleton
(``settings.*``), and the Elo k-factor is snapshotted per match at creation
time. Environment/config is the single source of truth (env/config wins).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('club_settings', schema=None) as batch_op:
        batch_op.drop_column('default_elo')
        batch_op.drop_column('k_factor')
        batch_op.drop_column('inactivity_months')


def downgrade() -> None:
    # Recreate the dropped columns with the historical default values so any
    # existing rows get the documented defaults.
    with op.batch_alter_table('club_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('default_elo', sa.Integer(), nullable=False, server_default='1200'))
        batch_op.add_column(sa.Column('k_factor', sa.Float(), nullable=False, server_default='32.0'))
        batch_op.add_column(sa.Column('inactivity_months', sa.Integer(), nullable=False, server_default='3'))