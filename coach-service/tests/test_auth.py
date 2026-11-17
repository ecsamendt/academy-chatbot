import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest

from app.auth import member_ref, verify_member_token

SECRET = "test-member-secret-0123456789-abcdefghij"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def php_style_token(claims: dict, secret: str = SECRET) -> str:
    """Builds the token exactly like wp-plugin/socio-coach/includes/class-token.php."""
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(sig)}"


def claims(**over):
    now = int(time.time())
    base = {"sub": "42", "memberships": [12, 7, 12], "staff": False, "iat": now, "exp": now + 600}
    base.update(over)
    return base


def test_plugin_token_verifies():
    m = verify_member_token(php_style_token(claims()), SECRET)
    assert m.user_id == "42"
    assert m.memberships == (7, 12)
    assert m.staff is False


def test_wrong_secret_rejected():
    with pytest.raises(jwt.InvalidSignatureError):
        verify_member_token(php_style_token(claims(), "another-secret-of-sufficient-length-xyz"), SECRET)


def test_expired_rejected():
    now = int(time.time())
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_member_token(php_style_token(claims(iat=now - 1000, exp=now - 400)), SECRET)


def test_overlong_lifetime_rejected():
    now = int(time.time())
    with pytest.raises(jwt.InvalidTokenError):
        verify_member_token(php_style_token(claims(iat=now, exp=now + 86400)), SECRET)


def test_alg_none_rejected():
    token = jwt.encode(claims(), key=None, algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        verify_member_token(token, SECRET)


def test_member_ref_is_pseudonymous_and_stable():
    assert member_ref("42") == member_ref("42")
    assert member_ref("42") != member_ref("43")
    assert "42" not in member_ref("42")
