from __future__ import annotations

import logging
import os
import smtplib
import threading
import time
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import requests

logger = logging.getLogger(__name__)


_SMTP_PORT_DEFAULT = 587
_SMTP_PORT_MIN = 1
_SMTP_PORT_MAX = 65535


@dataclass(frozen=True)
class KeywordAlertConfig:
    enabled: bool = False
    keywords: tuple[str, ...] = ()
    case_sensitive: bool = False
    max_alerts_per_window: int = 1
    window_seconds: int = 300

    bot_token: str = ""
    chat_id: str = ""
    api_base: str = "https://api.telegram.org"

    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addrs: tuple[str, ...] = ()
    starttls: bool = True


@dataclass(frozen=True)
class AlertEvent:
    session_id: str
    provider: str
    direction: str
    keyword: str
    excerpt: str


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in raw.split(",") if v and v.strip())


def _env_smtp_port() -> int:
    raw = os.environ.get("CLAUSY_ALERT_EMAIL_SMTP_PORT", str(_SMTP_PORT_DEFAULT))
    try:
        parsed = int((raw or "").strip())
    except (TypeError, ValueError):
        return _SMTP_PORT_DEFAULT
    if parsed < _SMTP_PORT_MIN or parsed > _SMTP_PORT_MAX:
        return _SMTP_PORT_DEFAULT
    return parsed


def load_keyword_alert_config_from_env() -> KeywordAlertConfig:
    enabled = _env_bool("CLAUSY_KEYWORD_ALERTS_ENABLED", False)
    keywords = _split_csv(os.environ.get("CLAUSY_KEYWORD_ALERTS_KEYWORDS", ""))
    if enabled and not keywords:
        raise ValueError("CLAUSY_KEYWORD_ALERTS_KEYWORDS must be set when alerts are enabled")

    return KeywordAlertConfig(
        enabled=enabled,
        keywords=keywords,
        case_sensitive=_env_bool("CLAUSY_KEYWORD_ALERTS_CASE_SENSITIVE", False),
        max_alerts_per_window=max(1, int(os.environ.get("CLAUSY_KEYWORD_ALERTS_MAX_PER_WINDOW", "1"))),
        window_seconds=max(1, int(os.environ.get("CLAUSY_KEYWORD_ALERTS_WINDOW_SECONDS", "300"))),
        bot_token=(os.environ.get("CLAUSY_ALERT_TELEGRAM_BOT_TOKEN") or "").strip(),
        chat_id=(os.environ.get("CLAUSY_ALERT_TELEGRAM_CHAT_ID") or "").strip(),
        api_base=(os.environ.get("CLAUSY_ALERT_TELEGRAM_API_BASE") or "https://api.telegram.org").strip(),
        host=(os.environ.get("CLAUSY_ALERT_EMAIL_SMTP_HOST") or "").strip(),
        port=_env_smtp_port(),
        username=(os.environ.get("CLAUSY_ALERT_EMAIL_USERNAME") or "").strip(),
        password=(os.environ.get("CLAUSY_ALERT_EMAIL_PASSWORD") or "").strip(),
        from_addr=(os.environ.get("CLAUSY_ALERT_EMAIL_FROM") or "").strip(),
        to_addrs=_split_csv(os.environ.get("CLAUSY_ALERT_EMAIL_TO", "")),
        starttls=_env_bool("CLAUSY_ALERT_EMAIL_STARTTLS", True),
    )


class KeywordDetector:
    def __init__(self, keywords: tuple[str, ...], *, case_sensitive: bool = False):
        self.keywords = tuple(dict.fromkeys(keywords))
        self.case_sensitive = case_sensitive
        self._needles = self.keywords if case_sensitive else tuple(k.lower() for k in self.keywords)

    def match(self, text: str) -> list[str]:
        if not text:
            return []
        haystack = text if self.case_sensitive else text.lower()
        out: list[str] = []
        for original, needle in zip(self.keywords, self._needles):
            if needle and needle in haystack and original not in out:
                out.append(original)
        return out


class AlertRateLimiter:
    def __init__(self, *, window_seconds: int, max_alerts_per_window: int):
        self.window_seconds = max(1, int(window_seconds))
        self.max_alerts_per_window = max(1, int(max_alerts_per_window))
        self._lock = threading.Lock()
        self._events: dict[tuple[str, str], list[float]] = {}

    def should_send(self, session_id: str, keyword: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        key = (session_id or "default", keyword)
        with self._lock:
            ts = [t for t in self._events.get(key, []) if now - t < self.window_seconds]
            allow = len(ts) < self.max_alerts_per_window
            if allow:
                ts.append(now)
            self._events[key] = ts
            return allow


class TelegramNotifier:
    def __init__(self, *, bot_token: str, chat_id: str, api_base: str = "https://api.telegram.org"):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_base = api_base.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, alert: AlertEvent) -> None:
        if not self.enabled:
            return
        url = f"{self.api_base}/bot{self.bot_token}/sendMessage"
        text = (
            "[Clausy Keyword Alert]\n"
            f"provider={alert.provider} session={alert.session_id}\n"
            f"direction={alert.direction} keyword={alert.keyword}\n"
            f"excerpt={alert.excerpt}"
        )
        requests.post(url, json={"chat_id": self.chat_id, "text": text}, timeout=10)


class EmailNotifier:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_addr: str,
        to_addrs: tuple[str, ...],
        starttls: bool = True,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.starttls = starttls

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_addr and self.to_addrs)

    def send(self, alert: AlertEvent) -> None:
        if not self.enabled:
            return
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg["Subject"] = f"[Clausy] Keyword alert: {alert.keyword}"
        msg.set_content(
            "Clausy keyword alert\n\n"
            f"provider: {alert.provider}\n"
            f"session: {alert.session_id}\n"
            f"direction: {alert.direction}\n"
            f"keyword: {alert.keyword}\n"
            f"excerpt: {alert.excerpt}\n"
        )

        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)


class AlertDispatcher:
    def __init__(self, notifiers: list[Any]):
        self.notifiers = list(notifiers)

    def send(self, alert: AlertEvent) -> None:
        for notifier in self.notifiers:
            try:
                notifier.send(alert)
            except Exception as e:
                logger.warning("keyword alert notifier failed: %s", e)
