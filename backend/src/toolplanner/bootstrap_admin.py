import argparse
from getpass import getpass

from sqlalchemy import func, select

from toolplanner.db import SessionLocal
from toolplanner.models import Department, UserAccount
from toolplanner.security import hash_password


def bootstrap_admins(count: int) -> None:
    with SessionLocal.begin() as db:
        existing = db.scalar(
            select(func.count()).select_from(UserAccount).where(
                UserAccount.role == "admin", UserAccount.is_active.is_(True)
            )
        )
        department = db.scalar(
            select(Department).where(Department.name == "Sites & Facilities")
        )
        for number in range(count):
            username = input(f"Admin {number + 1} username: ").strip().lower()
            display_name = input(f"Admin {number + 1} display name: ").strip()
            password = getpass(f"Admin {number + 1} initial password (12+ chars): ")
            confirmation = getpass("Confirm initial password: ")
            if len(password) < 12:
                raise SystemExit("Initial password must be at least 12 characters.")
            if password != confirmation:
                raise SystemExit("Passwords did not match.")
            if db.scalar(select(UserAccount.id).where(UserAccount.username == username)):
                raise SystemExit(f"Username {username!r} already exists.")
            db.add(
                UserAccount(
                    username=username,
                    password_hash=hash_password(password),
                    role="admin",
                    display_name=display_name,
                    department_id=department.id if department else None,
                    is_active=True,
                    must_change_password=True,
                )
            )
            print(f"Created administrator {username!r}; password change required at first login.")
        if int(existing or 0) + count < 2:
            raise SystemExit("At least two active admin accounts must exist.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manually create initial Tool Planner admins.")
    parser.add_argument("--count", type=int, default=2, choices=range(1, 11))
    args = parser.parse_args()
    bootstrap_admins(args.count)


if __name__ == "__main__":
    main()
