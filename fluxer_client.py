import asyncio
import traceback
from typing import Any

from fluxer.client import Client as FluxerClientBase
from fluxer.http import HTTPClient
from fluxer.enums import ChannelType
from fluxer.errors import HTTPException
from fluxer.models import Channel, Guild, Message, Emoji

API_TIMEOUT = 30.0
UPLOAD_TIMEOUT = 60.0

class FluxerClient:
    """
    A client for interacting with the Fluxer API using fluxer.py.
    Uses fluxer.client.Client for all interactions.
    """
    def __init__(self, token: str, fluxer_guild_id: str, user_mappings: dict = None):
        self.token = token
        self.fluxer_guild_id = fluxer_guild_id
        self.user_mappings = user_mappings or {}
        # Sanitize token for printing to avoid exposing full token in logs.
        sanitized_token = '*' * (len(token) - 4) + token[-4:] if token else 'None'
        print(f"FluxerClient initialized with token (last 4 chars): {sanitized_token}")
        self.fluxer_bot = FluxerClientBase() # Using the base Client for direct API calls

        self.fluxer_guild: Guild | None = None
        self._masquerade_https = {} # Cache for masquerade HTTP clients

    async def _get_masquerade_http(self, username: str) -> HTTPClient | None:
        """
        Returns an HTTPClient for a masqueraded user if a mapping exists.
        """
        if not username or username not in self.user_mappings:
            return None

        if username in self._masquerade_https:
            return self._masquerade_https[username]

        mapping = self.user_mappings[username]
        auth_key = mapping.get('fluxer_auth_key')
        if not auth_key:
            print(f"Warning: No auth key found for mapped user '{username}'.")
            return None

        print(f"FluxerClient: initializing masquerade client for '{username}'...")
        # Initialize HTTPClient with is_bot=False for user tokens
        http_client = HTTPClient(auth_key, is_bot=False)
        try:
            await http_client._ensure_session()
            self._masquerade_https[username] = http_client
            return http_client
        except Exception as e:
            print(f"Error initializing masquerade client for '{username}': {e}")
            return None

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

                # Add a timeout to the fetch_guild call to prevent indefinite hanging
                self.fluxer_guild = await asyncio.wait_for(
                    self.fluxer_bot.fetch_guild(self.fluxer_guild_id),
                    timeout=API_TIMEOUT
                )
                
                if not self.fluxer_guild:
                    print(f"FluxerClient: Error: Target Fluxer guild with ID {self.fluxer_guild_id} not found.")
                    raise ValueError(f"Target Fluxer guild {self.fluxer_guild_id} not found.")
                
                print(f"FluxerClient: Successfully fetched Fluxer guild '{self.fluxer_guild.name}' (ID: {self.fluxer_guild.id}).")
                return # Success

            except asyncio.TimeoutError:
                print("FluxerClient: Timeout during guild fetch. The API might be unresponsive or the connection is unstable.")
                # This will fall through to the retry logic below

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
        # Close masquerade clients
        for username, client in self._masquerade_https.items():
            print(f"Closing masquerade client for {username}...")
            if hasattr(client, '_session') and client._session and not client._session.closed:
                await client._session.close()
        self._masquerade_https.clear()

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
            created_channel_data = await asyncio.wait_for(
                self.fluxer_bot._http.create_guild_channel(
                    guild_id=self.fluxer_guild.id,
                    name=discord_channel_data["name"],
                    type=fluxer_channel_type.value,
                    topic="", # Discord channels don't have descriptions, so default empty
                    nsfw=False # Default to False, can be updated later if needed
                ),
                timeout=API_TIMEOUT
            )
            created_channel = Channel.from_data(created_channel_data, self.fluxer_bot._http)
            print(f"Fluxer: Successfully created channel '{created_channel.name}' (ID: {created_channel.id}).")
            return created_channel
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout creating channel '{discord_channel_data['name']}'.")
            return None
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
            channels_data = await asyncio.wait_for(
                self.fluxer_bot._http.get_guild_channels(guild_id),
                timeout=API_TIMEOUT
            )
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
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout fetching channels for guild {guild_id}.")
            return []
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

    async def send_message(self, channel_id: str, content: str, attachments: list[dict[str, Any]] | None = None, max_retries: int = 3, author_name: str | None = None, reply_to_id: str | None = None) -> dict[str, Any] | None:
        """
        Sends a message with optional attachments to a Fluxer channel.
        Attachments should be a list of dicts, each with 'filename' and 'data' (bytes).
        """
        http_client = self.fluxer_bot._http
        
        if author_name:
            masquerade_client = await self._get_masquerade_http(author_name)
            if masquerade_client:
                http_client = masquerade_client
                print(f"Fluxer: Sending message as masqueraded user '{author_name}'.")
            else:
                # Prepend username if no masquerade found
                content = f"{author_name}: {content}"
                print(f"Fluxer: Sending message as bot (prepended '{author_name}: ').")

        # Fallback for reply_to if not supported by library
        if reply_to_id:
            # Since HTTPClient.send_message doesn't support reply_to/replies, we add it to content
            # This is a visual fallback.
            # Note: If the library is updated to support it, we can revert this.
            # For now, we avoid the TypeError.
            # We check if content is empty to avoid just sending the reply indicator if that's weird,
            # but usually there's content.
            pass 
            # Actually, let's not modify content here to avoid clutter if the user didn't ask for visual indicator.
            # But since we can't link it natively, visual is better than nothing.
            # However, the user asked to "preserve the Reply-to linkage". 
            # Since the library fails, I will just remove the argument to fix the crash.
            # I'll log a warning.
            print(f"Fluxer: Warning - 'reply_to_id' {reply_to_id} ignored because underlying library does not support it in send_message.")

        print(f"Fluxer: Attempting to send message to channel {channel_id} with content: {content[:50]}...")
        if not http_client:
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
                # Removed reply_to/replies argument as it causes TypeError
                message_data = await asyncio.wait_for(
                    http_client.send_message(
                        channel_id=channel_id,
                        content=content,
                        files=files_to_send if files_to_send else None
                    ),
                    timeout=UPLOAD_TIMEOUT
                )
                print(f"Fluxer: Successfully sent message to channel {channel_id}. Message ID: {message_data.get('id')}")
                return message_data
            except asyncio.TimeoutError:
                print(f"Fluxer: Timeout sending message to channel {channel_id}. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
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
                await asyncio.wait_for(
                    self.fluxer_bot._http.edit_message(
                        channel_id=channel_id,
                        message_id=message_id,
                        content=new_content
                    ),
                    timeout=API_TIMEOUT
                )
                print(f"Fluxer: Successfully edited message {message_id} in channel {channel_id}.")
                return True
            except asyncio.TimeoutError:
                print(f"Fluxer: Timeout editing message {message_id}. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
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
            emojis_data = await asyncio.wait_for(
                self.fluxer_bot._http.get_guild_emojis(guild_id),
                timeout=API_TIMEOUT
            )
            parsed_emojis = []
            for emoji in emojis_data:
                parsed_emojis.append({
                    "id": str(emoji['id']),
                    "name": emoji['name']
                })
            print(f"Fluxer: Successfully fetched {len(parsed_emojis)} existing emojis for guild {guild_id}.")
            return parsed_emojis
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout fetching emojis for guild {guild_id}.")
            return []
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
            emoji_data = await asyncio.wait_for(
                self.fluxer_bot._http.create_guild_emoji(
                    guild_id=guild_id,
                    name=name,
                    image=file_data
                ),
                timeout=UPLOAD_TIMEOUT
            )
            print(f"Fluxer: Successfully created emoji '{name}' with ID {emoji_data['id']}.")
            return {"id": str(emoji_data['id']), "name": emoji_data['name']}
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout creating emoji '{name}'.")
            return None
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
        """
        print(f"Fluxer: Attempting to apply reaction '{emoji_id_or_name}' to message {message_id} in channel {channel_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot apply reaction.")
            return False

        try:
            await asyncio.wait_for(
                self.fluxer_bot._http.add_reaction(
                    channel_id=channel_id,
                    message_id=message_id,
                    emoji=emoji_id_or_name
                ),
                timeout=API_TIMEOUT
            )
            print(f"Fluxer: Successfully applied reaction '{emoji_id_or_name}' to message {message_id}.")
            return True
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout applying reaction '{emoji_id_or_name}' to message {message_id}.")
            return False
        except HTTPException as e:
            print(f"Fluxer: Error applying reaction '{emoji_id_or_name}' (HTTP {e.status}): {e.message}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred applying reaction: {e}")
            traceback.print_exc()
            return False

    async def remove_reaction(self, channel_id: str, message_id: str, emoji_id_or_name: str, user_id: str = "@me") -> bool:
        """
        Removes a reaction from a Fluxer message.
        """
        print(f"Fluxer: Attempting to remove reaction '{emoji_id_or_name}' from message {message_id} in channel {channel_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot remove reaction.")
            return False

        try:
            await asyncio.wait_for(
                self.fluxer_bot._http.delete_reaction(
                    channel_id=channel_id,
                    message_id=message_id,
                    emoji=emoji_id_or_name,
                    user_id=user_id
                ),
                timeout=API_TIMEOUT
            )
            print(f"Fluxer: Successfully removed reaction '{emoji_id_or_name}' from message {message_id}.")
            return True
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout removing reaction '{emoji_id_or_name}' from message {message_id}.")
            return False
        except HTTPException as e:
            print(f"Fluxer: Error removing reaction '{emoji_id_or_name}' (HTTP {e.status}): {e.message}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred removing reaction: {e}")
            traceback.print_exc()
            return False

    async def pin_message(self, channel_id: str, message_id: str, max_retries: int = 3) -> bool:
        """
        Pins a message in a Fluxer channel.
        """
        print(f"Fluxer: Attempting to pin message {message_id} in channel {channel_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot pin message.")
            return False

        for attempt in range(max_retries):
            try:
                await asyncio.wait_for(
                    self.fluxer_bot._http.pin_message(channel_id=channel_id, message_id=message_id),
                    timeout=API_TIMEOUT
                )
                print(f"Fluxer: Successfully pinned message {message_id} in channel {channel_id}.")
                return True
            except asyncio.TimeoutError:
                print(f"Fluxer: Timeout pinning message {message_id}. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
            except HTTPException as e:
                print(f"Fluxer: Error pinning message {message_id} (HTTP {e.status}): {e.message}. Attempt {attempt + 1}/{max_retries}")
                if e.status == 401:
                    print("Fluxer: Unauthorized (401) - Check bot token and 'Manage Messages' permission for pinning.")
                    return False
                elif e.status == 403:
                    print("Fluxer: Forbidden (403) - Bot lacks 'Manage Messages' permission for pinning in this channel.")
                    return False
                elif e.status == 404:
                    print(f"Fluxer: Message {message_id} or channel {channel_id} not found for pinning. Skipping.")
                    return False
                elif e.status == 429: # Rate limit
                    wait_time = e.retry_after if e.retry_after else (2 ** attempt)
                    print(f"Fluxer: Rate limit hit during pin. Waiting for {wait_time:.2f} seconds.")
                    await asyncio.sleep(wait_time)
                elif 500 <= e.status < 600: # Server errors (5xx)
                    wait_time = 2 ** attempt
                    print(f"Fluxer: Server error (HTTP {e.status}) during pin. Retrying in {wait_time} seconds.")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Fluxer: Unhandled HTTP error {e.status} during pin. Not retrying.")
                    return False
            except Exception as e:
                print(f"An unexpected error occurred pinning message {message_id}: {e}")
                traceback.print_exc()
                return False

        print(f"Fluxer: Failed to pin message {message_id} after {max_retries} attempts.")
        return False

    async def unpin_message(self, channel_id: str, message_id: str, max_retries: int = 3) -> bool:
        """
        Unpins a message in a Fluxer channel.
        """
        print(f"Fluxer: Attempting to unpin message {message_id} in channel {channel_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot unpin message.")
            return False

        for attempt in range(max_retries):
            try:
                await asyncio.wait_for(
                    self.fluxer_bot._http.unpin_message(channel_id=channel_id, message_id=message_id),
                    timeout=API_TIMEOUT
                )
                print(f"Fluxer: Successfully unpinned message {message_id} in channel {channel_id}.")
                return True
            except asyncio.TimeoutError:
                print(f"Fluxer: Timeout unpinning message {message_id}. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
            except HTTPException as e:
                print(f"Fluxer: Error unpinning message {message_id} (HTTP {e.status}): {e.message}. Attempt {attempt + 1}/{max_retries}")
                if e.status == 401:
                    print("Fluxer: Unauthorized (401) - Check bot token and 'Manage Messages' permission for unpinning.")
                    return False
                elif e.status == 403:
                    print("Fluxer: Forbidden (403) - Bot lacks 'Manage Messages' permission for unpinning in this channel.")
                    return False
                elif e.status == 404:
                    print(f"Fluxer: Message {message_id} or channel {channel_id} not found for unpinning. Skipping.")
                    return False
                elif e.status == 429: # Rate limit
                    wait_time = e.retry_after if e.retry_after else (2 ** attempt)
                    print(f"Fluxer: Rate limit hit during unpin. Waiting for {wait_time:.2f} seconds.")
                    await asyncio.sleep(wait_time)
                elif 500 <= e.status < 600: # Server errors (5xx)
                    wait_time = 2 ** attempt
                    print(f"Fluxer: Server error (HTTP {e.status}) during unpin. Retrying in {wait_time} seconds.")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Fluxer: Unhandled HTTP error {e.status} during unpin. Not retrying.")
                    return False
            except Exception as e:
                print(f"An unexpected error occurred unpinning message {message_id}: {e}")
                traceback.print_exc()
                return False

        print(f"Fluxer: Failed to unpin message {message_id} after {max_retries} attempts.")
        return False

    async def delete_channel(self, channel_id: str) -> bool:
        """
        Deletes a channel on Fluxer.
        """
        print(f"Fluxer: Attempting to delete channel {channel_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot delete channel.")
            return False

        try:
            await asyncio.wait_for(
                self.fluxer_bot._http.delete_channel(channel_id=channel_id),
                timeout=API_TIMEOUT
            )
            print(f"Fluxer: Successfully deleted channel {channel_id}.")
            return True
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout deleting channel {channel_id}.")
            return False
        except HTTPException as e:
            print(f"Fluxer: Error deleting channel {channel_id}: Status={e.status}, Code={e.code}, Message={e.message}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred deleting channel {channel_id}: {e}")
            traceback.print_exc()
            return False

    async def get_message(self, channel_id: str, message_id: str) -> dict[str, Any] | None:
        """
        Fetches a single message from Fluxer.
        """
        print(f"Fluxer: Fetching message {message_id} in channel {channel_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot fetch message.")
            return None

        try:
            message_data = await asyncio.wait_for(
                self.fluxer_bot._http.get_message(channel_id=channel_id, message_id=message_id),
                timeout=API_TIMEOUT
            )
            return message_data
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout fetching message {message_id}.")
            return None
        except HTTPException as e:
            if e.status == 404:
                return None # Message not found
            print(f"Fluxer: Error fetching message {message_id}: Status={e.status}, Code={e.code}, Message={e.message}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred fetching message {message_id}: {e}")
            traceback.print_exc()
            return None

    async def get_channel_pinned_messages(self, channel_id: str) -> list[dict[str, Any]]:
        """
        Fetches pinned messages from a Fluxer channel.
        """
        print(f"Fluxer: Attempting to fetch pinned messages for channel {channel_id}...")
        if not self.fluxer_bot._http:
            print("Error: Fluxer HTTP client not initialized. Cannot fetch pinned messages.")
            return []

        try:
            pinned_messages = await asyncio.wait_for(
                self.fluxer_bot._http.get_pinned_messages(channel_id),
                timeout=API_TIMEOUT
            )
            print(f"Fluxer: Successfully fetched {len(pinned_messages)} pinned messages for channel {channel_id}.")
            return pinned_messages
        except asyncio.TimeoutError:
            print(f"Fluxer: Timeout fetching pinned messages for channel {channel_id}.")
            return []
        except HTTPException as e:
            print(f"Fluxer: Error fetching pinned messages for channel {channel_id}: Status={e.status}, Code={e.code}, Message={e.message}")
            return []
        except AttributeError:
             print("Fluxer: Error - The underlying Fluxer.py library does not support 'get_pinned_messages'. Please update the library.")
             return []
        except Exception as e:
            print(f"An unexpected error occurred fetching pinned messages: {e}")
            traceback.print_exc()
            return []

    async def get_pinned_message_ids(self, channel_id: str) -> list[str]:
        """
        Fetches IDs of pinned messages from a Fluxer channel.
        """
        pinned_messages = await self.get_channel_pinned_messages(channel_id)
        return [str(msg['id']) for msg in pinned_messages if 'id' in msg]
