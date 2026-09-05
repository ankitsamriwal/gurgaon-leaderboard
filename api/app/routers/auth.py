import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.rate_limit import rate_limit
from app.services import auth as auth_service
from app.services.captcha_provider import get_captcha_provider
from app.services.otp_provider import get_otp_provider

router = APIRouter(prefix="/auth", tags=["auth"])


class OtpRequestBody(BaseModel):
    phone: str | None = None
    email: str | None = None
    captcha_token: str | None = None


class OtpRequestResponse(BaseModel):
    request_id: str
    # Only ever populated outside production — see app/services/otp_provider.py.
    debug_otp: str | None = None


@router.post("/otp/request", status_code=202, response_model=OtpRequestResponse)
async def otp_request(body: OtpRequestBody, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    key_suffix = body.phone or body.email or "unknown"
    await rate_limit(f"otp-request-contact:{key_suffix}", limit=5, window_seconds=3600)
    client_ip = request.client.host if request.client else "unknown"
    await rate_limit(f"otp-request-ip:{client_ip}", limit=10, window_seconds=3600)

    if not await get_captcha_provider().verify(body.captcha_token):
        raise HTTPException(
            status_code=400, detail={"error": {"code": "CAPTCHA_FAILED", "message": "CAPTCHA verification failed"}}
        )

    request_id, otp = await auth_service.request_otp(db, phone=body.phone, email=body.email)
    await get_otp_provider().send(phone=body.phone, email=body.email, otp=otp)

    return OtpRequestResponse(
        request_id=str(request_id),
        debug_otp=None if settings.is_production else otp,
    )


class OtpVerifyBody(BaseModel):
    request_id: str
    otp: str


class UserOut(BaseModel):
    id: str
    display_name: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserOut


@router.post("/otp/verify", response_model=TokenResponse)
async def otp_verify(body: OtpVerifyBody, db: Annotated[AsyncSession, Depends(get_db)]):
    user, access_token, refresh_token = await auth_service.verify_otp(
        db, request_id=uuid.UUID(body.request_id), otp=body.otp
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut(id=str(user.id), display_name=user.display_name),
    )


class RefreshBody(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str


@router.post("/token/refresh", response_model=RefreshResponse)
async def token_refresh(body: RefreshBody, db: Annotated[AsyncSession, Depends(get_db)]):
    access_token, refresh_token = await auth_service.rotate_refresh_token(db, raw_token=body.refresh_token)
    return RefreshResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=204)
async def logout(body: RefreshBody, db: Annotated[AsyncSession, Depends(get_db)]):
    await auth_service.logout(db, raw_token=body.refresh_token)
