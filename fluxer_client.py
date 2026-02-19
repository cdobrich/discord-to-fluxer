import asyncio
import traceback
from typing import Any

from fluxer.client import Client as FluxerClientBase
from fluxer.http import HTTPClient
from fluxer.enums import ChannelType
from fluxer.errors import HTTPException
from fluxer.models import Channel, Guild, Message, Emoji


class FluxerClient:
    """
    A client for interacting with the Fluxer API using fluxer.py.
    Uses fluxer.client.Client for all interactions.
    """
    def __init__(self, token: str, fluxer_guild_id: str):
        self.token = token
        self.fluxer_guild_id = fluxer_guild_id
        # Sanitize token for printing to avoid exposing full token in logs.
        sanitized_token = '*' * (len(token) - 4) + token[-4:] if token else 'None'
        print(f"FluxerClient initialized with token (last 4 chars): {sanitized_token}")
        self.fluxer_bot = FluxerClientBase() # Using the base Client for direct API calls

        self.fluxer_guild: Guild | None = None

    async def start(self):
        """Connects to Fluxer and fetches the target guild's information, with retries."""
        print(f"FluxerClient: Attempting to connect to Fluxer and fetch guild with ID: {self.fluxer_guild_id}...")
        
        self.fluxer_bot._http = HTTPClient(self.token)
        max_retries = 3
        retry_delay = 5  # seconds

        for attempt in range(max_retries):
            try:
                print(f"FluxerClient: Connection attempt {attempt + 1}/{max_retries}...")
                await self.fluxer_bot._http._ensure_session() # Initialize HTTP client session

                self.fluxer_guild = await self.fluxer_bot.fetch_guild(self.fluxer_guild_id)
                
                if not self.fluxer_guild:
                    print(f"FluxerClient: Error: Target Fluxer guild with ID {self.fluxer_guild_id} not found.")
                    raise ValueError(f"Target Fluxer guild {self.fluxer_guild_id} not found.")
                
                print(f"FluxerClient: Successfully fetched Fluxer guild '{self.fluxer_guild.name}' (ID: {self.fluxer_guild.id}).")
                return # Success

            except HTTPException as e:
                print(f"FluxerClient: Caught HTTPException during guild fetch: Status={e.status}, Code={e.code}, Message={e.message}")
                if e.status == 404:
                    print(f"FluxerClient: (Info) 'NotFound' error for guild ID {self.fluxer_guild_id}. This means the guild ID is likely incorrect or the bot is not a member of it, even if the token is valid.")
                    raise ValueError(f"Target Fluxer guild {self.fluxer_guild_id} not found or accessible by bot. Please check config.yaml and bot's guild membership/permissions.") from e
                elif e.status == 401:
                    print(f"FluxerClient: (Critical) 'Unauthorized' error received from Fluxer for guild ID {self.fluxer_guild_id}.")
                    print("FluxerClient: This error indicates an invalid token or insufficient permissions.")
                    raise ValueError(f"Fluxer API returned 'Unauthorized' for guild ID {self.fluxer_guild_id}. Please double-check your bot token and permissions.") from e
                
                # For other HTTP errors (like 5xx server errors), we retry.
                print(f"FluxerClient: A recoverable HTTP error occurred: {e}")

            except Exception as e:
                # This catches connection errors like 'Connection reset by peer'
                print(f"FluxerClient: An unexpected connection error occurred: Type={type(e).__name__}, Message={e}")

            if attempt < max_retries - 1:
                print(f"FluxerClient: Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                print(f"FluxerClient: All {max_retries} attempts failed. Could not connect to Fluxer.")
                print("FluxerClient: Printing full traceback for the final error:")
                traceback.print_exc()
                raise ConnectionError("Failed to connect to Fluxer API after multiple retries.")

    async def close(self):
        """Closes the Fluxer client session."""
        print("FluxerClient closing.")
        await self.fluxer_bot.close()

    async def _create_fluxer_channel_from_discord(self, discord_channel_data: dict[str, Any]) -> Channel | None:
        """
        Creates a channel on Fluxer based on Discord channel data.
        Handles mapping Discord channel types to Fluxer channel types.
        This function should only be called for actual text/voice channels.
        """
        fluxer_channel_type: ChannelType | None = None
        # Assuming Discord.ChannelType.text.value is 0 and voice is 2
        if discord_channel_data["type"] == 0: # Discord.ChannelType.text.value
            fluxer_channel_type = ChannelType.GUILD_TEXT
        elif discord_channel_data["type"] == 2: # Discord.ChannelType.voice.value
            fluxer_channel_type = ChannelType.GUILD_VOICE
        else:
            print(f"Warning: Discord channel type {discord_channel_data['type']} for channel '{discord_channel_data['name']}' not supported for direct creation on Fluxer (was not text or voice). Skipping.")
            return None

        if fluxer_channel_type is None:
            print(f"Error: Could not determine Fluxer channel type for Discord channel '{discord_channel_data['name']}' (type: {discord_channel_data['type']}). Skipping.")
            return None

        if not self.fluxer_guild:
            print("Error: Fluxer guild not initialized. Cannot create channel.")
            return None

        print(f"Fluxer: Creating channel '{discord_channel_data['name']}' (type: {fluxer_channel_type.name}) in guild {self.fluxer_guild.id}")
        try:
            created_channel_data = await self.fluxer_bot._http.create_guild_channel(
                guild_id=self.fluxer_guild.id,
                name=discord_channel_data["name"],
                type=fluxer_channel_type.value,
                topic="", # Discord channels don't have descriptions, so default empty
                nsfw=False # Default to False, can be updated later if needed
            )
            created_channel = Channel.from_data(created_channel_data, self.fluxer_bot._http)
            print(f"Fluxer: Successfully created channel '{created_channel.name}' (ID: {created_channel.id}).")
            return created_channel
        except HTTPException as e:
            print(f"Error creating Fluxer channel '{discord_channel_data['name']}': Status={e.status}, Code={e.code}, Message={e.message}")
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"An unexpected error occurred creating Fluxer channel '{discord_channel_data['name']}': {e}")
            traceback.print_exc()
            return None

    async def get_server_channels(self, guild_id: str) -> list[dict[str, Any]]:
        """
        Fetches channels from a Fluxer guild.
        Returns a list of dictionaries with 'id', 'name', 'type', 'parent_id'.
        """
        print(f"Fluxer: Fetching channels for guild {guild_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot fetch channels.")
            return []

        try:
            channels_data = await self.fluxer_bot._http.get_guild_channels(guild_id)
            parsed_channels = []
            for channel in channels_data:
                parsed_channels.append({
                    "id": str(channel['id']), # Ensure ID is string for consistency
                    "name": channel['name'],
                    "type": ChannelType(channel['type']).name.lower().replace('guild_', ''), # Map to simpler type name
                    "parent_id": str(channel['parent_id']) if channel.get('parent_id') else None
                })
            print(f"Fluxer: Successfully fetched {len(parsed_channels)} channels for guild {guild_id}.")
            return parsed_channels
        except HTTPException as e:
            print(f"Fluxer: Error fetching channels for guild {guild_id}: Status={e.status}, Code={e.code}, Message={e.message}")
            if e.status == 401:
                print("Fluxer: Unauthorized (401) - Check your Fluxer bot token and its permissions to view the guild and channels.")
            elif e.status == 404:
                print(f"Fluxer: Not Found (404) - The Fluxer guild ID '{guild_id}' might be incorrect, or the bot is not a member of it, or lacks 'View Channels' permission.")
            return []
        except Exception as e:
            print(f"An unexpected error occurred fetching Fluxer channels: {e}")
            traceback.print_exc()
            return []

    async def get_guild_channels(self, guild_id: str) -> list[dict[str, Any]]:
        """
        Fetches channels from a Fluxer guild.
        Returns a list of dictionaries with 'id', 'name', 'type', 'parent_id'.
        """
        return await self.get_server_channels(guild_id)

    async def send_message(self, channel_id: str, content: str, attachments: list[dict[str, Any]] | None = None, max_retries: int = 3) -> dict[str, Any] | None:
        """
        Sends a message with optional attachments to a Fluxer channel.
        Attachments should be a list of dicts, each with 'filename' and 'data' (bytes).
        """
        print(f"Fluxer: Attempting to send message to channel {channel_id} with content: {content[:50]}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot send message.")
            return None

        files_to_send = []
        if attachments:
            for attachment in attachments:
                files_to_send.append({
                    "filename": attachment["filename"],
                    "data": attachment["data"]
                })
            print(f"Fluxer: Preparing to send {len(files_to_send)} attachments.")

        for attempt in range(max_retries):
            try:
                message_data = await self.fluxer_bot._http.send_message(
                    channel_id=channel_id,
                    content=content,
                    files=files_to_send if files_to_send else None
                )
                print(f"Fluxer: Successfully sent message to channel {channel_id}. Message ID: {message_data.get('id')}")
                return message_data
            except HTTPException as e:
                print(f"Fluxer: Error sending message (HTTP {e.status}): {e.message}. Attempt {attempt + 1}/{max_retries}")
                if e.status == 401:
                    print("Fluxer: Unauthorized (401) - Check bot token and 'Send Messages' permission.")
                    return None
                elif e.status == 403:
                    print("Fluxer: Forbidden (403) - Bot lacks 'Send Messages' permission in this channel.")
                    return None
                elif e.status == 404:
                    print(f"Fluxer: Channel {channel_id} not found. Skipping.")
                    return None
                elif e.status == 429: # Rate limit
                    wait_time = e.retry_after if hasattr(e, 'retry_after') and e.retry_after else (2 ** attempt)
                    print(f"Fluxer: Rate limit hit. Waiting for {wait_time:.2f} seconds.")
                    await asyncio.sleep(wait_time)
                elif 500 <= e.status < 600: # Server errors (5xx)
                    wait_time = 2 ** attempt
                    print(f"Fluxer: Server error (HTTP {e.status}). Retrying in {wait_time} seconds.")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Fluxer: Unhandled HTTP error {e.status}. Not retrying.")
                    return None
            except Exception as e:
                print(f"An unexpected error occurred sending message: {e}")
                traceback.print_exc()
                return None

        print(f"Fluxer: Failed to send message to channel {channel_id} after {max_retries} attempts.")
        return None

    async def edit_message(self, channel_id: str, message_id: str, new_content: str, new_attachments: list[Any] | None = None, max_retries: int = 3) -> bool:
        """
        Edits an existing message in a Fluxer channel.
        Note: Fluxer.py's edit_message does not directly support editing attachments.
        """
        print(f"Fluxer: Attempting to edit message {message_id} in channel {channel_id} with content: {new_content[:50]}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot edit message.")
            return False

        if new_attachments:
            print("Warning: Fluxer.py does not directly support editing message attachments. Attachments will be ignored.")

        for attempt in range(max_retries):
            try:
                await self.fluxer_bot._http.edit_message(
                    channel_id=channel_id,
                    message_id=message_id,
                    content=new_content
                )
                print(f"Fluxer: Successfully edited message {message_id} in channel {channel_id}.")
                return True
            except HTTPException as e:
                print(f"Fluxer: Error editing message {message_id} (HTTP {e.status}): {e.message}. Attempt {attempt + 1}/{max_retries}")
                if e.status == 401:
                    print("Fluxer: Unauthorized (401) - Check bot token and 'Manage Messages' permission for editing.")
                    return False
                elif e.status == 403:
                    print("Fluxer: Forbidden (403) - Bot lacks 'Manage Messages' permission for editing in this channel.")
                    return False
                elif e.status == 404:
                    print(f"Fluxer: Message {message_id} or channel {channel_id} not found for editing. Skipping.")
                    return False
                elif e.status == 429: # Rate limit
                    wait_time = e.retry_after if e.retry_after else (2 ** attempt)
                    print(f"Fluxer: Rate limit hit during edit. Waiting for {wait_time:.2f} seconds.")
                    await asyncio.sleep(wait_time)
                elif 500 <= e.status < 600: # Server errors (5xx)
                    wait_time = 2 ** attempt
                    print(f"Fluxer: Server error (HTTP {e.status}) during edit. Retrying in {wait_time} seconds.")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Fluxer: Unhandled HTTP error {e.status} during edit. Not retrying.")
                    return False
            except Exception as e:
                print(f"An unexpected error occurred editing message {message_id}: {e}")
                traceback.print_exc()
                return False

        print(f"Fluxer: Failed to edit message {message_id} after {max_retries} attempts.")
        return False

    async def get_server_emojis(self, guild_id: str) -> list[dict[str, Any]]:
        """
        Fetches custom emojis from a Fluxer guild.
        Returns a list of dictionaries with 'id', 'name'.
        """
        print(f"Fluxer: Fetching existing emojis for guild {guild_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot fetch emojis.")
            return []

        try:
            emojis_data = await self.fluxer_bot._http.get_guild_emojis(guild_id)
            parsed_emojis = []
            for emoji in emojis_data:
                parsed_emojis.append({
                    "id": str(emoji['id']),
                    "name": emoji['name']
                })
            print(f"Fluxer: Successfully fetched {len(parsed_emojis)} existing emojis for guild {guild_id}.")
            return parsed_emojis
        except HTTPException as e:
            print(f"Fluxer: Error fetching existing emojis for guild {guild_id}: Status={e.status}, Code={e.code}, Message={e.message}")
            return []
        except Exception as e:
            print(f"An unexpected error occurred fetching existing Fluxer emojis: {e}")
            traceback.print_exc()
            return []

    async def get_guild_emojis(self, guild_id: str) -> list[dict[str, Any]]:
        """
        Fetches custom emojis from a Fluxer guild.
        Returns a list of dictionaries with 'id', 'name'.
        """
        return await self.get_server_emojis(guild_id)

    async def create_emoji(self, guild_id: str, name: str, file_data: bytes) -> dict[str, Any] | None:
        """
        Uploads an emoji to a Fluxer guild.
        The file_data should be the raw bytes of the image.
        """
        print(f"Fluxer: Attempting to create emoji '{name}' on guild {guild_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot create emoji.")
            return None

        try:
            emoji_data = await self.fluxer_bot._http.create_guild_emoji(
                guild_id=guild_id,
                name=name,
                image=file_data
            )
            print(f"Fluxer: Successfully created emoji '{name}' with ID {emoji_data['id']}.")
            return {"id": str(emoji_data['id']), "name": emoji_data['name']}
        except HTTPException as e:
            print(f"Fluxer: Error creating emoji '{name}' (HTTP {e.status}): {e.message}")
            if e.status == 401:
                print("Fluxer: Unauthorized (401) - Check your Fluxer bot token and 'Manage Emojis' permission.")
            elif e.status == 403:
                print("Fluxer: Forbidden (403) - Bot does not have 'Manage Emojis' permission on the guild.")
            elif e.status == 400:
                # Fluxer API might return specific error codes or messages for "AlreadyExists"
                if "already exists" in e.message.lower(): # Heuristic check
                    print(f"Fluxer: Emoji '{name}' already exists on guild {guild_id}. Skipping creation.")
                else:
                    print(f"Fluxer: Bad Request (400) creating emoji '{name}'. Message: {e.message}. Check emoji name validity (alphanumeric, underscores only) or other payload issues.")
            else:
                print(f"Fluxer: Other HTTP error {e.status} creating emoji '{name}': {e.message}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred creating emoji '{name}': {e}")
            traceback.print_exc()
            return None

    async def apply_reaction(self, channel_id: str, message_id: str, emoji_id_or_name: str) -> bool:
        """
        Applies a reaction to a Fluxer message.
        Note: Fluxer.py does not currently have a direct API for applying reactions.
        This method is a placeholder.
        """
        print(f"Fluxer: (Placeholder) Attempting to apply reaction '{emoji_id_or_name}' to message {message_id} in channel {channel_id}...")
        print("Fluxer: Reaction functionality is not directly supported by the current Fluxer.py library wrapper.")
        return False

    async def pin_message(self, channel_id: str, message_id: str, max_retries: int = 3) -> bool:
        """
        Pins a message in a Fluxer channel.
        Note: Fluxer.py does not currently have a direct API for pinning messages.
        This method is a placeholder.
        """
        print(f"Fluxer: (Placeholder) Attempting to pin message {message_id} in channel {channel_id}...")
        print("Fluxer: Pin message functionality is not directly supported by the current Fluxer.py library wrapper.")
        return False

    async def unpin_message(self, channel_id: str, message_id: str, max_retries: int = 3) -> bool:
        """
        Unpins a message in a Fluxer channel.
        Note: Fluxer.py does not currently have a direct API for unpinning messages.
        This method is a placeholder.
        """
        print(f"Fluxer: (Placeholder) Attempting to unpin message {message_id} in channel {channel_id}...")
        print("Fluxer: Unpin message functionality is not directly supported by the current Fluxer.py library wrapper.")
        return False

    async def delete_message(self, channel_id: str, message_id: str, max_retries: int = 3) -> bool:
        """
        Deletes a message in a Fluxer channel.
        """
        print(f"Fluxer: Attempting to delete message {message_id} in channel {channel_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot delete message.")
            return False

        for attempt in range(max_retries):
            try:
                await self.fluxer_bot._http.delete_message(channel_id=channel_id, message_id=message_id)
                print(f"Fluxer: Successfully deleted message {message_id} in channel {channel_id}.")
                return True
            except HTTPException as e:
                print(f"Fluxer: Error deleting message {message_id} (HTTP {e.status}): {e.message}. Attempt {attempt + 1}/{max_retries}")
                if e.status == 401:
                    print("Fluxer: Unauthorized (401) - Check bot token and 'Manage Messages' permission for deleting.")
                    return False
                elif e.status == 403:
                    print("Fluxer: Forbidden (403) - Bot lacks 'Manage Messages' permission for deleting in this channel.")
                    return False
                elif e.status == 404:
                    print(f"Fluxer: Message {message_id} or channel {channel_id} not found for deleting. Skipping.")
                    return False
                elif e.status == 429: # Rate limit
                    wait_time = e.retry_after if e.retry_after else (2 ** attempt)
                    print(f"Fluxer: Rate limit hit during delete. Waiting for {wait_time:.2f} seconds.")
                    await asyncio.sleep(wait_time)
                elif 500 <= e.status < 600: # Server errors (5xx)
                    wait_time = 2 ** attempt
                    print(f"Fluxer: Server error (HTTP {e.status}) during delete. Retrying in {wait_time} seconds.")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Fluxer: Unhandled HTTP error {e.status} during delete. Not retrying.")
                    return False
            except Exception as e:
                print(f"An unexpected error occurred deleting message {message_id}: {e}")
                traceback.print_exc()
                return False

        print(f"Fluxer: Failed to delete message {message_id} after {max_retries} attempts.")
        return False

    async def get_channel_pinned_messages(self, channel_id: str) -> list[dict[str, Any]]:
        """
        Fetches pinned messages from a Fluxer channel.
        Note: Fluxer.py's get_messages does not have a 'pinned' parameter.
        This method is a placeholder.
        """
        print(f"Fluxer: (Placeholder) Attempting to fetch pinned messages for channel {channel_id}...")
        print("Fluxer: Fetching pinned messages functionality is not directly supported by the current Fluxer.py library wrapper.")
        return []

    async def get_pinned_message_ids(self, channel_id: str) -> list[str]:
        """
        Fetches IDs of pinned messages from a Fluxer channel.
        Note: Fluxer.py's get_messages does not have a 'pinned' parameter.
        This method is a placeholder.
        """
        print(f"Fluxer: (Placeholder) Attempting to fetch pinned message IDs for channel {channel_id}...")
        print("Fluxer: Fetching pinned message IDs functionality is not directly supported by the current Fluxer.py library wrapper.")
        return []
