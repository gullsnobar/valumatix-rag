"""Hash credentials, manage accounts, and authenticate bearer-token subjects."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated, TypedDict
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.errors import ExternalServiceError, InvalidCredentialsError, UnauthorizedError
from app.repository import create_user, get_user, get_user_by_email
from app.schemas import AuthResponse, LoginRequest, SignupRequest, UserOut

_BCRYPT_ROUNDS = 12
_MAX_PASSWORD_BYTES = 72
# Match the verification cost of a real account even when the email is unknown.
_DUMMY_PASSWORD_HASH = "$2b$12$Qx.7JaP96b65PJJsoeVMRebIrULFNpxzxg8viFrJGIP4gBwaJoQ/y"
_EXAMPLE_SIGNING_KEY = "change_me_to_a_long_random_string"
_bearer = HTTPBearer(auto_error=False, bearerFormat="JWT")


class AccessClaims(TypedDict):
    """Carry the validated subject and lifetime of an access token."""

    sub: str
    iat: int
    exp: int


def _signing_key(settings: Settings) -> str:
    key = settings.jwt_secret.get_secret_value()
    if key.strip() == _EXAMPLE_SIGNING_KEY or len(key.encode("utf-8")) < 32:
        raise ExternalServiceError("Configure a private JWT_SECRET of at least 32 bytes.")
    return key


def hash_password(password: str) -> str:
    """Generate a salted bcrypt hash for a UTF-8 password."""

    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError("Password must be at most 72 UTF-8 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""

    try:
        encoded = password.encode("utf-8")
        return len(encoded) <= _MAX_PASSWORD_BYTES and bcrypt.checkpw(
            encoded, password_hash.encode("ascii")
        )
    except ValueError:
        return False


def create_access_token(user_id: UUID | str) -> str:
    """Sign a short-lived bearer token for a user."""

    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        },
        _signing_key(settings),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> AccessClaims:
    """Verify the signature, required claims, expiration, and UUID subject."""

    settings = get_settings()
    try:
        claims = jwt.decode(
            token, _signing_key(settings), algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "iat", "exp"]},
        )
        if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
            raise ValueError("JWT timestamps must be integer seconds.")
        return {"sub": str(UUID(claims["sub"])), "iat": claims["iat"], "exp": claims["exp"]}
    except (jwt.InvalidTokenError, ValueError, TypeError, ExternalServiceError):
        raise UnauthorizedError() from None


async def get_owner_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Resolve the current request's owner from a verified bearer token."""

    if credentials is None:
        raise UnauthorizedError()
    return decode_token(credentials.credentials)["sub"]


async def register_user(session: AsyncSession, request: SignupRequest) -> AuthResponse:
    """Hash the password off the event loop and create a new account."""

    _signing_key(get_settings())
    password_hash = await asyncio.to_thread(hash_password, request.password.get_secret_value())
    user = await create_user(session, request.email, password_hash)
    return AuthResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


async def login_user(session: AsyncSession, request: LoginRequest) -> AuthResponse:
    """Verify credentials without disclosing whether the email is registered."""

    _signing_key(get_settings())
    email = request.email.strip().lower()
    user = (
        await get_user_by_email(session, email)
        if len(email) <= 254 and "\x00" not in email
        else None
    )
    valid = await asyncio.to_thread(
        verify_password, request.password.get_secret_value(),
        user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
    )
    if user is None or not valid:
        raise InvalidCredentialsError()
    return AuthResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


async def current_user(session: AsyncSession, owner_id: str) -> UserOut:
    """Return the user profile for an authenticated owner."""

    user = await get_user(session, UUID(owner_id))
    if user is None:
        raise UnauthorizedError()
    return UserOut.model_validate(user)
