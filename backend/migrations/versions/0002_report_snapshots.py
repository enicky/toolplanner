"""Store immutable report dimensions on loan history."""

import sqlalchemy as sa
from alembic import op

revision = "0002_report_snapshots"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("loan")
    }
    columns = (
        (
            "department_id_snapshot",
            sa.Column(
                "department_id_snapshot",
                sa.String(length=36),
                sa.ForeignKey("department.id"),
                nullable=True,
            ),
        ),
        (
            "checkout_location_snapshot",
            sa.Column("checkout_location_snapshot", sa.String(length=120), nullable=True),
        ),
        (
            "return_location_snapshot",
            sa.Column("return_location_snapshot", sa.String(length=120), nullable=True),
        ),
    )
    for name, column in columns:
        if name not in existing_columns:
            op.add_column("loan", column)

    op.execute(
        sa.text(
            """
            UPDATE loan
            SET checkout_location_snapshot = (
                SELECT location.name
                FROM location
                WHERE location.id = loan.checkout_location_id
            )
            WHERE checkout_location_snapshot IS NULL
              AND checkout_location_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE loan
            SET return_location_snapshot = (
                SELECT location.name
                FROM location
                WHERE location.id = loan.return_location_id
            )
            WHERE return_location_snapshot IS NULL
              AND return_location_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE loan
            SET department_id_snapshot = (
                SELECT department.id
                FROM department
                WHERE department.name = loan.department_snapshot
                ORDER BY department.id
                LIMIT 1
            )
            WHERE department_id_snapshot IS NULL
            """
        )
    )

    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("loan")}
    indexes = (
        ("ix_loan_department_id_snapshot", ["department_id_snapshot"]),
        ("ix_loan_checkout_location_id", ["checkout_location_id"]),
    )
    for name, columns in indexes:
        if name not in existing_indexes:
            op.create_index(name, "loan", columns, unique=False)


def downgrade() -> None:
    op.drop_index("ix_loan_checkout_location_id", table_name="loan")
    op.drop_index("ix_loan_department_id_snapshot", table_name="loan")
    op.drop_column("loan", "return_location_snapshot")
    op.drop_column("loan", "checkout_location_snapshot")
    op.drop_column("loan", "department_id_snapshot")
