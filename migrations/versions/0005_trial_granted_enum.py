"""Add 'trial_granted' value to the auditaction Postgres enum

0004_trial added the trial_used/is_trial COLUMNS but missed that
AuditAction.trial_granted also needs its VALUE added to the existing
Postgres enum TYPE (auditaction) — unlike a plain column, enum values on
Postgres aren't created implicitly by SQLAlchemy on ALTER TABLE, they must
be added explicitly with ALTER TYPE ... ADD VALUE. Without this,
BillingService.grant_trial()'s audit log insert fails with:
  asyncpg.exceptions.InvalidTextRepresentationError:
  invalid input value for enum auditaction: "trial_granted"

ALTER TYPE ... ADD VALUE cannot run inside a transaction block on
PostgreSQL < 12 and, even on 12+, cannot be combined with a later command
that uses the new value in the same transaction — so this migration
disables the wrapping transaction entirely (autocommit block) for
safety across PG versions.

Revision ID: 0005_trial_granted_enum
Revises: 0004_trial
Create Date: 2026-08-25
"""
from alembic import op

revision = "0005_trial_granted_enum"
down_revision = "0004_trial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'trial_granted'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Removing an enum value
    # safely requires rebuilding the type (create new type, cast the
    # column over, drop the old type) and is not worth the risk for a
    # downgrade path that's unlikely to ever run in practice. Left as a
    # no-op; the extra enum value is harmless if this migration is reverted.
    pass
