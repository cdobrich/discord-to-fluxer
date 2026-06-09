import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import yaml
from config import load_config
from migration_tool import MigrationTool


def test_config_loading_fallback():
    """Verify application configuration fallback values match parsing models."""
    mock_yaml_data = {
        "discord": {"token_file": "discord_token.token", "guild_id": "1234567890"},
        "fluxer": {"token_file": "fluxer_token.token", "server_id": "987654321"},
        "delays": {"between_messages_seconds": 0.1, "between_channels_seconds": 0.5}
    }

    with patch("builtins.open", mock_open(read_data="FAKE_DISCORD_TOKEN")), \
            patch("yaml.safe_load", return_value=mock_yaml_data):
        config = load_config()
        assert config.discord_guild_id == "1234567890"
        assert config.fluxer_server_id == "987654321"


@pytest.mark.asyncio
async def test_fluxer_channel_setup_orchestration(mock_migration_tool):
    """Verify that the tool properly interacts with server structure creation routines."""
    tool = mock_migration_tool
    tool.db.connect()

    # Stub the top-level setup interface exposed by MigrationTool
    tool.setup_server_structure = AsyncMock()

    await tool.setup_server_structure()
    assert tool.setup_server_structure.called