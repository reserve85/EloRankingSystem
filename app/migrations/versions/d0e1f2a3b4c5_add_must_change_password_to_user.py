"""add_must_change_password_to_user

Revision ID: d0e1f2a3b4c5
Revises: b2c3d4e5f6a7
Create Date: 2026-09-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add must_change_password with a False server default for existing rows
    # (SQLite stores booleans as 0/1). Fix H2: forces the one-shot SYSTEM
    # bootstrap (and admin password resets) to set a real password on first login.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('must_change_password', sa.Boolean(),
                      server_default='0', nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('must_change_password')