"""Unit tests for history pagination (before/after_message_id) and search_messages.

These exercise the real call_tool dispatch with a fake Discord client, so the
before/after passthrough, bounded-scan, truncation reporting and resume cursor
are all covered without a live gateway.
"""

import os
import datetime

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token-not-real")

from discord_mcp import server  # noqa: E402


class FakeAuthor:
    def __init__(self, name, uid):
        self.name = name
        self.id = uid

    def __str__(self):
        return self.name


class FakeMessage:
    def __init__(self, mid, content, author="alice", uid=1):
        self.id = mid
        self.content = content
        self.author = FakeAuthor(author, uid)
        self.reactions = []
        self.attachments = []
        # deterministic timestamps derived from id
        self.created_at = datetime.datetime(
            2025, 1, 1, tzinfo=datetime.timezone.utc
        ) + datetime.timedelta(seconds=mid)


class FakeHistory:
    """Async iterator mimicking discord.py channel.history(limit, before)."""

    def __init__(self, messages, limit, before=None, after=None, oldest_first=None):
        pool = list(messages)
        if before is not None:
            pool = [m for m in pool if m.id < int(before.id)]
        if after is not None:
            pool = [m for m in pool if m.id > int(after.id)]
        # discord.py: oldest-first when oldest_first=True, OR when `after` is set
        # and oldest_first was left unset; newest-first otherwise.
        if oldest_first is None:
            ascending = after is not None
        else:
            ascending = bool(oldest_first)
        pool.sort(key=lambda m: m.id, reverse=not ascending)
        self._page = pool[:limit]

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._page):
            raise StopAsyncIteration
        m = self._page[self._i]
        self._i += 1
        return m


class FakeChannel:
    def __init__(self, messages):
        # newest-first
        self.messages = sorted(messages, key=lambda m: m.id, reverse=True)

    def history(self, limit=100, before=None, after=None, oldest_first=None, **kw):
        return FakeHistory(self.messages, limit, before, after, oldest_first)


class FakeClient:
    def __init__(self, channel):
        self._channel = channel

    async def fetch_channel(self, cid):
        return self._channel


@pytest.fixture
def wire_client(monkeypatch):
    def _wire(messages):
        channel = FakeChannel(messages)
        monkeypatch.setattr(server, "discord_client", FakeClient(channel))
        return channel
    return _wire


def _text(result):
    return result[0].text


@pytest.mark.asyncio
async def test_read_messages_before_cursor_in_header(wire_client):
    msgs = [FakeMessage(i, f"msg {i}") for i in range(1, 6)]
    wire_client(msgs)
    out = _text(await server.call_tool("read_messages", {"channel_id": "1", "limit": 2}))
    # newest-first, limit 2 -> ids 5,4; page full -> continue hint with oldest id (4)
    assert "[msg_id:5]" in out and "[msg_id:4]" in out
    assert "page full" in out and "before_message_id=4" in out


@pytest.mark.asyncio
async def test_read_messages_before_filters_older(wire_client):
    msgs = [FakeMessage(i, f"msg {i}") for i in range(1, 6)]
    wire_client(msgs)
    out = _text(await server.call_tool(
        "read_messages", {"channel_id": "1", "limit": 10, "before_message_id": "3"}))
    assert "before 3" in out
    assert "[msg_id:2]" in out and "[msg_id:1]" in out
    assert "[msg_id:3]" not in out and "[msg_id:4]" not in out


@pytest.mark.asyncio
async def test_read_messages_oldest_first(wire_client):
    msgs = [FakeMessage(i, f"msg {i}") for i in range(1, 6)]
    wire_client(msgs)
    out = _text(await server.call_tool(
        "read_messages", {"channel_id": "1", "limit": 3, "oldest_first": True}))
    # oldest-first -> ids 1,2,3 in that order
    assert out.index("[msg_id:1]") < out.index("[msg_id:2]") < out.index("[msg_id:3]")


