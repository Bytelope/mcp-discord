"""Unit tests for reaction-user expansion in read_messages output formatting."""

import os

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token-not-real")

from discord_mcp import server  # noqa: E402


def _build_format_reaction(include_users: bool):
    """Exercise the real module-level reaction formatter used by read_messages.

    The formatter renders whatever dict it is handed, so we return the live
    function directly instead of a local copy that would silently drift."""
    return server._format_reaction


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



class TestCompactFormat:
    def _msg(self, **over):
        m = {"id": "1", "author": "a", "content": "hi",
             "timestamp": "2026-06-12T20:24:06.609000+00:00",
             "reactions": [], "attachments": []}
        m.update(over)
        return m

    def test_compact_omits_empty_reactions_and_trims_timestamp(self):
        out = server._format_message(self._msg())
        assert "No reactions" not in out
        assert "(2026-06-12T20:24)" in out

    def test_compact_keeps_real_reactions(self):
        out = server._format_message(self._msg(reactions=[{"emoji": "x", "count": 2}]))
        assert "Reactions: x(2)" in out

    def test_non_compact_restores_legacy_format(self, monkeypatch):
        monkeypatch.setattr(server, "_COMPACT", False)
        out = server._format_message(self._msg())
        assert "Reactions: No reactions" in out
        assert "(2026-06-12T20:24:06.609000+00:00)" in out
