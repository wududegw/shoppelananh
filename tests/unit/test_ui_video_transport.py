from unittest.mock import AsyncMock
import pytest
from agent.services.flow_client import FlowClient


@pytest.mark.asyncio
async def test_ui_video_returns_completed_clip_without_rpc(monkeypatch):
    monkeypatch.setenv('FLOW_VIDEO_TRANSPORT', 'ui')
    client = FlowClient()
    mid = '8f7007e5-5b04-4314-9413-3fdc8ba7bf36'
    client._send = AsyncMock(return_value={'data': {
        'mediaId': mid, 'url': 'https://flow-content.google/video/' + mid}})
    result = await client.generate_video('image', 'prompt', 'project', 'scene')
    assert result['data']['operations'][0]['status'] == 'MEDIA_GENERATION_STATUS_SUCCESSFUL'
    assert client._send.call_args.args[0] == 'ui_generate_video'


@pytest.mark.asyncio
async def test_ui_timeout_is_terminal_and_not_retried(monkeypatch):
    monkeypatch.setenv('FLOW_VIDEO_TRANSPORT', 'ui')
    client = FlowClient()
    client._send = AsyncMock(return_value={'error': 'Timeout'})
    result = await client.generate_video('image', 'prompt', 'project', 'scene')
    assert result['error'].startswith('UI_VIDEO:')
    assert client._send.await_count == 1


@pytest.mark.asyncio
async def test_ui_rejects_non_flow_output(monkeypatch):
    monkeypatch.setenv('FLOW_VIDEO_TRANSPORT', 'ui')
    client = FlowClient()
    client._send = AsyncMock(return_value={'data': {
        'mediaId': '8f7007e5-5b04-4314-9413-3fdc8ba7bf36',
        'url': 'https://example.com/video'}})
    result = await client.generate_video('image', 'prompt', 'project', 'scene')
    assert result['error'].startswith('UI_VIDEO:')


@pytest.mark.asyncio
async def test_canvas_result_resolves_media_without_generating_again(monkeypatch):
    monkeypatch.setenv('FLOW_VIDEO_TRANSPORT', 'ui')
    monkeypatch.setattr('agent.services.flow_client.asyncio.sleep', AsyncMock())
    client = FlowClient()
    mid = '8f7007e5-5b04-4314-9413-3fdc8ba7bf36'
    client._send = AsyncMock(side_effect=[{'data': {'refreshing': True}}, {'data': {'mediaId': mid}}])
    client.get_media = AsyncMock(return_value={'data': {'video': {'fifeUrl': 'https://flow-content.google/video/' + mid}}})
    result = await client.generate_video('image', 'prompt', 'project', 'scene')
    client.get_media.assert_awaited_once_with(mid)
    assert client._send.await_count == 2
    assert result['data']['operations'][0]['status'] == 'MEDIA_GENERATION_STATUS_SUCCESSFUL'


@pytest.mark.asyncio
async def test_failed_url_lookup_never_resubmits_paid_generation(monkeypatch):
    monkeypatch.setenv('FLOW_VIDEO_TRANSPORT', 'ui')
    monkeypatch.setattr('agent.services.flow_client.asyncio.sleep', AsyncMock())
    client = FlowClient()
    mid = '8f7007e5-5b04-4314-9413-3fdc8ba7bf36'
    client._send = AsyncMock(side_effect=[{'data': {'refreshing': True}}, {'data': {'mediaId': mid}}])
    client.get_media = AsyncMock(return_value={'error': 'read failed'})
    result = await client.generate_video('image', 'prompt', 'project', 'scene')
    assert result['error'].startswith('UI_VIDEO:')
    assert mid in result['error']
    assert client._send.await_count == 2


def test_upload_label_is_persistent_and_project_scoped(monkeypatch, tmp_path):
    from agent.services import ui_assets
    monkeypatch.setattr(ui_assets.config, 'BASE_DIR', tmp_path)
    mid = '8f7007e5-5b04-4314-9413-3fdc8ba7bf36'
    ui_assets.remember(mid, 'project-a', 'flowkit-unique.webp')
    assert ui_assets.lookup(mid, 'project-a') == 'flowkit-unique.webp'
    assert ui_assets.lookup(mid, 'project-b') == ''
    assert ui_assets.lookup('../outside', 'project-a') == ''


@pytest.mark.asyncio
async def test_studio_attaches_all_references_in_order_without_duplicate(monkeypatch):
    monkeypatch.setenv('FLOW_VIDEO_TRANSPORT', 'ui')
    monkeypatch.setattr('agent.services.flow_client.asyncio.sleep', AsyncMock())
    monkeypatch.setattr('agent.services.ui_assets.lookup', lambda mid, project: mid + '.png')
    client = FlowClient()
    mid = '8f7007e5-5b04-4314-9413-3fdc8ba7bf36'
    client._send = AsyncMock(side_effect=[{'data': {'refreshing': True}}, {'data': {
        'mediaId': mid, 'url': 'https://flow-content.google/video/' + mid}}])
    await client.generate_video('outfit', 'prompt', 'project', 'scene', reference_media_ids=['outfit', 'model', 'location'])
    sent = client._send.call_args.args[1]
    assert sent['images'] == [{'imageId': name, 'imageName': name + '.png'} for name in ['outfit', 'model', 'location']]
