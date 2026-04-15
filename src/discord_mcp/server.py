import os
import sys
import io
import asyncio
import logging
from datetime import datetime
from typing import Any, List, Optional
from functools import wraps
from urllib.parse import urlparse
import discord
from discord.ext import commands
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

def _configure_windows_stdout_encoding():
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

_configure_windows_stdout_encoding()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord-mcp-server")

# Discord bot setup
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is required")

# Initialize Discord bot with necessary intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize MCP server
app = Server("discord-server")

# Store Discord client reference
discord_client = None

@bot.event
async def on_ready():
    global discord_client
    discord_client = bot
    logger.info(f"Logged in as {bot.user.name}")

# Helper function to ensure Discord client is ready
def require_discord_client(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not discord_client:
            raise RuntimeError("Discord client not ready")
        return await func(*args, **kwargs)
    return wrapper

async def _download_image(url: str) -> Optional[discord.File]:
    """Download an image from URL and return as discord.File."""
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/png")
            ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(content_type, ".png")
            filename = f"image{ext}"
            return discord.File(io.BytesIO(resp.content), filename=filename)
    except Exception as e:
        logger.error(f"Failed to download image from {url}: {e}")
        return None

def _resolve_channel_ids(arguments: dict) -> list[str]:
    ids = arguments.get("channel_ids")
    if ids:
        if not isinstance(ids, list) or not ids:
            raise ValueError("channel_ids must be a non-empty list of strings")
        return [str(c) for c in ids]
    single = arguments.get("channel_id")
    if not single:
        raise ValueError("Provide either channel_id or channel_ids")
    return [str(single)]

@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available Discord tools."""
    return [
        # Server Information Tools
        Tool(
            name="get_server_info",
            description="Get information about a Discord server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Discord server (guild) ID"
                    }
                },
                "required": ["server_id"]
            }
        ),
        Tool(
            name="get_channels",
            description="Get a list of all channels in a Discord server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Discord server (guild) ID"
                    }
                },
                "required": ["server_id"]
            }
        ),
        Tool(
            name="list_members",
            description="Get a list of members in a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Discord server (guild) ID"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of members to fetch",
                        "minimum": 1,
                        "maximum": 1000
                    }
                },
                "required": ["server_id"]
            }
        ),

        # Role Management Tools
        Tool(
            name="add_role",
            description="Add a role to a user",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Discord server ID"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User to add role to"
                    },
                    "role_id": {
                        "type": "string",
                        "description": "Role ID to add"
                    }
                },
                "required": ["server_id", "user_id", "role_id"]
            }
        ),
        Tool(
            name="remove_role",
            description="Remove a role from a user",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Discord server ID"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User to remove role from"
                    },
                    "role_id": {
                        "type": "string",
                        "description": "Role ID to remove"
                    }
                },
                "required": ["server_id", "user_id", "role_id"]
            }
        ),

        # Channel Management Tools
        Tool(
            name="create_text_channel",
            description="Create a new text channel",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Discord server ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "Channel name"
                    },
                    "category_id": {
                        "type": "string",
                        "description": "Optional category ID to place channel in"
                    },
                    "topic": {
                        "type": "string",
                        "description": "Optional channel topic"
                    }
                },
                "required": ["server_id", "name"]
            }
        ),
        Tool(
            name="delete_channel",
            description="Delete a channel",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "ID of channel to delete"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for deletion"
                    }
                },
                "required": ["channel_id"]
            }
        ),

        # Message Reaction Tools
        Tool(
            name="add_reaction",
            description="Add a reaction to a message",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel containing the message"
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Message to react to"
                    },
                    "emoji": {
                        "type": "string",
                        "description": "Emoji to react with (Unicode or custom emoji ID)"
                    }
                },
                "required": ["channel_id", "message_id", "emoji"]
            }
        ),
        Tool(
            name="add_multiple_reactions",
            description="Add multiple reactions to a message",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel containing the message"
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Message to react to"
                    },
                    "emojis": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "Emoji to react with (Unicode or custom emoji ID)"
                        },
                        "description": "List of emojis to add as reactions"
                    }
                },
                "required": ["channel_id", "message_id", "emojis"]
            }
        ),
        Tool(
            name="remove_reaction",
            description="Remove a reaction from a message",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel containing the message"
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Message to remove reaction from"
                    },
                    "emoji": {
                        "type": "string",
                        "description": "Emoji to remove (Unicode or custom emoji ID)"
                    }
                },
                "required": ["channel_id", "message_id", "emoji"]
            }
        ),
        Tool(
            name="send_message",
            description="Send a message to a specific channel. Supports image attachments and replies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Discord channel ID"
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content"
                    },
                    "image_url": {
                        "type": "string",
                        "description": "URL of image to attach (downloaded and sent as file)"
                    },
                    "reply_to_message_id": {
                        "type": "string",
                        "description": "Message ID to reply to (creates a threaded reply)"
                    }
                },
                "required": ["channel_id", "content"]
            }
        ),
        Tool(
            name="edit_message",
            description="Edit a message sent by this bot",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel containing the message"
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Message ID to edit"
                    },
                    "content": {
                        "type": "string",
                        "description": "New message content"
                    }
                },
                "required": ["channel_id", "message_id", "content"]
            }
        ),
        Tool(
            name="delete_message",
            description="Delete a specific message (bot's own or with Manage Messages permission)",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel containing the message"
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Message ID to delete"
                    }
                },
                "required": ["channel_id", "message_id"]
            }
        ),
        Tool(
            name="read_messages",
            description="Read recent messages from one or more channels. Pass either channel_id (single) or channel_ids (batch) — batched calls are fetched concurrently.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Discord channel ID (single-channel mode)"
                    },
                    "channel_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Discord channel IDs (batch mode). Provide instead of channel_id to fetch many at once."
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of messages to fetch per channel (max 100)",
                        "minimum": 1,
                        "maximum": 100
                    }
                }
            }
        ),
        Tool(
            name="get_user_info",
            description="Get information about a Discord user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Discord user ID"
                    }
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="moderate_message",
            description="Delete a message and optionally timeout the user",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel ID containing the message"
                    },
                    "message_id": {
                        "type": "string",
                        "description": "ID of message to moderate"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for moderation"
                    },
                    "timeout_minutes": {
                        "type": "number",
                        "description": "Optional timeout duration in minutes",
                        "minimum": 0,
                        "maximum": 40320  # Max 4 weeks
                    }
                },
                "required": ["channel_id", "message_id", "reason"]
            }
        ),
        Tool(
            name="list_servers",
            description="Get a list of all Discord servers the bot has access to with their details such as name, id, member count, and creation date.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),

        # Thread Tools
        Tool(
            name="create_thread",
            description="Create a new thread in a channel. Can be attached to a message or standalone.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel to create thread in"
                    },
                    "name": {
                        "type": "string",
                        "description": "Thread name"
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Optional message ID to attach thread to"
                    },
                    "auto_archive_duration": {
                        "type": "number",
                        "description": "Minutes before auto-archive (60, 1440, 4320, or 10080)",
                        "enum": [60, 1440, 4320, 10080]
                    }
                },
                "required": ["channel_id", "name"]
            }
        ),
        Tool(
            name="list_threads",
            description="List threads in one or more channels. Pass either channel_id (single) or channel_ids (batch) — batched calls are fetched concurrently.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel to list threads from (single-channel mode)"
                    },
                    "channel_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Channels to list threads from (batch mode). Provide instead of channel_id to query many at once."
                    },
                    "include_archived": {
                        "type": "boolean",
                        "description": "Include archived threads (default: false)"
                    }
                }
            }
        ),
        Tool(
            name="send_thread_message",
            description="Send a message to a thread. Supports image attachments and replies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "Thread ID to send message to"
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content"
                    },
                    "image_url": {
                        "type": "string",
                        "description": "URL of image to attach (downloaded and sent as file)"
                    },
                    "reply_to_message_id": {
                        "type": "string",
                        "description": "Message ID to reply to within the thread"
                    }
                },
                "required": ["thread_id", "content"]
            }
        ),
        Tool(
            name="archive_thread",
            description="Archive or unarchive a thread",
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "Thread ID"
                    },
                    "archived": {
                        "type": "boolean",
                        "description": "True to archive, false to unarchive"
                    }
                },
                "required": ["thread_id", "archived"]
            }
        ),
        Tool(
            name="edit_thread",
            description="Edit a thread's name or other properties",
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "Thread ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "New thread name"
                    }
                },
                "required": ["thread_id"]
            }
        ),

        # Forum Channel Tools
        Tool(
            name="create_forum_post",
            description="Create a new post in a forum channel. Supports image attachment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Forum channel ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "Post title"
                    },
                    "content": {
                        "type": "string",
                        "description": "Initial message content"
                    },
                    "image_url": {
                        "type": "string",
                        "description": "URL of image to attach to the first message"
                    }
                },
                "required": ["channel_id", "name", "content"]
            }
        ),
        Tool(
            name="edit_channel_name",
            description="Rename a channel or thread",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel or thread ID"
                    },
                    "name": {
                        "type": "string",
                        "description": "New name"
                    }
                },
                "required": ["channel_id", "name"]
            }
        )
    ]

@app.call_tool()
@require_discord_client
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    """Handle Discord tool calls."""
    
    if name == "send_message":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        kwargs = {"content": arguments["content"]}
        if arguments.get("image_url"):
            file = await _download_image(arguments["image_url"])
            if file:
                kwargs["file"] = file
        if arguments.get("reply_to_message_id"):
            ref_msg = await channel.fetch_message(int(arguments["reply_to_message_id"]))
            kwargs["reference"] = ref_msg
        message = await channel.send(**kwargs)
        return [TextContent(
            type="text",
            text=f"Message sent successfully. Message ID: {message.id}"
        )]

    elif name == "edit_message":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        message = await channel.fetch_message(int(arguments["message_id"]))
        await message.edit(content=arguments["content"])
        return [TextContent(
            type="text",
            text=f"Message {arguments['message_id']} edited successfully."
        )]

    elif name == "delete_message":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        message = await channel.fetch_message(int(arguments["message_id"]))
        await message.delete()
        return [TextContent(
            type="text",
            text=f"Message {arguments['message_id']} deleted."
        )]

    elif name == "read_messages":
        channel_ids = _resolve_channel_ids(arguments)
        limit = min(int(arguments.get("limit", 10)), 100)

        def format_reaction(r):
            return f"{r['emoji']}({r['count']})"

        def format_message(m):
            lines = [f"{m['author']} ({m['timestamp']}): {m['content']}"]
            if m['attachments']:
                att_strs = [f"{a['filename']} ({a['content_type']}, {a['url']})" for a in m['attachments']]
                lines.append(f"Attachments: {', '.join(att_strs)}")
            lines.append(f"Reactions: {', '.join([format_reaction(r) for r in m['reactions']]) if m['reactions'] else 'No reactions'}")
            return "\n".join(lines)

        async def fetch_one(cid: str) -> str:
            try:
                channel = await discord_client.fetch_channel(int(cid))
            except Exception as e:
                return f"Error fetching channel {cid}: {e}"

            if isinstance(channel, discord.ForumChannel):
                threads = list(channel.threads)
                if not threads:
                    return "No active threads in this forum channel. Use list_threads to see archived threads."
                thread_list = [f"#{t.name} (ID: {t.id}, messages: {t.message_count})" for t in threads]
                return (f"Forum channel has {len(threads)} active threads:\n" + "\n".join(thread_list) +
                        "\n\nUse read_messages with a thread ID to read messages within a thread.")

            messages = []
            async for message in channel.history(limit=limit):
                reaction_data = []
                for reaction in message.reactions:
                    emoji_str = str(reaction.emoji.name) if hasattr(reaction.emoji, 'name') and reaction.emoji.name else str(reaction.emoji.id) if hasattr(reaction.emoji, 'id') else str(reaction.emoji)
                    reaction_data.append({"emoji": emoji_str, "count": reaction.count})
                attachment_data = [{
                    "filename": att.filename,
                    "url": att.url,
                    "content_type": att.content_type,
                    "size": att.size,
                } for att in message.attachments]
                messages.append({
                    "id": str(message.id),
                    "author": str(message.author),
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                    "reactions": reaction_data,
                    "attachments": attachment_data,
                })
            return (f"Retrieved {len(messages)} messages:\n\n" +
                    "\n".join([format_message(m) for m in messages]))

        if len(channel_ids) == 1:
            return [TextContent(type="text", text=await fetch_one(channel_ids[0]))]

        results = await asyncio.gather(*[fetch_one(cid) for cid in channel_ids])
        sections = [f"=== Channel {cid} ===\n{body}" for cid, body in zip(channel_ids, results)]
        return [TextContent(type="text", text="\n\n".join(sections))]

    elif name == "get_user_info":
        user = await discord_client.fetch_user(int(arguments["user_id"]))
        user_info = {
            "id": str(user.id),
            "name": user.name,
            "discriminator": user.discriminator,
            "bot": user.bot,
            "created_at": user.created_at.isoformat()
        }
        return [TextContent(
            type="text",
            text=f"User information:\n" + 
                 f"Name: {user_info['name']}#{user_info['discriminator']}\n" +
                 f"ID: {user_info['id']}\n" +
                 f"Bot: {user_info['bot']}\n" +
                 f"Created: {user_info['created_at']}"
        )]

    elif name == "moderate_message":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        message = await channel.fetch_message(int(arguments["message_id"]))
        
        # Delete the message
        await message.delete(reason=arguments["reason"])
        
        # Handle timeout if specified
        if "timeout_minutes" in arguments and arguments["timeout_minutes"] > 0:
            if isinstance(message.author, discord.Member):
                duration = discord.utils.utcnow() + datetime.timedelta(
                    minutes=arguments["timeout_minutes"]
                )
                await message.author.timeout(
                    duration,
                    reason=arguments["reason"]
                )
                return [TextContent(
                    type="text",
                    text=f"Message deleted and user timed out for {arguments['timeout_minutes']} minutes."
                )]
        
        return [TextContent(
            type="text",
            text="Message deleted successfully."
        )]

    # Server Information Tools
    elif name == "get_server_info":
        guild = await discord_client.fetch_guild(int(arguments["server_id"]))
        info = {
            "name": guild.name,
            "id": str(guild.id),
            "owner_id": str(guild.owner_id),
            "member_count": guild.member_count,
            "created_at": guild.created_at.isoformat(),
            "description": guild.description,
            "premium_tier": guild.premium_tier,
            "explicit_content_filter": str(guild.explicit_content_filter)
        }
        return [TextContent(
            type="text",
            text=f"Server Information:\n" + "\n".join(f"{k}: {v}" for k, v in info.items())
        )]

    elif name == "get_channels":
        try:
            guild = discord_client.get_guild(int(arguments["server_id"]))
            if guild:
                channel_list = []
                for channel in guild.channels:
                    channel_list.append(f"#{channel.name} (ID: {channel.id}) - {channel.type}")
                
                return [TextContent(
                    type="text", 
                    text=f"Channels in {guild.name}:\n" + "\n".join(channel_list)
                )]
            else:
                return [TextContent(type="text", text="Guild not found")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "list_members":
        guild = await discord_client.fetch_guild(int(arguments["server_id"]))
        limit = min(int(arguments.get("limit", 100)), 1000)
        
        members = []
        async for member in guild.fetch_members(limit=limit):
            members.append({
                "id": str(member.id),
                "name": member.name,
                "nick": member.nick,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "roles": [str(role.id) for role in member.roles[1:]]  # Skip @everyone
            })
        
        return [TextContent(
            type="text",
            text=f"Server Members ({len(members)}):\n" + 
                 "\n".join(f"{m['name']} (ID: {m['id']}, Roles: {', '.join(m['roles'])})" for m in members)
        )]

    # Role Management Tools
    elif name == "add_role":
        guild = await discord_client.fetch_guild(int(arguments["server_id"]))
        member = await guild.fetch_member(int(arguments["user_id"]))
        role = guild.get_role(int(arguments["role_id"]))
        
        await member.add_roles(role, reason="Role added via MCP")
        return [TextContent(
            type="text",
            text=f"Added role {role.name} to user {member.name}"
        )]

    elif name == "remove_role":
        guild = await discord_client.fetch_guild(int(arguments["server_id"]))
        member = await guild.fetch_member(int(arguments["user_id"]))
        role = guild.get_role(int(arguments["role_id"]))
        
        await member.remove_roles(role, reason="Role removed via MCP")
        return [TextContent(
            type="text",
            text=f"Removed role {role.name} from user {member.name}"
        )]

    # Channel Management Tools
    elif name == "create_text_channel":
        guild = await discord_client.fetch_guild(int(arguments["server_id"]))
        category = None
        if "category_id" in arguments:
            category = guild.get_channel(int(arguments["category_id"]))
        
        channel = await guild.create_text_channel(
            name=arguments["name"],
            category=category,
            topic=arguments.get("topic"),
            reason="Channel created via MCP"
        )
        
        return [TextContent(
            type="text",
            text=f"Created text channel #{channel.name} (ID: {channel.id})"
        )]

    elif name == "delete_channel":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        await channel.delete(reason=arguments.get("reason", "Channel deleted via MCP"))
        return [TextContent(
            type="text",
            text=f"Deleted channel successfully"
        )]

    # Message Reaction Tools
    elif name == "add_reaction":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        message = await channel.fetch_message(int(arguments["message_id"]))
        await message.add_reaction(arguments["emoji"])
        return [TextContent(
            type="text",
            text=f"Added reaction {arguments['emoji']} to message"
        )]

    elif name == "add_multiple_reactions":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        message = await channel.fetch_message(int(arguments["message_id"]))
        for emoji in arguments["emojis"]:
            await message.add_reaction(emoji)
        return [TextContent(
            type="text",
            text=f"Added reactions: {', '.join(arguments['emojis'])} to message"
        )]

    elif name == "remove_reaction":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        message = await channel.fetch_message(int(arguments["message_id"]))
        await message.remove_reaction(arguments["emoji"], discord_client.user)
        return [TextContent(
            type="text",
            text=f"Removed reaction {arguments['emoji']} from message"
        )]

    elif name == "list_servers":
        servers = []
        for guild in discord_client.guilds:
            servers.append({
                "id": str(guild.id),
                "name": guild.name,
                "member_count": guild.member_count,
                "created_at": guild.created_at.isoformat()
            })
        
        return [TextContent(
            type="text",
            text=f"Available Servers ({len(servers)}):\n" + 
                 "\n".join(f"{s['name']} (ID: {s['id']}, Members: {s['member_count']})" for s in servers)
        )]

    # Thread Tools
    elif name == "create_thread":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        if "message_id" in arguments:
            message = await channel.fetch_message(int(arguments["message_id"]))
            thread = await message.create_thread(
                name=arguments["name"],
                auto_archive_duration=arguments.get("auto_archive_duration", 1440)
            )
        else:
            thread = await channel.create_thread(
                name=arguments["name"],
                auto_archive_duration=arguments.get("auto_archive_duration", 1440),
                type=discord.ChannelType.public_thread
            )
        return [TextContent(
            type="text",
            text=f"Created thread '{thread.name}' (ID: {thread.id})"
        )]

    elif name == "list_threads":
        channel_ids = _resolve_channel_ids(arguments)
        include_archived = arguments.get("include_archived", False)

        async def list_one(cid: str) -> str:
            try:
                channel = await discord_client.fetch_channel(int(cid))
            except Exception as e:
                return f"Error fetching channel {cid}: {e}"
            active = list(channel.threads)
            archived = []
            if include_archived:
                try:
                    async for t in channel.archived_threads(limit=50):
                        archived.append(t)
                except Exception:
                    pass
            all_threads = active + archived
            if not all_threads:
                return "No active threads in this channel."
            thread_list = []
            for t in all_threads:
                prefix = "[archived] " if t.archived else ""
                thread_list.append(f"{prefix}#{t.name} (ID: {t.id}, messages: {t.message_count})")
            return (f"Threads ({len(active)} active"
                    f"{f', {len(archived)} archived' if archived else ''}):\n" + "\n".join(thread_list))

        if len(channel_ids) == 1:
            return [TextContent(type="text", text=await list_one(channel_ids[0]))]

        results = await asyncio.gather(*[list_one(cid) for cid in channel_ids])
        sections = [f"=== Channel {cid} ===\n{body}" for cid, body in zip(channel_ids, results)]
        return [TextContent(type="text", text="\n\n".join(sections))]

    elif name == "send_thread_message":
        thread = await discord_client.fetch_channel(int(arguments["thread_id"]))
        kwargs = {"content": arguments["content"]}
        if arguments.get("image_url"):
            file = await _download_image(arguments["image_url"])
            if file:
                kwargs["file"] = file
        if arguments.get("reply_to_message_id"):
            ref_msg = await thread.fetch_message(int(arguments["reply_to_message_id"]))
            kwargs["reference"] = ref_msg
        message = await thread.send(**kwargs)
        return [TextContent(
            type="text",
            text=f"Message sent to thread. Message ID: {message.id}"
        )]

    elif name == "archive_thread":
        thread = await discord_client.fetch_channel(int(arguments["thread_id"]))
        await thread.edit(archived=arguments["archived"])
        status = "archived" if arguments["archived"] else "unarchived"
        return [TextContent(
            type="text",
            text=f"Thread '{thread.name}' {status}."
        )]

    elif name == "edit_thread":
        thread = await discord_client.fetch_channel(int(arguments["thread_id"]))
        kwargs = {}
        if "name" in arguments:
            kwargs["name"] = arguments["name"]
        await thread.edit(**kwargs)
        return [TextContent(
            type="text",
            text=f"Thread updated: {thread.name}"
        )]

    elif name == "create_forum_post":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        kwargs = {"name": arguments["name"], "content": arguments["content"]}
        if arguments.get("image_url"):
            file = await _download_image(arguments["image_url"])
            if file:
                kwargs["file"] = file
        thread_with_message = await channel.create_thread(**kwargs)
        thread = thread_with_message[0] if isinstance(thread_with_message, tuple) else thread_with_message
        return [TextContent(
            type="text",
            text=f"Created forum post '{arguments['name']}' (Thread ID: {thread.id})"
        )]

    elif name == "edit_channel_name":
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        await channel.edit(name=arguments["name"])
        return [TextContent(
            type="text",
            text=f"Channel renamed to '{arguments['name']}'"
        )]

    raise ValueError(f"Unknown tool: {name}")

async def main():
    # Start Discord bot in the background
    asyncio.create_task(bot.start(DISCORD_TOKEN))
    
    # Run MCP server
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
