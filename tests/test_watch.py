"""Unit tests for `discord_mcp.watch`.

These tests deliberately avoid importing `discord_mcp.server` because the
server module performs a hard-fail import-time check on `DISCORD_TOKEN`.
The watch module has no such side-effects, which is why the production
wire-up keeps env reads out of `watch.py`.
"""

import asyncio
import subprocess
import types
from unittest.mock import MagicMock

import pytest

from discord_mcp.watch import (
    MessageWatcher,
    format_notification,
    parse_watch_channels,
    tmux_inject,
)


# ---------- parse_watch_channels ----------

class TestParseWatchChannels:
    def test_empty_returns_empty_set(self):
        assert parse_watch_channels(None) == set()
        assert parse_watch_channels("") == set()

    def test_single_id(self):
        assert parse_watch_channels("12345") == {"12345"}

    def test_multiple_ids_strip_whitespace(self):
        assert parse_watch_channels(" 1, 2 ,3 ") == {"1", "2", "3"}

    def test_skip_empty_entries(self):
        assert parse_watch_channels("1,,2,") == {"1", "2"}


# ---------- format_notification ----------

class TestFormatNotification:
    def test_empty_returns_empty_string(self):
        assert format_notification([]) == ""

    def test_single_message(self):
        out = format_notification([("general", "jahwag")])
        assert out == "[discord] 1 new: #general(@jahwag)"

    def test_multiple_authors_same_channel(self):
        out = format_notification([
            ("general", "jahwag"),
            ("general", "amara"),
        ])
        assert out == "[discord] 2 new: #general(@jahwag,@amara)"

    def test_dedups_repeat_author_in_window(self):
        out = format_notification([
            ("general", "jahwag"),
            ("general", "jahwag"),
            ("general", "jahwag"),
        ])
        # Total count reflects all messages, mention list is deduped.
        assert out == "[discord] 3 new: #general(@jahwag)"

    def test_multiple_channels_sorted_stable(self):
        out = format_notification([
            ("tasks", "amara"),
            ("general", "jahwag"),
        ])
        # alphabetical channel order keeps output deterministic
        assert out == "[discord] 2 new: #general(@jahwag) #tasks(@amara)"


# ---------- tmux_inject ----------

class TestTmuxInject:
    def test_no_target_returns_false(self):
        assert tmux_inject("", "msg") is False

    def test_no_text_returns_false(self):
        assert tmux_inject("target", "") is False

    def test_calls_send_keys_then_enter(self):
        runner = MagicMock(return_value=MagicMock())
        ok = tmux_inject("worker:0", "[discord] 1 new: ...", runner=runner)
        assert ok is True
        assert runner.call_count == 2
        first_call_args = runner.call_args_list[0][0][0]
        second_call_args = runner.call_args_list[1][0][0]
        assert first_call_args == [
            "tmux", "send-keys", "-t", "worker:0", "-l",
            "[discord] 1 new: ...",
        ]
        assert second_call_args == [
            "tmux", "send-keys", "-t", "worker:0", "Enter",
        ]

    def test_subprocess_error_returns_false_no_raise(self):
        runner = MagicMock(side_effect=subprocess.CalledProcessError(1, "tmux"))
        assert tmux_inject("worker:0", "msg", runner=runner) is False

    def test_tmux_not_installed_returns_false(self):
        runner = MagicMock(side_effect=FileNotFoundError("tmux"))
        assert tmux_inject("worker:0", "msg", runner=runner) is False

    def test_timeout_returns_false(self):
        runner = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="tmux", timeout=5))
        assert tmux_inject("worker:0", "msg", runner=runner) is False

    def test_special_chars_passed_literally(self):
        # tmux send-keys -l treats input as literal; quotes/backticks/dollars
        # must pass through without shell interpretation.
        runner = MagicMock(return_value=MagicMock())
        payload = "[discord] msg with `back$ticks` & 'quotes' \"and\" $vars"
        tmux_inject("worker:0", payload, runner=runner)
        sent = runner.call_args_list[0][0][0]
        assert sent[-1] == payload


# ---------- MessageWatcher ----------

def _fake_message(channel_id: str, author_name: str = "jahwag",
                  author_id: int = 100, is_bot: bool = False,
                  channel_name: str = "general"):
    """Build a duck-typed object that quacks like discord.Message for handle_message."""
    return types.SimpleNamespace(
        channel=types.SimpleNamespace(id=channel_id, name=channel_name),
        author=types.SimpleNamespace(
            id=author_id, name=author_name, bot=is_bot),
    )


class TestMessageWatcher:
    @pytest.fixture
    def collector(self):
        notifications: list[str] = []
        return notifications

    @pytest.fixture
    def watcher(self, collector):
        # Tiny debounce so tests stay fast.
        return MessageWatcher(
            watch_channel_ids={"100", "200"},
            on_notify=collector.append,
            debounce_seconds=0.05,
        )

    async def test_filters_bot_self(self, watcher, collector):
        watcher.set_bot_user_id(999)
        await watcher.handle_message(_fake_message("100", author_id=999))
        await asyncio.sleep(0.1)
        assert collector == []

    async def test_filters_any_bot(self, watcher, collector):
        await watcher.handle_message(
            _fake_message("100", author_name="someBot", is_bot=True))
        await asyncio.sleep(0.1)
        assert collector == []

    async def test_filters_unwatched_channel(self, watcher, collector):
        await watcher.handle_message(_fake_message("999"))
        await asyncio.sleep(0.1)
        assert collector == []

    async def test_emits_after_debounce(self, watcher, collector):
        await watcher.handle_message(_fake_message("100"))
        # Before debounce expires nothing has fired.
        assert collector == []
        await asyncio.sleep(0.1)
        assert len(collector) == 1
        assert "@jahwag" in collector[0]
        assert "#general" in collector[0]

    async def test_batches_burst_within_window(self, watcher, collector):
        await watcher.handle_message(_fake_message("100", "jahwag"))
        await watcher.handle_message(
            _fake_message("100", "amara", author_id=101))
        await watcher.handle_message(
            _fake_message("100", "athena", author_id=102))
        await asyncio.sleep(0.1)
        assert len(collector) == 1
        assert "3 new" in collector[0]
        # All three authors should appear, single channel
        assert "@jahwag" in collector[0]
        assert "@amara" in collector[0]
        assert "@athena" in collector[0]

    async def test_separate_bursts_emit_separately(self, watcher, collector):
        await watcher.handle_message(_fake_message("100"))
        await asyncio.sleep(0.1)
        await watcher.handle_message(
            _fake_message("200", "amara", author_id=101,
                          channel_name="tasks"))
        await asyncio.sleep(0.1)
        assert len(collector) == 2

    async def test_callback_exception_does_not_break_watcher(
            self, collector):
        boom_count = [0]

        def boom(_msg):
            boom_count[0] += 1
            raise RuntimeError("downstream broke")

        watcher = MessageWatcher(
            watch_channel_ids={"100"},
            on_notify=boom,
            debounce_seconds=0.05,
        )
        await watcher.handle_message(_fake_message("100"))
        await asyncio.sleep(0.1)
        # Second burst still triggers the callback — watcher kept running.
        await watcher.handle_message(_fake_message("100"))
        await asyncio.sleep(0.1)
        assert boom_count[0] == 2
