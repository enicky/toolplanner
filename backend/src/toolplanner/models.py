from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from toolplanner.db import Base


def new_id() -> str:
    return str(uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Department(TimestampMixin, Base):
    __tablename__ = "department"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Location(TimestampMixin, Base):
    __tablename__ = "location"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    details: Mapped[str | None] = mapped_column(String(240))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


Index(
    "uq_location_single_default",
    Location.is_default,
    unique=True,
    postgresql_where=Location.is_default.is_(True),
    sqlite_where=Location.is_default.is_(True),
)


class UserAccount(TimestampMixin, Base):
    __tablename__ = "user_account"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_user_account_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    department: Mapped[Department | None] = relationship()


class UserSession(Base):
    __tablename__ = "user_session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[UserAccount] = relationship()


class Elevator(TimestampMixin, Base):
    __tablename__ = "elevator"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'blocked', 'retired')", name="ck_elevator_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    registration_number: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    block_reason: Mapped[str | None] = mapped_column(Text)
    qr_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    last_known_location_id: Mapped[str | None] = mapped_column(ForeignKey("location.id"))
    last_known_location: Mapped[Location | None] = relationship()


class Loan(TimestampMixin, Base):
    __tablename__ = "loan"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'cancelled', 'returned')", name="ck_loan_status"
        ),
        CheckConstraint(
            "(status = 'returned' AND returned_at IS NOT NULL) OR "
            "(status IN ('active', 'cancelled') AND returned_at IS NULL)",
            name="ck_loan_return_state",
        ),
        CheckConstraint(
            "(status != 'cancelled') OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
            name="ck_loan_cancel_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    elevator_id: Mapped[str] = mapped_column(ForeignKey("elevator.id"), nullable=False)
    checkout_actor_user_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.id"), nullable=False
    )
    borrower_name: Mapped[str] = mapped_column(String(160), nullable=False)
    department_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    checkout_location_id: Mapped[str | None] = mapped_column(ForeignKey("location.id"))
    destination: Mapped[str] = mapped_column(String(240), nullable=False)
    checked_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    return_actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    return_location_id: Mapped[str | None] = mapped_column(ForeignKey("location.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    cancelled_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    elevator: Mapped[Elevator] = relationship()


Index(
    "uq_loan_outstanding_custody",
    Loan.elevator_id,
    unique=True,
    postgresql_where=Loan.returned_at.is_(None),
    sqlite_where=Loan.returned_at.is_(None),
)
Index("ix_loan_checked_out_at", Loan.checked_out_at)


class ReservationPolicy(TimestampMixin, Base):
    __tablename__ = "reservation_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    minimum_notice_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=604800)
    maximum_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=604800)
    cancellation_cutoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=604800)
    no_show_grace_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=604800)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('confirmed', 'cancelled', 'expired', 'picked_up')",
            name="ck_reservation_status",
        ),
        CheckConstraint("starts_at < ends_at", name="ck_reservation_window"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    elevator_id: Mapped[str] = mapped_column(ForeignKey("elevator.id"), nullable=False)
    requester_user_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.id"), nullable=False
    )
    borrower_name: Mapped[str] = mapped_column(String(160), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed")
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    loan_id: Mapped[str | None] = mapped_column(ForeignKey("loan.id"), unique=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserNotification(Base):
    __tablename__ = "user_notification"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient_user_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.id"), nullable=False
    )
    reservation_id: Mapped[str | None] = mapped_column(ForeignKey("reservation.id"))
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
