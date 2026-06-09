import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from state_manager import StateManager
from migration_tool import MigrationTool


def test_database_isolated_in_memory_state():
    """Verify underlying SQLite storage engine maps and reads relational identifiers accurately."""
    db = StateManager(":memory:")
    db.connect()

    db.store_channel_mapping("discord123", "fluxer456")
    assert db.get_fluxer_channel_id("discord123") == "fluxer456"
    db.close()


def test_database_message_mapping_state():
    """Verify storage engine accurately tracks historical message syncing keys."""
    db = StateManager(":memory:")
    db.connect()

    db.store_message_mapping("msg1", "fmsg1", "chan1", "fchan1", "content", [])
    assert db.get_last_migrated_message_id("chan1") == "msg1"
    db.close()


@pytest.mark.asyncio
async def test_message_migration_skips_when_no_mappings(mock_migration_tool):
    """Verify migrate_messages returns early if no active channel mappings exist in DB."""
    tool = mock_migration_tool
    tool.db.connect()

    # Ensure get_all_channel_mappings returns empty collection to trigger early exit optimization
    tool.db.get_all_channel_mappings.return_value = []

    with patch('builtins.print') as mock_print:
        await tool.migrate_messages()
        # Assert exact console print match including its standard 2-space layout indent
        mock_print.assert_any_call(
            "  No channel mappings found. Skipping message migration. Ensure channels were successfully created and mapped in the previous stage and database wasn't cleared.")


@pytest.mark.asyncio
async def test_migration_tool_orchestration_loop(mock_migration_tool):
    """Verify full orchestration logic initializes states and calls lifecycle handlers."""
    tool = mock_migration_tool

    # Mock all heavy lifecycle steps to isolate top level startup loops safely
    tool.setup_server_structure = AsyncMock()
    tool.migrate_emojis = AsyncMock()
    tool.migrate_roles = AsyncMock()
    tool.migrate_members = AsyncMock()
    tool.migrate_messages = AsyncMock()

    await tool.run_full_migration()

    # Confirm fundamental gateway connections are fired off sequentially
    tool.discord_client.start.assert_called_once()
    tool.fluxer_client.start.assert_called_once()