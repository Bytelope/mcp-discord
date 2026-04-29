"""Optional Discord-message watcher that injects notifications into a tmux pane.

When `DISCORD_WATCH_CHANNELS` and `CLEM_TMUX_TARGET` are both set, the
running MCP server attaches a lightweight `on_message` listener that
debounces inbound messages from the configured channels and pushes a
single-line notification to the named tmux session via `tmux send-keys`.

The notification is intentionally minimal — channel + author only — so the
agent can decide whether to fetch full content via the existing
`read_messages` tool. This keeps PTY logs free of message bodies and lets
the agent prioritize against its current task.

Watcher logic is split into pure helpers (`parse_watch_channels`,
`format_notification`, `tmux_inject`) plus a stateful `MessageWatcher` so
that tests can drive each piece without a Discord gateway.
"""

import asyncio
import logging
import os
import subprocess
from typing import Callable, Optional

import discord

logger = logging.getLogger("discord-mcp.watch")

DEFAULT_DEBOUNCE_SECONDS = 2.0


def parse_watch_channels(env_value: Optional[str]) -> set[str]:
    """Parse a comma-separated env value into a set of channel-id strings.

    Whitespace around entries is stripped; empty entries are ignored. Channel
    *names* are not supported here — pass numeric IDs to avoid ambiguity
    across servers."""
    if not env_value:
        return set()
    return {c.strip() for c in env_value.split(",") if c.strip()}


def format_notification(messages: list[tuple[str, str]]) -> str:
    """Render a batch of (channel_name, author_name) into one inject line.

    Authors per channel are deduplicated while preserving first-seen order so
    that repeat senders within a debounce window collapse to a single mention.
    """
    if not messages:
        return ""
    by_channel: dict[str, list[str]] = {}
    for channel, author in messages:
        by_channel.setdefault(channel, []).append(author)
    parts = []
    for channel in sorted(by_channel):
        seen: set[str] = set()
        unique = [a for a in by_channel[channel] if not (a in seen or seen.add(a))]
        parts.append(f"#{channel}({','.join('@' + a for a in unique)})")
    total = sum(len(v) for v in by_channel.values())
    return f"[discord] {total} new: {' '.join(parts)}"


def tmux_inject(target: str, text: str,
                runner: Callable = subprocess.run) -> bool:
    """Send literal text followed by Enter to the given tmux target.

    Returns True on success, False on failure. Failures are logged, never
    raised, because a push that crashes the gateway loop is worse than a
    dropped notification.
    """
    if not target or not text:
        return False
    try:
        runner(["tmux", "send-keys", "-t", target, "-l", text],
               check=True, capture_output=True, timeout=5)
        runner(["tmux", "send-keys", "-t", target, "Enter"],
               check=True, capture_output=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError) as e:
        logger.warning("tmux inject failed (target=%s): %s", target, e)
        return False


class MessageWatcher:
    """Filter, debounce, and dispatch inbound Discord messages.

    The watcher is intentionally transport-agnostic: it calls `on_notify`
    with the rendered string and lets the caller decide where it goes
    (tmux in production, a list in tests).
    """

    def __init__(self, watch_channel_ids: set[str],
                 on_notify: Callable[[str], None],
                 bot_user_id: Optional[int] = None,
                 debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS):
        self.watch = watch_channel_ids
        self.on_notify = on_notify
        self.bot_user_id = bot_user_id
        self.debounce = debounce_seconds
        self._pending: list[tuple[str, str]] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None

    def set_bot_user_id(self, uid: int) -> None:
        self.bot_user_id = uid

    async def handle_message(self, message: discord.Message) -> None:
        # Only filter self-echoes — keeping cross-bot chatter visible is the
        # whole point (Amara→Athena coordination, helper bots, etc.). The
        # generic "any bot" filter was too aggressive and dropped legitimate
        # notifications from other automated sources.
        if self.bot_user_id is not None and message.author.id == self.bot_user_id:
            return
        if str(message.channel.id) not in self.watch:
            return
        channel_name = getattr(message.channel, "name", str(message.channel.id))
        async with self._lock:
            self._pending.append((channel_name, message.author.name))
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(
                    self._flush_after_debounce())

    async def _flush_after_debounce(self) -> None:
        try:
            await asyncio.sleep(self.debounce)
        except asyncio.CancelledError:
            return
        async with self._lock:
            if not self._pending:
                return
            batch = self._pending
            self._pending = []
        text = format_notification(batch)
        if not text:
            return
        try:
            self.on_notify(text)
        except Exception:
            logger.exception("on_notify callback raised; notification dropped")
