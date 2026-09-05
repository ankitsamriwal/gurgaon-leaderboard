"""OTP verification, JWT issuance, and refresh-token rotation.

Refresh reuse detection (docs/05-security-anti-fraud.md): each refresh
token belongs to a `family_id` (one per login). Using a token marks it
`revoked=True` and issues a new one in the same family. If an
already-revoked token is presented again — the signal that someone is
replaying a stolen, already-rotated token — the *entire family* is
revoked, forcing a fresh login on every device sharing that session chain.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OtpRequest, RefreshToken, User
from app.security import (
    OTP_MAX_ATTEMPTS,
    OTP_TTL_MINUTES,
    REFRESH_TOKEN_TTL_DAYS,
    create_access_token,
    generate_otp,
    generate_refresh_token,
    hash_otp,
    hash_refresh_token,
)


def _error(status_code: int, code: str, message: str):
    raise HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


async def request_otp(session: AsyncSession, *, phone: str | None, email: str | None) -> tuple[uuid.UUID, str]:
    if not phone and not email:
        _error(400, "INVALID_REQUEST", "phone or email is required")

    otp = generate_otp()
    record = OtpRequest(
        phone=phone,
        email=email,
        otp_hash=hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record.id, otp


async def verify_otp(session: AsyncSession, *, request_id: uuid.UUID, otp: str) -> tuple[User, str, str]:
    record = await session.get(OtpRequest, request_id)
    if record is None:
        _error(400, "OTP_INVALID", "unknown request_id")

    if record.consumed:
        _error(400, "OTP_INVALID", "this OTP has already been used")
    if record.expires_at < datetime.now(timezone.utc):
        _error(400, "OTP_EXPIRED", "OTP has expired, request a new one")
    if record.attempts >= OTP_MAX_ATTEMPTS:
        _error(429, "OTP_LOCKED", "too many incorrect attempts, request a new OTP")

    if hash_otp(otp) != record.otp_hash:
        record.attempts += 1
        await session.commit()
        _error(400, "OTP_INCORRECT", "incorrect OTP")

    record.consumed = True

    user: User | None = None
    if record.phone:
        user = (await session.execute(select(User).where(User.phone == record.phone))).scalar_one_or_none()
    elif record.email:
        user = (await session.execute(select(User).where(User.email == record.email))).scalar_one_or_none()

    if user is None:
        user = User(
            phone=record.phone,
            email=record.email,
            display_name=record.phone or record.email,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
    elif not user.is_verified:
        user.is_verified = True

    access_token = create_access_token(user_id=user.id, role=user.role)
    refresh_token, _ = await _issue_refresh_token(session, user_id=user.id, family_id=uuid.uuid4())

    await session.commit()
    await session.refresh(user)
    return user, access_token, refresh_token


async def _issue_refresh_token(
    session: AsyncSession, *, user_id: uuid.UUID, family_id: uuid.UUID
) -> tuple[str, RefreshToken]:
    raw = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        token_hash=hash_refresh_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    )
    session.add(row)
    await session.flush()
    return raw, row


async def rotate_refresh_token(session: AsyncSession, *, raw_token: str) -> tuple[str, str]:
    token_hash = hash_refresh_token(raw_token)
    row = (
        await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    ).scalar_one_or_none()

    if row is None:
        _error(401, "REFRESH_INVALID", "unknown refresh token")

    if row.revoked:
        await _revoke_family(session, row.family_id)
        await session.commit()
        if row.replaced_by is not None:
            # It was already exchanged for a newer token once before —
            # this second use is a replay of a stolen, rotated-out token.
            _error(401, "REFRESH_REUSED", "refresh token reuse detected, session revoked")
        _error(401, "REFRESH_REVOKED", "refresh token has been revoked, please log in again")

    if row.expires_at < datetime.now(timezone.utc):
        _error(401, "REFRESH_EXPIRED", "refresh token expired, please log in again")

    user = await session.get(User, row.user_id)

    new_raw, new_row = await _issue_refresh_token(session, user_id=row.user_id, family_id=row.family_id)
    row.revoked = True
    row.replaced_by = new_row.id

    access_token = create_access_token(user_id=user.id, role=user.role)

    await session.commit()
    return access_token, new_raw


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    rows = (await session.execute(select(RefreshToken).where(RefreshToken.family_id == family_id))).scalars().all()
    for r in rows:
        r.revoked = True


async def logout(session: AsyncSession, *, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    row = (
        await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    ).scalar_one_or_none()
    if row is not None:
        await _revoke_family(session, row.family_id)
        await session.commit()
