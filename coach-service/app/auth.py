"""Member identity and shared-secret checks.

The WordPress plugin signs a short-lived HS256 JWT for the logged-in user:
    {"sub": "<wp user id>", "memberships": [12, 34], "staff": false,
     "iat": ..., "exp": ...}
The chat window sends it as `Authorization: Bearer <token>`.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException, Request

from app.config import get_settings

MAX_TOKEN_LIFETIME_SEC = 60 * 60  # refuse tokens issued for longer than an hour


@dataclass(frozen=True)
class Member:
    user_id: str
    memberships: tuple[int, ...]
    staff: bool

    @property
    def ref(self) -> str:
        """Pseudonymous ID for logs: never the email or raw WordPress user ID."""
        return member_ref(self.user_id)


def member_ref(user_id: str) -> str:
    secret = get_settings().member_token_secret.encode()
    return "m_" + hmac.new(secret, f"member:{user_id}".encode(), hashlib.sha256).hexdigest()[:20]


def verify_member_token(token: str, secret: str) -> Member:
    if not secret:
        raise ValueError("MEMBER_TOKEN_SECRET is not configured")
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ["sub", "exp", "iat"]},
        leeway=30,
    )
    if claims["exp"] - claims["iat"] > MAX_TOKEN_LIFETIME_SEC:
        raise jwt.InvalidTokenError("token lifetime too long")
    raw = claims.get("memberships") or []
    if not isinstance(raw, list):
        raise jwt.InvalidTokenError("memberships must be a list")
    memberships = tuple(sorted({int(m) for m in raw}))
    return Member(user_id=str(claims["sub"]), memberships=memberships, staff=bool(claims.get("staff")))


def current_member(authorization: str = Header(default="")) -> Member:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing member token")
    try:
        return verify_member_token(token, get_settings().member_token_secret)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="invalid member token") from exc


def sign_body(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def verified_webhook_body(request: Request) -> bytes:
    """Checks X-Socio-Signature (hex HMAC-SHA256 of the raw body)."""
    secret = get_settings().webhook_secret
    body = await request.body()
    given = request.headers.get("x-socio-signature", "")
    if not secret or not hmac.compare_digest(sign_body(body, secret), given):
        raise HTTPException(status_code=401, detail="bad signature")
    return body


def require_admin(x_admin_key: str = Header(default="")) -> None:
    expected = get_settings().admin_api_key
    if not expected or not hmac.compare_digest(expected, x_admin_key):
        raise HTTPException(status_code=401, detail="admin key required")
