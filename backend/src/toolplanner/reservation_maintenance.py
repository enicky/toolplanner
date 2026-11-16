import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from toolplanner.db import SessionLocal
from toolplanner.models import (
    AuditEvent,
    Elevator,
    Loan,
    Reservation,
    ReservationPolicy,
    UserNotification,
)


def expire_no_show_reservations(
    db: Session, now: datetime | None = None
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    policy = db.get(ReservationPolicy, 1)
    if not policy:
        return {"expired": 0, "at_risk": 0}
    cutoff = now - timedelta(seconds=policy.no_show_grace_seconds)
    reservations = db.scalars(
        select(Reservation)
        .where(
            Reservation.status == "confirmed",
            Reservation.starts_at <= cutoff,
        )
        .with_for_update()
    ).all()
    expired = 0
    at_risk = 0
    for reservation in reservations:
        elevator = db.get(Elevator, reservation.elevator_id)
        custody = db.scalar(
            select(Loan.id).where(
                Loan.elevator_id == reservation.elevator_id,
                Loan.returned_at.is_(None),
            )
        )
        if not elevator or elevator.status != "active" or custody:
            at_risk += 1
            key = f"late:{reservation.id}"
            if not db.scalar(
                select(UserNotification.id).where(
                    UserNotification.deduplication_key == key
                )
            ):
                name = elevator.name if elevator else "This elevator"
                db.add(
                    UserNotification(
                        recipient_user_id=reservation.requester_user_id,
                        reservation_id=reservation.id,
                        deduplication_key=key,
                        message=f"{name} is not available for your reservation.",
                    )
                )
            continue
        reservation.status = "expired"
        reservation.expired_at = now
        db.add(
            AuditEvent(
                actor_user_id=None,
                action="reservation_expired_no_show",
                entity_type="reservation",
                entity_id=reservation.id,
            )
        )
        expired += 1
    db.commit()
    return {"expired": expired, "at_risk": at_risk}


def main() -> None:
    argparse.ArgumentParser(description="Expire Tool Planner no-show reservations.").parse_args()
    with SessionLocal() as db:
        result = expire_no_show_reservations(db)
    print(f"expired={result['expired']}")
    print(f"at_risk={result['at_risk']}")


if __name__ == "__main__":
    main()
