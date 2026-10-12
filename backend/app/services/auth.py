import os
import secrets
import time

import jwt
from fastapi import Header, HTTPException
from jwt import InvalidTokenError


ISSUER = "calling-agent"
TOKEN_LIFETIME_SECONDS = 8 * 60 * 60


def auth_required() -> bool:
    return bool(os.getenv("RENDER")) or os.getenv("AUTH_REQUIRED", "false").lower() == "true"


def auth_configured() -> bool:
    username = os.getenv("APP_USERNAME", "")
    password = os.getenv("APP_PASSWORD", "")
    signing_secret = os.getenv("APP_TOKEN_SECRET", "")
    return bool(username and len(password) >= 16 and len(signing_secret) >= 32)


def issue_access_token(username: str, password: str) -> dict[str, str | int]:
    if not auth_configured():
        raise HTTPException(status_code=503, detail="Owner authentication is not configured.")

    configured_username = os.environ["APP_USERNAME"]
    configured_password = os.environ["APP_PASSWORD"]
    if not secrets.compare_digest(username, configured_username) or not secrets.compare_digest(
        password, configured_password
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    issued_at = int(time.time())
    token = jwt.encode(
        {
            "sub": configured_username,
            "iss": ISSUER,
            "iat": issued_at,
            "exp": issued_at + TOKEN_LIFETIME_SECONDS,
        },
        os.environ["APP_TOKEN_SECRET"],
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_LIFETIME_SECONDS}


def require_owner(authorization: str | None = Header(default=None)) -> str | None:
    if not auth_required():
        return None
    if not auth_configured():
        raise HTTPException(status_code=503, detail="Owner authentication is not configured.")
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Owner sign-in is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="A valid bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = jwt.decode(
            token,
            os.environ["APP_TOKEN_SECRET"],
            algorithms=["HS256"],
            issuer=ISSUER,
        )
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=401,
            detail="Owner session is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    username = os.environ["APP_USERNAME"]
    if claims.get("sub") != username:
        raise HTTPException(status_code=401, detail="Owner session is invalid.")
    return username