import csv
import secrets
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from typing import Annotated

import qrcode
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from toolplanner.config import settings
from toolplanner.db import SessionLocal, build_engine
from toolplanner.models import (
    AuditEvent,
    Department,
    Elevator,
    Loan,
    Location,
    Reservation,
    ReservationPolicy,
    UserAccount,
    UserNotification,
    UserSession,
)
from toolplanner.schemas import (
    BlockRequest,
    ChangePasswordRequest,
    CheckoutRequest,
    DepartmentCreate,
    DepartmentUpdate,
    ElevatorCreate,
    ElevatorUpdate,
    LocationCreate,
    LocationUpdate,
    LoginRequest,
    PasswordReset,
    ReservationCreate,
    ReservationPolicyUpdate,
    ReturnRequest,
    UserCreate,
    UserUpdate,
)
from toolplanner.security import (
    hash_password,
    new_qr_token,
    new_session_values,
    token_hash,
    verify_password,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def audit(
    db: Session,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    reason: str | None = None,
    details: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            details=details,
        )
    )


def require_department(db: Session, department_id: str | None) -> Department:
    department = db.get(Department, department_id) if department_id else None
    if not department or not department.is_active:
        raise HTTPException(status_code=422, detail="Choose an active department.")
    return department


def get_db(request: Request):
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_current_account(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> UserAccount:
    token = request.cookies.get("toolplanner_session")
    if not token:
        raise HTTPException(status_code=401, detail="Sign in is required.")
    now = utc_now()
    session_row = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_hash(token),
            UserSession.revoked_at.is_(None),
        )
    )
    if not session_row or as_utc(session_row.expires_at) <= now:
        raise HTTPException(status_code=401, detail="Sign in is required.")
    account = db.get(UserAccount, session_row.user_id)
    if not account or not account.is_active:
        raise HTTPException(status_code=401, detail="Sign in is required.")
    request.state.session_row = session_row
    return account


