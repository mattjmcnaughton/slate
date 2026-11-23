"""HTTP contract and auth, through the real app with injected fakes (no mocks)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from slate.app import create_app
from slate.auth import FakeOAuthProvider, Identity, SessionAuthenticator
from slate.clock import FixedClock
from slate.container import Container
from slate.repositories.memory import MemoryUnitOfWorkFactory
from slate.seed import seed_if_empty

NOW = datetime(2026, 11, 21, 14, 0, tzinfo=UTC)  # Sat 09:00 in New York
ISSUER = "https://tenant.example.test/"
ME = Identity(issuer=ISSUER, subject="auth0|me", name="Me", email="me@example.com")


def _container(**kw) -> Container:
    clock = FixedClock(NOW)
    signer = URLSafeTimedSerializer("x" * 40)
    return Container(
        clock=clock,
        uow_factory=MemoryUnitOfWorkFactory(clock),
        authenticator=SessionAuthenticator(signer, frozenset({"agent-token"})),
        oauth=FakeOAuthProvider(kw.pop("identity", ME)),
        signer=signer,
        allowed_emails=frozenset({"me@example.com"}),
        secure_cookies=False,
        **kw,
    )


@pytest.fixture
def client():
    with TestClient(create_app(_container(), serve_frontend=False)) as c:
        yield c


AGENT = {"Authorization": "Bearer agent-token"}


def _sign_in(c: TestClient) -> None:
    r = c.get("/auth/signin?return_to=/projects/1", follow_redirects=False)
    assert r.status_code == 303
    state = r.headers["location"].split("state=")[1]
    r = c.get(f"/auth/callback?code=ok&state={state}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/projects/1"


def test_requires_auth_until_signed_in(client):
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/healthz").status_code == 200
    _sign_in(client)
    me = client.get("/api/me").json()
    assert (me["name"], me["email"], me["via"]) == ("Me", "me@example.com", "session")


def test_sign_in_records_one_user_per_identity():
    container = _container()
    with TestClient(create_app(container, serve_frontend=False)) as c:
        _sign_in(c)
        first = c.get("/api/me").json()["id"]
        c.post("/auth/signout")
        _sign_in(c)
        assert c.get("/api/me").json()["id"] == first
    assert isinstance(container.uow_factory, MemoryUnitOfWorkFactory)
    [account] = container.uow_factory.db.table("users").values()
    assert (str(account.uuid), account.issuer, account.subject) == (first, ISSUER, "auth0|me")


def test_bearer_token_and_wrong_token(client):
    assert client.get("/api/me", headers=AGENT).json()["via"] == "token"
    assert client.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_callback_rejects_bad_state_and_unlisted_user():
    with TestClient(create_app(_container(), serve_frontend=False)) as c:
        c.get("/auth/signin", follow_redirects=False)
        assert c.get("/auth/callback?code=ok&state=forged").status_code == 400
    stranger = Identity(issuer=ISSUER, subject="auth0|x", name="X", email="x@example.com")
    # The provider leaves email unset when it is not verified, even for an allowed address.
    unverified = Identity(issuer=ISSUER, subject="auth0|me2", name="Me", email=None)
    for identity in (stranger, unverified):
        container = _container(identity=identity)
        with TestClient(create_app(container, serve_frontend=False)) as c:
            r = c.get("/auth/signin", follow_redirects=False)
            state = r.headers["location"].split("state=")[1]
            assert c.get(f"/auth/callback?code=ok&state={state}").status_code == 403
            assert c.get("/api/tasks").status_code == 401
        assert isinstance(container.uow_factory, MemoryUnitOfWorkFactory)
        assert container.uow_factory.db.table("users") == {}


def test_cross_origin_cookie_write_is_refused(client):
    _sign_in(client)
    evil = {"Origin": "https://evil.example"}
    assert client.post("/api/tasks", json={"title": "x"}, headers=evil).status_code == 403
    assert client.post("/api/tasks", json={"title": "x"}).status_code == 201


def test_task_lifecycle_by_key(client):
    t = client.post(
        "/api/tasks/quick-add", json={"text": "Water plants every day p4"}, headers=AGENT
    ).json()
    assert t["key"] == f"SLT-{t['id']}" and t["priority"] == 0
    assert t["due_date"] == "2026-11-21" and t["recurrence"]["mode"] == "fixed"

    done = client.post(f"/api/tasks/{t['key']}/complete", headers=AGENT).json()["task"]
    assert done["due_date"] == "2026-11-22" and done["status"] == "todo"

    # A typed date moves only this run; the rule stays.
    moved = client.patch(
        f"/api/tasks/{t['key']}", json={"due_string": "2026-11-30"}, headers=AGENT
    ).json()
    assert moved["due_date"] == "2026-11-30" and moved["recurrence"] is not None

    cleared = client.patch(
        f"/api/tasks/{t['key']}", json={"clear_recurrence": True, "due_date": None}, headers=AGENT
    ).json()
    assert cleared["recurrence"] is None and cleared["due_date"] is None

    client.post(f"/api/tasks/{t['id']}/comments", json={"body": "hi"}, headers=AGENT)
    kinds = [a["kind"] for a in client.get(f"/api/tasks/{t['id']}/activity", headers=AGENT).json()]
    assert kinds[:2] == ["created", "completed_run"] and "commented" in kinds
    assert client.get("/api/tasks/SLT-999", headers=AGENT).status_code == 404


def test_import_endpoint_is_idempotent(client):
    payload = {
        "source": "linear",
        "areas": [{"source_id": "team-1", "name": "Work"}],
        "projects": [{"source_id": "p-1", "name": "Launch", "area_source_id": "team-1"}],
        "tasks": [
            {
                "source_id": "ENG-1",
                "title": "Ship it",
                "project_source_id": "p-1",
                "status": "in_progress",
                "created_at": "2025-01-02T03:04:05Z",
                "comments": [{"source_id": "c1", "body": "go"}],
            }
        ],
    }
    first = client.post("/api/import", json=payload, headers=AGENT).json()
    second = client.post("/api/import", json=payload, headers=AGENT).json()
    assert first["created"] == {"areas": 1, "projects": 1, "tasks": 1, "comments": 1}
    assert second["created"] == {}
    tasks = client.get("/api/tasks", headers=AGENT).json()
    assert len(tasks) == 1 and tasks[0]["created_at"].startswith("2025-01-02T03:04:05")


def test_demo_seed_gives_a_full_today():
    c = _container(startup=[seed_if_empty])
    with TestClient(create_app(c, serve_frontend=False)) as client:
        ag = client.get("/api/agenda", headers=AGENT).json()
        assert len(ag["overdue"]) >= 2 and len(ag["days"][0]["tasks"]) >= 3
        assert any(d["ghosts"] for d in ag["days"])
