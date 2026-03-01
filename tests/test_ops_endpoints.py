from __future__ import annotations

import pytest


class BrokenRegistry:
    def get(self, _name: str):
        raise RuntimeError("Authentication required: please sign in")


@pytest.mark.contract
def test_health_includes_ops_metadata(configure_server):
    class _Provider:
        def ensure_ready(self, _page):
            pass

    client = configure_server(provider_name="chatgpt", providers={"chatgpt": _Provider()})

    resp = client.get("/health")
    body = resp.get_json()

    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["service"] == "clausy"
    assert body["provider"] == "chatgpt"
    assert isinstance(body["version"], str) and body["version"]
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0
    assert body["tool_password_required"] is False


@pytest.mark.contract
def test_ready_returns_200_when_provider_registry_is_healthy(configure_server):
    class _Provider:
        def ensure_ready(self, _page):
            pass

    client = configure_server(provider_name="chatgpt", providers={"chatgpt": _Provider()})

    resp = client.get("/ready")
    body = resp.get_json()

    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["provider"] == "chatgpt"


@pytest.mark.contract
def test_ready_returns_controlled_auth_error_when_provider_unavailable(monkeypatch, configure_server):
    class _Provider:
        def ensure_ready(self, _page):
            pass

    client = configure_server(provider_name="chatgpt", providers={"chatgpt": _Provider()})
    import clausy.server as server

    monkeypatch.setattr(server, "registry", BrokenRegistry())

    resp = client.get("/ready")
    body = resp.get_json()

    assert resp.status_code == 503
    assert body["error"]["type"] == "provider_auth_error"
