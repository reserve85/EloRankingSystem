"""drop_club_settings_club_name

Revision ID: d1e2f3a4b5c6
Revises: f1e2d3c4b5a6
Create Date: 2026-09-04

Club identity (``club_name``) is read exclusively from env/config
(``settings.club_name`` / ``_get_club_name``); the DB column was
write-rarely / never-read and is now dropped - environment/config wins, the
same decision already applied to the Elo knobs in ``f1e2d3c4b5a6``.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("club_settings", schema=None) as batch_op:
        batch_op.drop_column("club_name")


def downgrade() -> None:
    # Recreate the column with the historical default so existing rows get the
    # documented default value (mirrors f1e2d3c4b5a6's downgrade pattern).
    with op.batch_alter_table("club_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "club_name", sa.String(length=200), nullable=False, server_default="Dart Club"
            )
        )
