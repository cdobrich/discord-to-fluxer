import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fluxer_client import FluxerClient
from fluxer.errors import HTTPException
from fluxer.enums import ChannelType
from fluxer.models import Channel, Guild

@pytest.fixture
def mock_fluxer_api():
    with patch('fluxer_client.FluxerClientBase') as MockClientBase, \
         patch('fluxer_client.HTTPClient') as MockHTTPClient:
        
        mock_bot = MockClientBase.return_value
        mock_http = MockHTTPClient.return_value
        mock_bot._http = mock_http
        
        # Setup async methods on mock_bot and mock_http
        mock_bot.fetch_guild = AsyncMock()
        mock_bot.close = AsyncMock()
        mock_http._ensure_session = AsyncMock()
        mock_http.create_guild_channel = AsyncMock()
        mock_http.get_guild_channels = AsyncMock()
        mock_http.edit_message = AsyncMock()
        mock_http.get_guild_emojis = AsyncMock()
        mock_http.create_guild_emoji = AsyncMock()
        mock_http.delete_message = AsyncMock()

        yield {
            'ClientBase': MockClientBase,
            'HTTPClient': MockHTTPClient,
            'bot': mock_bot,
            'http': mock_http
        }

@pytest.mark.asyncio
async def test_init(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    assert client.token == "fake_token"
    assert client.fluxer_guild_id == "fake_guild_id"
    assert client.fluxer_bot == mock_fluxer_api['bot']

@pytest.mark.asyncio
async def test_start_success(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    mock_guild = MagicMock(spec=Guild)
    mock_guild.id = "fake_guild_id"
    mock_guild.name = "Test Guild"
    mock_fluxer_api['bot'].fetch_guild.return_value = mock_guild

    await client.start()

    mock_fluxer_api['HTTPClient'].assert_called_with("fake_token")
    mock_fluxer_api['http']._ensure_session.assert_called_once()
    mock_fluxer_api['bot'].fetch_guild.assert_called_with("fake_guild_id")
    assert client.fluxer_guild == mock_guild

@pytest.mark.asyncio
async def test_start_guild_not_found_error(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    # Simulate 404
    error = HTTPException(AsyncMock(), MagicMock(), "Not Found")
    error.status = 404
    mock_fluxer_api['bot'].fetch_guild.side_effect = error

    with pytest.raises(ValueError, match="Target Fluxer guild fake_guild_id not found or accessible"):
        await client.start()

@pytest.mark.asyncio
async def test_start_unauthorized_error(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    # Simulate 401
    error = HTTPException(AsyncMock(), MagicMock(), "Unauthorized")
    error.status = 401
    mock_fluxer_api['bot'].fetch_guild.side_effect = error

    with pytest.raises(ValueError, match="Fluxer API returned 'Unauthorized'"):
        await client.start()

@pytest.mark.asyncio
async def test_start_generic_error(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    mock_fluxer_api['bot'].fetch_guild.side_effect = Exception("Boom")

    with pytest.raises(Exception, match="Boom"):
        await client.start()

@pytest.mark.asyncio
async def test_close(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    await client.close()
    mock_fluxer_api['bot'].close.assert_called_once()

@pytest.mark.asyncio
async def test_create_fluxer_channel_from_discord_text(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    client.fluxer_guild = MagicMock(spec=Guild)
    client.fluxer_guild.id = "fake_guild_id"

    discord_channel_data = {"name": "general", "type": 0} # 0 is text
    
    mock_created_channel_data = {
        "id": "new_channel_id",
        "type": ChannelType.GUILD_TEXT.value,
        "name": "general",
        "guild_id": "fake_guild_id"
    }
    mock_fluxer_api['http'].create_guild_channel.return_value = mock_created_channel_data

    # We need to patch Channel.from_data because it might try to use the real HTTP client or do validation
    with patch('fluxer.models.Channel.from_data') as mock_from_data:
        mock_channel_obj = MagicMock(spec=Channel)
        mock_channel_obj.id = "new_channel_id"
        mock_channel_obj.name = "general"
        mock_from_data.return_value = mock_channel_obj

        result = await client._create_fluxer_channel_from_discord(discord_channel_data)

        assert result == mock_channel_obj
        mock_fluxer_api['http'].create_guild_channel.assert_called_with(
            guild_id="fake_guild_id",
            name="general",
            type=ChannelType.GUILD_TEXT.value,
            topic="",
            nsfw=False
        )

@pytest.mark.asyncio
async def test_create_fluxer_channel_from_discord_voice(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    client.fluxer_guild = MagicMock(spec=Guild)
    client.fluxer_guild.id = "fake_guild_id"

    discord_channel_data = {"name": "voice", "type": 2} # 2 is voice
    
    mock_created_channel_data = {
        "id": "new_voice_id",
        "type": ChannelType.GUILD_VOICE.value,
        "name": "voice",
        "guild_id": "fake_guild_id"
    }
    mock_fluxer_api['http'].create_guild_channel.return_value = mock_created_channel_data

    with patch('fluxer.models.Channel.from_data') as mock_from_data:
        mock_channel_obj = MagicMock(spec=Channel)
        mock_channel_obj.id = "new_voice_id"
        mock_from_data.return_value = mock_channel_obj

        result = await client._create_fluxer_channel_from_discord(discord_channel_data)

        assert result == mock_channel_obj
        mock_fluxer_api['http'].create_guild_channel.assert_called_with(
            guild_id="fake_guild_id",
            name="voice",
            type=ChannelType.GUILD_VOICE.value,
            topic="",
            nsfw=False
        )

@pytest.mark.asyncio
async def test_create_fluxer_channel_unsupported_type(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    discord_channel_data = {"name": "category", "type": 4} # 4 is category, not supported by this method
    
    result = await client._create_fluxer_channel_from_discord(discord_channel_data)
    assert result is None
    mock_fluxer_api['http'].create_guild_channel.assert_not_called()

@pytest.mark.asyncio
async def test_create_fluxer_channel_no_guild(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    client.fluxer_guild = None # Not initialized
    
    discord_channel_data = {"name": "general", "type": 0}
    
    result = await client._create_fluxer_channel_from_discord(discord_channel_data)
    assert result is None
    mock_fluxer_api['http'].create_guild_channel.assert_not_called()

@pytest.mark.asyncio
async def test_get_guild_channels(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    mock_channels_data = [
        {"id": "c1", "name": "general", "type": ChannelType.GUILD_TEXT.value, "parent_id": None},
        {"id": "c2", "name": "voice", "type": ChannelType.GUILD_VOICE.value, "parent_id": "cat1"}
    ]
    mock_fluxer_api['http'].get_guild_channels.return_value = mock_channels_data

    channels = await client.get_guild_channels("fake_guild_id")
    
    assert len(channels) == 2
    assert channels[0]['id'] == "c1"
    assert channels[0]['name'] == "general"
    assert channels[0]['type'] == "text"
    assert channels[1]['id'] == "c2"
    assert channels[1]['type'] == "voice"
    assert channels[1]['parent_id'] == "cat1"

@pytest.mark.asyncio
async def test_edit_message_success(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    result = await client.edit_message("c1", "m1", "new content")
    
    assert result is True
    mock_fluxer_api['http'].edit_message.assert_called_with(
        channel_id="c1",
        message_id="m1",
        content="new content"
    )

@pytest.mark.asyncio
async def test_edit_message_failure(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    error = HTTPException(AsyncMock(), MagicMock(), "Forbidden")
    error.status = 403
    mock_fluxer_api['http'].edit_message.side_effect = error

    result = await client.edit_message("c1", "m1", "new content")
    
    assert result is False

@pytest.mark.asyncio
async def test_get_guild_emojis(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    mock_emojis_data = [
        {"id": "e1", "name": "smile"},
        {"id": "e2", "name": "frown"}
    ]
    mock_fluxer_api['http'].get_guild_emojis.return_value = mock_emojis_data

    emojis = await client.get_guild_emojis("fake_guild_id")
    
    assert len(emojis) == 2
    assert emojis[0]['id'] == "e1"
    assert emojis[0]['name'] == "smile"

@pytest.mark.asyncio
async def test_create_emoji_success(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    mock_emoji_data = {"id": "e1", "name": "smile"}
    mock_fluxer_api['http'].create_guild_emoji.return_value = mock_emoji_data

    result = await client.create_emoji("fake_guild_id", "smile", b"image_data")
    
    assert result['id'] == "e1"
    assert result['name'] == "smile"
    mock_fluxer_api['http'].create_guild_emoji.assert_called_with(
        guild_id="fake_guild_id",
        name="smile",
        image=b"image_data"
    )

@pytest.mark.asyncio
async def test_delete_message_success(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    result = await client.delete_message("c1", "m1")
    
    assert result is True
    mock_fluxer_api['http'].delete_message.assert_called_with(
        channel_id="c1",
        message_id="m1"
    )

@pytest.mark.asyncio
async def test_placeholders(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    
    assert await client.apply_reaction("c1", "m1", "smile") is False
    assert await client.pin_message("c1", "m1") is False
    assert await client.unpin_message("c1", "m1") is False
    assert await client.get_channel_pinned_messages("c1") == []
    assert await client.get_pinned_message_ids("c1") == []
