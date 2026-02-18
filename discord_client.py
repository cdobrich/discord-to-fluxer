import asyncio
import aiohttp
import discord
import os
import traceback


class DiscordClient:
    """
    A client for interacting with the Discord API using discord.py.
    """
    def __init__(self, token):
        self.token = token
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.reactions = True # Enable reaction intent
        self.client = discord.Client(intents=intents)
        self._ready_event = asyncio.Event() # Event to signal when the client is ready
        self._guilds_loaded_event = asyncio.Event() # Event to signal when all guilds are loaded

        # Attach event listeners
        @self.client.event
        async def on_ready():
            print(f"Discord: Logged in as {self.client.user} (ID: {self.client.user.id})")
            print("Discord: Bot is ready and connected to Discord gateway.")
            self._ready_event.set() # Signal that the client is ready

        @self.client.event
        async def on_guild_available(guild):
            print(f"Discord: Guild '{guild.name}' (ID: {guild.id}) is now available.")
            # This is a simplification. For very large bots in many guilds,
            # we might need to track all expected GUILD_CREATE events.
            # For a single guild migration, the on_ready often covers it.
            # However, start() itself often waits for this to stabilize.
            # We'll rely on the on_ready event primarily for now.
            if guild.id == int(os.environ.get('DISCORD_GUILD_ID_FOR_BOT_WAIT', '0')): # Placeholder for specific guild if needed
                self._guilds_loaded_event.set()


        print(f"DiscordClient initialized with token: {'*' * (len(token) - 4) + token[-4:] if token else 'None'}")

    async def start(self):
        """Starts the discord.py client session and waits for it to be ready."""
        print("Discord: Starting client in background task...")
        # Run the bot in a separate task so we can await the ready event
        self._run_task = asyncio.create_task(self.client.start(self.token))

        print("Discord: Waiting for 'on_ready' event...")
        # Wait for the on_ready event to be triggered
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=60.0) # Wait up to 60 seconds for ready
            print("Discord: 'on_ready' event received. Client is confirmed ready.")
        except asyncio.TimeoutError:
            print("Discord: Timeout waiting for 'on_ready' event. The client might not have fully connected.")
            raise ConnectionError("Discord client failed to become ready within timeout.")
        except Exception as e:
            print(f"Discord: An unexpected error occurred while waiting for client to be ready: {e}")
            raise


    async def close(self):
        """Closes the discord.py client session."""
        print("Discord: Closing client session...")
        if hasattr(self, '_run_task') and not self._run_task.done():
            self._run_task.cancel() # Cancel the background task if still running
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass # Expected if cancelled
        print("Discord client session closed.")

    async def get_guild_channels(self, guild_id):
        """
        Fetches channels from a Discord guild.
        Returns a list of dictionaries with 'id', 'name', 'type', 'position', 'parent_id'.
        """
        print(f"Discord: Fetching channels for guild {guild_id}...")
        try:
            guild = self.client.get_guild(int(guild_id))
            if not guild:
                # If guild not found via get_guild (which uses cache), try fetching
                print(f"Discord: Guild {guild_id} not in cache, attempting fetch...")
                guild = await self.client.fetch_guild(int(guild_id))

            if not guild:
                print(f"Error: Discord guild with ID {guild_id} not found or inaccessible by the bot.")
                return []

            channels = guild.channels
            parsed_channels = []
            for channel in channels:
                # Only include text, voice, and category channels for initial processing
                if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel)):
                    parsed_channels.append({
                        "id": str(channel.id),
                        "name": channel.name,
                        "type": channel.type.value, # Get the integer value of the channel type
                        "position": channel.position,
                        "parent_id": str(channel.category_id) if channel.category_id else None
                    })
            print(f"Discord: Successfully fetched {len(parsed_channels)} channels for guild {guild_id}.")
            return parsed_channels
        except discord.NotFound:
            print(f"Error: Discord guild with ID {guild_id} not found.")
            return []
        except discord.Forbidden:
            print(f"Error: Bot lacks permissions to fetch channels in guild {guild_id}.")
            return []
        except Exception as e:
            print(f"An error occurred fetching Discord channels: {e}")
            traceback.print_exc()
            return []

    async def get_guild_emojis(self, guild_id):
        """
        Fetches custom emojis from a Discord guild.
        Returns a list of dictionaries with 'id', 'name', 'url', 'animated'.
        """
        print(f"Discord: Fetching emojis for guild {guild_id}...")
        try:
            guild = self.client.get_guild(int(guild_id))
            if not guild:
                print(f"Discord: Guild {guild_id} not in cache, attempting fetch for emojis...")
                guild = await self.client.fetch_guild(int(guild_id))

            if not guild:
                print(f"Error: Discord guild with ID {guild_id} not found or inaccessible by the bot for emoji fetching.")
                return []

            emojis = guild.emojis
            parsed_emojis = []
            for emoji in emojis:
                parsed_emojis.append({
                    "id": str(emoji.id),
                    "name": emoji.name,
                    "url": str(emoji.url),
                    "animated": emoji.animated
                })
            print(f"Discord: Successfully fetched {len(parsed_emojis)} emojis for guild {guild_id}.")
            return parsed_emojis
        except discord.NotFound:
            print(f"Error: Discord guild with ID {guild_id} not found for emoji fetching.")
            return []
        except discord.Forbidden:
            print(f"Error: Bot lacks permissions to fetch emojis in guild {guild_id}.")
            return []
        except Exception as e:
            print(f"An error occurred fetching Discord emojis: {e}")
            traceback.print_exc()
            return []

    async def get_channel_messages(self, channel_id, after_message_id=None, limit=100):
        """
        Fetches messages from a Discord channel.
        Uses 'after' parameter for pagination and resumption.
        Messages are returned in chronological order.
        Includes reactions.
        """
        print(f"Discord: Fetching messages for channel {channel_id}, after {after_message_id if after_message_id else 'start of channel'} (limit: {limit})...")
        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                try:
                    channel = await self.client.fetch_channel(int(channel_id))
                    print(f"Discord: Fetched channel {channel_id} via API.")
                except discord.NotFound:
                    print(f"Error: Discord channel with ID {channel_id} not found.")
                    return []
                except discord.Forbidden:
                    print(f"Error: Bot lacks permissions to fetch channel {channel_id}.")
                    return []

            parsed_messages = []

            # Start fetching from the beginning if after_message_id is not set or if it's not found.
            # We will filter messages later to ensure no duplicates.
            start_message = None
            if after_message_id:
                try:
                    start_message = await channel.fetch_message(int(after_message_id))
                    print(f"Discord: Found 'after_message_id' {after_message_id}. Fetching messages after this point.")
                except discord.NotFound:
                    print(f"Warning: 'after_message_id' {after_message_id} not found in channel {channel_id}. Fetching from start of history and will filter manually.")
                    start_message = None # Reset to None to fetch from beginning
                except discord.Forbidden:
                    print(f"Warning: Bot lacks permissions to fetch 'after_message_id' {after_message_id}. Fetching from start of history and will filter manually.")
                    start_message = None # Reset to None to fetch from beginning


            # Fetch messages in chronological order (oldest_first=True)
            # If start_message is None, it fetches from the very beginning.
            messages_fetched_raw = [msg async for msg in channel.history(limit=limit, after=start_message, oldest_first=True)]

            # Filter out messages that are older than or equal to the last migrated ID,
            # but only if a last_migrated_discord_message_id was actually provided.
            filtered_messages = []
            if after_message_id:
                for message in messages_fetched_raw:
                    if int(message.id) > int(after_message_id):
                        filtered_messages.append(message)
                print(f"Discord: Filtered {len(messages_fetched_raw) - len(filtered_messages)} messages older than {after_message_id}.")
                messages_to_process = filtered_messages
            else:
                messages_to_process = messages_fetched_raw

            for message in messages_to_process:
                if message.webhook_id or message.author.bot: # Skip webhooks and other bots
                    continue

                attachments_data = []
                for attachment in message.attachments:
                    attachments_data.append({
                        "id": str(attachment.id),
                        "filename": attachment.filename,
                        "url": str(attachment.url)
                    })

                reactions_data = []
                for reaction in message.reactions:
                    emoji_info = {}
                    if isinstance(reaction.emoji, discord.Emoji): # Custom emoji
                        emoji_info = {
                            "type": "custom",
                            "id": str(reaction.emoji.id),
                            "name": reaction.emoji.name,
                            "animated": reaction.emoji.animated,
                            "url": str(reaction.emoji.url)
                        }
                    elif isinstance(reaction.emoji, str): # Unicode emoji
                        emoji_info = {
                            "type": "unicode",
                            "name": reaction.emoji # The actual unicode character
                        }

                    if emoji_info:
                        reactions_data.append(emoji_info)

                reply_to_discord_id = None
                if message.reference and message.reference.message_id:
                    reply_to_discord_id = str(message.reference.message_id)

                parsed_messages.append({
                    "id": str(message.id),
                    "author": {
                        "username": message.author.name,
                        "discriminator": message.author.discriminator,
                        "avatar_url": str(message.author.display_avatar.url) if message.author.display_avatar else None
                    },
                    "content": message.content if message.content else "",
                    "timestamp": message.created_at.isoformat(),
                    "attachments": attachments_data,
                    "reactions": reactions_data, # Added reactions data
                    "reply_to_discord_id": reply_to_discord_id
                })

            print(f"Discord: Fetched {len(parsed_messages)} new messages for channel {channel_id}.")
            return parsed_messages
        except discord.Forbidden:
            print(f"Error: Bot lacks permissions to read messages in channel {channel_id}.")
            return []
        except Exception as e:
            print(f"An error occurred fetching Discord messages for channel {channel_id}: {e}")
            traceback.print_exc()
            return []

    async def get_channel_pinned_messages(self, channel_id):
        """
        Fetches pinned messages from a Discord channel.
        Returns a list of Discord message IDs that are pinned.
        """
        print(f"Discord: Fetching pinned messages for channel {channel_id}...")
        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                try:
                    channel = await self.client.fetch_channel(int(channel_id))
                    print(f"Discord: Fetched channel {channel_id} via API for pinned messages.")
                except discord.NotFound:
                    print(f"Error: Discord channel with ID {channel_id} not found for pinned messages.")
                    return []
                except discord.Forbidden:
                    print(f"Error: Bot lacks permissions to fetch channel {channel_id} for pinned messages.")
                    return []

            pinned_messages = await channel.pins()
            pinned_message_ids = [str(msg.id) for msg in pinned_messages]
            print(f"Discord: Successfully fetched {len(pinned_message_ids)} pinned messages for channel {channel_id}.")
            return pinned_message_ids
        except discord.Forbidden:
            print(f"Error: Bot lacks permissions to read pinned messages in channel {channel_id}.")
            return []
        except Exception as e:
            print(f"An error occurred fetching Discord pinned messages for channel {channel_id}: {e}")
            traceback.print_exc()
            return []


    async def download_attachment(self, url):
        """
        Downloads an attachment from a given URL.
        """
        print(f"Discord: Downloading attachment from {url}...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    return await response.read()
        except aiohttp.ClientResponseError as e:
            print(f"Error downloading attachment from {url}: {e.status} - {e.message}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during attachment download from {url}: {e}")
            traceback.print_exc()
            return None

    async def fetch_message_exists(self, channel_id, message_id):
        """
        Checks if a specific Discord message exists in a given channel.
        Returns True if found, False if not found.
        """
        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                channel = await self.client.fetch_channel(int(channel_id))
            msg = await channel.fetch_message(int(message_id))
            return True if msg else False
        except discord.NotFound:
            return False
        except discord.Forbidden:
            print(f"Bot forbidden from accessing channel {channel_id} to check message {message_id}. Assuming exists.")
            return True
        except Exception as e:
            print(f"Error checking existence of Discord message {message_id} in channel {channel_id}: {e}")
            return True

    async def get_message_by_id(self, channel_id, message_id):
        """Fetch a single Discord message and return parsed dict, or None if inaccessible."""
        print(f"Discord: Fetching single message {message_id} from channel {channel_id}...")
        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                channel = await self.client.fetch_channel(int(channel_id))
            msg = await channel.fetch_message(int(message_id))
            if not msg:
                return None
            if msg.webhook_id or msg.author.bot:
                return None
            attachments_data = []
            for attachment in msg.attachments:
                attachments_data.append({
                    "id": str(attachment.id),
                    "filename": attachment.filename,
                    "url": str(attachment.url)
                })
            reactions_data = []
            for reaction in msg.reactions:
                emoji_info = {}
                if isinstance(reaction.emoji, discord.Emoji):
                    emoji_info = {
                        "type": "custom",
                        "id": str(reaction.emoji.id),
                        "name": reaction.emoji.name,
                        "animated": reaction.emoji.animated,
                        "url": str(reaction.emoji.url)
                    }
                elif isinstance(reaction.emoji, str):
                    emoji_info = {"type": "unicode", "name": reaction.emoji}
                if emoji_info:
                    reactions_data.append(emoji_info)
            reply_to_discord_id = None
            if msg.reference and msg.reference.message_id:
                reply_to_discord_id = str(msg.reference.message_id)
            parsed = {
                "id": str(msg.id),
                "author": {
                    "username": msg.author.name,
                    "discriminator": msg.author.discriminator,
                    "avatar_url": str(msg.author.display_avatar.url) if msg.author.display_avatar else None
                },
                "content": msg.content or "",
                "timestamp": msg.created_at.isoformat(),
                "attachments": attachments_data,
                "reactions": reactions_data,
                "reply_to_discord_id": reply_to_discord_id
            }
            return parsed
        except discord.NotFound:
            return None
        except discord.Forbidden:
            print(f"Discord: Forbidden fetching message {message_id} in channel {channel_id}.")
            return None
        except Exception as e:
            print(f"Discord: Error fetching message {message_id} in channel {channel_id}: {e}")
            return None
