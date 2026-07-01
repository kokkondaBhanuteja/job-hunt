"""Notifications — Telegram/Discord daily report."""
from __future__ import annotations

from job_hunt.notify.base import Notifier, NullNotifier, get_notifier
from job_hunt.notify.report import build_daily_report, send_report

__all__ = ["Notifier", "NullNotifier", "get_notifier", "build_daily_report", "send_report"]
