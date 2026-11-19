from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class CheckoutRequest(StrictModel):
    borrower_name: str = Field(min_length=1, max_length=160)
    department_id: str | None = None
    destination: str = Field(min_length=1, max_length=240)
    checkout_location_id: str | None = None
    reservation_id: str | None = None


class ReturnRequest(StrictModel):
    return_location_id: str | None = None


class ReservationCreate(StrictModel):
    borrower_name: str = Field(min_length=1, max_length=160)
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Reservation times must include a time zone.")
        return value


class UserUpdate(StrictModel):
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    department_id: str | None = None
    is_active: bool | None = None


class UserCreate(StrictModel):
    username: str = Field(min_length=3, max_length=80)
    initial_password: str = Field(min_length=12, max_length=256)
    role: str = Field(pattern="^(user|admin)$")
    display_name: str = Field(min_length=1, max_length=160)
    department_id: str | None = None


class PasswordReset(StrictModel):
    initial_password: str = Field(min_length=12, max_length=256)


class ElevatorCreate(StrictModel):
    registration_number: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    location_id: str | None = None


class ElevatorUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    location_id: str | None = None


class BlockRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=1000)


class LocationCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    details: str | None = Field(default=None, max_length=240)
    is_default: bool = False


class LocationUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    details: str | None = Field(default=None, max_length=240)


class DepartmentCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class DepartmentUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class ReservationPolicyUpdate(StrictModel):
    minimum_notice_seconds: int = Field(ge=0, le=60 * 60 * 24 * 365)
    maximum_duration_seconds: int = Field(gt=0, le=60 * 60 * 24 * 365)
    cancellation_cutoff_seconds: int = Field(ge=0, le=60 * 60 * 24 * 365)
    no_show_grace_seconds: int = Field(ge=0, le=60 * 60 * 24 * 365)
