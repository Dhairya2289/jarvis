"""Tests that all ported V2 modules are importable from compat."""
from __future__ import annotations


class TestCompatImports:
    def test_swarm(self):
        from jarvis.compat import swarm
        assert callable(swarm.smart_delegate)

    def test_planner(self):
        from jarvis.compat import planner
        assert callable(planner.get_todays_tasks)

    def test_daemon(self):
        from jarvis.compat import daemon
        assert callable(daemon.main)

    def test_world_model(self):
        from jarvis.compat import world_model
        assert callable(world_model.start_background)

    def test_telegram_bot(self):
        from jarvis.compat import telegram_bot
        assert callable(telegram_bot.main)

    def test_voice_assistant(self):
        from jarvis.compat import voice_assistant
        assert callable(voice_assistant.run_voice_loop)

    def test_tts(self):
        from jarvis.compat import tts
        assert callable(tts.speak)