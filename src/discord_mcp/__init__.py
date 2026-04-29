"""Discord integration for Model Context Protocol."""

import asyncio
import warnings
import tracemalloc

__version__ = "0.1.0"


def main():
    """Main entry point for the package.

    `server` is imported lazily so that submodules (e.g. `watch`) and
    package introspection (`pip show`, test collection) do not trigger
    its module-level `DISCORD_TOKEN` requirement.
    """
    tracemalloc.start()
    warnings.filterwarnings(
        'ignore', module='discord.client',
        message='PyNaCl is not installed')

    from . import server  # noqa: WPS433 — lazy by design
    try:
        asyncio.run(server.main())
    except KeyboardInterrupt:
        print("\nShutting down Discord MCP server...")
    except Exception as e:
        print(f"Error running Discord MCP server: {e}")
        raise


__all__ = ['main']
