"""
Notification adapters for trade events.

Supports Telegram and Discord via env vars:
- TRADE_TELEGRAM_TOKEN + TRADE_TELEGRAM_CHAT_ID
- TRADE_DISCORD_WEBHOOK
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from ..utils.logger import get_logger

logger = get_logger()


class NotificationAdapter(ABC):
    """Base class for notification adapters."""

    @abstractmethod
    def send(self, message: str) -> bool:
        """Send a notification message. Returns True on success."""
        ...

    def notify_signal(self, symbol: str, direction: str, size_usdt: float) -> bool:
        """Send a trade signal notification."""
        return self.send(f"Signal: {direction} {symbol} ${size_usdt:.2f}")

    def notify_fill(self, symbol: str, direction: str, fill_price: float) -> bool:
        """Send an order fill notification."""
        return self.send(f"Fill: {direction} {symbol} @ ${fill_price:,.2f}")

    def notify_error(self, message: str) -> bool:
        """Send an error notification."""
        return self.send(f"ERROR: {message}")

    def notify_panic(self, reason: str) -> bool:
        """Send a panic notification."""
        return self.send(f"PANIC: {reason}")


class TelegramAdapter(NotificationAdapter):
    """Send notifications via Telegram Bot API."""

    def __init__(self, token: str, chat_id: str):
        self._token = token
        self._chat_id = chat_id
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(self, message: str) -> bool:
        data = json.dumps({
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "HTML",
        }).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError) as e:
            logger.warning(f"Telegram notification failed: {e}")
            return False


class DiscordAdapter(NotificationAdapter):
    """Send notifications via Discord webhook."""

    def __init__(self, webhook_url: str):
        self._url = webhook_url

    def send(self, message: str) -> bool:
        data = json.dumps({"content": message}).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 204)
        except (urllib.error.URLError, OSError) as e:
            logger.warning(f"Discord notification failed: {e}")
            return False


class NoopAdapter(NotificationAdapter):
    """No-op adapter when no notification service is configured."""

    def send(self, message: str) -> bool:
        return True


def get_notification_adapter() -> NotificationAdapter:
    """
    Create notification adapter from environment variables.

    Checks for:
    - TRADE_TELEGRAM_TOKEN + TRADE_TELEGRAM_CHAT_ID -> TelegramAdapter
    - TRADE_DISCORD_WEBHOOK -> DiscordAdapter
    - Otherwise -> NoopAdapter (silent)
    """
    telegram_token = os.environ.get("TRADE_TELEGRAM_TOKEN")
    telegram_chat = os.environ.get("TRADE_TELEGRAM_CHAT_ID")
    discord_webhook = os.environ.get("TRADE_DISCORD_WEBHOOK")

    if telegram_token and telegram_chat:
        logger.info("Notifications: Telegram configured")
        return TelegramAdapter(telegram_token, telegram_chat)
    elif discord_webhook:
        logger.info("Notifications: Discord configured")
        return DiscordAdapter(discord_webhook)
    else:
        return NoopAdapter()
