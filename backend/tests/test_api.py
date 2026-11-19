from datetime import UTC, datetime, timedelta

from conftest import csrf
from sqlalchemy import select

from toolplanner.models import Department, Elevator, Loan, Reservation, UserAccount
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
    logout = client.post("/api/v1/auth/logout", headers=csrf(client))
    assert logout.status_code == 204
    assert "toolplanner_session" in logout.headers.get("set-cookie", "")
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
    assert user.get("/api/v1/admin/audit").status_code == 403


def test_admin_can_view_audit_activity(clients):
    admin, _, _ = clients
    response = admin.get("/api/v1/admin/audit")
    assert response.status_code == 200
    assert response.json() == []


def test_location_edit_archive_restore_preserves_default_and_history(clients):
    admin, _, _ = clients
    default_location = next(
        item
        for item in admin.get("/api/v1/admin/locations").json()
        if item["is_default"]
    )
    cannot_archive_default = admin.delete(
        f"/api/v1/admin/locations/{default_location['id']}",
        headers=csrf(admin),
    )
    assert cannot_archive_default.status_code == 409

    created = admin.post(
        "/api/v1/admin/locations",
        headers=csrf(admin),
        json={"name": "Workshop", "details": "North building"},
    )
    assert created.status_code == 201
    location_id = created.json()["id"]
    updated = admin.patch(
        f"/api/v1/admin/locations/{location_id}",
        headers=csrf(admin),
        json={"name": "Workshop West", "details": "West entrance"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Workshop West"
    assert updated.json()["details"] == "West entrance"

    archived = admin.delete(
        f"/api/v1/admin/locations/{location_id}",
        headers=csrf(admin),
    )
    assert archived.status_code == 200
    assert archived.json()["preserved_for_history"] is True
    assert all(
        item["id"] != location_id
        for item in admin.get("/api/v1/locations").json()
    )
    assert any(
        item["id"] == location_id and not item["is_active"]
        for item in admin.get("/api/v1/admin/locations").json()
    )

    restored = admin.post(
        f"/api/v1/admin/locations/{location_id}/restore",
        headers=csrf(admin),
    )
    assert restored.status_code == 200
    assert any(item["id"] == location_id for item in admin.get("/api/v1/locations").json())


def test_department_delete_requires_reassigning_users_and_archives_record(clients):
    admin, user, _ = clients
    department = admin.post(
        "/api/v1/admin/departments",
        headers=csrf(admin),
        json={"name": "Research"},
    )
    assert department.status_code == 201, department.text
    department_id = department.json()["id"]
    with admin.app.state.session_factory.begin() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.username == "user"))
        account.department_id = department_id

    updated = admin.patch(
        f"/api/v1/admin/departments/{department_id}",
        headers=csrf(admin),
        json={"name": "Research West"},
    )
    assert updated.status_code == 200
    still_in_use = admin.delete(
        f"/api/v1/admin/departments/{department_id}",
        headers=csrf(admin),
    )
    assert still_in_use.status_code == 409
    with admin.app.state.session_factory.begin() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.username == "user"))
        default_department_id = db.scalar(
            select(Department.id).where(Department.name == "Sites & Facilities")
        )
        account.department_id = default_department_id
    archived = admin.delete(
        f"/api/v1/admin/departments/{department_id}",
        headers=csrf(admin),
    )
    assert archived.status_code == 200
    with admin.app.state.session_factory() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.username == "user"))
        assert account.department_id == default_department_id
        archived_department = db.get(Department, department_id)
        assert archived_department.name == "Research West"
        assert archived_department.is_active is False
    assert all(
        item["id"] != department_id
        for item in user.get("/api/v1/departments").json()
    )
    assert any(
        item["id"] == department_id and not item["is_active"]
        for item in admin.get("/api/v1/admin/departments").json()
    )


def test_admin_overview_is_aggregated_without_borrower_details(clients):
    admin, user, token = clients
    response = user.post(
        f"/api/v1/qr/{token}/checkout",
        headers=csrf(user),
        json={"borrower_name": "Private Borrower Name", "destination": "Building 2"},
    )
    assert response.status_code == 201
    starts_at = datetime.now(UTC) + timedelta(days=8)
    reservation = user.post(
        f"/api/v1/qr/{token}/reservations",
        headers=csrf(user),
        json={
            "borrower_name": "Reservation Owner",
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=2)).isoformat(),
        },
    )
    assert reservation.status_code == 201
    with admin.app.state.session_factory.begin() as db:
        db.get(Reservation, reservation.json()["id"]).starts_at = datetime.now(UTC) - timedelta(minutes=1)
    overview = admin.get("/api/v1/admin/overview")
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["outstanding_custody_count"] == 1
    assert payload["at_risk_reservation_count"] == 1
    assert payload["oldest_custody"][0]["registration_number"] == "LIFT-001"
    assert "borrower_name" not in overview.text
    assert "Private Borrower Name" not in overview.text


def test_admin_overview_does_not_count_blocked_custody_as_active_inventory(clients):
    admin, user, token = clients
    with admin.app.state.session_factory.begin() as db:
        db.add(
            Elevator(
                registration_number="LIFT-002",
                name="LIFT-002",
                status="active",
                qr_token="overview-lift-002-token",
            )
        )
    checkout = user.post(
        f"/api/v1/qr/{token}/checkout",
        headers=csrf(user),
        json={"borrower_name": "Current Borrower", "destination": "Building 2"},
    )
    assert checkout.status_code == 201
    block = admin.post(
        f"/api/v1/admin/elevators/{_elevator_id(admin)}/block",
        headers=csrf(admin),
        json={"reason": "Inspection"},
    )
    assert block.status_code == 200
    overview = admin.get("/api/v1/admin/overview").json()
    assert overview["active_count"] == 1
    assert overview["blocked_count"] == 1
    assert overview["outstanding_custody_count"] == 1
    assert overview["available_count"] == 1


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


def test_duplicate_elevator_registration_returns_conflict_and_recovers(clients):
    admin, _, _ = clients
    response = admin.post(
        "/api/v1/admin/elevators",
        headers=csrf(admin),
        json={"name": "Duplicate lift", "registration_number": "lift-001"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Registration number already exists."

    inventory = admin.get("/api/v1/admin/elevators")
    assert inventory.status_code == 200
    assert len(inventory.json()) == 1


def _elevator_id(client):
    return client.get("/api/v1/admin/elevators").json()[0]["id"]
