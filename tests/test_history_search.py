"""Unit tests for history pagination kwargs and the search_messages matcher."""

import os

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token-not-real")

import discord  # noqa: E402

from discord_mcp.server import _compile_matcher, _history_kwargs  # noqa: E402


class TestHistoryKwargs:
    def test_empty_arguments_yield_no_kwargs(self):
        assert _history_kwargs({}) == {}

    def test_before_message_id_maps_to_object(self):
        kwargs = _history_kwargs({"before_message_id": "1376248378022826037"})
        assert isinstance(kwargs["before"], discord.Object)
        assert kwargs["before"].id == 1376248378022826037
        assert "after" not in kwargs and "oldest_first" not in kwargs

    def test_after_message_id_maps_to_object(self):
        kwargs = _history_kwargs({"after_message_id": "42"})
        assert isinstance(kwargs["after"], discord.Object)
        assert kwargs["after"].id == 42

    def test_oldest_first_passthrough_true_and_false(self):
        assert _history_kwargs({"oldest_first": True})["oldest_first"] is True
        # Explicit false must be forwarded, not dropped: it overrides
        # discord.py's implicit oldest-first flip when `after` is set.
        kwargs = _history_kwargs({"after_message_id": "42", "oldest_first": False})
        assert kwargs["oldest_first"] is False

    def test_absent_oldest_first_not_forwarded(self):
        assert "oldest_first" not in _history_kwargs({"before_message_id": "42"})

    def test_bad_message_id_raises(self):
        with pytest.raises(ValueError):
            _history_kwargs({"before_message_id": "not-a-snowflake"})


class TestCompileMatcher:
    def test_substring_is_case_insensitive(self):
        match = _compile_matcher("Clementine", is_regex=False)
        assert match("a wild CLEMENTINE appeared")
        assert not match("no oranges here")

    def test_regex_matches(self):
        match = _compile_matcher(r"fib\(\d+\)", is_regex=True)
        assert match("script that computes fib(70)")
        assert not match("fibonacci")

    def test_regex_is_case_insensitive(self):
        match = _compile_matcher(r"oteno", is_regex=True)
        assert match("A wild Oteno appeared.")

    def test_invalid_regex_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid regex"):
            _compile_matcher("[unclosed", is_regex=True)

    def test_substring_never_treated_as_regex(self):
        match = _compile_matcher("[unclosed", is_regex=False)
        assert match("literal [unclosed bracket")
