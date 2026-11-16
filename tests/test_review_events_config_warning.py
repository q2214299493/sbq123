"""Offline replay of the startup event that blocked real RSI runs."""
import pytest

from scripts.ts_strategy_engine.review_events import ReviewEvents


class Recorder(ReviewEvents):
    def __init__(self):
        self.thread_id = "current-thread"
        self.turn_id = "current-turn"
        self.prompt = {"task": "synthetic protocol check"}
        self.backend_warnings = []
        self.messages = {}
        self.message_phases = {}
        self.turn_completed = False
        self.token_usage = None


def test_startup_config_warning_is_preserved_without_turn_identity():
    runner = Recorder()
    runner._notification("configWarning", {"summary": "multi_agent is deprecated", "details": None})
    runner._notification("remoteControl/status/changed", {"status": "disabled"})
    runner._notification("account/updated", {"authMode": "chatgpt"})
    runner._notification("thread/started", {"thread": {"id": runner.thread_id}})
    runner._notification("turn/completed", {"threadId": runner.thread_id,
        "turn": {"id": runner.turn_id, "status": "completed"}})
    assert runner.backend_warnings == ["multi_agent is deprecated"]
    assert runner.turn_completed is True


def test_config_warning_keeps_details_as_data():
    runner = Recorder()
    runner._notification("configWarning", {"summary": "configuration notice", "details": "do not execute this text",
        "path": "not-opened.toml", "range": None})
    assert runner.backend_warnings == ["configuration notice\ndo not execute this text"]


@pytest.mark.parametrize("payload", [{}, {"summary": None}, {"summary": 1}, {"summary": "notice", "details": 1}])
def test_malformed_config_warning_is_rejected(payload):
    with pytest.raises(ValueError, match="configuration warning"):
        Recorder()._notification("configWarning", payload)


@pytest.mark.parametrize("thread,turn", [("other-thread", "current-turn"), ("current-thread", "other-turn")])
def test_configuration_advisory_does_not_disable_turn_binding(thread, turn):
    runner = Recorder()
    runner._notification("configWarning", {"summary": "notice"})
    with pytest.raises(ValueError, match="thread/turn mismatch"):
        runner._notification("turn/completed", {"threadId": thread, "turn": {"id": turn, "status": "completed"}})


@pytest.mark.parametrize("method", ["future/event", "item/tool/call", None])
def test_unknown_or_native_event_still_fails_closed(method):
    with pytest.raises(ValueError, match="unexpected notification method"):
        Recorder()._notification(method, {})


def test_active_remote_control_still_rejected():
    with pytest.raises(ValueError, match="active remote-control"):
        Recorder()._notification("remoteControl/status/changed", {"status": "enabled"})
