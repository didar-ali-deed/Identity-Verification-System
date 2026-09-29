"""hash stored refresh tokens

Revision ID: d21ab84f970c
Revises: c3a8f1d92e47
Create Date: 2026-09-30 00:00:00.000000
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d21ab84f970c"
down_revision: str | None = "c3a8f1d92e47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, refresh_token FROM users WHERE refresh_token IS NOT NULL")).all()
    for user_id, token in rows:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        connection.execute(
            sa.text("UPDATE users SET refresh_token = :token_hash WHERE id = :user_id"),
            {"token_hash": token_hash, "user_id": user_id},
        )


def downgrade() -> None:
    # Original tokens cannot be recovered from their hashes; force sign-in again.
    op.execute("UPDATE users SET refresh_token = NULL")
