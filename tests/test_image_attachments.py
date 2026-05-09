"""Unit tests for local image attachment helpers in discord_mcp.server."""

import io
import os

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token-not-real")

from discord_mcp import server


@pytest.fixture
def png_file(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake-bytes")
    return path


class TestLoadLocalImage:
    def test_loads_absolute_path(self, png_file):
        f = server._load_local_image(str(png_file))
        assert f is not None
        assert f.filename == "shot.png"

    def test_loads_file_url(self, png_file):
        f = server._load_local_image(f"file://{png_file}")
        assert f is not None
        assert f.filename == "shot.png"

    def test_expands_user_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        target = tmp_path / "hello.png"
        target.write_bytes(b"x")
        f = server._load_local_image("~/hello.png")
        assert f is not None
        assert f.filename == "hello.png"

    def test_relative_path_rejected(self):
        assert server._load_local_image("relative.png") is None

    def test_missing_file_returns_none(self, tmp_path):
        assert server._load_local_image(str(tmp_path / "nope.png")) is None


class TestResolveImageAttachment:
    @pytest.mark.asyncio
    async def test_prefers_image_path_over_url(self, png_file, monkeypatch):
        called = {"url": False}

        async def fake_download(url):
            called["url"] = True
            return None

        monkeypatch.setattr(server, "_download_image", fake_download)
        f = await server._resolve_image_attachment(
            {"image_path": str(png_file), "image_url": "https://example.com/x.png"}
        )
        assert f is not None
        assert called["url"] is False

    @pytest.mark.asyncio
    async def test_falls_back_to_url(self, monkeypatch):
        sentinel = object()

        async def fake_download(url):
            assert url == "https://example.com/x.png"
            return sentinel

        monkeypatch.setattr(server, "_download_image", fake_download)
        result = await server._resolve_image_attachment(
            {"image_url": "https://example.com/x.png"}
        )
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_returns_none_when_neither_provided(self):
        assert await server._resolve_image_attachment({}) is None
