"""add_match_statistics

Revision ID: c3d4e5f6a7b8
Revises: 1a77da3178db
Create Date: 2026-07-22 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = '1a77da3178db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('player_a_180s', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('player_b_180s', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('player_a_high_finishes', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('player_b_high_finishes', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('player_a_low_darts', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('player_b_low_darts', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.drop_column('player_b_low_darts')
        batch_op.drop_column('player_a_low_darts')
        batch_op.drop_column('player_b_high_finishes')
        batch_op.drop_column('player_a_high_finishes')
        batch_op.drop_column('player_b_180s')
        batch_op.drop_column('player_a_180s')