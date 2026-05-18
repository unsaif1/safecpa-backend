"""
SaifHaven FastAPI - pytest + TestClient test suite
Covers: health, contact, chat, nft-metrics, nft-collection
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

DEFAULTS = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "user@example.com",
    "SMTP_PASS": "secret",
    "OPENROUTER_API_KEY": "sk-test-key",
    "APP_PORT": "8000",
    "APP_HOST": "0.0.0.0",
}



def load_app():
    main_path = Path(__file__).parent.parent / "main.py"
    spec = importlib.util.spec_from_file_location("backend_app", main_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["backend_app"] = mod
    spec.loader.exec_module(mod)
    return mod.app


@pytest.fixture
def client(monkeypatch):
    for k, v in DEFAULTS.items():
        monkeypatch.setenv(k, v)
    return TestClient(load_app())


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "ts" in data


class TestNFTMetrics:
    def test_nft_metrics_returns_expected_keys(self, client):
        r = client.get("/api/nft-metrics")
        assert r.status_code == 200
        data = r.json()
        assert "portfolio" in data
        assert data["portfolio"]["total_items"] > 0

    def test_nft_collection_returns_items(self, client):
        r = client.get("/api/nft-collection")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1


class TestChat:
    @respx.mock
    def test_chat_returns_reply(self, client):
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={"choices": [{"message": {"content": "Hello from Saif!"}}]},
        )
        r = client.post("/api/chat", json={"message": "Hi!"})
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data
        assert "session_id" in data

    def test_chat_rejects_empty_message(self, client):
        r = client.post("/api/chat", json={})
        assert r.status_code == 400

    def test_chat_503_when_no_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        for k, v in DEFAULTS.items():
            if k != "OPENROUTER_API_KEY":
                monkeypatch.setenv(k, v)
        app = load_app()
        c = TestClient(app)
        r = c.post("/api/chat", json={"message": "hello"})
        assert r.status_code == 503


class TestContact:
    def test_contact_missing_fields(self, client):
        r = client.post("/api/contact", json={"name": "Rod"})
        assert r.status_code == 400

    def test_contact_503_when_no_smtp(self, monkeypatch):
        for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
            monkeypatch.setenv(k, "")
        app = load_app()
        c = TestClient(app)
        r = c.post(
            "/api/contact",
            json={"name": "Rod", "email": "rod@test.com", "message": "hello"},
        )
        assert r.status_code == 503

    def test_contact_sends_email(self, client, monkeypatch):
        import smtplib

        sent = {}

        class FakeSMTP:
            def __init__(self, host, port, **kwargs):
                sent["host"] = host
                sent["port"] = port

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def ehlo(self):
                pass

            def starttls(self, ctx):
                pass

            def login(self, u, p):
                sent["user"] = u

            def sendmail(self, frm, to, msg):
                sent["from"] = frm
                sent["to"] = to
                sent["msg"] = msg

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        r = client.post(
            "/api/contact",
            json={
                "name": "Test",
                "email": "test@example.com",
                "subject": "Hi",
                "message": "Hello",
            },
        )
        assert r.status_code == 200
        assert sent.get("to") == ["test@example.com"]
