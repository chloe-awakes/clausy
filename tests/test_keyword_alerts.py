from __future__ import annotations

from unittest.mock import patch

import pytest

from clausy.alerts import (
    AlertDispatcher,
    AlertEvent,
    AlertRateLimiter,
    EmailNotifier,
    KeywordDetector,
    TelegramNotifier,
    load_keyword_alert_config_from_env,
)


def test_alert_config_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CLAUSY_KEYWORD_ALERTS_ENABLED", raising=False)
    monkeypatch.delenv("CLAUSY_KEYWORD_ALERTS_KEYWORDS", raising=False)

    cfg = load_keyword_alert_config_from_env()
    assert cfg.enabled is False
    assert cfg.keywords == ()


def test_alert_config_parses_keywords_and_channels(monkeypatch):
    monkeypatch.setenv("CLAUSY_KEYWORD_ALERTS_ENABLED", "1")
    monkeypatch.setenv("CLAUSY_KEYWORD_ALERTS_KEYWORDS", "token,password")
    monkeypatch.setenv("CLAUSY_ALERT_TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("CLAUSY_ALERT_TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("CLAUSY_ALERT_EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("CLAUSY_ALERT_EMAIL_TO", "a@x.com,b@x.com")

    cfg = load_keyword_alert_config_from_env()
    assert cfg.enabled is True
    assert cfg.keywords == ("token", "password")
    assert cfg.bot_token == "bot"
    assert cfg.chat_id == "123"
    assert cfg.host == "smtp.example.com"
    assert cfg.to_addrs == ("a@x.com", "b@x.com")


def test_alert_config_rejects_empty_keywords(monkeypatch):
    monkeypatch.setenv("CLAUSY_KEYWORD_ALERTS_ENABLED", "1")
    monkeypatch.setenv("CLAUSY_KEYWORD_ALERTS_KEYWORDS", "")
    with pytest.raises(ValueError):
        load_keyword_alert_config_from_env()


def test_alert_config_accepts_smtp_port_at_upper_boundary(monkeypatch):
    monkeypatch.setenv("CLAUSY_ALERT_EMAIL_SMTP_PORT", "65535")
    cfg = load_keyword_alert_config_from_env()
    assert cfg.port == 65535


def test_alert_config_rejects_smtp_port_above_upper_boundary(monkeypatch):
    monkeypatch.setenv("CLAUSY_ALERT_EMAIL_SMTP_PORT", "65536")
    cfg = load_keyword_alert_config_from_env()
    assert cfg.port == 587


def test_alert_config_rejects_non_finite_or_oversized_smtp_port(monkeypatch):
    monkeypatch.setenv("CLAUSY_ALERT_EMAIL_SMTP_PORT", "9" * 5000)
    cfg = load_keyword_alert_config_from_env()
    assert cfg.port == 587


def test_detector_matches_case_insensitive_by_default():
    d = KeywordDetector(("Secret", "token"), case_sensitive=False)
    assert d.match("found secret and TOKEN") == ["Secret", "token"]


def test_detector_respects_case_sensitive_mode():
    d = KeywordDetector(("Secret",), case_sensitive=True)
    assert d.match("secret") == []
    assert d.match("Secret") == ["Secret"]


def test_detector_returns_matched_keywords_once():
    d = KeywordDetector(("token",), case_sensitive=False)
    assert d.match("token token token") == ["token"]


def test_rate_limiter_suppresses_duplicates_within_window():
    limiter = AlertRateLimiter(window_seconds=60, max_alerts_per_window=1)
    assert limiter.should_send("s1", "token", now=1000) is True
    assert limiter.should_send("s1", "token", now=1005) is False
    assert limiter.should_send("s1", "token", now=1061) is True


@patch("clausy.alerts.requests.post")
def test_telegram_notifier_posts_message(mock_post):
    n = TelegramNotifier(bot_token="abc", chat_id="123")
    n.send(AlertEvent(session_id="s1", provider="chatgpt", direction="request", keyword="token", excerpt="contains token"))
    assert mock_post.call_count == 1
    args, kwargs = mock_post.call_args
    assert "sendMessage" in args[0]
    assert kwargs["json"]["chat_id"] == "123"
    assert "token" in kwargs["json"]["text"]


@patch("clausy.alerts.smtplib.SMTP")
def test_email_notifier_sends_message(mock_smtp):
    n = EmailNotifier(
        host="smtp.example.com",
        port=587,
        username="u",
        password="p",
        from_addr="from@example.com",
        to_addrs=("to@example.com",),
        starttls=True,
    )
    n.send(AlertEvent(session_id="s1", provider="chatgpt", direction="response", keyword="secret", excerpt="..."))
    smtp = mock_smtp.return_value.__enter__.return_value
    assert smtp.starttls.call_count == 1
    assert smtp.login.call_count == 1
    assert smtp.send_message.call_count == 1


def test_notifier_failures_do_not_raise():
    class Bad:
        def send(self, _alert):
            raise RuntimeError("boom")

    d = AlertDispatcher([Bad()])
    d.send(AlertEvent(session_id="s1", provider="chatgpt", direction="request", keyword="k", excerpt="e"))
