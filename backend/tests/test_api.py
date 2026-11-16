from datetime import UTC, datetime, timedelta

from conftest import csrf
from sqlalchemy import select

from toolplanner.models import Loan, Reservation, UserAccount
from toolplanner.security import verify_password


def test_qr_status_is_public_and_does_not_expose_borrower(clients):
    _, client, token = clients
    response = client.get(f"/api/v1/qr/{token}")
    assert response.status_code == 200
    assert response.json() == {
        "name": "LIFT-001",
        "registration_number": "LIFT-001",
        "status": "available",
        "elevator_status": "active",
        "can_return": False,
        "can_borrow": True,
    }


def test_borrow_requires_login(clients):
    _, client, token = clients
    client.post("/api/v1/auth/logout", headers=csrf(client))
    response = client.post(
        f"/api/v1/qr/{token}/checkout",
        json={"borrower_name": "Test Borrower", "destination": "Building 2"},
    )
    assert response.status_code == 401


def test_admin_block_cancels_loan_but_return_closes_custody(clients):
    admin, user, token = clients
    checkout = user.post(
        f"/api/v1/qr/{token}/checkout",
        headers=csrf(user),
        json={"borrower_name": "Typed Borrower", "destination": "Building 2"},
    )
    assert checkout.status_code == 201
    loan_id = checkout.json()["id"]

    block = admin.post(
        f"/api/v1/admin/elevators/{_elevator_id(admin)}/block",
        headers=csrf(admin),
        json={"reason": "Inspection required"},
    )
    assert block.status_code == 200
    status_after_block = admin.get(f"/api/v1/qr/{token}").json()
    assert status_after_block["can_return"] is True
    assert status_after_block["elevator_status"] == "blocked"

    with admin.app.state.session_factory() as db:
        loan = db.get(Loan, loan_id)
        assert loan.status == "cancelled"
        assert loan.returned_at is None

    returned = user.post(
        f"/api/v1/qr/{token}/return",
        headers=csrf(user),
        json={},
    )
    assert returned.status_code == 200
    with admin.app.state.session_factory() as db:
        loan = db.get(Loan, loan_id)
        assert loan.status == "returned"
        assert loan.returned_at is not None
        assert loan.cancellation_reason == "Inspection required"
    cannot_reborrow = user.post(
        f"/api/v1/qr/{token}/checkout",
        headers=csrf(user),
        json={"borrower_name": "Another Borrower", "destination": "Building 3"},
    )
    assert cannot_reborrow.status_code == 409


def test_non_admin_cannot_manage_inventory(clients):
    _, user, _ = clients
    response = user.get("/api/v1/admin/elevators")
    assert response.status_code == 403


def test_reservations_enforce_time_window_and_overlap(clients):
    admin, user, token = clients
    with admin.app.state.session_factory() as db:
        assert db.scalar(select(Reservation.id)) is None
    starts_at = datetime.now(UTC) + timedelta(days=8)
    ends_at = starts_at + timedelta(hours=2)
    body = {
        "borrower_name": "Test Borrower",
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    }
    created = user.post(
        f"/api/v1/qr/{token}/reservations",
        headers=csrf(user),
        json=body,
    )
    assert created.status_code == 201, created.text
    conflict = user.post(
        f"/api/v1/qr/{token}/reservations",
        headers=csrf(user),
        json=body,
    )
    assert conflict.status_code == 409


def test_reserved_user_can_pick_up_their_reservation(clients):
    admin, user, token = clients
    starts_at = datetime.now(UTC) + timedelta(days=8)
    ends_at = starts_at + timedelta(hours=2)
    payload = {
        "borrower_name": "Reservation Owner",
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    }
    created = user.post(
        f"/api/v1/qr/{token}/reservations",
        headers=csrf(user),
        json=payload,
    )
    assert created.status_code == 201
    reservation_id = created.json()["id"]
    with admin.app.state.session_factory.begin() as db:
        reservation = db.get(Reservation, reservation_id)
        reservation.starts_at = datetime.now(UTC) - timedelta(minutes=5)

    owner_reservations = user.get("/api/v1/me/reservations").json()
    assert owner_reservations[0]["qr_token"] == token
    status_response = user.get(f"/api/v1/qr/{token}")
    assert status_response.json()["status"] == "reserved"

    pickup = user.post(
        f"/api/v1/qr/{token}/checkout",
        headers=csrf(user),
        json={
            "borrower_name": "Reservation Owner",
            "destination": "Building 2",
            "reservation_id": reservation_id,
        },
    )
    assert pickup.status_code == 201
    with admin.app.state.session_factory() as db:
        reservation = db.get(Reservation, reservation_id)
        assert reservation.status == "picked_up"
        assert reservation.loan_id == pickup.json()["id"]


def test_initial_password_requires_reset_and_new_password_works(clients):
    admin, user, _ = clients
    department_id = user.get("/api/v1/me").json()["department_id"]
    created = admin.post(
        "/api/v1/admin/users",
        headers=csrf(admin),
        json={
            "username": "new.person",
            "initial_password": "temporary-password-123",
            "role": "user",
            "display_name": "New Person",
            "department_id": department_id,
        },
    )
    assert created.status_code == 201
    new_client = type(user)(user.app)
    login = new_client.post(
        "/api/v1/auth/login",
        json={"username": "new.person", "password": "temporary-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True
    blocked = new_client.get("/api/v1/me/reservations")
    assert blocked.status_code == 403
    changed = new_client.post(
        "/api/v1/auth/change-password",
        headers=csrf(new_client),
        json={
            "current_password": "temporary-password-123",
            "new_password": "a-new-password-longer",
        },
    )
    assert changed.status_code == 200
    with admin.app.state.session_factory() as db:
        account = db.scalar(
            select(UserAccount).where(UserAccount.username == "new.person")
        )
        assert account is not None
        assert account.must_change_password is False
        assert verify_password(account.password_hash, "a-new-password-longer")


def test_admin_history_export_is_admin_only_and_formula_safe(clients):
    admin, user, token = clients
    checkout = user.post(
        f"/api/v1/qr/{token}/checkout",
        headers=csrf(user),
        json={"borrower_name": "=1+1", "destination": "+cmd"},
    )
    assert checkout.status_code == 201
    assert user.get("/api/v1/admin/reports/loans.csv").status_code == 403
    report = admin.get("/api/v1/admin/reports/loans.csv")
    assert report.status_code == 200
    assert "'=1+1" in report.text
    assert "'+cmd" in report.text


def test_admin_usage_report_counts_checkouts_and_returned_durations(clients):
    admin, user, token = clients
    checkout = user.post(
        f"/api/v1/qr/{token}/checkout",
        headers=csrf(user),
        json={"borrower_name": "Test Borrower", "destination": "Building 2"},
    )
    assert checkout.status_code == 201
    before_return = admin.get("/api/v1/admin/reports/usage").json()
    assert before_return[0]["checkout_count"] == 1
    assert before_return[0]["average_duration_seconds"] is None
    returned = user.post(
        f"/api/v1/qr/{token}/return",
        headers=csrf(user),
        json={},
    )
    assert returned.status_code == 200
    after_return = admin.get("/api/v1/admin/reports/usage").json()
    assert after_return[0]["average_duration_seconds"] is not None


def _elevator_id(client):
    return client.get("/api/v1/admin/elevators").json()[0]["id"]
