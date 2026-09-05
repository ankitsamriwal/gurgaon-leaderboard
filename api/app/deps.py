from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, id: str, role: str):
        self.id = id
        self.role = role


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHENTICATED", "message": "missing bearer token"}},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail={"error": {"code": "TOKEN_EXPIRED", "message": "access token expired"}}
        )
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=401, detail={"error": {"code": "TOKEN_INVALID", "message": "invalid access token"}}
        )
    return CurrentUser(id=payload["sub"], role=payload.get("role", "user"))


def require_role(*roles: str):
    async def _check(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "insufficient role"}}
            )
        return user

    return _check
