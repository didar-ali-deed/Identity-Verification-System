"""Maintenance commands without default administrator credentials."""

import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select

from app.database import async_session_factory, engine
from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest
from app.utils.security import hash_password


async def create_admin(email: str, full_name: str, password: str) -> None:
    validated = RegisterRequest(email=email, full_name=full_name, password=password)
    try:
        async with async_session_factory() as db:
            existing = await db.scalar(select(User).where(User.email == str(validated.email).lower()))
            if existing:
                raise ValueError("This account already exists; no credentials or roles were changed")
            db.add(
                User(
                    email=str(validated.email).lower(),
                    full_name=validated.full_name,
                    password_hash=hash_password(validated.password),
                    role=UserRole.ADMIN,
                )
            )
            await db.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create-admin"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrator")
    args = parser.parse_args()
    password = getpass("Administrator password: ")
    if password != getpass("Confirm password: "):
        parser.error("Passwords do not match")
    try:
        asyncio.run(create_admin(args.email, args.name, password))
    except ValueError as exc:
        parser.error(str(exc))
    print("Administrator created. No password was printed or stored in source code.")


if __name__ == "__main__":
    main()
