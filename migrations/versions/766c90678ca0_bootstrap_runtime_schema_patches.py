"""bootstrap runtime schema patches

Revision ID: 766c90678ca0
Revises:
Create Date: 2026-02-11 09:07:17.553097

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "766c90678ca0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if _has_table("checklist_progress"):
        if not _has_column("checklist_progress", "tenant_id"):
            op.add_column(
                "checklist_progress",
                sa.Column("tenant_id", sa.String(length=255), nullable=True),
            )
        if not _has_column("checklist_progress", "tenant_name"):
            op.add_column(
                "checklist_progress",
                sa.Column("tenant_name", sa.String(length=255), nullable=True),
            )

    if _has_table("users") and not _has_column("users", "bas_lodge_method"):
        op.add_column(
            "users",
            sa.Column(
                "bas_lodge_method",
                sa.String(length=10),
                nullable=True,
                server_default="self",
            ),
        )

    if not _has_table("runtime_health_snapshots"):
        op.create_table(
            "runtime_health_snapshots",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("degraded_reasons", sa.JSON(), nullable=True),
            sa.Column("scheduler", sa.JSON(), nullable=False),
            sa.Column("jobs", sa.JSON(), nullable=False),
            sa.Column("queue", sa.JSON(), nullable=False),
            sa.Column("startup_config_audit", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if _has_table("runtime_health_snapshots"):
        if not _has_index(
            "runtime_health_snapshots", "ix_runtime_health_snapshots_status"
        ):
            op.create_index(
                "ix_runtime_health_snapshots_status",
                "runtime_health_snapshots",
                ["status"],
                unique=False,
            )
        if not _has_index(
            "runtime_health_snapshots", "ix_runtime_health_snapshots_created_at"
        ):
            op.create_index(
                "ix_runtime_health_snapshots_created_at",
                "runtime_health_snapshots",
                ["created_at"],
                unique=False,
            )


def downgrade():
    if _has_table("runtime_health_snapshots"):
        if _has_index(
            "runtime_health_snapshots", "ix_runtime_health_snapshots_created_at"
        ):
            op.drop_index(
                "ix_runtime_health_snapshots_created_at",
                table_name="runtime_health_snapshots",
            )
        if _has_index("runtime_health_snapshots", "ix_runtime_health_snapshots_status"):
            op.drop_index(
                "ix_runtime_health_snapshots_status",
                table_name="runtime_health_snapshots",
            )
        op.drop_table("runtime_health_snapshots")

    if _has_table("users") and _has_column("users", "bas_lodge_method"):
        op.drop_column("users", "bas_lodge_method")

    if _has_table("checklist_progress"):
        if _has_column("checklist_progress", "tenant_name"):
            op.drop_column("checklist_progress", "tenant_name")
        if _has_column("checklist_progress", "tenant_id"):
            op.drop_column("checklist_progress", "tenant_id")


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return bool(inspector.has_table(table_name))


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}
