from __future__ import annotations

import clausy.server as server


import pytest


@pytest.mark.parametrize(
    "provider_name,expected_model_id",
    [
        ("grok", "grok-web"),
        ("gemini_web", "gemini-web"),
    ],
)
def test_models_endpoint_exposes_web_provider_model(monkeypatch, provider_name, expected_model_id):
    monkeypatch.setattr(server, "PROVIDER_NAME", provider_name)
    client = server.app.test_client()

    resp = client.get("/v1/models")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["object"] == "list"
    ids = [m["id"] for m in body["data"]]
    assert expected_model_id in ids
