"""Tests for telegram_bot.py."""
from telegram_bot import allowed


class FakeUser:
    id = 123


class FakeUpdate:
    effective_user = FakeUser()


def test_allowed_user(monkeypatch):
    monkeypatch.setattr("telegram_bot.ALLOWED_USER_IDS", {123})
    assert allowed(FakeUpdate()) is True
