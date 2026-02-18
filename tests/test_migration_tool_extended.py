import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
import asyncio
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from config import load_config
from migration_tool import MigrationTool
from state_manager import StateManager
from revolt_client import RevoltClient


class TestExtendedMigrationTool(unittest.IsolatedAsyncioTestCase):

    def test_store_and_get_channel_mapping(self):
        db = StateManager(":memory:")
        db.connect()
        db.store_channel_mapping("discord123", "revolt456")
        revolt_id = db.get_revolt_channel_id("discord123")
        self.assertEqual(revolt_id, "revolt456")
        db.close()

    def test_store_and_get_last_migrated_message(self):
        db = StateManager(":memory:")
        db.connect()
        db.store_message_mapping("msg1", "rmsg1", "chan1", "rchan1")
        last_id = db.get_last_migrated_message_id("chan1")
        self.assertEqual(last_id, "msg1")
        db.close()

    @patch("aiohttp.ClientSession.post")
    async def test_revolt_upload_attachment_413(self, mock_post):
        mock_response = AsyncMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=None, history=None, status=413, message="Payload Too Large"
        )
        mock_post.return_value = mock_response

        client = RevoltClient("TOKEN", "server123")
        result = await client.upload_attachment(b"fake", "bigfile.png")
        self.assertIsNone(result)

    @patch("discord_to_revolt.RevoltClient.send_message", new_callable=AsyncMock)
    async def test_skip_empty_message_with_no_attachments(self, mock_send):
        config = load_config("tests/test_config.yaml")
        migrator = MigrationTool(config)

        migrator.discord_client = AsyncMock()
        migrator.revolt_client = AsyncMock()
        migrator.db = MagicMock()

        migrator.db.get_all_channel_mappings.return_value = [("chan1", "rchan1")]
        migrator.db.get_last_migrated_message_id.return_value = None
        migrator.discord_client.get_channel_messages.return_value = [{
            "id": "msg1",
            "author": {"username": "User", "discriminator": "1234", "avatar_url": None},
            "content": "",
            "timestamp": "2023-01-01T00:00:00",
            "attachments": [],
            "reply_to_discord_id": None
        }]

        await migrator.migrate_messages()
        mock_send.assert_not_awaited()


    @patch("discord_to_revolt.MigrationTool.setup_server_structure", new_callable=AsyncMock)
    @patch("discord_to_revolt.MigrationTool.migrate_messages", new_callable=AsyncMock)
    @patch("discord_to_revolt.MigrationTool.migrate_roles", new_callable=AsyncMock)
    @patch("discord_to_revolt.MigrationTool.migrate_members", new_callable=AsyncMock)
    @patch("discord_to_revolt.DiscordClient.start", new_callable=AsyncMock)
    @patch("discord_to_revolt.RevoltClient.start", new_callable=AsyncMock)
    @patch("discord_to_revolt.DiscordClient.close", new_callable=AsyncMock)
    @patch("discord_to_revolt.RevoltClient.close", new_callable=AsyncMock)
    async def test_full_migration_runs_all_stages(self, mock_revolt_close, mock_discord_close,
                                                  mock_revolt_start, mock_discord_start,
                                                  mock_migrate_members, mock_migrate_roles,
                                                  mock_migrate_messages, mock_setup):
        config = load_config("tests/test_config.yaml")
        migrator = MigrationTool(config)

        migrator.db = MagicMock()
        await migrator.run_full_migration()

        mock_discord_start.assert_awaited_once()
        mock_revolt_start.assert_awaited_once()
        mock_setup.assert_awaited_once()
        mock_migrate_roles.assert_awaited_once()
        mock_migrate_members.assert_awaited_once()
        mock_migrate_messages.assert_awaited_once()
        mock_discord_close.assert_awaited_once()
        mock_revolt_close.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()