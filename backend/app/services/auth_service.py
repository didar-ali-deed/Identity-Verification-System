import hmac
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User, UserRole
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

settings = get_settings()
logger = structlog.get_logger()


class AuthServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
) -> User:
    """Register a new user with hashed password."""
    email = email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise AuthServiceError("Email already registered", status_code=409)

    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=UserRole.USER,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    await logger.ainfo("User registered", user_id=str(user.id), email=user.email)
    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> tuple[User, str, str]:
    """Authenticate user and return user + tokens. Raises on invalid credentials."""
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        raise AuthServiceError("Invalid email or password", status_code=401)

    if not user.is_active:
        raise AuthServiceError("Account is deactivated", status_code=403)

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id)

    user.refresh_token_hash = hash_refresh_token(refresh_token)
    await db.flush()

    await logger.ainfo("User logged in", user_id=str(user.id))
    return user, access_token, refresh_token


async def refresh_tokens(
    db: AsyncSession,
    refresh_token: str,
) -> tuple[str, str]:
    """Validate refresh token and issue new token pair."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthServiceError("Invalid refresh token", status_code=401)

    user_id = payload.get("sub")
    if not user_id:
        raise AuthServiceError("Invalid refresh token", status_code=401)

    try:
        parsed_id = uuid.UUID(user_id)
    except ValueError as exc:
        raise AuthServiceError("Invalid refresh token", status_code=401) from exc
    result = await db.execute(select(User).where(User.id == parsed_id).with_for_update())
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthServiceError("User not found or deactivated", status_code=401)

    token_hash = hash_refresh_token(refresh_token)
    if not user.refresh_token_hash or not hmac.compare_digest(user.refresh_token_hash, token_hash):
        user.refresh_token_hash = None
        await db.flush()
        await logger.awarn("Refresh token reuse detected", user_id=str(user.id))
        # Persist revocation before the route converts this into an HTTP error;
        # the request dependency rolls back transactions when exceptions escape.
        await db.commit()
        raise AuthServiceError("Refresh token has been revoked", status_code=401)

    new_access_token = create_access_token(user.id, user.role.value)
    new_refresh_token = create_refresh_token(user.id)

    user.refresh_token_hash = hash_refresh_token(new_refresh_token)
    await db.flush()

    return new_access_token, new_refresh_token


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch a user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
