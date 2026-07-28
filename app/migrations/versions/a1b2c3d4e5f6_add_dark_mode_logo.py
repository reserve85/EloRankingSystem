"""add_dark_mode_logo

Revision ID: a1b2c3d4e5f6
Revises: f94bc295c642
Create Date: 2026-07-28 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f94bc295c642'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('club_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('club_logo_dark_path', sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('club_settings', schema=None) as batch_op:
        batch_op.drop_column('club_logo_dark_path')
