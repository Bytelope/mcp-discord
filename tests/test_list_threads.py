"""Unit tests for list_threads: name_contains triggers a full-archive scan."""

import os
import types

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token-not-real")

from discord_mcp import server  # noqa: E402


def _thread(name, tid, archived=False):
    return types.SimpleNamespace(name=name, id=tid, archived=archived, message_count=1)


class FakeChannel:
    def __init__(self, active, archived):
        self.threads = active
        self._archived = archived
        self.archived_limit_seen = "unset"

    def archived_threads(self, limit=50):
        self.archived_limit_seen = limit

        async def gen():
            for t in self._archived:
                yield t

        return gen()


class FakeClient:
    def __init__(self, channel):
        self._channel = channel

    async def fetch_channel(self, cid):
        return self._channel


@pytest.mark.asyncio
async def test_name_contains_scans_full_archive(monkeypatch):
    channel = FakeChannel(
        active=[_thread("[TODO] fix login", 1), _thread("[DONE] old", 2)],
        archived=[_thread("[TODO] ancient ticket", 3, archived=True)],
    )
    monkeypatch.setattr(server, "discord_client", FakeClient(channel))

    result = await server.call_tool(
        "list_threads", {"channel_id": "123", "name_contains": "[todo]"}
    )
    text = result[0].text
    assert "[TODO] fix login" in text
    assert "[TODO] ancient ticket" in text
    assert "[DONE] old" not in text
    # the filter must remove the 50-thread archive cap
    assert channel.archived_limit_seen is None


@pytest.mark.asyncio
async def test_include_archived_keeps_cap(monkeypatch):
    channel = FakeChannel(active=[_thread("a", 1)], archived=[_thread("b", 2, archived=True)])
    monkeypatch.setattr(server, "discord_client", FakeClient(channel))

    result = await server.call_tool(
        "list_threads", {"channel_id": "123", "include_archived": True}
    )
    assert "1 active, 1 archived" in result[0].text
    assert channel.archived_limit_seen == 50


@pytest.mark.asyncio
async def test_name_contains_no_match(monkeypatch):
    channel = FakeChannel(active=[_thread("a", 1)], archived=[])
    monkeypatch.setattr(server, "discord_client", FakeClient(channel))

    result = await server.call_tool(
        "list_threads", {"channel_id": "123", "name_contains": "[TODO]"}
    )
    assert "No matching threads" in result[0].text
