"""
Tests for the notification path.

The app has to reach you when you are not looking at it — that is the whole
point of it for someone who may be away for weeks. It could not. The scheduler
ran every thirty minutes with no channel to send through, and the one formatter
that would have rendered an alert raised on every call.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.notifications import (
    Alert,
    EmailChannel,
    NotificationService,
)


def _alert(**overrides) -> Alert:
    fields = dict(
        ticker="TPCS",
        buy_confidence=85.0,
        signal_strength="STRONG",
        entry_price=4.56,
        target_price=14.00,
        stop_loss=3.25,
        kelly_size=0.05,
        message="Cena pod green line.",
    )
    fields.update(overrides)
    return Alert(**fields)


def _channel() -> EmailChannel:
    return EmailChannel(
        "smtp.gmail.com", 587, "me@example.com", "pw",
        "me@example.com", "me@example.com",
    )


# ==============================================================================
# The formatter ran zero times successfully
# ==============================================================================

class TestHtmlFormatting:
    def test_formatting_an_alert_does_not_raise(self):
        """
        Every price row was written as `{alert.entry_price:.2f if ... else ...}`.
        A conditional expression is not a format spec — ValueError, every call,
        swallowed by `send()`'s except block and returned as a bare False.
        """
        html = _channel()._format_html(_alert())
        assert "TPCS" in html
        assert "$4.56" in html

    def test_missing_prices_render_as_a_dash_not_a_crash(self):
        """
        The conditional was trying to express exactly this. It just could not
        be written there.
        """
        html = _channel()._format_html(
            _alert(entry_price=None, target_price=None,
                   stop_loss=None, kelly_size=None)
        )
        assert "—" in html
        assert "None" not in html

    def test_zero_is_a_price_not_a_gap(self):
        """
        A falsy check would have printed a dash for a genuine 0.00. The guard
        is `is not None` for that reason.
        """
        html = _channel()._format_html(_alert(entry_price=0.0))
        assert "$0.00" in html

    def test_kelly_size_renders_as_a_percentage(self):
        html = _channel()._format_html(_alert(kelly_size=0.05))
        assert "5.0%" in html


# ==============================================================================
# A channel can actually be built
# ==============================================================================

class TestChannelConstruction:
    def _settings(self, **overrides):
        settings = MagicMock()
        settings.TELEGRAM_BOT_TOKEN = None
        settings.TELEGRAM_CHAT_ID = None
        settings.SMTP_SERVER = "smtp.gmail.com"
        settings.SMTP_PORT = 587
        settings.SMTP_USERNAME = "me@example.com"
        settings.SMTP_PASSWORD = "app-password"
        settings.EMAIL_RECIPIENT = "me@example.com"
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def test_the_env_that_exists_builds_an_email_channel(self):
        """
        `from_env` read SMTP_FROM_EMAIL and SMTP_TO_EMAIL — two names that
        appear nowhere in .env and nowhere else in the codebase. The
        `all([...])` check could never pass, so the automated stack had no
        channel while a configured mailbox sat in .env as EMAIL_RECIPIENT.
        """
        with patch("app.services.notifications.Settings",
                   return_value=self._settings()):
            service = NotificationService.from_env()

        assert len(service.channels) == 1
        assert isinstance(service.channels[0], EmailChannel)

    def test_gmail_sends_as_the_account_that_authenticates(self):
        with patch("app.services.notifications.Settings",
                   return_value=self._settings()):
            channel = NotificationService.from_env().channels[0]
        assert channel.from_email == "me@example.com"
        assert channel.username == channel.from_email

    def test_a_missing_setting_is_named_not_swallowed(self):
        """
        "No notification channels configured" told you nothing about which one.
        """
        with patch("app.services.notifications.Settings",
                   return_value=self._settings(SMTP_PASSWORD=None)):
            service = NotificationService.from_env()

        assert service.channels == []
        assert any("SMTP_PASSWORD" in reason for reason in service.unconfigured)

    def test_telegram_absence_is_reported_too(self):
        with patch("app.services.notifications.Settings",
                   return_value=self._settings()):
            service = NotificationService.from_env()
        assert any("Telegram" in reason for reason in service.unconfigured)


# ==============================================================================
# Sending
# ==============================================================================

class TestSending:
    @pytest.mark.asyncio
    async def test_a_send_reaches_smtp(self):
        smtp = MagicMock()
        with patch("app.services.notifications.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.__enter__.return_value = smtp
            sent = await _channel().send(_alert())

        assert sent is True
        smtp.login.assert_called_once()
        smtp.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_an_smtp_failure_reports_false(self):
        with patch("app.services.notifications.smtplib.SMTP",
                   side_effect=OSError("connection refused")):
            assert await _channel().send(_alert()) is False
