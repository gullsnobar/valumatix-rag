"""Exercise real JWTs and account isolation with fake model providers."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import AskLog, Document, SessionFactory, User
from app.llm_client import get_chat_client, get_embedding_client
from app.main import app
from tests.api.test_ask_api import FakeChatClient
from tests.api.test_documents_api import FakeEmbeddingClient, _assert_error

_PASSWORD = "sample-test-password"
_QUESTION = "What annual leave does the policy provide?"


@pytest.fixture
async def auth_api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    """Use real auth dependencies and remove only the accounts created by this test."""

    prefix = f"auth-test-{uuid4().hex}-"
    monkeypatch.setattr(get_settings(), "jwt_secret", SecretStr(token_urlsafe(48)))
    monkeypatch.setitem(app.dependency_overrides, get_embedding_client, FakeEmbeddingClient)
    monkeypatch.setitem(app.dependency_overrides, get_chat_client, FakeChatClient)
    async with app.router.lifespan_context(app):
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=(prefix, 1234)),
                base_url="http://testserver",
            ) as client:
                yield client, prefix
        finally:
            async with SessionFactory.begin() as session:
                users = list(await session.scalars(select(User.id).where(User.email.like(prefix + "%"))))
                if users:
                    owners = [str(user_id) for user_id in users]
                    await session.execute(delete(Document).where(Document.owner_id.in_(owners)))
                    await session.execute(delete(AskLog).where(AskLog.owner_id.in_(owners)))
                    await session.execute(delete(User).where(User.id.in_(users)))


async def _signup(client: httpx.AsyncClient, email: str) -> httpx.Response:
    response = await client.post("/auth/signup", json={"email": email, "password": _PASSWORD})
    assert response.status_code == 201, response.text
    return response


def _bearer(response: httpx.Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_signup_login_and_me(auth_api: tuple[httpx.AsyncClient, str]) -> None:
    """Issue a signed token for signup and login with a lowercase stored email."""

    client, prefix = auth_api
    email = f"{prefix}Person@Example.TEST"
    signup = await _signup(client, email)
    payload = signup.json()
    user = payload["user"]
    assert payload["token_type"] == "bearer"
    assert set(user) == {"email", "id"}
    assert user["email"] == email.lower()
    assert UUID(user["id"])

    login = await client.post("/auth/login", json={"email": email.upper(), "password": _PASSWORD})
    assert login.status_code == 200, login.text
    assert login.json()["user"] == user
    assert login.json()["token_type"] == "bearer"
    for token_response in (signup, login):
        me = await client.get("/auth/me", headers=_bearer(token_response))
        assert me.status_code == 200
        assert me.json() == user


async def test_duplicate_email(auth_api: tuple[httpx.AsyncClient, str]) -> None:
    """Reject duplicate signup across letter case."""

    client, prefix = auth_api
    email = f"{prefix}repeat@example.test"
    await _signup(client, email)
    duplicate = await client.post(
        "/auth/signup", json={"email": email.upper(), "password": _PASSWORD}
    )
    _assert_error(duplicate, 409, "email_taken")


async def test_bad_credentials_are_indistinguishable(auth_api: tuple[httpx.AsyncClient, str]) -> None:
    """Use the same response for a wrong password and an unknown email."""

    client, prefix = auth_api
    email = f"{prefix}known@example.test"
    await _signup(client, email)
    wrong = await client.post("/auth/login", json={"email": email, "password": "wrong"})
    missing = await client.post(
        "/auth/login", json={"email": f"{prefix}unknown@example.test", "password": "wrong"}
    )
    assert _assert_error(wrong, 401, "invalid_credentials")["message"] == _assert_error(
        missing, 401, "invalid_credentials"
    )["message"]


@pytest.mark.parametrize("token", [None, "invalid.jwt.text"])
async def test_get_documents_requires_a_valid_token(
    auth_api: tuple[httpx.AsyncClient, str], token: str | None
) -> None:
    """Require an authenticated subject for document listing."""

    client, _ = auth_api
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    response = await client.get("/documents", headers=headers)
    _assert_error(response, 401, "unauthorized")
    assert response.headers["WWW-Authenticate"] == "Bearer"
    samples = await client.post("/documents/samples", headers=headers)
    _assert_error(samples, 401, "unauthorized")


async def test_expired_token(auth_api: tuple[httpx.AsyncClient, str]) -> None:
    """Reject a correctly signed but expired token."""

    client, prefix = auth_api
    user_id = (await _signup(client, f"{prefix}expired@example.test")).json()["user"]["id"]
    now = datetime.now(UTC)
    settings = get_settings()
    token = jwt.encode(
        {"sub": user_id, "iat": now - timedelta(minutes=2), "exp": now - timedelta(minutes=1)},
        settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm,
    )
    response = await client.get("/documents", headers={"Authorization": f"Bearer {token}"})
    _assert_error(response, 401, "unauthorized")
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_documents_and_answers_are_owner_scoped(auth_api: tuple[httpx.AsyncClient, str]) -> None:
    """Keep a second owner's uploads out of direct access, lists, and retrieval."""

    client, prefix = auth_api
    owner_a = _bearer(await _signup(client, f"{prefix}a@example.test"))
    owner_b = _bearer(await _signup(client, f"{prefix}b@example.test"))
    uploaded = await client.post(
        "/documents", headers=owner_b,
        files={"file": ("private.txt", b"Employees receive 21 working days of annual leave.")},
    )
    assert uploaded.status_code == 201, uploaded.text
    path = f"/documents/{uploaded.json()['id']}"

    listed = await client.get("/documents", headers=owner_a)
    assert listed.status_code == 200
    assert listed.json() == {"documents": [], "total": 0}
    for response in (
        await client.get(path, headers=owner_a),
        await client.delete(path, headers=owner_a),
    ):
        _assert_error(response, 404, "document_not_found")
    asked = await client.post("/ask", headers=owner_a, json={"question": _QUESTION})
    assert asked.status_code == 200
    assert asked.json()["refusal_reason"] == "no_documents"
    assert asked.json()["chunks"] == []
    assert (await client.get(path, headers=owner_b)).status_code == 200


