"""Agent access through the real app: MCP, the sidebar (stub model), Pending changes."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from slate.app import create_app
from slate.auth import FakeOAuthProvider, Identity
from tests.integration.test_api import ISSUER, _container, _key, _sign_in

CATALOG = {
    "get_overview",
    "find_tasks",
    "get_task",
    "list_pending_changes",
    "save_tasks",
    "complete_task",
    "reopen_task",
    "delete_task",
    "add_comment",
    "save_project",
    "save_area",
    "save_label",
    "import_tasks",
}


def _client(**kw) -> TestClient:
    container = _container(agent_model="stub", **kw)
    return TestClient(create_app(container, serve_frontend=False))


@pytest.fixture
def client():
    with _client() as c:
        _sign_in(c)
        yield c


def mcp(c: TestClient, key: dict, method: str, params: dict | None = None):
    r = c.post(
        "/mcp",
        headers={**key, "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )
    return r


def call(c: TestClient, key: dict, name: str, args: dict) -> dict:
    r = mcp(c, key, "tools/call", {"name": name, "arguments": args})
    assert r.status_code == 200, r.text
    body = r.json()["result"]
    assert not body.get("isError"), body
    return body["structuredContent"]


def _set(c: TestClient, **settings) -> None:
    assert c.patch("/api/agent/settings", json=settings).status_code == 200


def _tasks(c: TestClient) -> list[str]:
    return [t["title"] for t in c.get("/api/tasks", params={"include_closed": True}).json()]


def test_mcp_needs_an_mcp_key_and_mcp_keys_stay_off_rest(client):
    rest, key = _key(client), _key(client, "mcp")
    assert mcp(client, rest, "tools/list").status_code == 401
    assert mcp(client, {}, "tools/list").status_code == 401
    assert client.get("/api/tasks", headers=key).status_code == 403
    r = mcp(client, key, "tools/list")
    assert r.status_code == 200
    tools = {t["name"]: t for t in r.json()["result"]["tools"]}
    assert set(tools) == CATALOG
    assert tools["delete_task"]["annotations"]["destructiveHint"] is True
    assert tools["get_overview"]["annotations"]["readOnlyHint"] is True
    # Revoking takes effect on the next call.
    key_id = next(k["id"] for k in client.get("/api/api-keys").json() if k["kind"] == "mcp")
    client.delete(f"/api/api-keys/{key_id}")
    assert mcp(client, key, "tools/list").status_code == 401


def test_suggest_mode_pends_and_only_a_browser_applies_once(client):
    key, rest = _key(client, "mcp"), _key(client)
    before = _tasks(client)
    out = call(client, key, "save_tasks", {"tasks": [{"title": "Buy milk", "due_string": "fri"}]})
    assert out["outcome"] == "pending" and len(out["pending_change_ids"]) == 1
    assert _tasks(client) == before
    [pending] = client.get("/api/pending-changes").json()
    assert pending["origin"] == "mcp" and pending["summary"] == "New task: Buy milk"
    # The due date was resolved when drafted (Sat Nov 21 -> Fri Nov 27).
    assert pending["input"]["tasks"][0]["due_date"] == "2026-11-27"
    pid = pending["id"]
    assert (
        client.post(f"/api/pending-changes/{pid}/apply", json={}, headers=rest).status_code == 403
    )
    edited = {"tasks": [{**pending["input"]["tasks"][0], "title": "Buy oat milk"}]}
    r = client.post(f"/api/pending-changes/{pid}/apply", json={"input": edited})
    assert r.status_code == 200 and r.json()["status"] == "applied"
    assert client.post(f"/api/pending-changes/{pid}/apply", json={}).json()["status"] == "applied"
    assert _tasks(client).count("Buy oat milk") == 1 and "Buy milk" not in _tasks(client)
    assert client.get("/api/pending-changes").json() == []


def test_apply_mode_runs_writes_but_deletes_still_pend(client):
    key = _key(client, "mcp")
    _set(client, mode="apply")
    made = call(client, key, "save_tasks", {"tasks": [{"title": "Call Sam"}]})
    assert made["outcome"] == "applied"
    ref = made["tasks"][0]["key"]
    assert call(client, key, "complete_task", {"ref": ref})["tasks"][0]["status"] == "done"
    assert call(client, key, "delete_task", {"ref": ref})["outcome"] == "pending"
    assert "Call Sam" in _tasks(client)
    # An agent cannot change the mode: there is no tool, and keys get 403.
    assert (
        client.patch(
            "/api/agent/settings", json={"mode": "suggest"}, headers=_key(client)
        ).status_code
        == 403
    )


def test_tool_rejections_do_not_store_anything(client):
    key = _key(client, "mcp")
    r = mcp(client, key, "tools/call", {"name": "complete_task", "arguments": {"ref": "SLT-999"}})
    assert r.json()["result"]["isError"] is True
    assert client.get("/api/pending-changes").json() == []


def test_pending_changes_are_per_workspace():
    other = Identity(issuer=ISSUER, subject="google-oauth2|you", name="You")
    container = _container(agent_model="stub")
    oauth = container.oauth
    assert isinstance(oauth, FakeOAuthProvider)
    with TestClient(create_app(container, serve_frontend=False)) as c:
        _sign_in(c)
        out = call(c, _key(c, "mcp"), "save_tasks", {"tasks": [{"title": "Mine"}]})
        pid = out["pending_change_ids"][0]
        out = c.post("/auth/signout", follow_redirects=False)
        oauth.end_session(out.headers["location"])
        oauth.identity = other
        _sign_in(c)
        assert c.get("/api/pending-changes").json() == []
        assert c.post(f"/api/pending-changes/{pid}/apply", json={}).status_code == 404
        assert c.post(f"/api/pending-changes/{pid}/dismiss").status_code == 404


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for frame in text.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


def _send(c: TestClient, content: str, files: list | None = None):
    return c.post("/api/agent/messages", data={"content": content}, files=files or [])


def test_sidebar_is_off_until_enabled_and_drafts_cards(client):
    assert _send(client, "hi").status_code == 409
    _set(client, enabled=True)
    r = _send(client, "Add these:\n- Pick the tile\n- Send the deposit")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _events(r.text)
    names = [e for e, _ in events]
    assert names[-1] == "done" and names.count("pending_change") == 2
    cards = [d for e, d in events if e == "pending_change"]
    assert [c["summary"] for c in cards] == [
        "New task: Pick the tile",
        "New task: Send the deposit",
    ]
    assert "Pick the tile" not in _tasks(client)
    convo = client.get("/api/agent/conversation").json()
    assert [m["role"] for m in convo] == ["owner", "agent"]
    assert sorted(convo[1]["pending_change_ids"]) == sorted(c["id"] for c in cards)
    # API keys cannot use the sidebar.
    assert client.get("/api/agent/conversation", headers=_key(client)).status_code == 403
    assert client.delete("/api/agent/conversation").status_code == 204
    assert client.get("/api/agent/conversation").json() == []


def test_sidebar_apply_mode_applies_and_reports(client):
    _set(client, enabled=True, mode="apply")
    ref = client.post("/api/tasks", json={"title": "Stretch"}).json()["key"]
    events = _events(_send(client, f"please complete {ref}").text)
    applied = [d for e, d in events if e == "applied"]
    assert applied and applied[0]["tool"] == "complete_task"
    assert client.get(f"/api/tasks/{ref}").json()["status"] == "done"


def test_sidebar_images_are_validated_and_reach_the_model(client):
    _set(client, enabled=True)
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="PNG")
    r = _send(client, "", files=[("images", ("note.png", buf.getvalue(), "image/png"))])
    events = _events(r.text)
    assert [d["summary"] for e, d in events if e == "pending_change"] == [
        "New task: Task from image"
    ]
    assert client.get("/api/agent/conversation").json()[0]["image_count"] == 1
    bad = _send(client, "x", files=[("images", ("x.png", b"not an image", "image/png"))])
    assert bad.status_code == 422


def test_daily_cap_counts_failed_turns():
    with _client(agent_daily_message_cap=2) as c:
        _sign_in(c)
        _set(c, enabled=True)
        assert [e for e, _ in _events(_send(c, "[stub-fail]").text)][-1] == "error"
        assert _send(c, "hello").status_code == 200
        r = _send(c, "again")
        assert r.status_code == 429 and r.json()["detail"]["code"] == "daily_cap_reached"


def test_stub_model_is_refused_on_a_public_origin():
    with _client(public_url="https://slate.example.com") as c:
        _sign_in(c)
        _set(c, enabled=True)
        assert _send(c, "hi").status_code == 503
