from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from app.config import settings
from app.utils import utcnow

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def new_token_id() -> str:
    return uuid.uuid4().hex


def create_access_token(user_id: int, session_id: str, role_type: str, company_id: int | None) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": session_id,
        "jti": new_token_id(),
        "roleType": role_type,
        "companyId": company_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_force_login_token(user_id: int, current_session_id: str) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "purpose": "force-login",
        "sub": str(user_id),
        "sid": current_session_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.force_login_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_force_login_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != "force-login":
        raise ValueError("invalid token purpose")
    return payload


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
