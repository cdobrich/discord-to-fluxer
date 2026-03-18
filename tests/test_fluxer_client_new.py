import asyncio
import pytest
from unittest.mock import AsyncMock, patch, call

from fluxer_client import FluxerClient

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_http_client():
    """Fixture to create a mock of the HTTPClient."""
    return AsyncMock()

@patch('fluxer_client.HTTPClient')
async def test_masquerade_sends_as_mapped_user(MockHTTPClient, mock_http_client):
    """
    Verify that when a user mapping exists, a separate client is used
    and the message content is not altered.
    """
    # Arrange
    user_mappings = {
        "test_user#1234": {
            "fluxer_username": "TestUserFluxer",
            "fluxer_auth_key": "masquerade_token"
        }
    }
    
    # Mock the default and masquerade clients
    default_client = AsyncMock()
    masquerade_client = AsyncMock()
    MockHTTPClient.side_effect = [default_client, masquerade_client]

    client = FluxerClient(token="main_bot_token", fluxer_guild_id="123", user_mappings=user_mappings)
    await client.start() # This initializes the default client

    # Act
    await client.send_message(
        channel_id="channel1",
        content="Hello from test_user",
        author_name="test_user#1234"
    )

    # Assert
    # The main bot's HTTP client should NOT have been used to send the message
    default_client.send_message.assert_not_called()

    # The masquerade client SHOULD have been used
    masquerade_client.send_message.assert_awaited_once()
    
    # Get the arguments passed to the masquerade client's send_message
    _, kwargs = masquerade_client.send_message.call_args
    
    # Verify the content was sent as-is, without the author name prepended
    assert kwargs['content'] == "Hello from test_user"
    assert kwargs['channel_id'] == "channel1"

@patch('fluxer_client.HTTPClient')
async def test_masquerade_sends_as_bot_for_unmapped_user(MockHTTPClient, mock_http_client):
    """
    Verify that for an unmapped user, the default bot client is used
    and the username is prepended to the content.
    """
    # Arrange
    user_mappings = {} # No mappings provided
    
    default_client = AsyncMock()
    MockHTTPClient.return_value = default_client

    client = FluxerClient(token="main_bot_token", fluxer_guild_id="123", user_mappings=user_mappings)
    await client.start()

    # Act
    await client.send_message(
        channel_id="channel1",
        content="Hello from other_user",
        author_name="other_user#5678"
    )

    # Assert
    # The default bot's client SHOULD have been used
    default_client.send_message.assert_awaited_once()
    
    # Get the arguments passed to the default client's send_message
    _, kwargs = default_client.send_message.call_args
    
    # Verify the content was prepended with the author's name
    assert kwargs['content'] == "other_user#5678: Hello from other_user"
    assert kwargs['channel_id'] == "channel1"

@patch('fluxer_client.HTTPClient')
async def test_apply_single_reaction(MockHTTPClient, mock_http_client):
    """Verify that a single reaction is applied correctly."""
    # Arrange
    default_client = AsyncMock()
    MockHTTPClient.return_value = default_client
    
    client = FluxerClient(token="main_bot_token", fluxer_guild_id="123")
    await client.start()

    channel_id = "channel1"
    message_id = "message1"
    emoji = "👍"

    # Act
    success = await client.apply_reaction(channel_id, message_id, emoji)

    # Assert
    assert success is True
    default_client.add_reaction.assert_awaited_once_with(
        channel_id=channel_id,
        message_id=message_id,
        emoji=emoji
    )

@patch('fluxer_client.HTTPClient')
async def test_apply_multiple_reactions(MockHTTPClient, mock_http_client):
    """Verify that multiple reactions can be applied sequentially."""
    # Arrange
    default_client = AsyncMock()
    MockHTTPClient.return_value = default_client
    
    client = FluxerClient(token="main_bot_token", fluxer_guild_id="123")
    await client.start()

    channel_id = "channel1"
    message_id = "message1"
    reactions = ["👍", "<:kek:123456789>", "😂"]

    # Act
    for reaction in reactions:
        await client.apply_reaction(channel_id, message_id, reaction)

    # Assert
    assert default_client.add_reaction.call_count == 3
    
    # Check that each call was made with the correct emoji
    expected_calls = [
        call(channel_id=channel_id, message_id=message_id, emoji="👍"),
        call(channel_id=channel_id, message_id=message_id, emoji="<:kek:123456789>"),
        call(channel_id=channel_id, message_id=message_id, emoji="😂"),
    ]
    default_client.add_reaction.assert_has_calls(expected_calls, any_order=False)
