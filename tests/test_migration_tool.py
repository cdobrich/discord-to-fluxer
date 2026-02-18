import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import builtins
import os
from config import AppConfig, load_config
from revolt_client import RevoltClient
from discord_client import DiscordClient
import discord # Import discord to access discord.TextChannel


class TestMigrationTool(unittest.IsolatedAsyncioTestCase):

    @patch("builtins.open", new_callable=mock_open, read_data="FAKE_DISCORD_TOKEN")
    @patch("yaml.safe_load")
    def test_config_loading(self, mock_yaml, mock_open_file):
        # Simulate config.yaml contents
        mock_yaml.return_value = {
            "discord": {"token_file": "discord_token.token", "guild_id": "1234567890"},
            "revolt": {"token_file": "revolt_token.token", "server_id": "abcdef"},
            "delays": {"between_messages_seconds": 0.1, "between_channels_seconds": 0.5}
        }
        config = load_config()
        self.assertEqual(config.discord_token, "FAKE_DISCORD_TOKEN")
        self.assertEqual(config.discord_guild_id, "1234567890")
        self.assertEqual(config.revolt_server_id, "abcdef")

    @patch("discord.Client.start", new_callable=AsyncMock)
    @patch("discord_to_revolt.discord.Client", autospec=True)
    async def test_discord_client_connection(self, mock_client_class, mock_start):
        mock_client = mock_client_class.return_value
        mock_client.user = MagicMock(id="123", name="BotUser")
        client = DiscordClient(token="FAKE_DISCORD_TOKEN")
        # manually set the ready event since `on_ready` won't be triggered
        client._ready_event.set()
        await client.start()
        self.assertTrue(mock_client.start.called)
            
    @patch("discord_to_revolt.discord.Client")
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

    @patch("pyvolt.Client.fetch_server", new_callable=AsyncMock)
    async def test_revolt_client_connection(self, mock_fetch_server):
        mock_fetch_server.return_value = MagicMock(id="abc123", name="TestServer")
        client = RevoltClient(token="FAKE_REVOLT_TOKEN", revolt_server_id="abc123")
        await client.start()
        self.assertEqual(client.revolt_server.id, "abc123")

    @patch("aiohttp.ClientSession.get")
    async def test_revolt_fetch_channels(self, mock_get):
        mock_response = AsyncMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.status = 200
        mock_response.json.return_value = {
            "channels": [
                {"_id": "chan1", "name": "chat", "channel_type": "TextChannel"}
            ]
        }
        mock_get.return_value = mock_response

        client = RevoltClient(token="FAKE", revolt_server_id="abc")
        result = await client.get_server_channels("abc")
        self.assertEqual(result[0]['name'], "chat")
        self.assertEqual(result[0]['type'], "text")

    @patch("pyvolt.Server.create_channel", new_callable=AsyncMock)
    async def test_revolt_create_channel(self, mock_create):
        # Properly mock the channel object with explicit attribute values
        mock_channel = MagicMock()
        mock_channel.id = "chan123"
        mock_channel.name = "general"
        mock_channel.type.name = "text"

        mock_create.return_value = mock_channel

        client = RevoltClient(token="FAKE", revolt_server_id="abc")
        client.revolt_server = MagicMock()
        client.revolt_server.create_channel = mock_create

        test_discord_channel = {
            "name": "general",
            "type": 0  # DiscordChannelType.text
        }

        result = await client._create_revolt_channel_from_discord(test_discord_channel)
        self.assertEqual(result["name"], "general")
        self.assertEqual(result["type"], "text")


    @patch("aiohttp.ClientSession.post")
    async def test_revolt_send_message(self, mock_post):
        mock_response = AsyncMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.status = 200
        mock_response.json.return_value = {"_id": "msg123"}
        mock_post.return_value = mock_response

        client = RevoltClient(token="FAKE", revolt_server_id="abc")
        result = await client.send_message(
            channel_id="chan1",
            content="Hello",
            attachments=None
        )
        self.assertEqual(result['id'], "msg123")

    @patch("aiohttp.ClientSession.post")
    async def test_revolt_send_message_with_attachments(self, mock_post):
        mock_response = AsyncMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.status = 200
        mock_response.json.return_value = {"_id": "msg456"}
        mock_post.return_value = mock_response

        client = RevoltClient(token="FAKE", revolt_server_id="abc")
        result = await client.send_message(
            channel_id="chan1",
            content="File attached",
            attachments=["att123"]
        )
        self.assertEqual(result['id'], "msg456")

class TestConfigLoading(unittest.TestCase):
    def test_load_test_config_file(self):
        config = load_config("tests/test_config.yaml")
        self.assertEqual(config.discord_token, "FAKE_DISCORD_TOKEN")
        self.assertEqual(config.revolt_server_id, "test_server_123")
        self.assertEqual(config.discord_guild_id, "111111111111111111")

if __name__ == "__main__":
    unittest.main()