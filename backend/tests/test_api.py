from datetime import UTC, datetime, timedelta

from conftest import csrf
from sqlalchemy import select

from toolplanner.models import (
    Department,
    Elevator,
    Loan,
    Location,
    Reservation,
    UserAccount,
)
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


def test_admin_reports_dashboard_applies_filters_and_groups_in_brussels_time(clients):
    admin, user, _token = clients
    second_elevator_response = admin.post(
        "/api/v1/admin/elevators",
        headers=csrf(admin),
        json={"name": "Second lift", "registration_number": "LIFT-002"},
    )
    assert second_elevator_response.status_code == 201
    second_elevator_id = second_elevator_response.json()["id"]
    with admin.app.state.session_factory.begin() as db:
        elevator = db.scalar(select(Elevator).where(Elevator.registration_number == "LIFT-001"))
        user_account = db.scalar(select(UserAccount).where(UserAccount.username == "user"))
        research = Department(name="Research")
        annex = Location(name="Annex", is_active=True, is_default=False)
        db.add_all([research, annex])
        db.flush()
        db.add_all(
            [
                Loan(
                    elevator_id=elevator.id,
                    checkout_actor_user_id=user_account.id,
                    borrower_name="Historical Borrower",
                    department_snapshot=research.name,
                    department_id_snapshot=research.id,
                    checkout_location_id=annex.id,
                    checkout_location_snapshot=annex.name,
                    destination="Building 2",
                    checked_out_at=datetime(2026, 3, 29, 22, 30, tzinfo=UTC),
                    returned_at=datetime(2026, 3, 30, 2, 30, tzinfo=UTC),
                    return_location_id=annex.id,
                    return_location_snapshot=annex.name,
                    status="returned",
                ),
                Loan(
                    elevator_id=elevator.id,
                    checkout_actor_user_id=user_account.id,
                    borrower_name="Current Borrower",
                    department_snapshot="Sites & Facilities",
                    department_id_snapshot=user_account.department_id,
                    checkout_location_id=None,
                    checkout_location_snapshot=None,
                    destination="Building 3",
                    checked_out_at=datetime(2026, 3, 30, 22, 30, tzinfo=UTC),
                    status="cancelled",
                    cancelled_at=datetime(2026, 3, 30, 22, 30, tzinfo=UTC),
                    cancellation_reason="Inspection",
                ),
                Loan(
                    elevator_id=second_elevator_id,
                    checkout_actor_user_id=user_account.id,
                    borrower_name="Other Elevator Borrower",
                    department_snapshot=research.name,
                    department_id_snapshot=research.id,
                    checkout_location_id=annex.id,
                    checkout_location_snapshot=annex.name,
                    destination="Building 4",
                    checked_out_at=datetime(2026, 3, 29, 23, 30, tzinfo=UTC),
                    returned_at=datetime(2026, 3, 30, 1, 30, tzinfo=UTC),
                    return_location_id=annex.id,
                    return_location_snapshot=annex.name,
                    status="returned",
                ),
            ]
        )
        annex.name = "Annex renamed"
        db.flush()
        db.add_all(
            [
                Reservation(
                    elevator_id=elevator.id,
                    requester_user_id=user_account.id,
                    borrower_name="Reservation Borrower",
                    starts_at=datetime(2026, 3, 30, 1, tzinfo=UTC),
                    ends_at=datetime(2026, 3, 30, 3, tzinfo=UTC),
                    status="picked_up",
                    policy_version=1,
                ),
                Reservation(
                    elevator_id=elevator.id,
                    requester_user_id=user_account.id,
                    borrower_name="No Show",
                    starts_at=datetime(2026, 3, 30, 4, tzinfo=UTC),
                    ends_at=datetime(2026, 3, 30, 5, tzinfo=UTC),
                    status="expired",
                    policy_version=1,
                ),
                Reservation(
                    elevator_id=elevator.id,
                    requester_user_id=user_account.id,
                    borrower_name="Cancelled",
                    starts_at=datetime(2026, 3, 30, 6, tzinfo=UTC),
                    ends_at=datetime(2026, 3, 30, 7, tzinfo=UTC),
                    status="cancelled",
                    policy_version=1,
                ),
            ]
        )
        department_id = research.id
        location_id = annex.id

    assert user.get("/api/v1/admin/reports/dashboard").status_code == 403
    query = (
        "?start_date=2026-03-30&end_date=2026-03-30"
        f"&department_id={department_id}&location_id={location_id}"
    )
    report_response = admin.get(f"/api/v1/admin/reports/dashboard{query}")
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["summary"]["checkout_count"] == 2
    assert report["summary"]["completed_loan_count"] == 2
    assert report["summary"]["average_returned_duration_seconds"] == 10800
    assert report["trend"] == [{"period": "2026-03-30", "checkout_count": 2}]
    assert report["department_usage"] == [
        {"department_id": department_id, "department": "Research", "checkout_count": 2}
    ]
    assert report["location_usage"] == [
        {"location_id": location_id, "location": "Annex", "checkout_count": 2}
    ]
    assert report["reservation_outcomes"] is None
    assert "do not capture department" in report["reservation_note"]

    elevator_filtered = admin.get(
        f"/api/v1/admin/reports/dashboard{query}&elevator_id={second_elevator_id}"
    ).json()
    assert elevator_filtered["summary"]["checkout_count"] == 1

    unfiltered = admin.get(
        "/api/v1/admin/reports/dashboard?start_date=2026-03-30&end_date=2026-03-30"
    ).json()
    assert unfiltered["current_custody_count"] == 1
    assert sum(item["count"] for item in unfiltered["custody_age_bands"]) == 1
    assert unfiltered["reservation_outcomes"] == {
        "picked_up": 1,
        "no_show": 1,
        "cancelled": 1,
        "upcoming": 0,
        "awaiting_pickup": 0,
        "pickup_rate_percent": 50.0,
        "resolved_count": 2,
    }

    export = admin.get(
        f"/api/v1/admin/reports/loans.csv{query}&elevator_id={second_elevator_id}"
    )
    assert export.status_code == 200
    assert "Other Elevator Borrower" in export.text
    assert "Historical Borrower" not in export.text
    assert "Current Borrower" not in export.text
    assert "checkout_location" in export.text
    assert "return_location" in export.text


