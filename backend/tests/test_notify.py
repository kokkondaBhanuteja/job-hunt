"""Tests for notifications + the daily report (injected transport, no network)."""
from __future__ import annotations

from job_hunt import services
from job_hunt.notify import base
from job_hunt.notify.base import NullNotifier
from job_hunt.notify.discord import DiscordNotifier
from job_hunt.notify.telegram import TelegramNotifier


def _job(db):
    return db.insert_job_if_new(
        dedup_hash="n1", source="remoteok", source_job_id=None, title="BE", company="Acme",
        location="remote", description="d", apply_url="u", posted_date=None,
    )


# ---------- notifiers ----------


def test_telegram_send_posts_message():
    calls: list[tuple[str, dict]] = []
    n = TelegramNotifier(token="t", chat_id="c", transport=lambda url, p: calls.append((url, p)))
    assert n.send("hello") is True
    assert "sendMessage" in calls[0][0]
    assert calls[0][1]["text"] == "hello" and calls[0][1]["chat_id"] == "c"


def test_telegram_without_config_returns_false():
    assert TelegramNotifier(token=None, chat_id=None).send("x") is False


def test_discord_send_posts_content():
    calls: list[tuple[str, dict]] = []
    n = DiscordNotifier(webhook_url="https://hook", transport=lambda url, p: calls.append((url, p)))
    assert n.send("hi") is True
    assert calls[0][1]["content"] == "hi"


def test_null_notifier_returns_false():
    assert NullNotifier().send("x") is False


def test_send_failure_is_swallowed():
    def boom(url, payload):
        raise RuntimeError("network down")

    assert TelegramNotifier(token="t", chat_id="c", transport=boom).send("x") is False


# ---------- channel resolution ----------


def test_get_notifier_defaults_to_null(monkeypatch):
    monkeypatch.delenv("NOTIFY_CHANNEL", raising=False)
    assert isinstance(base.get_notifier(), NullNotifier)


def test_get_notifier_telegram(monkeypatch):
    monkeypatch.setenv("NOTIFY_CHANNEL", "telegram")
    assert isinstance(base.get_notifier(), TelegramNotifier)


# ---------- daily report ----------


def test_build_daily_report_summarizes(tmp_db):
    _job(tmp_db)
    text = services.daily_report_text()  # service composes dashboard → report (layering)
    assert "Job-Hunt daily report" in text
    assert "Jobs tracked: 1" in text
    assert "LLM spend:" in text


def test_send_daily_report_uses_notifier(tmp_db):
    _job(tmp_db)
    sent: list[str] = []

    class _Fake:
        name = "fake"

        def send(self, text: str) -> bool:
            sent.append(text)
            return True

    assert services.send_daily_report(_Fake()) is True
    assert "Job-Hunt daily report" in sent[0]


def test_send_test_notification_uses_configured_channel(monkeypatch):
    sent: list[str] = []

    class _Fake:
        name = "telegram"

        def send(self, text: str) -> bool:
            sent.append(text)
            return True

    monkeypatch.setattr(base, "get_notifier", lambda: _Fake())
    assert services.send_test_notification() == {"channel": "telegram", "sent": True}
    assert sent and "wired" in sent[0]


def test_send_test_notification_none_channel(monkeypatch):
    monkeypatch.delenv("NOTIFY_CHANNEL", raising=False)
    assert services.send_test_notification() == {"channel": "none", "sent": False}
