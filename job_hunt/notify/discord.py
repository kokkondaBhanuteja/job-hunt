"""Discord notifier — posts to an incoming webhook URL."""
from __future__ import annotations

from job_hunt.notify.base import Transport, default_post


class DiscordNotifier:
    name = "discord"

    def __init__(self, *, webhook_url: str | None, transport: Transport | None = None):
        self._webhook_url = webhook_url
        self._post = transport or default_post

    def send(self, text: str) -> bool:
        if not self._webhook_url:
            return False
        try:
            self._post(self._webhook_url, {"content": text})
            return True
        except Exception:  # noqa: BLE001
            return False
