"""Notifier contract + channel resolution.

A Notifier sends a plain-text message somewhere (Telegram, Discord, or nowhere).
`get_notifier()` picks the channel from `NOTIFY_CHANNEL` env (telegram|discord|none).
The HTTP transport is injectable so senders are unit-testable without network.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Protocol

import httpx

Transport = Callable[[str, dict[str, Any]], None]


def default_post(url: str, payload: dict[str, Any]) -> None:
    httpx.post(url, json=payload, timeout=15.0).raise_for_status()


class Notifier(Protocol):
    name: str

    def send(self, text: str) -> bool:
        """Send a message; return True on success. Never raises."""
        ...


class NullNotifier:
    name = "none"

    def send(self, text: str) -> bool:  # noqa: ARG002
        return False


def get_notifier(*, transport: Transport | None = None) -> Notifier:
    channel = os.getenv("NOTIFY_CHANNEL", "none").lower()
    if channel == "telegram":
        from job_hunt.notify.telegram import TelegramNotifier

        return TelegramNotifier(
            token=os.getenv("TELEGRAM_BOT_TOKEN"),
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            transport=transport,
        )
    if channel == "discord":
        from job_hunt.notify.discord import DiscordNotifier

        return DiscordNotifier(
            webhook_url=os.getenv("DISCORD_WEBHOOK_URL"), transport=transport
        )
    return NullNotifier()
