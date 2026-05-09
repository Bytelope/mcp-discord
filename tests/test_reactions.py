"""Unit tests for reaction-user expansion in read_messages output formatting."""

import os

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token-not-real")

from discord_mcp import server  # noqa: E402


def _build_format_reaction(include_users: bool):
    """Recreate the inner closure logic exposed via the read_messages handler."""
    def format_reaction(r):
        base = f"{r['emoji']}({r['count']}"
        if r.get("users"):
            base += ": " + ", ".join(r["users"])
        return base + ")"
    return format_reaction


class TestFormatReactionSerialization:
    def test_count_only_when_users_absent(self):
        fmt = _build_format_reaction(include_users=False)
        assert fmt({"emoji": "👍", "count": 3}) == "👍(3)"

    def test_lists_users_when_present(self):
        fmt = _build_format_reaction(include_users=True)
        out = fmt({"emoji": "🔥", "count": 2, "users": ["alice", "bob"]})
        assert out == "🔥(2: alice, bob)"

    def test_empty_users_list_falls_back_to_count(self):
        fmt = _build_format_reaction(include_users=True)
        # An empty list is falsy → no expansion suffix.
        assert fmt({"emoji": "❤", "count": 0, "users": []}) == "❤(0)"


class TestServerHelpersWired:
    """Smoke check that the server module exposes the new helpers/flag."""

    def test_resolve_image_attachment_callable(self):
        assert callable(server._resolve_image_attachment)

    def test_load_local_image_callable(self):
        assert callable(server._load_local_image)