@pytest.mark.asyncio
async def test_read_messages_after_filters_newer(wire_client):
    msgs = [FakeMessage(i, f"msg {i}") for i in range(1, 6)]
    wire_client(msgs)
    out = _text(await server.call_tool(
        "read_messages", {"channel_id": "1", "limit": 10, "after_message_id": "3"}))
    assert "after 3" in out
    # only ids > 3, and oldest-first ordering (after implies ascending)
    assert "[msg_id:4]" in out and "[msg_id:5]" in out
    assert "[msg_id:3]" not in out and "[msg_id:2]" not in out
    assert out.index("[msg_id:4]") < out.index("[msg_id:5]")


@pytest.mark.asyncio
async def test_read_messages_full_ascending_page_hints_forward(wire_client):
    # ascending page that is full must advise after_message_id (forward), not before
    msgs = [FakeMessage(i, f"msg {i}") for i in range(1, 11)]
    wire_client(msgs)
    out = _text(await server.call_tool(
        "read_messages", {"channel_id": "1", "limit": 3, "oldest_first": True}))
    # oldest-first page = 1,2,3 ; newest of page is 3 -> continue forward after 3
    assert "after_message_id=3 to continue forward" in out
    assert "before_message_id" not in out


@pytest.mark.asyncio
async def test_read_messages_rejects_garbage_cursor(wire_client):
    wire_client([FakeMessage(1, "x")])
    out = _text(await server.call_tool(
        "read_messages", {"channel_id": "1", "before_message_id": "not-a-number"}))
    assert "numeric Discord message ID" in out


@pytest.mark.asyncio
async def test_search_rejects_garbage_max_pages(wire_client):
    wire_client([FakeMessage(1, "x")])
    out = _text(await server.call_tool(
        "search_messages", {"channel_id": "1", "query": "x", "max_pages": "lots"}))
    assert "must be integers" in out


@pytest.mark.asyncio
async def test_search_zero_max_pages_clamped(wire_client):
    # max_pages=0 must clamp to >=1, not silently scan nothing / emit None cursor
    msgs = [FakeMessage(i, "hello" if i == 1 else "x") for i in range(1, 4)]
    wire_client(msgs)
    out = _text(await server.call_tool(
        "search_messages", {"channel_id": "1", "query": "hello", "max_pages": 0}))
    assert "before_message_id=None" not in out
    assert "[msg_id:1]" in out  # clamped to 1 page, channel small -> found + exhaustive


@pytest.mark.asyncio
async def test_search_finds_match_exhaustive(wire_client):
    msgs = [FakeMessage(i, "hello world" if i == 7 else "nope") for i in range(1, 20)]
    wire_client(msgs)
    out = _text(await server.call_tool(
        "search_messages", {"channel_id": "1", "query": "hello"}))
    assert "[msg_id:7]" in out
    assert "1 match(es)" in out
    assert "exhaustive" in out  # < 100 msgs -> reached channel start


@pytest.mark.asyncio
async def test_search_truncates_on_max_pages(wire_client):
    # 250 messages, none match -> must hit max_pages and report truncation loudly
    msgs = [FakeMessage(i, "nope") for i in range(1, 251)]
    wire_client(msgs)
    out = _text(await server.call_tool(
        "search_messages", {"channel_id": "1", "query": "needle", "max_pages": 2}))
    assert "0 match(es)" in out
    assert "SCAN TRUNCATED" in out
    assert "max_pages=2" in out
    assert "resume" in out.lower() and "before_message_id=" in out
    # scanned exactly 2 pages of 100
    assert "scanned 200 messages across 2 page(s)" in out


@pytest.mark.asyncio
async def test_search_author_filter(wire_client):
    msgs = [FakeMessage(i, "ping", author="bob", uid=99) if i == 5
            else FakeMessage(i, "ping", author="alice", uid=1) for i in range(1, 10)]
    wire_client(msgs)
    out = _text(await server.call_tool(
        "search_messages", {"channel_id": "1", "query": "ping", "author": "bob"}))
    assert "[msg_id:5]" in out
    assert "1 match(es)" in out
    assert "[msg_id:4]" not in out
