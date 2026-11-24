"""HTTP contract and auth, through the real app with injected fakes (no mocks)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from slate.app import create_app
from slate.auth import FakeOAuthProvider, Identity, SessionAuthenticator
from slate.clock import FixedClock
from slate.container import Container
from slate.repositories.memory import MemoryUnitOfWorkFactory
from slate.seed import seed_workspace

NOW = datetime(2026, 11, 21, 14, 0, tzinfo=UTC)  # Sat 09:00 in New York
ISSUER = "https://tenant.example.test/"
ME = Identity(issuer=ISSUER, subject="auth0|me", name="Me", email="me@example.com")
YOU = Identity(issuer=ISSUER, subject="google-oauth2|you", name="You", email=None)


def _container(**kw) -> Container:
    clock = FixedClock(NOW)
    signer = URLSafeTimedSerializer("x" * 40)
    return Container(
        clock=clock,
        uow_factory=kw.pop("uow_factory", None) or MemoryUnitOfWorkFactory(clock),
        authenticator=SessionAuthenticator(signer),
        oauth=FakeOAuthProvider(kw.pop("identity", ME)),
        signer=signer,
        allowed_user_ids=frozenset({YOU.subject}),
        allowed_emails=frozenset({"me@example.com"}),
        secure_cookies=False,
        **kw,
    )


def _client(container: Container) -> TestClient:
    return TestClient(create_app(container, serve_frontend=False))


@pytest.fixture
def client():
    with _client(_container()) as c:
        yield c


def _sign_in(c: TestClient, return_to: str = "/") -> None:
    r = c.get(f"/auth/signin?return_to={return_to}", follow_redirects=False)
    assert r.status_code == 303
    state = r.headers["location"].split("state=")[1]
    r = c.get(f"/auth/callback?code=ok&state={state}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == return_to


def _key(c: TestClient, kind: str = "rest") -> dict[str, str]:
    r = c.post("/api/api-keys", json={"name": "agent", "kind": kind})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['secret']}"}


def test_requires_auth_until_signed_in(client):
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/healthz").status_code == 200
    _sign_in(client, "/projects/x")
    me = client.get("/api/me").json()
    assert (me["name"], me["email"], me["via"]) == ("Me", "me@example.com", "session")


def test_sign_in_records_one_user_and_workspace_per_identity():
    container = _container()
    with _client(container) as c:
        _sign_in(c)
        first = c.get("/api/me").json()
        c.post("/auth/signout")
        _sign_in(c)
        assert c.get("/api/me").json() == first
    assert isinstance(container.uow_factory, MemoryUnitOfWorkFactory)
    [account] = container.uow_factory.db.table("users").values()
    [ws] = container.uow_factory.db.table("workspaces").values()
    assert (str(account.id), account.subject) == (first["id"], "auth0|me")
    assert (str(ws.id), ws.owner_id) == (first["workspace_id"], account.id)


def test_admission_by_subject_or_verified_email():
    # YOU has no verified email but its subject is allowlisted.
    with _client(_container(identity=YOU)) as c:
        _sign_in(c)
        assert c.get("/api/me").json()["name"] == "You"
    stranger = Identity(issuer=ISSUER, subject="auth0|x", name="X", email="x@example.com")
    # The provider leaves email unset when it is not verified, even for an allowed address.
    unverified = Identity(issuer=ISSUER, subject="auth0|me2", name="Me", email=None)
    for identity in (stranger, unverified):
        container = _container(identity=identity)
        with _client(container) as c:
            c.get("/auth/signin", follow_redirects=False)
            assert c.get("/auth/callback?code=ok&state=forged").status_code == 400
            r = c.get("/auth/signin", follow_redirects=False)
            state = r.headers["location"].split("state=")[1]
            denied = c.get(f"/auth/callback?code=ok&state={state}")
            assert denied.status_code == 403 and identity.subject in denied.text
            assert c.get("/api/tasks").status_code == 401
        assert isinstance(container.uow_factory, MemoryUnitOfWorkFactory)
        assert container.uow_factory.db.table("users") == {}


def test_api_keys_are_per_user_revocable_and_kind_bound(client):
    _sign_in(client)
    agent = _key(client)
    me = client.get("/api/me", headers=agent).json()
    assert me["via"] == "key" and me["name"] == "Me"
    # Keys cannot manage keys or settings.
    assert client.get("/api/api-keys", headers=agent).status_code == 403
    assert client.post("/api/api-keys", json={"name": "x"}, headers=agent).status_code == 403
    assert client.patch("/api/settings", json={"timezone": "UTC"}, headers=agent).status_code == 403
    # An MCP key never works on REST.
    assert client.get("/api/tasks", headers=_key(client, "mcp")).status_code == 403
    [listed, _] = sorted(client.get("/api/api-keys").json(), key=lambda k: k["kind"] != "rest")
    assert "secret" not in listed and listed["last_used_at"] is not None
    assert client.delete(f"/api/api-keys/{listed['id']}").status_code == 204
    assert client.get("/api/me", headers=agent).status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_two_people_never_see_each_other():
    container = _container()
    other = _container(identity=YOU, uow_factory=container.uow_factory)
    with _client(container) as a, _client(other) as b:
        _sign_in(a)
        _sign_in(b)
        assert a.get("/api/me").json()["workspace_id"] != b.get("/api/me").json()["workspace_id"]
        project = a.post("/api/projects", json={"name": "Secret"}).json()
        task = a.post("/api/tasks", json={"title": "Mine", "project_id": project["id"]}).json()
        a.post(f"/api/tasks/{task['id']}/comments", json={"body": "private"})
        comment = a.get(f"/api/tasks/{task['id']}/comments").json()[0]
        theirs = b.post("/api/tasks", json={"title": "Theirs"}).json()

        # Each workspace numbers from SLT-1.
        assert task["key"] == theirs["key"] == "SLT-1"
        assert b.get("/api/tasks/SLT-1").json()["title"] == "Theirs"
        assert [t["title"] for t in b.get("/api/tasks").json()] == ["Theirs"]
        assert b.get("/api/projects").json() == []
        for method, path in [
            ("get", f"/api/tasks/{task['id']}"),
            ("delete", f"/api/tasks/{task['id']}"),
            ("get", f"/api/projects/{project['id']}"),
            ("delete", f"/api/projects/{project['id']}"),
            ("delete", f"/api/comments/{comment['id']}"),
        ]:
            assert getattr(b, method)(path).status_code == 404, path
        # Linking to A's project is refused as unknown.
        r = b.patch(f"/api/tasks/{theirs['id']}", json={"project_id": project["id"]})
        assert r.status_code == 422
        assert a.get(f"/api/tasks/{task['id']}").json()["comment_count"] == 1


def test_cross_origin_cookie_write_is_refused(client):
    _sign_in(client)
    evil = {"Origin": "https://evil.example"}
    assert client.post("/api/tasks", json={"title": "x"}, headers=evil).status_code == 403
    assert client.post("/api/tasks", json={"title": "x"}).status_code == 201


def test_routes_take_uuids_not_integers(client):
    _sign_in(client)
    area = client.post("/api/areas", json={"name": "Home"}).json()
    assert len(area["id"]) == 36
    assert client.get("/api/projects/1").status_code == 422
    assert (
        client.patch(f"/api/areas/{area['id']}", json={"name": "House"}).json()["name"] == "House"
    )
    assert client.get("/api/tasks/123").status_code == 404


def test_task_lifecycle_by_key(client):
    _sign_in(client)
    agent = _key(client)
    t = client.post(
        "/api/tasks/quick-add", json={"text": "Water plants every day p4"}, headers=agent
    ).json()
    assert t["key"] == f"SLT-{t['number']}" and t["priority"] == 0
    assert t["due_date"] == "2026-11-21" and t["recurrence"]["mode"] == "fixed"

    done = client.post(f"/api/tasks/{t['key']}/complete", headers=agent).json()["task"]
    assert done["due_date"] == "2026-11-22" and done["status"] == "todo"

    # A typed date moves only this run; the rule stays.
    moved = client.patch(
        f"/api/tasks/{t['key']}", json={"due_string": "2026-11-30"}, headers=agent
    ).json()
    assert moved["due_date"] == "2026-11-30" and moved["recurrence"] is not None

    cleared = client.patch(
        f"/api/tasks/{t['key']}", json={"clear_recurrence": True, "due_date": None}, headers=agent
    ).json()
    assert cleared["recurrence"] is None and cleared["due_date"] is None

    client.post(f"/api/tasks/{t['id']}/comments", json={"body": "hi"}, headers=agent)
    kinds = [a["kind"] for a in client.get(f"/api/tasks/{t['id']}/activity", headers=agent).json()]
    assert kinds[:2] == ["created", "completed_run"] and "commented" in kinds
    assert client.get("/api/tasks/SLT-999", headers=agent).status_code == 404


def test_import_endpoint_is_idempotent(client):
    _sign_in(client)
    agent = _key(client)
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
    first = client.post("/api/import", json=payload, headers=agent).json()
    second = client.post("/api/import", json=payload, headers=agent).json()
    assert first["created"] == {"areas": 1, "projects": 1, "tasks": 1, "comments": 1}
    assert second["created"] == {}
    tasks = client.get("/api/tasks", headers=agent).json()
    assert len(tasks) == 1 and tasks[0]["created_at"].startswith("2025-01-02T03:04:05")


def test_demo_seed_gives_a_full_today():
    container = _container()
    with _client(container) as client:
        _sign_in(client)
        ws = client.get("/api/me").json()["workspace_id"]
        asyncio.run(seed_workspace(container, UUID(ws)))
        ag = client.get("/api/agenda").json()
        assert len(ag["overdue"]) >= 2 and len(ag["days"][0]["tasks"]) >= 3
        assert any(d["ghosts"] for d in ag["days"])
