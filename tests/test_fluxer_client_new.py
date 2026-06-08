import asyncio
import pytest
from unittest.mock import AsyncMock, patch, call, MagicMock

from fluxer_client import FluxerClient
from fluxer.models import Message # Import Message for mocking

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
    default_client.add_reaction = AsyncMock() # Explicitly mock add_reaction as AsyncMock
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
    default_client.add_reaction = AsyncMock() # Explicitly mock add_reaction as AsyncMock
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

@patch('fluxer_client.HTTPClient')
@patch('fluxer_client.Message.from_data')
@patch('fluxer_client.FluxerClient.get_message')
async def test_send_message_with_reply_linking(mock_get_message, mock_message_from_data, MockHTTPClient):
    """
    Verify that send_message correctly uses reply-linking when reply_to_id is provided,
    and falls back to regular send if the original message is not found.
    """
    # Arrange
    default_client_http = AsyncMock()
    MockHTTPClient.return_value = default_client_http

    client = FluxerClient(token="main_bot_token", fluxer_guild_id="123")
    await client.start()

    channel_id = "channel1"
    message_content = "This is a reply."
    reply_to_id = "original_message_id"
    attachments = [{"filename": "test.txt", "data": b"test data"}]

    # --- Test Case 1: Original message found, reply should be used ---
    print("\n--- Testing reply-linking: Original message found ---")
    mock_original_message_data = {"id": reply_to_id, "channel_id": channel_id, "content": "Original message"}
    mock_get_message.return_value = mock_original_message_data

    mock_message_instance = MagicMock(spec=Message)
    mock_message_instance.reply = AsyncMock(return_value={"id": "new_reply_id", "content": message_content})
    mock_message_from_data.return_value = mock_message_instance

    # Act
    result = await client.send_message(
        channel_id=channel_id,
        content=message_content,
        attachments=attachments,
        reply_to_id=reply_to_id
    )

    # Assert
    mock_get_message.assert_awaited_once_with(channel_id, reply_to_id)
    mock_message_from_data.assert_called_once_with(mock_original_message_data, default_client_http)
    mock_message_instance.reply.assert_awaited_once_with(
        content=message_content,
        files=[{"filename": "test.txt", "data": b"test data"}]
    )
    default_client_http.send_message.assert_not_called() # Should not call regular send_message
    assert result == {"id": "new_reply_id", "content": message_content}

    # Reset mocks for the next test case
    mock_get_message.reset_mock()
    mock_message_from_data.reset_mock()
    default_client_http.send_message.reset_mock()

    # --- Test Case 2: Original message NOT found, should fall back to regular send ---
    print("\n--- Testing reply-linking: Original message NOT found (fallback) ---")
    mock_get_message.return_value = None # Simulate message not found
    default_client_http.send_message.return_value = {"id": "fallback_message_id", "content": message_content}

    # Act
    result = await client.send_message(
        channel_id=channel_id,
        content=message_content,
        attachments=attachments,
        reply_to_id=reply_to_id
    )

    # Assert
    mock_get_message.assert_awaited_once_with(channel_id, reply_to_id)
    mock_message_from_data.assert_not_called() # Should not try to create Message object
    mock_message_instance.reply.assert_not_called() # Should not try to reply
    default_client_http.send_message.assert_awaited_once_with(
        channel_id=channel_id,
        content=message_content,
        files=[{"filename": "test.txt", "data": b"test data"}]
    )
    assert result == {"id": "fallback_message_id", "content": message_content}