async def test_recent_metrics_are_limited_sorted_and_owner_scoped(
    auth_api: tuple[httpx.AsyncClient, str],
) -> None:
    """Expose only the current owner's most recent telemetry fields."""

    client, prefix = auth_api
    owner_a = _bearer(await _signup(client, f"{prefix}a@example.test"))
    owner_b = _bearer(await _signup(client, f"{prefix}b@example.test"))
    for headers in (owner_a, owner_b, owner_a):
        asked = await client.post("/ask", headers=headers, json={"question": _QUESTION})
        assert asked.status_code == 200
    result = await client.get("/metrics/recent", headers=owner_a)
    assert result.status_code == 200
    rows = result.json()
    assert len(rows) == 2
    assert rows[0]["created_at"] >= rows[1]["created_at"]
    assert set(rows[0]) == {"created_at", "latency_ms", "provider", "refused", "refusal_reason"}
    assert rows[0]["refused"] is True and rows[0]["refusal_reason"] == "no_documents"
    limited = await client.get("/metrics/recent?limit=1", headers=owner_a)
    assert limited.status_code == 200
    assert limited.json() == rows[:1]
    invalid = await client.get("/metrics/recent?limit=201", headers=owner_a)
    _assert_error(invalid, 422, "validation_error")


async def test_login_rate_limit(
    auth_api: tuple[httpx.AsyncClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Limit unsuccessful login attempts by the configured client rule."""

    client, prefix = auth_api
    monkeypatch.setattr(get_settings(), "rate_limit_login", "2/minute")
    payload = {"email": f"{prefix}unknown@example.test", "password": "wrong"}
    for _ in range(2):
        _assert_error(await client.post("/auth/login", json=payload), 401, "invalid_credentials")
    _assert_error(await client.post("/auth/login", json=payload), 429, "rate_limited")


@pytest.mark.parametrize(
    ("email", "password"),
    [("invalid-email", _PASSWORD), ("valid@example.test", "short")],
)
async def test_signup_validates_email_and_password(
    auth_api: tuple[httpx.AsyncClient, str], email: str, password: str
) -> None:
    """Validate the registration form before writing an account."""

    client, prefix = auth_api
    signup = await client.post("/auth/signup", json={"email": prefix + email, "password": password})
    _assert_error(signup, 422, "validation_error")


async def test_swagger_declares_bearer_security_and_health_is_public(
    auth_api: tuple[httpx.AsyncClient, str],
) -> None:
    """Show Swagger's bearer scheme and attach it to each protected operation."""

    client, _ = auth_api
    assert (await client.get("/health")).status_code == 200
    schema = (await client.get("/openapi.json")).json()
    bearer = schema["components"]["securitySchemes"]["HTTPBearer"]
    assert bearer["type"] == "http" and bearer["scheme"] == "bearer"
    for path in ("/documents", "/documents/samples", "/documents/{document_id}", "/ask", "/ask/stream",
                 "/metrics", "/metrics/recent", "/auth/me"):
        assert all(operation["security"] == [{"HTTPBearer": []}] for operation in schema["paths"][path].values())
    assert "security" not in schema["paths"]["/health"]["get"]


async def test_example_signing_key_is_rejected(
    auth_api: tuple[httpx.AsyncClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed when the configuration uses the public example value."""

    client, prefix = auth_api
    example_key = "change_me_to_a_long_random_string"
    monkeypatch.setattr(get_settings(), "jwt_secret", SecretStr(example_key))
    response = await client.post(
        "/auth/signup", json={"email": f"{prefix}misconfigured@example.test", "password": _PASSWORD}
    )
    _assert_error(response, 503, "service_unavailable")
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(uuid4()), "iat": now, "exp": now + timedelta(hours=1)},
        example_key, algorithm="HS256",
    )
    response = await client.get("/documents", headers={"Authorization": f"Bearer {token}"})
    _assert_error(response, 401, "unauthorized")
