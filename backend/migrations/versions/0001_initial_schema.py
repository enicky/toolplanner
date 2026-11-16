"""Create the initial Tool Planner schema and seed the first site inventory."""

from uuid import uuid4

from alembic import op
from sqlalchemy import Boolean, Integer, String, column, table

from toolplanner.security import new_qr_token

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from toolplanner import models  # noqa: F401
    from toolplanner.db import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    department_id = str(uuid4())
    location_id = str(uuid4())
    elevator_id = str(uuid4())
    op.bulk_insert(
        table(
            "department",
            column("id", String),
            column("name", String),
            column("is_active", Boolean),
        ),
        [{"id": department_id, "name": "Sites & Facilities", "is_active": True}],
    )
    op.bulk_insert(
        table(
            "location",
            column("id", String),
            column("name", String),
            column("is_active", Boolean),
            column("is_default", Boolean),
        ),
        [{"id": location_id, "name": "Geel", "is_active": True, "is_default": True}],
    )
    op.bulk_insert(
        table(
            "elevator",
            column("id", String),
            column("registration_number", String),
            column("name", String),
            column("status", String),
            column("qr_token", String),
            column("last_known_location_id", String),
        ),
        [
            {
                "id": elevator_id,
                "registration_number": "LIFT-001",
                "name": "LIFT-001",
                "status": "active",
                "qr_token": new_qr_token(),
                "last_known_location_id": location_id,
            }
        ],
    )
    op.bulk_insert(
        table(
            "reservation_policy",
            column("id", Integer),
            column("minimum_notice_seconds", Integer),
            column("maximum_duration_seconds", Integer),
            column("cancellation_cutoff_seconds", Integer),
            column("no_show_grace_seconds", Integer),
            column("version", Integer),
        ),
        [
            {
                "id": 1,
                "minimum_notice_seconds": 604800,
                "maximum_duration_seconds": 604800,
                "cancellation_cutoff_seconds": 604800,
                "no_show_grace_seconds": 604800,
                "version": 1,
            }
        ],
    )


def downgrade() -> None:
    from toolplanner import models  # noqa: F401
    from toolplanner.db import Base

    Base.metadata.drop_all(bind=op.get_bind())
