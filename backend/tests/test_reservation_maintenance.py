from datetime import UTC, datetime, timedelta

from toolplanner.models import (
    Elevator,
    Loan,
    Reservation,
    ReservationPolicy,
    UserAccount,
)
from toolplanner.reservation_maintenance import expire_no_show_reservations


def test_no_show_expires_only_when_elevator_is_available(clients):
    admin, _, _ = clients
    now = datetime.now(UTC)
    with admin.app.state.session_factory.begin() as db:
        user = db.query(UserAccount).filter_by(username="user").one()
        elevator = db.query(Elevator).first()
        elevator2 = Elevator(
            registration_number="LIFT-002",
            name="LIFT-002",
            status="active",
            qr_token="test-qr-token-002",
        )
        db.add(elevator2)
        db.flush()
        db.add(ReservationPolicy(id=1))
        available_reservation = Reservation(
            elevator_id=elevator.id,
            requester_user_id=user.id,
            borrower_name="Available User",
            starts_at=now - timedelta(days=8),
            ends_at=now - timedelta(days=7),
            status="confirmed",
            policy_version=1,
        )
        blocked_reservation = Reservation(
            elevator_id=elevator2.id,
            requester_user_id=user.id,
            borrower_name="At-risk User",
            starts_at=now - timedelta(days=8),
            ends_at=now - timedelta(days=7),
            status="confirmed",
            policy_version=1,
        )
        db.add_all([available_reservation, blocked_reservation])
        db.flush()
        available_reservation_id = available_reservation.id
        blocked_reservation_id = blocked_reservation.id
        db.add(
            Loan(
                elevator_id=elevator2.id,
                checkout_actor_user_id=user.id,
                borrower_name="Late Borrower",
                department_snapshot="Sites & Facilities",
                destination="Building 2",
                checked_out_at=now - timedelta(days=9),
                status="active",
            )
        )

    with admin.app.state.session_factory() as db:
        result = expire_no_show_reservations(db, now=now)
        assert result == {"expired": 1, "at_risk": 1}
        assert db.get(Reservation, available_reservation_id).status == "expired"
        assert db.get(Reservation, blocked_reservation_id).status == "confirmed"
