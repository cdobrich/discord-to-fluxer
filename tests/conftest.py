import sys
import os

# Add the parent directory (project root) to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import yaml
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Import classes from your script
from config import AppConfig
from migration_tool import MigrationTool
from state_manager import StateManager
from revolt_client import RevoltClient
from discord_client import DiscordClient
import discord # For discord.ChannelType
from pyvolt.enums import ChannelType # For pyvolt.enums.ChannelType

# Fixture for a mock configuration file content
@pytest.fixture
def mock_config_content():
    return {
        'discord': {
            'token_file': 'mock_discord_token.token',
            'guild_id': '123456789012345678'
        },
        'revolt': {
            'token_file': 'mock_revolt_token.token',
            'server_id': 'mockserverid'
        },
        'delays': {
            'between_messages_seconds': 0.01, # Reduce for faster tests
            'between_channels_seconds': 0.05
        }
    }

# Fixture for a mock config.yaml file path
@pytest.fixture
def mock_config_file(tmp_path, mock_config_content):
    file = tmp_path / "config.yaml"
    with open(file, 'w') as f:
        yaml.dump(mock_config_content, f)
    return str(file)

# Fixture for mock token files
@pytest.fixture
def mock_token_files(tmp_path):
    discord_token_file = tmp_path / "mock_discord_token.token"
    revolt_token_file = tmp_path / "mock_revolt_token.token"
    discord_token_file.write_text("fake_discord_token")
    revolt_token_file.write_text("fake_revolt_token")
    return {
        'discord': str(discord_token_file),
        'revolt': str(revolt_token_file)
    }

# Fixture for an AppConfig instance with mocked token reading
@pytest.fixture
def mock_app_config(mock_config_content, mock_token_files):
    with patch('discord_to_revolt.read_token_from_file', side_effect=lambda f: {
        mock_token_files['discord']: "fake_discord_token",
        mock_token_files['revolt']: "fake_revolt_token"
    }.get(f, None)):
        return AppConfig(mock_config_content)

# Fixture for a mock DiscordClient
@pytest.fixture
def mock_discord_client():
    mock_client = AsyncMock(spec=DiscordClient)
    # Mock discord.Client attributes and methods
    mock_client.client = AsyncMock(spec=discord.Client)
    mock_client.client.user = MagicMock()
    mock_client.client.user.name = "MockDiscordBot"
    mock_client.client.user.id = 123
    mock_client.client.get_guild.return_value = MagicMock(id=123456789012345678)
    mock_client.client.fetch_guild.return_value = MagicMock(id=123456789012345678)
    mock_client.client.get_channel.return_value = MagicMock(id=12345)
    mock_client.client.fetch_channel.return_value = MagicMock(id=12345)
    mock_client._ready_event = asyncio.Event()
    mock_client._guilds_loaded_event = asyncio.Event()
    
    # Simulate on_ready being called shortly after start
    async def mock_start_side_effect():
        await asyncio.sleep(0.01) # Simulate some async work
        mock_client._ready_event.set()
    mock_client.start.side_effect = mock_start_side_effect

    return mock_client

# Fixture for a mock RevoltClient
@pytest.fixture
def mock_revolt_client():
    mock_client = AsyncMock(spec=RevoltClient)
    mock_client.token = "fake_revolt_token"
    mock_client.revolt_server_id = "mockserverid"
    
    mock_server = MagicMock()
    mock_server.name = "MockRevoltServer"
    mock_server.id = "mockserverid"
    mock_client.revolt_server = mock_server

    # Mock pyvolt client and methods
    mock_client.revolt_bot = MagicMock(spec=pyvolt.Client)
    mock_client.revolt_bot.fetch_server.return_value = mock_server
    
    # Mock create_channel to return a mock channel object
    mock_client._create_revolt_channel_from_discord.return_value = {
        "id": "new_revolt_channel_id", "name": "new-channel", "type": "text"
    }
    
    # Mock send_message to return a mock message ID
    mock_client.send_message.return_value = {"id": "revolt_message_id_123"}
    
    # Mock upload_attachment
    mock_client.upload_attachment.return_value = {"id": "revolt_attachment_id_123", "filename": "test.txt"}

    return mock_client

# Fixture for a mock StateManager
@pytest.fixture
def mock_state_manager(tmp_path):
    mock_db_file = tmp_path / "mock_migration_state.db"
    mock_manager = MagicMock(spec=StateManager)
    mock_manager.db_file = str(mock_db_file)
    # Mock the internal connection and cursor if needed, or just mock the public methods
    mock_manager.connect.return_value = None
    mock_manager.close.return_value = None
    mock_manager.create_tables.return_value = None
    mock_manager.store_channel_mapping.return_value = None
    mock_manager.get_revolt_channel_id.return_value = None
    mock_manager.store_message_mapping.return_value = None
    mock_manager.get_last_migrated_message_id.return_value = None
    mock_manager.set_migration_status.return_value = None
    mock_manager.get_migration_status.return_value = None
    mock_manager.get_all_channel_mappings.return_value = []
    mock_manager.get_all_message_mappings_for_channel.return_value = []
    mock_manager.clear_all_data.return_value = True # Assume successful clear if called

    return mock_manager

# Fixture for MigrationTool with mocked clients and state manager
@pytest.fixture
def mock_migration_tool(mock_app_config, mock_discord_client, mock_revolt_client, mock_state_manager):
    # Patch the actual classes with our mock instances
    with patch('discord_to_revolt.DiscordClient', return_value=mock_discord_client), \
         patch('discord_to_revolt.RevoltClient', return_value=mock_revolt_client), \
         patch('discord_to_revolt.StateManager', return_value=mock_state_manager):
        
        # Instantiate MigrationTool, it will now use the patched clients/manager
        tool = MigrationTool(mock_app_config)
        # Ensure the internal instances are our mocks
        tool.discord_client = mock_discord_client
        tool.revolt_client = mock_revolt_client
        tool.db = mock_state_manager
        return tool