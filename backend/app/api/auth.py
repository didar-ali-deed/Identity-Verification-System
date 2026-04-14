from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    AuthServiceError,
    authenticate_user,
    refresh_tokens,
    register_user,
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        user = await register_user(
            db=db,
            email=data.email,
            password=data.password,
            full_name=data.full_name,
        )
        return user
    except AuthServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        user, access_token, refresh_token = await authenticate_user(
            db=db,
            email=data.email,
            password=data.password,
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }
    except AuthServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        access_token, new_refresh_token = await refresh_tokens(
            db=db,
            refresh_token=request.refresh_token,
        )
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }
    except AuthServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_user.refresh_token = None
    await db.flush()
    return {"detail": "Successfully logged out"}
