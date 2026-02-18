import unittest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from config import AppConfig, load_config
from fluxer_client import FluxerClient
from discord_client import DiscordClient
import discord # Import discord to access discord.TextChannel
from fluxer.enums import ChannelType

class TestMigrationTool(unittest.IsolatedAsyncioTestCase):

    @patch("builtins.open", new_callable=mock_open, read_data="FAKE_DISCORD_TOKEN")
    @patch("yaml.safe_load")
    def test_config_loading(self, mock_yaml, mock_open_file):
        # Simulate config.yaml contents
        mock_yaml.return_value = {
            "discord": {"token_file": "discord_token.token", "guild_id": "1234567890"},
            "fluxer": {"token_file": "fluxer_token.token", "server_id": "abcdef"},
            "delays": {"between_messages_seconds": 0.1, "between_channels_seconds": 0.5}
        }
        config = load_config()
        self.assertEqual(config.discord_token, "FAKE_DISCORD_TOKEN")
        self.assertEqual(config.discord_guild_id, "1234567890")
        self.assertEqual(config.fluxer_server_id, "abcdef")

    @patch("discord.Client.start", new_callable=AsyncMock)
    @patch("discord_to_fluxer.discord.Client", autospec=True)
    async def test_discord_client_connection(self, mock_client_class, mock_start):
        mock_client = mock_client_class.return_value
        mock_client.user = MagicMock(id="123", name="BotUser")
        client = DiscordClient(token="FAKE_DISCORD_TOKEN")
        # manually set the ready event since `on_ready` won't be triggered
        client._ready_event.set()
        await client.start()
        self.assertTrue(mock_client.start.called)
            
    @patch("discord_to_fluxer.discord.Client")
    async def test_discord_get_channels(self, mock_client_class):
        # Create mock client instance
        mock_client_instance = mock_client_class.return_value

        # Setup mock channel
        mock_channel = MagicMock()
        mock_channel.id = 123
        mock_channel.name = "general"
        mock_channel.type.value = 0  # Text channel
        mock_channel.position = 1
        mock_channel.category_id = None
        # Fix: Make mock_channel behave like a discord.TextChannel for isinstance checks
        mock_channel.__class__ = discord.TextChannel 

        # Setup mock guild with `.channels`
        mock_guild = MagicMock()
        mock_guild.channels = [mock_channel]

        # Fix: get_guild is synchronous, so it should return the mock_guild directly.
        # fetch_guild is asynchronous, so it should be an AsyncMock.
        mock_client_instance.get_guild.return_value = mock_guild
        mock_client_instance.fetch_guild = AsyncMock(return_value=mock_guild)

        # Run the test
        client = DiscordClient("TOKEN")
        result = await client.get_guild_channels("123")

        # Assertions
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "general")
        # Ensure ID is a string as per parsed_channels in DiscordClient
        self.assertEqual(result[0]["id"], "123") 

    @patch("fluxer_api.client.Client.fetch_guild", new_callable=AsyncMock)
    @patch("fluxer_api.http.HTTPClient._ensure_session", new_callable=AsyncMock)
    async def test_fluxer_client_connection(self, mock_ensure_session, mock_fetch_guild):
        mock_fetch_guild.return_value = MagicMock(id="abc123", name="TestServer")
        client = FluxerClient(token="FAKE_FLUXER_TOKEN", fluxer_guild_id="abc123")
        await client.start()
        self.assertEqual(client.fluxer_guild.id, "abc123")

    @patch("fluxer_api.http.HTTPClient.get_guild_channels", new_callable=AsyncMock)
    async def test_fluxer_fetch_channels(self, mock_get_channels):
        mock_get_channels.return_value = [
            {"id": "chan1", "name": "chat", "type": ChannelType.GUILD_TEXT.value, "parent_id": None}
        ]

        client = FluxerClient(token="FAKE", fluxer_guild_id="abc")
        # Initialize http client manually as start() is not called
        from fluxer_api.http import HTTPClient
        client.fluxer_bot._http = HTTPClient("FAKE")
        
        result = await client.get_guild_channels("abc")
        self.assertEqual(result[0]['name'], "chat")
        self.assertEqual(result[0]['type'], "text")

    @patch("fluxer_api.http.HTTPClient.create_guild_channel", new_callable=AsyncMock)
    async def test_fluxer_create_channel(self, mock_create):
        mock_create.return_value = {
            "id": "chan123",
            "name": "general",
            "type": ChannelType.GUILD_TEXT.value,
            "guild_id": "abc"
        }

        client = FluxerClient(token="FAKE", fluxer_guild_id="abc")
        client.fluxer_guild = MagicMock()
        client.fluxer_guild.id = "abc"
        # Initialize http client
        from fluxer_api.http import HTTPClient
        client.fluxer_bot._http = HTTPClient("FAKE")

        test_discord_channel = {
            "name": "general",
            "type": 0  # DiscordChannelType.text
        }

        result = await client._create_fluxer_channel_from_discord(test_discord_channel)
        self.assertEqual(result.name, "general")
        self.assertEqual(result.type, ChannelType.GUILD_TEXT.value)

class TestConfigLoading(unittest.TestCase):
    def test_load_test_config_file(self):
        config = load_config("tests/test_config.yaml")
        self.assertEqual(config.discord_token, "FAKE_DISCORD_TOKEN")
        self.assertEqual(config.fluxer_server_id, "test_server_123")
        self.assertEqual(config.discord_guild_id, "111111111111111111")

if __name__ == "__main__":
    unittest.main()