"""make guardian email and phone nullable

Revision ID: 20260325232336
Revises:
Create Date: 2026-03-25 23:23:36

"""
from alembic import op
import sqlalchemy as sa


revision = '20260325232336'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite doesn't support ALTER COLUMN directly — use batch mode
    with op.batch_alter_table('guardians') as batch_op:
        batch_op.alter_column('email',
                              existing_type=sa.String(200),
                              nullable=True)
        batch_op.alter_column('phone',
                              existing_type=sa.String(50),
                              nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('guardians') as batch_op:
        batch_op.alter_column('email',
                              existing_type=sa.String(200),
                              nullable=False)
        batch_op.alter_column('phone',
                              existing_type=sa.String(50),
                              nullable=False)
