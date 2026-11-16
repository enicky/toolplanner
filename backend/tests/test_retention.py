from datetime import UTC, datetime, timedelta

from toolplanner.models import (
    AuditEvent,
    Elevator,
    Loan,
    Reservation,
    UserAccount,
    UserNotification,
    UserSession,
)
from toolplanner.retention import purge_expired_records


def test_retention_deletes_expired_history_but_keeps_open_custody(clients):
    admin, _, _ = clients
    now = datetime.now(UTC)
    old_return = now - timedelta(days=365 * 4)
    with admin.app.state.session_factory.begin() as db:
        elevator = db.query(Elevator).first()
        user = db.query(UserAccount).filter_by(username="user").one()
        returned = Loan(
            elevator_id=elevator.id,
            checkout_actor_user_id=user.id,
            borrower_name="Old Borrower",
            department_snapshot="Sites & Facilities",
            destination="Building 2",
            checked_out_at=old_return - timedelta(days=1),
            returned_at=old_return,
            status="returned",
        )
        outstanding = Loan(
            elevator_id=elevator.id,
            checkout_actor_user_id=user.id,
            borrower_name="Current Borrower",
            department_snapshot="Sites & Facilities",
            destination="Building 2",
            checked_out_at=old_return - timedelta(days=1),
            status="active",
        )
        db.add(returned)
        db.flush()
        reservation = Reservation(
            elevator_id=elevator.id,
            requester_user_id=user.id,
            borrower_name="Old Borrower",
            starts_at=old_return - timedelta(days=10),
            ends_at=old_return - timedelta(days=9),
            status="picked_up",
            policy_version=1,
            loan_id=returned.id,
        )
        db.add_all(
            [
                outstanding,
                reservation,
                AuditEvent(
                    actor_user_id=user.id,
                    action="old_action",
                    entity_type="loan",
                    entity_id=returned.id,
                    occurred_at=old_return,
                ),
                UserNotification(
                    recipient_user_id=user.id,
                    reservation_id=reservation.id,
                    message="old notice",
                    deduplication_key="old_notice",
                    created_at=old_return,
                ),
                UserSession(
                    user_id=user.id,
                    token_hash="a" * 64,
                    csrf_token="b" * 64,
                    expires_at=now - timedelta(days=1),
                ),
            ]
        )
        db.flush()
        returned_id, outstanding_id = returned.id, outstanding.id

    with admin.app.state.session_factory() as db:
        counts = purge_expired_records(db, now=now)
        assert counts["loans_deleted"] == 1
        assert counts["reservations_deleted"] == 1
        assert counts["audit_events_deleted"] == 1
        assert counts["notifications_deleted"] == 1
        assert counts["sessions_deleted"] == 1
        assert db.get(Loan, returned_id) is None
        assert db.get(Loan, outstanding_id) is not None
