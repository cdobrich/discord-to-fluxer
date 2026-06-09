import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import yaml
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from config import AppConfig
from migration_tool import MigrationTool
from state_manager import StateManager
from fluxer_client import FluxerClient
from discord_client import DiscordClient
import discord


@pytest.fixture
def mock_config_content():
    return {
        'discord': {
            'token_file': 'mock_discord_token.token',
            'guild_id': '123456789012345678'
        },
        'fluxer': {
            'token_file': 'mock_fluxer_token.token',
            'server_id': 'mockserverid'
        },
        'delays': {
            'between_messages_seconds': 0.01,
            'between_channels_seconds': 0.05
        },
        'user_mappings': {}
    }


@pytest.fixture
def mock_config_file(tmp_path, mock_config_content):
    file = tmp_path / "config.yaml"
    with open(file, 'w') as f:
        yaml.dump(mock_config_content, f)
    return str(file)


@pytest.fixture
def mock_app_config(mock_config_content):
    with patch('config.read_token_from_file', return_value="fake_token"):
        return AppConfig(mock_config_content)


@pytest.fixture
def mock_discord_client():
    mock_client = MagicMock(spec=DiscordClient)
    mock_client.start = AsyncMock()
    mock_client.close = AsyncMock()
    return mock_client


@pytest.fixture
def mock_fluxer_client():
    mock_client = MagicMock(spec=FluxerClient)
    mock_client.start = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.delete_message = AsyncMock(return_value=True)
    mock_client.send_message = AsyncMock()
    mock_client._create_fluxer_channel_from_discord = AsyncMock()
    return mock_client


@pytest.fixture
def mock_state_manager():
    mock_manager = MagicMock(spec=StateManager)
    mock_manager.connect = MagicMock()
    mock_manager.close = MagicMock()
    mock_manager.create_tables = MagicMock()
    mock_manager.store_channel_mapping = MagicMock()
    mock_manager.get_fluxer_channel_id = MagicMock(return_value=None)
    mock_manager.store_message_mapping = MagicMock()
    mock_manager.get_last_migrated_message_id = MagicMock(return_value=None)
    mock_manager.get_migration_status = MagicMock(return_value=None)
    mock_manager.get_all_channel_mappings = MagicMock(return_value=[])
    mock_manager.get_all_message_mappings_for_channel = MagicMock(return_value=[])
    return mock_manager


@pytest.fixture
def mock_migration_tool(mock_app_config, mock_discord_client, mock_fluxer_client, mock_state_manager):
    with patch('discord_client.DiscordClient', return_value=mock_discord_client), \
            patch('fluxer_client.FluxerClient', return_value=mock_fluxer_client), \
            patch('state_manager.StateManager', return_value=mock_state_manager):
        tool = MigrationTool(mock_app_config)
        tool.discord_client = mock_discord_client
        tool.fluxer_client = mock_fluxer_client
        tool.db = mock_state_manager
        return tool