"""initial registry schema

Revision ID: 0001
Revises:
Create Date: 2026-09-12

Creates ``document_signatures`` exactly as specified in the registry guide.
No ``valid`` or ``status`` column, by design — see registry.py's module
docstring: status is always computed, never stored.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_signatures",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        # Document identity
        sa.Column("document_hash", sa.String, nullable=False),
        sa.Column("filename", sa.String, nullable=True),
        # Cryptographic material
        sa.Column("signature", sa.String, nullable=False),
        sa.Column("certificate_pem", sa.String, nullable=False),
        sa.Column("algorithm", sa.String, nullable=False, server_default="Ed25519"),
        sa.Column("hash_algorithm", sa.String, nullable=False, server_default="SHA-256"),
        # Parsed certificate fields — display/query only, never trusted by verify.py
        sa.Column("employee_id", sa.String, nullable=False),
        sa.Column("employee_name", sa.String, nullable=False),
        sa.Column("key_id", sa.String, nullable=False),
        sa.Column("certificate_serial", sa.String, nullable=False),
        sa.Column("certificate_not_before", sa.String, nullable=False),
        sa.Column("certificate_not_after", sa.String, nullable=False),
        # Timestamp
        sa.Column("signed_at", sa.String, nullable=False),
        sa.Column("timestamp_token", sa.String, nullable=True),
        # Registry metadata
        sa.Column("created_at", sa.String, nullable=False),
        sa.Column("revoked_at", sa.String, nullable=True),
        # Source tracking
        sa.Column("source", sa.String, nullable=False, server_default="signed"),
        sa.Column("import_verified_at", sa.String, nullable=True),
    )

    # Primary lookup: hash -> all signatures for this document
    op.create_index("idx_document_hash", "document_signatures", ["document_hash"])
    # Secondary lookup: employee's signing history
    op.create_index("idx_employee_id", "document_signatures", ["employee_id"])
    # Secondary lookup: certificate serial (for revocation queries)
    op.create_index("idx_certificate_serial", "document_signatures", ["certificate_serial"])

    # No unique constraint on document_hash: multiple legitimate signers per
    # document are expected, not an error.


def downgrade() -> None:
    op.drop_index("idx_certificate_serial", table_name="document_signatures")
    op.drop_index("idx_employee_id", table_name="document_signatures")
    op.drop_index("idx_document_hash", table_name="document_signatures")
    op.drop_table("document_signatures")
