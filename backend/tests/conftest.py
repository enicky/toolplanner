from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from toolplanner.db import Base
from toolplanner.main import create_app
from toolplanner.models import Department, Elevator, Location, UserAccount
from toolplanner.security import hash_password, new_qr_token


@pytest.fixture
def clients() -> Iterator[tuple[TestClient, TestClient, str]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory.begin() as db:
        department = Department(name="Sites & Facilities", is_active=True)
        location = Location(name="Geel", is_active=True, is_default=True)
        admin = UserAccount(
            username="admin",
            password_hash=hash_password("initial-admin-password"),
            role="admin",
            display_name="Test Admin",
            department=department,
            must_change_password=False,
        )
        user = UserAccount(
            username="user",
            password_hash=hash_password("initial-user-password"),
            role="user",
            display_name="Test User",
            department=department,
            must_change_password=False,
        )
        elevator = Elevator(
            registration_number="LIFT-001",
            name="LIFT-001",
            status="active",
            qr_token=new_qr_token(),
            last_known_location=location,
        )
        db.add_all([department, location, admin, user, elevator])
        db.flush()
        qr_token = elevator.qr_token
    app = create_app(session_factory=factory)
    admin_client = TestClient(app)
    user_client = TestClient(app)
    for client, username, password in (
        (admin_client, "admin", "initial-admin-password"),
        (user_client, "user", "initial-user-password"),
    ):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200
    try:
        yield admin_client, user_client, qr_token
    finally:
        admin_client.close()
        user_client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["toolplanner_csrf"]}
