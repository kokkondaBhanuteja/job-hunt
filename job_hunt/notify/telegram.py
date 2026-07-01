"""Telegram notifier — posts to the Bot API sendMessage endpoint."""
from __future__ import annotations

from job_hunt.notify.base import Transport, default_post


class TelegramNotifier:
    name = "telegram"

    def __init__(self, *, token: str | None, chat_id: str | None, transport: Transport | None = None):
        self._token = token
        self._chat_id = chat_id
        self._post = transport or default_post

    def send(self, text: str) -> bool:
        if not self._token or not self._chat_id:
            return False
        try:
            self._post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                {"chat_id": self._chat_id, "text": text},
            )
            return True
        except Exception:  # noqa: BLE001 — notifications must never crash a run
            return False
