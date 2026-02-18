import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from config import load_config
from migration_tool import MigrationTool
from state_manager import StateManager

class TestExtendedMigrationTool(unittest.IsolatedAsyncioTestCase):

    def test_store_and_get_channel_mapping(self):
        db = StateManager(":memory:")
        db.connect()
        db.store_channel_mapping("discord123", "fluxer456")
        fluxer_id = db.get_revolt_channel_id("discord123")
        self.assertEqual(fluxer_id, "fluxer456")
        db.close()

    def test_store_and_get_last_migrated_message(self):
        db = StateManager(":memory:")
        db.connect()
        db.store_message_mapping("msg1", "fmsg1", "chan1", "fchan1")
        last_id = db.get_last_migrated_message_id("chan1")
        self.assertEqual(last_id, "msg1")
        db.close()

    @patch("fluxer_client.FluxerClient.send_message", new_callable=AsyncMock, create=True)
    async def test_skip_empty_message_with_no_attachments(self, mock_send):
        config = load_config("tests/test_config.yaml")
        migrator = MigrationTool(config)

        migrator.discord_client = AsyncMock()
        migrator.fluxer_client = AsyncMock()
        migrator.db = MagicMock()

        migrator.db.get_all_channel_mappings.return_value = [("chan1", "fchan1")]
        migrator.db.get_last_migrated_message_id.return_value = None
        migrator.discord_client.get_channel_messages.return_value = [{
            "id": "msg1",
            "author": {"username": "User", "discriminator": "1234", "avatar_url": None},
            "content": "",
            "timestamp": "2023-01-01T00:00:00",
            "attachments": [],
            "reply_to_discord_id": None,
            "reactions": []
        }]
        
        # Mock get_pinned_message_ids to return empty list
        migrator.fluxer_client.get_pinned_message_ids.return_value = []
        # Mock discord get_channel_pinned_messages
        migrator.discord_client.get_channel_pinned_messages.return_value = []

        await migrator.migrate_messages()
        mock_send.assert_not_awaited()


    @patch("discord_to_fluxer.MigrationTool.setup_server_structure", new_callable=AsyncMock)
    @patch("discord_to_fluxer.MigrationTool.migrate_messages", new_callable=AsyncMock)
    @patch("discord_to_fluxer.MigrationTool.migrate_roles", new_callable=AsyncMock)
    @patch("discord_to_fluxer.MigrationTool.migrate_members", new_callable=AsyncMock)
    @patch("discord_to_fluxer.DiscordClient.start", new_callable=AsyncMock)
    @patch("discord_to_fluxer.FluxerClient.start", new_callable=AsyncMock)
    @patch("discord_to_fluxer.DiscordClient.close", new_callable=AsyncMock)
    @patch("discord_to_fluxer.FluxerClient.close", new_callable=AsyncMock)
    async def test_full_migration_runs_all_stages(self, mock_fluxer_close, mock_discord_close,
                                                  mock_fluxer_start, mock_discord_start,
                                                  mock_migrate_members, mock_migrate_roles,
                                                  mock_migrate_messages, mock_setup):
        config = load_config("tests/test_config.yaml")
        migrator = MigrationTool(config)

        migrator.db = MagicMock()
        await migrator.run_full_migration()

        mock_discord_start.assert_awaited_once()
        mock_fluxer_start.assert_awaited_once()
        mock_setup.assert_awaited_once()
        mock_migrate_roles.assert_awaited_once()
        mock_migrate_members.assert_awaited_once()
        mock_migrate_messages.assert_awaited_once()
        mock_discord_close.assert_awaited_once()
        mock_fluxer_close.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()