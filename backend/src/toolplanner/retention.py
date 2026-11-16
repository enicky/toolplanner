import argparse
import secrets
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from toolplanner.db import SessionLocal
from toolplanner.models import (
    AuditEvent,
    Loan,
    Reservation,
    UserAccount,
    UserNotification,
    UserSession,
)


def three_years_before(value: datetime) -> datetime:
    value = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        return value.replace(year=value.year - 3)
    except ValueError:
        return value.replace(year=value.year - 3, month=2, day=28)


def purge_expired_records(db: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    cutoff = three_years_before(now)
    returned_loan_ids = list(
        db.scalars(
            select(Loan.id).where(
                Loan.returned_at.is_not(None),
                Loan.returned_at <= cutoff,
            )
        )
    )
    expired_reservations = list(
        db.scalars(
            select(Reservation.id).where(
                or_(
                    (
                        Reservation.status == "picked_up"
                    )
                    & Reservation.loan_id.in_(returned_loan_ids or [""]),
                    (
                        Reservation.status == "cancelled"
                    )
                    & (Reservation.cancelled_at <= cutoff),
                    (
                        Reservation.status == "expired"
                    )
                    & (Reservation.expired_at <= cutoff),
                )
            )
        )
    )

    notifications_deleted = db.execute(
        delete(UserNotification).where(
            or_(
                UserNotification.created_at <= cutoff,
                UserNotification.reservation_id.in_(expired_reservations or [""]),
            )
        )
    ).rowcount or 0
    reservations_deleted = db.execute(
        delete(Reservation).where(Reservation.id.in_(expired_reservations or [""]))
    ).rowcount or 0
    loans_deleted = db.execute(
        delete(Loan).where(Loan.id.in_(returned_loan_ids or [""]))
    ).rowcount or 0
    audit_deleted = db.execute(
        delete(AuditEvent).where(AuditEvent.occurred_at <= cutoff)
    ).rowcount or 0
    sessions_deleted = db.execute(
        delete(UserSession).where(
            or_(
                UserSession.expires_at <= now,
                UserSession.revoked_at <= cutoff,
            )
        )
    ).rowcount or 0

    accounts_anonymized = 0
    disabled_accounts = db.scalars(
        select(UserAccount).where(
            UserAccount.is_active.is_(False),
            UserAccount.disabled_at.is_not(None),
            UserAccount.disabled_at <= cutoff,
        )
    ).all()
    for account in disabled_accounts:
        outstanding_custody = db.scalar(
            select(Loan.id).where(
                Loan.checkout_actor_user_id == account.id,
                Loan.returned_at.is_(None),
            )
        )
        outstanding_reservation = db.scalar(
            select(Reservation.id).where(
                Reservation.requester_user_id == account.id,
                Reservation.status == "confirmed",
            )
        )
        if outstanding_custody or outstanding_reservation:
            continue
        account.username = f"former-{account.id}"
        account.display_name = "Former user"
        account.password_hash = f"disabled${secrets.token_hex(32)}"
        account.role = "user"
        account.department_id = None
        account.must_change_password = True
        accounts_anonymized += 1

    db.commit()
    return {
        "loans_deleted": loans_deleted,
        "reservations_deleted": reservations_deleted,
        "audit_events_deleted": audit_deleted,
        "notifications_deleted": notifications_deleted,
        "sessions_deleted": sessions_deleted,
        "accounts_anonymized": accounts_anonymized,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Tool Planner three-year retention.")
    parser.parse_args()
    with SessionLocal() as db:
        counts = purge_expired_records(db)
    for entity, count in counts.items():
        print(f"{entity}={count}")


if __name__ == "__main__":
    main()