def require_csrf(
    request: Request,
    _: Annotated[UserAccount, Depends(get_current_account)],
) -> None:
    cookie = request.cookies.get("toolplanner_csrf")
    header = request.headers.get("x-csrf-token")
    session_row = getattr(request.state, "session_row", None)
    if (
        not cookie
        or not header
        or not session_row
        or not secrets.compare_digest(cookie, header)
        or not secrets.compare_digest(cookie, session_row.csrf_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")


def require_full_access(
    account: Annotated[UserAccount, Depends(get_current_account)],
) -> UserAccount:
    if account.must_change_password:
        raise HTTPException(status_code=403, detail="Change your password to continue.")
    return account


def require_admin(
    account: Annotated[UserAccount, Depends(require_full_access)],
) -> UserAccount:
    if account.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return account


def create_app(
    database_url: str | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    app = FastAPI(title="Tool Planner API", version="0.1.0")
    app.state.session_factory = session_factory or (
        sessionmaker(bind=build_engine(database_url), autoflush=False, expire_on_commit=False)
        if database_url
        else SessionLocal
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.get("/health/live")
    def liveness():
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness(db: Annotated[Session, Depends(get_db)]):
        db.execute(text("SELECT 1"))
        return {"status": "ready"}

    @app.post("/api/v1/auth/login")
    def login(payload: LoginRequest, response: Response, db: Annotated[Session, Depends(get_db)]):
        username = payload.username.strip().lower()
        account = db.scalar(select(UserAccount).where(UserAccount.username == username))
        if (
            not account
            or not account.is_active
            or not verify_password(account.password_hash, payload.password)
        ):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        token, csrf_token, expires_at = new_session_values()
        hashed_token = token_hash(token)
        db.add(
            UserSession(
                user_id=account.id,
                token_hash=hashed_token,
                csrf_token=csrf_token,
                expires_at=expires_at,
            )
        )
        account.last_login_at = utc_now()
        db.commit()
        response.set_cookie(
            "toolplanner_session",
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.session_ttl_hours * 3600,
            path="/",
        )
        response.set_cookie(
            "toolplanner_csrf",
            csrf_token,
            httponly=False,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.session_ttl_hours * 3600,
            path="/",
        )
        return {
            "user": {
                "id": account.id,
                "username": account.username,
                "display_name": account.display_name,
                "role": account.role,
                "must_change_password": account.must_change_password,
            }
        }

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(
        request: Request,
        response: Response,
        account: Annotated[UserAccount, Depends(get_current_account)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        session_row = request.state.session_row
        session_row.revoked_at = utc_now()
        db.commit()
        response.delete_cookie("toolplanner_session", path="/")
        response.delete_cookie("toolplanner_csrf", path="/")
        response.status_code = 204
        return response

    @app.get("/api/v1/me")
    def me(account: Annotated[UserAccount, Depends(get_current_account)]):
        return {
            "id": account.id,
            "username": account.username,
            "display_name": account.display_name,
            "department_id": account.department_id,
            "role": account.role,
            "must_change_password": account.must_change_password,
        }

    @app.post("/api/v1/auth/change-password")
    def change_password(
        payload: ChangePasswordRequest,
        request: Request,
        account: Annotated[UserAccount, Depends(get_current_account)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        if not verify_password(account.password_hash, payload.current_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        account.password_hash = hash_password(payload.new_password)
        account.must_change_password = False
        now = utc_now()
        for session_row in db.scalars(
            select(UserSession).where(
                UserSession.user_id == account.id,
                UserSession.revoked_at.is_(None),
            )
        ):
            if session_row.id != request.state.session_row.id:
                session_row.revoked_at = now
        audit(db, account.id, "password_changed", "user_account", account.id)
        db.commit()
        return {"status": "password_changed"}

    @app.get("/api/v1/qr/{qr_token}")
    def qr_status(qr_token: str, db: Annotated[Session, Depends(get_db)]):
        elevator = db.scalar(select(Elevator).where(Elevator.qr_token == qr_token))
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        now = utc_now()
        custody = db.scalar(
            select(Loan).where(Loan.elevator_id == elevator.id, Loan.returned_at.is_(None))
        )
        reservation = db.scalar(
            select(Reservation).where(
                Reservation.elevator_id == elevator.id,
                Reservation.status == "confirmed",
                Reservation.starts_at <= now,
                Reservation.ends_at > now,
            )
        )
        if custody:
            availability = "checked_out"
        elif elevator.status != "active":
            availability = elevator.status
        elif reservation:
            availability = "reserved"
        else:
            availability = "available"
        return {
            "name": elevator.name,
            "registration_number": elevator.registration_number,
            "status": availability,
            "elevator_status": elevator.status,
            "can_return": custody is not None,
            "can_borrow": elevator.status == "active" and custody is None and reservation is None,
        }

    @app.get("/api/v1/locations")
    def public_locations(db: Annotated[Session, Depends(get_db)]):
        return [
            {"id": row.id, "name": row.name, "is_default": row.is_default}
            for row in db.scalars(
                select(Location)
                .where(Location.is_active.is_(True))
                .order_by(Location.name)
            ).all()
        ]

    @app.get("/api/v1/departments")
    def public_departments(db: Annotated[Session, Depends(get_db)]):
        return [
            {"id": row.id, "name": row.name}
            for row in db.scalars(
                select(Department)
                .where(Department.is_active.is_(True))
                .order_by(Department.name)
            ).all()
        ]

    @app.post("/api/v1/qr/{qr_token}/checkout", status_code=201)
    def checkout(
        qr_token: str,
        payload: CheckoutRequest,
        account: Annotated[UserAccount, Depends(require_full_access)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.scalar(
            select(Elevator)
            .where(Elevator.qr_token == qr_token)
            .with_for_update()
        )
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        if elevator.status != "active":
            raise HTTPException(status_code=409, detail="This elevator is not available.")
        existing = db.scalar(
            select(Loan).where(Loan.elevator_id == elevator.id, Loan.returned_at.is_(None))
        )
        if existing:
            raise HTTPException(status_code=409, detail="This elevator is already in custody.")
        now = utc_now()
        live_reservation = db.scalar(
            select(Reservation).where(
                Reservation.elevator_id == elevator.id,
                Reservation.status == "confirmed",
                Reservation.starts_at <= now,
                Reservation.ends_at > now,
            )
        )
        reservation = None
        if payload.reservation_id:
            reservation = db.get(Reservation, payload.reservation_id)
            if (
                not reservation
                or reservation.elevator_id != elevator.id
                or reservation.requester_user_id != account.id
                or reservation.status != "confirmed"
                or not (as_utc(reservation.starts_at) <= now)
            ):
                raise HTTPException(status_code=409, detail="Reservation cannot be picked up.")
            if as_utc(reservation.ends_at) <= now:
                raise HTTPException(status_code=409, detail="Reservation window has ended.")
            live_reservation = None
        if live_reservation:
            raise HTTPException(status_code=409, detail="This elevator is reserved.")
        department_id = payload.department_id or account.department_id
        department = require_department(db, department_id)
        if payload.checkout_location_id and not db.get(Location, payload.checkout_location_id):
            raise HTTPException(status_code=422, detail="Choose a valid pickup location.")
        loan = Loan(
            elevator_id=elevator.id,
            checkout_actor_user_id=account.id,
            borrower_name=payload.borrower_name.strip(),
            department_snapshot=department.name,
            checkout_location_id=payload.checkout_location_id,
            destination=payload.destination.strip(),
            checked_out_at=now,
            status="active",
        )
        db.add(loan)
        db.flush()
        if reservation:
            reservation.status = "picked_up"
            reservation.loan_id = loan.id
        audit(db, account.id, "loan_checked_out", "loan", loan.id)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="This elevator is already in custody."
            ) from exc
        return {"id": loan.id, "status": loan.status, "checked_out_at": now}

    @app.post("/api/v1/qr/{qr_token}/return")
    def return_elevator(
        qr_token: str,
        payload: ReturnRequest,
        account: Annotated[UserAccount, Depends(require_full_access)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.scalar(
            select(Elevator).where(Elevator.qr_token == qr_token).with_for_update()
        )
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        loan = db.scalar(
            select(Loan)
            .where(Loan.elevator_id == elevator.id, Loan.returned_at.is_(None))
            .with_for_update()
        )
        if not loan:
            raise HTTPException(status_code=409, detail="There is no outstanding loan to return.")
        return_location_id = payload.return_location_id
        if return_location_id:
            return_location = db.get(Location, return_location_id)
            if not return_location or not return_location.is_active:
                raise HTTPException(status_code=422, detail="Choose an active return location.")
        else:
            return_location = db.scalar(
                select(Location).where(Location.is_default.is_(True), Location.is_active.is_(True))
            )
            if not return_location:
                raise HTTPException(status_code=409, detail="No default return location is configured.")
            return_location_id = return_location.id
        now = utc_now()
        loan.status = "returned"
        loan.returned_at = now
        loan.return_actor_user_id = account.id
        loan.return_location_id = return_location_id
        elevator.last_known_location_id = return_location_id
        audit(db, account.id, "loan_returned", "loan", loan.id)
        db.commit()
        return {"id": loan.id, "status": loan.status, "returned_at": now}

    @app.post("/api/v1/qr/{qr_token}/reservations", status_code=201)
    def create_reservation(
        qr_token: str,
        payload: ReservationCreate,
        account: Annotated[UserAccount, Depends(require_full_access)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.scalar(
            select(Elevator).where(Elevator.qr_token == qr_token).with_for_update()
        )
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        if elevator.status != "active":
            raise HTTPException(status_code=409, detail="This elevator cannot be reserved.")
        now = utc_now()
        starts_at, ends_at = as_utc(payload.starts_at), as_utc(payload.ends_at)
        policy = db.get(ReservationPolicy, 1)
        if not policy:
            policy = ReservationPolicy(id=1)
            db.add(policy)
            db.flush()
        duration = (ends_at - starts_at).total_seconds()
        if starts_at < now + timedelta(seconds=policy.minimum_notice_seconds):
            raise HTTPException(status_code=422, detail="Reservation does not meet minimum notice.")
        if duration > policy.maximum_duration_seconds:
            raise HTTPException(status_code=422, detail="Reservation exceeds maximum duration.")
        if starts_at >= ends_at:
            raise HTTPException(status_code=422, detail="Reservation end must follow its start.")
        collision = db.scalar(
            select(Reservation.id).where(
                Reservation.elevator_id == elevator.id,
                Reservation.status == "confirmed",
                Reservation.starts_at < ends_at,
                Reservation.ends_at > starts_at,
            )
        )
        if collision:
            raise HTTPException(status_code=409, detail="This time window is already reserved.")
        reservation = Reservation(
            elevator_id=elevator.id,
            requester_user_id=account.id,
            borrower_name=payload.borrower_name.strip(),
            starts_at=starts_at,
            ends_at=ends_at,
            status="confirmed",
            policy_version=policy.version,
        )
        db.add(reservation)
        db.flush()
        audit(db, account.id, "reservation_created", "reservation", reservation.id)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="This time window is already reserved.") from exc
        return {
            "id": reservation.id,
            "status": reservation.status,
            "starts_at": starts_at,
            "ends_at": ends_at,
        }

    @app.get("/api/v1/me/reservations")
    def my_reservations(
        account: Annotated[UserAccount, Depends(require_full_access)],
        db: Annotated[Session, Depends(get_db)],
    ):
        rows = db.execute(
            select(Reservation, Elevator)
            .join(Elevator, Elevator.id == Reservation.elevator_id)
            .where(Reservation.requester_user_id == account.id)
            .order_by(Reservation.starts_at.desc())
            .limit(100)
        ).all()
        return [
            {
                "id": reservation.id,
                "elevator_id": reservation.elevator_id,
                "elevator_name": elevator.name,
                "registration_number": elevator.registration_number,
                "qr_token": elevator.qr_token,
                "starts_at": reservation.starts_at,
                "ends_at": reservation.ends_at,
                "status": reservation.status,
            }
            for reservation, elevator in rows
        ]

    @app.post("/api/v1/reservations/{reservation_id}/cancel")
    def cancel_reservation(
        reservation_id: str,
        account: Annotated[UserAccount, Depends(require_full_access)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        reservation = db.scalar(
            select(Reservation).where(Reservation.id == reservation_id).with_for_update()
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found.")
        if reservation.status != "confirmed":
            raise HTTPException(status_code=409, detail="Reservation is no longer active.")
        if reservation.requester_user_id != account.id and account.role != "admin":
            raise HTTPException(status_code=403, detail="You cannot cancel this reservation.")
        policy = db.get(ReservationPolicy, 1)
        if account.role != "admin" and (
            as_utc(reservation.starts_at) - utc_now()
        ).total_seconds() <= policy.cancellation_cutoff_seconds:
            raise HTTPException(status_code=409, detail="The cancellation cutoff has passed.")
        reservation.status = "cancelled"
        reservation.cancelled_at = utc_now()
        audit(db, account.id, "reservation_cancelled", "reservation", reservation.id)
        db.commit()
        return {"id": reservation.id, "status": reservation.status}

    @app.get("/api/v1/me/notifications")
    def my_notifications(
        account: Annotated[UserAccount, Depends(require_full_access)],
        db: Annotated[Session, Depends(get_db)],
    ):
        now = utc_now()
        affected = db.execute(
            select(Reservation, Elevator)
            .join(Elevator, Elevator.id == Reservation.elevator_id)
            .where(
                Reservation.requester_user_id == account.id,
                Reservation.status == "confirmed",
                Reservation.starts_at <= now,
                or_(
                    Elevator.status != "active",
                    select(Loan.id)
                    .where(Loan.elevator_id == Elevator.id, Loan.returned_at.is_(None))
                    .exists(),
                ),
            )
        ).all()
        for reservation, elevator in affected:
            key = f"late:{reservation.id}"
            exists = db.scalar(
                select(UserNotification.id).where(
                    UserNotification.deduplication_key == key
                )
            )
            if not exists:
                db.add(
                    UserNotification(
                        recipient_user_id=account.id,
                        reservation_id=reservation.id,
                        deduplication_key=key,
                        message=f"{elevator.name} is not available for your reservation.",
                    )
                )
        db.commit()
        notifications = db.scalars(
            select(UserNotification)
            .where(UserNotification.recipient_user_id == account.id)
            .order_by(UserNotification.created_at.desc())
            .limit(100)
        ).all()
        result = []
        for item in notifications:
            reservation = db.get(Reservation, item.reservation_id) if item.reservation_id else None
            alternatives = []
            if reservation:
                rows = db.execute(
                    select(Elevator)
                    .where(Elevator.status == "active", Elevator.id != reservation.elevator_id)
                    .limit(20)
                ).scalars()
                for candidate in rows:
                    custody = db.scalar(
                        select(Loan.id).where(
                            Loan.elevator_id == candidate.id, Loan.returned_at.is_(None)
                        )
                    )
                    overlap = db.scalar(
                        select(Reservation.id).where(
                            Reservation.elevator_id == candidate.id,
                            Reservation.status == "confirmed",
                            Reservation.starts_at < reservation.ends_at,
                            Reservation.ends_at > reservation.starts_at,
                        )
                    )
                    if not custody and not overlap:
                        alternatives.append(
                            {
                                "id": candidate.id,
                                "name": candidate.name,
                                "registration_number": candidate.registration_number,
                            }
                        )
            result.append(
                {
                    "id": item.id,
                    "message": item.message,
                    "created_at": item.created_at,
                    "read": item.read_at is not None,
                    "alternatives": alternatives,
                }
            )
        return result

    @app.post("/api/v1/me/notifications/{notification_id}/read", status_code=204)
    def mark_notification_read(
        notification_id: str,
        account: Annotated[UserAccount, Depends(require_full_access)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        notification = db.get(UserNotification, notification_id)
        if not notification or notification.recipient_user_id != account.id:
            raise HTTPException(status_code=404, detail="Notification not found.")
        if notification.read_at is None:
            notification.read_at = utc_now()
            db.commit()
        return Response(status_code=204)

    @app.get("/api/v1/admin/users")
    def list_users(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        users = db.scalars(select(UserAccount).order_by(UserAccount.username)).all()
        return [
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "department_id": user.department_id,
                "role": user.role,
                "is_active": user.is_active,
                "must_change_password": user.must_change_password,
            }
            for user in users
        ]

    @app.post("/api/v1/admin/users", status_code=201)
    def create_user(
        payload: UserCreate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        username = payload.username.strip().lower()
        if payload.department_id:
            department = db.get(Department, payload.department_id)
            if not department or not department.is_active:
                raise HTTPException(status_code=422, detail="Active department not found.")
        account = UserAccount(
            username=username,
            password_hash=hash_password(payload.initial_password),
            role=payload.role,
            display_name=payload.display_name.strip(),
            department_id=payload.department_id,
            must_change_password=True,
        )
        db.add(account)
        db.flush()
        audit(db, admin.id, "user_created", "user_account", account.id)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Username already exists.") from exc
        return {"id": account.id, "username": account.username, "must_change_password": True}

    @app.patch("/api/v1/admin/users/{user_id}")
    def update_user(
        user_id: str,
        payload: UserUpdate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        account = db.get(UserAccount, user_id)
        if not account:
            raise HTTPException(status_code=404, detail="User not found.")
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=422, detail="Provide at least one field to update.")
        if changes.get("department_id"):
            department = db.get(Department, changes["department_id"])
            if not department or not department.is_active:
                raise HTTPException(status_code=422, detail="Active department not found.")
        becomes_non_admin = account.role == "admin" and account.is_active and (
            changes.get("role") == "user" or changes.get("is_active") is False
        )
        if becomes_non_admin:
            active_admins = db.scalar(
                select(func.count()).select_from(UserAccount).where(
                    UserAccount.role == "admin", UserAccount.is_active.is_(True)
                )
            )
            if int(active_admins or 0) <= 2:
                raise HTTPException(
                    status_code=409,
                    detail="At least two active administrator accounts are required.",
                )
        for field, value in changes.items():
            setattr(account, field, value)
        if changes.get("is_active") is False:
            account.disabled_at = utc_now()
            for session_row in db.scalars(
                select(UserSession).where(
                    UserSession.user_id == account.id,
                    UserSession.revoked_at.is_(None),
                )
            ):
                session_row.revoked_at = utc_now()
        elif changes.get("is_active") is True:
            account.disabled_at = None
        audit(db, admin.id, "user_updated", "user_account", account.id)
        db.commit()
        return {
            "id": account.id,
            "username": account.username,
            "role": account.role,
            "is_active": account.is_active,
        }

    @app.post("/api/v1/admin/users/{user_id}/reset-password", status_code=204)
    def reset_password(
        user_id: str,
        payload: PasswordReset,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        account = db.get(UserAccount, user_id)
        if not account:
            raise HTTPException(status_code=404, detail="User not found.")
        account.password_hash = hash_password(payload.initial_password)
        account.must_change_password = True
        now = utc_now()
        for session_row in db.scalars(
            select(UserSession).where(
                UserSession.user_id == account.id,
                UserSession.revoked_at.is_(None),
            )
        ):
            session_row.revoked_at = now
        audit(db, admin.id, "password_reset", "user_account", account.id)
        db.commit()
        return Response(status_code=204)

    @app.get("/api/v1/admin/elevators")
    def list_elevators(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevators = db.scalars(
            select(Elevator).order_by(Elevator.registration_number)
        ).all()
        result = []
        for elevator in elevators:
            loan = db.scalar(
                select(Loan).where(
                    Loan.elevator_id == elevator.id, Loan.returned_at.is_(None)
                )
            )
            result.append(
                {
                    "id": elevator.id,
                    "name": elevator.name,
                    "registration_number": elevator.registration_number,
                    "status": elevator.status,
                    "qr_url": f"{settings.public_base_url}/qr/{elevator.qr_token}",
                    "outstanding_borrower": loan.borrower_name if loan else None,
                }
            )
        return result

    @app.post("/api/v1/admin/elevators", status_code=201)
    def create_elevator(
        payload: ElevatorCreate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        if payload.location_id and not db.get(Location, payload.location_id):
            raise HTTPException(status_code=422, detail="Location not found.")
        elevator = Elevator(
            registration_number=payload.registration_number.strip().upper(),
            name=payload.name.strip(),
            status="active",
            qr_token=new_qr_token(),
            last_known_location_id=payload.location_id,
        )
        db.add(elevator)
        try:
            db.flush()
            audit(db, admin.id, "elevator_created", "elevator", elevator.id)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="Registration number already exists."
            ) from exc
        return {
            "id": elevator.id,
            "name": elevator.name,
            "registration_number": elevator.registration_number,
            "qr_url": f"{settings.public_base_url}/qr/{elevator.qr_token}",
        }

    @app.patch("/api/v1/admin/elevators/{elevator_id}")
    def update_elevator(
        elevator_id: str,
        payload: ElevatorUpdate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.get(Elevator, elevator_id)
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=422, detail="Provide at least one field to update.")
        if "location_id" in changes:
            location_id = changes["location_id"]
            location = db.get(Location, location_id) if location_id else None
            if location_id and (not location or not location.is_active):
                raise HTTPException(status_code=422, detail="Active location not found.")
            elevator.last_known_location_id = location_id
        if "name" in changes and changes["name"] is not None:
            elevator.name = changes["name"].strip()
        audit(db, admin.id, "elevator_updated", "elevator", elevator.id)
        db.commit()
        return {
            "id": elevator.id,
            "name": elevator.name,
            "registration_number": elevator.registration_number,
            "status": elevator.status,
        }

    @app.post("/api/v1/admin/elevators/{elevator_id}/rotate-qr")
    def rotate_elevator_qr(
        elevator_id: str,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.get(Elevator, elevator_id)
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        elevator.qr_token = new_qr_token()
        audit(db, admin.id, "elevator_qr_rotated", "elevator", elevator.id)
        db.commit()
        return {
            "id": elevator.id,
            "qr_url": f"{settings.public_base_url}/qr/{elevator.qr_token}",
        }

    @app.get("/api/v1/admin/elevators/{elevator_id}/qr-code")
    def elevator_qr_code(
        elevator_id: str,
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.get(Elevator, elevator_id)
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        image = qrcode.make(f"{settings.public_base_url}/qr/{elevator.qr_token}")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="image/png")

    @app.post("/api/v1/admin/elevators/{elevator_id}/block")
    def block_elevator(
        elevator_id: str,
        payload: BlockRequest,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.scalar(
            select(Elevator).where(Elevator.id == elevator_id).with_for_update()
        )
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        if elevator.status == "blocked":
            raise HTTPException(status_code=409, detail="Elevator is already blocked.")
        elevator.status = "blocked"
        elevator.block_reason = payload.reason.strip()
        now = utc_now()
        active_loan = db.scalar(
            select(Loan).where(
                Loan.elevator_id == elevator.id,
                Loan.status == "active",
                Loan.returned_at.is_(None),
            )
        )
        if active_loan:
            active_loan.status = "cancelled"
            active_loan.cancelled_by_user_id = admin.id
            active_loan.cancelled_at = now
            active_loan.cancellation_reason = payload.reason.strip()
            audit(
                db,
                admin.id,
                "loan_cancelled_by_block",
                "loan",
                active_loan.id,
                payload.reason.strip(),
            )
        reservations = db.scalars(
            select(Reservation).where(
                Reservation.elevator_id == elevator.id,
                Reservation.status == "confirmed",
                Reservation.ends_at > now,
            )
        ).all()
        for reservation in reservations:
            db.add(
                UserNotification(
                    recipient_user_id=reservation.requester_user_id,
                    reservation_id=reservation.id,
                    deduplication_key=f"blocked:{elevator.id}:{reservation.id}",
                    message=f"{elevator.name} is blocked and unavailable for your reservation.",
                )
            )
        audit(db, admin.id, "elevator_blocked", "elevator", elevator.id, payload.reason)
        db.commit()
        return {"id": elevator.id, "status": elevator.status}

    @app.post("/api/v1/admin/elevators/{elevator_id}/retire")
    def retire_elevator(
        elevator_id: str,
        payload: BlockRequest,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.scalar(
            select(Elevator).where(Elevator.id == elevator_id).with_for_update()
        )
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        if db.scalar(
            select(Loan.id).where(
                Loan.elevator_id == elevator.id, Loan.returned_at.is_(None)
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="Return the outstanding elevator before retiring it.",
            )
        elevator.status = "retired"
        elevator.block_reason = payload.reason.strip()
        audit(db, admin.id, "elevator_retired", "elevator", elevator.id, payload.reason)
        db.commit()
        return {"id": elevator.id, "status": elevator.status}

    @app.post("/api/v1/admin/elevators/{elevator_id}/unblock")
    def unblock_elevator(
        elevator_id: str,
        payload: BlockRequest,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        elevator = db.get(Elevator, elevator_id)
        if not elevator:
            raise HTTPException(status_code=404, detail="Elevator not found.")
        if elevator.status != "blocked":
            raise HTTPException(status_code=409, detail="Elevator is not blocked.")
        elevator.status = "active"
        elevator.block_reason = None
        audit(db, admin.id, "elevator_unblocked", "elevator", elevator.id, payload.reason.strip())
        db.commit()
        return {"id": elevator.id, "status": elevator.status}

    @app.get("/api/v1/admin/locations")
    def list_locations(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        rows = db.execute(
            select(Location, func.count(Elevator.id))
            .outerjoin(
                Elevator,
                (Elevator.last_known_location_id == Location.id)
                & (Elevator.status != "retired"),
            )
            .group_by(Location.id)
            .order_by(Location.name)
        ).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "details": row.details,
                "is_active": row.is_active,
                "is_default": row.is_default,
                "elevator_count": int(elevator_count),
            }
            for row, elevator_count in rows
        ]

    @app.post("/api/v1/admin/locations", status_code=201)
    def create_location(
        payload: LocationCreate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        if payload.is_default:
            db.query(Location).filter(Location.is_default.is_(True)).update(
                {"is_default": False}
            )
        location = Location(
            name=payload.name.strip(),
            details=payload.details,
            is_active=True,
            is_default=payload.is_default,
        )
        db.add(location)
        db.flush()
        audit(db, admin.id, "location_created", "location", location.id)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Location already exists.") from exc
        return {"id": location.id, "name": location.name, "is_default": location.is_default}

    @app.patch("/api/v1/admin/locations/{location_id}")
    def update_location(
        location_id: str,
        payload: LocationUpdate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        location = db.get(Location, location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Location not found.")
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=422, detail="Provide at least one field to update.")
        if "name" in changes:
            name = changes["name"].strip()
            if not name:
                raise HTTPException(status_code=422, detail="Location name cannot be empty.")
            location.name = name
        if "details" in changes:
            location.details = changes["details"].strip() if changes["details"] else None
        audit(db, admin.id, "location_updated", "location", location.id)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Location name already exists.") from exc
        return {
            "id": location.id,
            "name": location.name,
            "details": location.details,
            "is_active": location.is_active,
            "is_default": location.is_default,
        }

    @app.delete("/api/v1/admin/locations/{location_id}")
    def archive_location(
        location_id: str,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        location = db.get(Location, location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Location not found.")
        if not location.is_active:
            raise HTTPException(status_code=409, detail="Location is already archived.")
        if location.is_default:
            raise HTTPException(
                status_code=409,
                detail="Choose another default location before deleting this one.",
            )
        assigned_elevator = db.scalar(
            select(Elevator.id).where(
                Elevator.last_known_location_id == location.id,
                Elevator.status != "retired",
            )
        )
        if assigned_elevator:
            raise HTTPException(
                status_code=409,
                detail="Move non-retired elevators to another location before deleting this one.",
            )
        location.is_active = False
        audit(db, admin.id, "location_archived", "location", location.id)
        db.commit()
        return {"id": location.id, "is_active": False, "preserved_for_history": True}

    @app.post("/api/v1/admin/locations/{location_id}/restore")
    def restore_location(
        location_id: str,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        location = db.get(Location, location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Location not found.")
        if location.is_active:
            raise HTTPException(status_code=409, detail="Location is already active.")
        location.is_active = True
        audit(db, admin.id, "location_restored", "location", location.id)
        db.commit()
        return {"id": location.id, "is_active": True}

    @app.post("/api/v1/admin/locations/{location_id}/set-default")
    def set_default_location(
        location_id: str,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        location = db.get(Location, location_id)
        if not location or not location.is_active:
            raise HTTPException(status_code=404, detail="Active location not found.")
        db.query(Location).filter(Location.is_default.is_(True)).update({"is_default": False})
        location.is_default = True
        audit(db, admin.id, "default_location_changed", "location", location.id)
        db.commit()
        return {"id": location.id, "is_default": True}

    @app.get("/api/v1/admin/departments")
    def list_departments(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        rows = db.execute(
            select(Department, func.count(UserAccount.id))
            .outerjoin(
                UserAccount,
                (UserAccount.department_id == Department.id)
                & UserAccount.is_active.is_(True),
            )
            .group_by(Department.id)
            .order_by(Department.name)
        ).all()
        return [
            {
                "id": department.id,
                "name": department.name,
                "is_active": department.is_active,
                "active_user_count": int(active_user_count),
            }
            for department, active_user_count in rows
        ]

    @app.post("/api/v1/admin/departments", status_code=201)
    def create_department(
        payload: DepartmentCreate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        department = Department(name=payload.name.strip(), is_active=True)
        db.add(department)
        db.flush()
        audit(db, admin.id, "department_created", "department", department.id)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Department already exists.") from exc
        return {"id": department.id, "name": department.name}

    @app.patch("/api/v1/admin/departments/{department_id}")
    def update_department(
        department_id: str,
        payload: DepartmentUpdate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        department = db.get(Department, department_id)
        if not department:
            raise HTTPException(status_code=404, detail="Department not found.")
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=422, detail="Provide a department name.")
        name = changes["name"].strip() if changes["name"] else ""
        if not name:
            raise HTTPException(status_code=422, detail="Department name cannot be empty.")
        department.name = name
        audit(db, admin.id, "department_updated", "department", department.id)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Department name already exists.") from exc
        return {"id": department.id, "name": department.name, "is_active": department.is_active}

    @app.delete("/api/v1/admin/departments/{department_id}")
    def archive_department(
        department_id: str,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        department = db.get(Department, department_id)
        if not department:
            raise HTTPException(status_code=404, detail="Department not found.")
        if not department.is_active:
            raise HTTPException(status_code=409, detail="Department is already archived.")
        active_user = db.scalar(
            select(UserAccount.id).where(
                UserAccount.department_id == department.id,
                UserAccount.is_active.is_(True),
            )
        )
        if active_user:
            raise HTTPException(
                status_code=409,
                detail="Reassign active user accounts before deleting this department.",
            )
        department.is_active = False
        audit(db, admin.id, "department_archived", "department", department.id)
        db.commit()
        return {"id": department.id, "is_active": False, "preserved_for_history": True}

    @app.post("/api/v1/admin/departments/{department_id}/restore")
    def restore_department(
        department_id: str,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        department = db.get(Department, department_id)
        if not department:
            raise HTTPException(status_code=404, detail="Department not found.")
        if department.is_active:
            raise HTTPException(status_code=409, detail="Department is already active.")
        department.is_active = True
        audit(db, admin.id, "department_restored", "department", department.id)
        db.commit()
        return {"id": department.id, "is_active": True}

    @app.get("/api/v1/admin/reservation-settings")
    def get_reservation_settings(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        policy = db.get(ReservationPolicy, 1)
        if not policy:
            policy = ReservationPolicy(id=1)
            db.add(policy)
            db.commit()
            db.refresh(policy)
        return {
            "minimum_notice_seconds": policy.minimum_notice_seconds,
            "maximum_duration_seconds": policy.maximum_duration_seconds,
            "cancellation_cutoff_seconds": policy.cancellation_cutoff_seconds,
            "no_show_grace_seconds": policy.no_show_grace_seconds,
            "version": policy.version,
        }

    @app.patch("/api/v1/admin/reservation-settings")
    def update_reservation_settings(
        payload: ReservationPolicyUpdate,
        admin: Annotated[UserAccount, Depends(require_admin)],
        _: Annotated[None, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db)],
    ):
        policy = db.get(ReservationPolicy, 1)
        if not policy:
            policy = ReservationPolicy(id=1)
            db.add(policy)
        for field, value in payload.model_dump().items():
            setattr(policy, field, value)
        policy.version += 1
        audit(db, admin.id, "reservation_policy_updated", "reservation_policy", "1")
        db.commit()
        return {"version": policy.version, **payload.model_dump()}

    @app.get("/api/v1/admin/loans")
    def list_loans(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        rows = db.execute(
            select(Loan, Elevator.registration_number, Location.name)
            .join(Elevator, Elevator.id == Loan.elevator_id)
            .outerjoin(Location, Location.id == Loan.checkout_location_id)
            .order_by(Loan.checked_out_at.desc())
            .limit(200)
        ).all()
        return [
            {
                "id": loan.id,
                "elevator_id": loan.elevator_id,
                "registration_number": registration_number,
                "borrower_name": loan.borrower_name,
                "department": loan.department_snapshot,
                "checkout_location": location_name,
                "destination": loan.destination,
                "checked_out_at": loan.checked_out_at,
                "returned_at": loan.returned_at,
                "status": loan.status,
            }
            for loan, registration_number, location_name in rows
        ]

    @app.get("/api/v1/admin/overview")
    def admin_overview(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        active_elevators = db.scalar(
            select(func.count()).select_from(Elevator).where(Elevator.status == "active")
        )
        available_elevators = db.scalar(
            select(func.count())
            .select_from(Elevator)
            .where(
                Elevator.status == "active",
                ~select(Loan.id)
                .where(Loan.elevator_id == Elevator.id, Loan.returned_at.is_(None))
                .exists(),
            )
        )
        blocked_elevators = db.scalar(
            select(func.count()).select_from(Elevator).where(Elevator.status == "blocked")
        )
        retired_elevators = db.scalar(
            select(func.count()).select_from(Elevator).where(Elevator.status == "retired")
        )
        outstanding_query = (
            select(Loan.id, Loan.checked_out_at, Loan.status, Elevator.registration_number)
            .join(Elevator, Elevator.id == Loan.elevator_id)
            .where(Loan.returned_at.is_(None))
            .order_by(Loan.checked_out_at.asc())
        )
        outstanding = db.execute(outstanding_query).all()
        now = utc_now()
        at_risk_count = db.scalar(
            select(func.count()).select_from(Reservation).join(
                Elevator, Elevator.id == Reservation.elevator_id
            ).where(
                Reservation.status == "confirmed",
                Reservation.starts_at <= now,
                Reservation.ends_at > now,
                or_(
                    Elevator.status != "active",
                    select(Loan.id)
                    .where(Loan.elevator_id == Elevator.id, Loan.returned_at.is_(None))
                    .exists(),
                ),
            )
        )
        oldest = [
            {
                "registration_number": row.registration_number,
                "loan_age_seconds": max(0, int((now - as_utc(row.checked_out_at)).total_seconds())),
                "status": row.status,
            }
            for row in outstanding[:5]
        ]
        return {
            "available_count": int(available_elevators or 0),
            "active_count": int(active_elevators or 0),
            "outstanding_custody_count": len(outstanding),
            "blocked_count": int(blocked_elevators or 0),
            "retired_count": int(retired_elevators or 0),
            "at_risk_reservation_count": int(at_risk_count or 0),
            "oldest_custody": oldest,
        }

    @app.get("/api/v1/admin/reservations")
    def list_admin_reservations(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        rows = db.execute(
            select(Reservation, Elevator, UserAccount)
            .join(Elevator, Elevator.id == Reservation.elevator_id)
            .join(UserAccount, UserAccount.id == Reservation.requester_user_id)
            .order_by(Reservation.starts_at.desc())
            .limit(200)
        ).all()
        return [
            {
                "id": reservation.id,
                "elevator": elevator.registration_number,
                "requester": requester.display_name,
                "starts_at": reservation.starts_at,
                "ends_at": reservation.ends_at,
                "status": reservation.status,
            }
            for reservation, elevator, requester in rows
        ]

    @app.get("/api/v1/admin/audit")
    def list_audit_events(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        rows = db.execute(
            select(AuditEvent, UserAccount.display_name)
            .outerjoin(UserAccount, UserAccount.id == AuditEvent.actor_user_id)
            .order_by(AuditEvent.occurred_at.desc())
            .limit(200)
        ).all()
        return [
            {
                "id": event.id,
                "actor": actor_name or "System",
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "reason": event.reason,
                "occurred_at": event.occurred_at,
            }
            for event, actor_name in rows
        ]

    @app.get("/api/v1/admin/reports/usage")
    def usage_report(
        _: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        rows = db.execute(
            select(Loan, Elevator.registration_number)
            .join(Elevator, Elevator.id == Loan.elevator_id)
            .order_by(Elevator.registration_number)
            .limit(10000)
        ).all()
        totals: dict[str, dict[str, float | int]] = {}
        for loan, registration_number in rows:
            stats = totals.setdefault(
                registration_number,
                {"checkout_count": 0, "duration_sum": 0.0, "duration_count": 0},
            )
            stats["checkout_count"] += 1
            if loan.returned_at is not None:
                duration = (
                    as_utc(loan.returned_at) - as_utc(loan.checked_out_at)
                ).total_seconds()
                stats["duration_sum"] += duration
                stats["duration_count"] += 1
        return [
            {
                "registration_number": registration_number,
                "checkout_count": int(stats["checkout_count"]),
                "average_duration_seconds": (
                    float(stats["duration_sum"]) / int(stats["duration_count"])
                    if stats["duration_count"]
                    else None
                ),
            }
            for registration_number, stats in sorted(totals.items())
        ]

    @app.get("/api/v1/admin/reports/loans.csv")
    def export_loans(
        admin: Annotated[UserAccount, Depends(require_admin)],
        db: Annotated[Session, Depends(get_db)],
    ):
        rows = db.execute(
            select(Loan, Elevator.registration_number)
            .join(Elevator, Elevator.id == Loan.elevator_id)
            .order_by(Loan.checked_out_at.desc())
            .limit(5000)
        ).all()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "registration_number",
                "borrower_name",
                "department",
                "destination",
                "checked_out_at_utc",
                "returned_at_utc",
                "status",
            ]
        )
        for loan, registration_number in rows:
            safe_borrower = loan.borrower_name
            if safe_borrower.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                safe_borrower = "'" + safe_borrower
            safe_department = loan.department_snapshot
            if safe_department.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                safe_department = "'" + safe_department
            safe_destination = loan.destination
            if safe_destination.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                safe_destination = "'" + safe_destination
            writer.writerow(
                [
                    registration_number,
                    safe_borrower,
                    safe_department,
                    safe_destination,
                    loan.checked_out_at.isoformat(),
                    loan.returned_at.isoformat() if loan.returned_at else "",
                    loan.status,
                ]
            )
        audit(db, admin.id, "loan_report_exported", "report", "loans")
        db.commit()
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="tool-planner-loans.csv"'},
        )

    return app


app = create_app()
