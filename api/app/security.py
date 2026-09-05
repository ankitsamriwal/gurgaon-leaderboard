"""JWT + OTP + refresh-token primitives for the auth flow in
docs/00-overview.md and docs/05-security-anti-fraud.md.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

ACCESS_TOKEN_TTL_MINUTES = 20
REFRESH_TOKEN_TTL_DAYS = 30
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
JWT_ALGORITHM = "HS256"


def generate_otp() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(*, user_id: uuid.UUID, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