def test_admin_reports_validate_date_range_and_keep_all_history_export(clients):
    admin, user, token = clients
    invalid_range = admin.get(
        "/api/v1/admin/reports/dashboard?start_date=2026-04-02&end_date=2026-04-01"
    )
    assert invalid_range.status_code == 422
    too_wide = admin.get(
        "/api/v1/admin/reports/dashboard?start_date=2020-01-01&end_date=2026-01-01"
    )
    assert too_wide.status_code == 422
    unknown_elevator = admin.get(
        "/api/v1/admin/reports/dashboard?elevator_id=not-an-elevator"
    )
    assert unknown_elevator.status_code == 422

    empty = admin.get(
        "/api/v1/admin/reports/dashboard?start_date=2020-01-01&end_date=2020-01-01"
    ).json()
    assert empty["summary"]["checkout_count"] == 0
    assert empty["summary"]["average_returned_duration_seconds"] is None
    assert empty["reservation_outcomes"]["pickup_rate_percent"] is None
    assert empty["trend"] == [{"period": "2020-01-01", "checkout_count": 0}]

    checkout = user.post(
        f"/api/v1/qr/{token}/checkout",
        headers=csrf(user),
        json={"borrower_name": "=1+1", "destination": "+cmd"},
    )
    assert checkout.status_code == 201
    assert user.get("/api/v1/admin/reports/loans-all.csv").status_code == 403
    all_history = admin.get("/api/v1/admin/reports/loans-all.csv")
    assert all_history.status_code == 200
    assert "'=1+1" in all_history.text
    assert "'+cmd" in all_history.text
    assert all_history.headers["content-disposition"].endswith(
        'filename="tool-planner-all-retained-loans.csv"'
    )


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
