import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fluxer_client import FluxerClient
from fluxer.errors import HTTPException
from fluxer.enums import ChannelType


@pytest.fixture
def mock_fluxer_api():
    with patch('fluxer_client.FluxerClientBase') as MockClientBase, \
            patch('fluxer_client.HTTPClient') as MockHTTPClient:
        mock_bot = MockClientBase.return_value
        mock_http = MockHTTPClient.return_value
        mock_bot._http = mock_http

        mock_bot.fetch_guild = AsyncMock()
        mock_bot.close = AsyncMock()
        mock_http._ensure_session = AsyncMock()
        mock_http.create_guild_channel = AsyncMock()
        mock_http.get_guild_channels = AsyncMock()
        mock_http.edit_message = AsyncMock()
        mock_http.get_guild_emojis = AsyncMock()
        mock_http.create_guild_emoji = AsyncMock()
        mock_http.delete_message = AsyncMock()
        mock_http.send_message = AsyncMock()

        yield {
            'ClientBase': MockClientBase,
            'HTTPClient': MockHTTPClient,
            'bot': mock_bot,
            'http': mock_http
        }


@pytest.mark.asyncio
async def test_init(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id", user_mappings={})
    assert client.token == "fake_token"
    assert client.fluxer_guild_id == "fake_guild_id"


@pytest.mark.asyncio
async def test_send_message_with_attachments(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")

    mock_msg_obj = MagicMock()
    mock_msg_obj.id = "m1"
    mock_msg_obj.content = "hello"
    mock_msg_obj.get.return_value = "m1"
    mock_fluxer_api['http'].send_message.return_value = mock_msg_obj

    attachments = [
        {"filename": "test.txt", "data": b"test data"},
        {"filename": "image.png", "data": b"image data"}
    ]

    result = await client.send_message("c1", "hello", attachments=attachments)

    assert result.id == "m1"
    assert mock_fluxer_api['http'].send_message.called


@pytest.mark.asyncio
async def test_send_message_no_attachments(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")

    mock_msg_obj = MagicMock()
    mock_msg_obj.id = "m1"
    mock_msg_obj.content = "hello"
    mock_msg_obj.get.return_value = "m1"
    mock_fluxer_api['http'].send_message.return_value = mock_msg_obj

    result = await client.send_message("c1", "hello")

    assert result.id == "m1"
    assert mock_fluxer_api['http'].send_message.called


@pytest.mark.asyncio
async def test_edit_message_success(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")

    mock_msg_obj = MagicMock()
    mock_msg_obj.id = "m1"
    mock_msg_obj.content = "updated content"
    mock_fluxer_api['http'].edit_message.return_value = mock_msg_obj

    result = await client.edit_message("c1", "m1", "updated content")

    assert result is True
    assert mock_fluxer_api['http'].edit_message.called


@pytest.mark.asyncio
async def test_delete_message_success(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")
    mock_fluxer_api['http'].delete_message.return_value = True

    result = await client.delete_message("c1", "m1")

    assert result is True
    assert mock_fluxer_api['http'].delete_message.called


@pytest.mark.asyncio
async def test_delete_message_http_exception(mock_fluxer_api):
    client = FluxerClient("fake_token", "fake_guild_id")

    # Construct an explicitly structured mock exception instance that passes type evaluation
    # while providing the exact fields checked during downstream exception extraction log passes
    exc = MagicMock()
    exc.__class__ = HTTPException
    exc.status = 500
    exc.message = "Internal Server Error"

    mock_fluxer_api['http'].delete_message.side_effect = exc

    result = await client.delete_message("c1", "m1")
    assert result is False