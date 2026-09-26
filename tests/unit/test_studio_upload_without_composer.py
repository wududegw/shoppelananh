from unittest.mock import AsyncMock, Mock
import pytest
from fastapi import HTTPException
from agent.api import studio


@pytest.mark.asyncio
async def test_upload_uses_rpc_even_when_ui_composer_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv('FLOW_VIDEO_TRANSPORT', 'ui')
    monkeypatch.setattr(studio, 'OUTPUT_DIR', tmp_path)
    probe = AsyncMock(side_effect=HTTPException(409, 'Composer unavailable'))
    monkeypatch.setattr(studio, '_check_ui_ready', probe)
    client = Mock(connected=True)
    client.upload_image = AsyncMock(return_value={'_mediaId': 'uploaded-image'})
    monkeypatch.setattr(studio, 'get_flow_client', lambda: client)
    result = await studio.studio_upload_image(studio.UploadBase64ImageRequest(
        image_base64='data:image/png;base64,aW1hZ2U=', file_name='test.png'))
    assert result['media_id'] == 'uploaded-image'
    probe.assert_not_awaited()
    client.upload_image.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_still_reports_flow_api_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(studio, 'OUTPUT_DIR', tmp_path)
    client = Mock(connected=True)
    client.upload_image = AsyncMock(return_value={'status': 403, 'error': 'Sign in required'})
    monkeypatch.setattr(studio, 'get_flow_client', lambda: client)
    with pytest.raises(HTTPException) as exc:
        await studio.studio_upload_image(studio.UploadBase64ImageRequest(image_base64='aW1hZ2U='))
    assert exc.value.status_code == 403
