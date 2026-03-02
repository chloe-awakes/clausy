from __future__ import annotations

import clausy.server as server


def test_models_endpoint_exposes_grok_model(monkeypatch):
    monkeypatch.setattr(server, "PROVIDER_NAME", "grok")
    client = server.app.test_client()

    resp = client.get("/v1/models")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["object"] == "list"
    ids = [m["id"] for m in body["data"]]
    assert "grok-web" in ids
