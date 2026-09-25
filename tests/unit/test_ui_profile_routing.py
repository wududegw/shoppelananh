import json
from unittest.mock import AsyncMock

import pytest
from agent.services.flow_client import FlowClient


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['probe', 'refresh', 'generate'])
async def test_missing_tab_routes_to_second_profile(mode):
    client = FlowClient()
    first, second = AsyncMock(), AsyncMock()
    client.set_extension(first)
    client.set_extension(second)

    async def reject(payload):
        await client.handle_message({
            'id': json.loads(payload)['id'], 'status': 409,
            'code': 'UI_PROJECT_TAB_UNAVAILABLE', 'error': 'Missing tab',
        }, first)

    async def respond(payload):
        await client.handle_message({
            'id': json.loads(payload)['id'], 'data': {'ready': True},
        }, second)

    first.send.side_effect = reject
    second.send.side_effect = respond
    result = await client._send('ui_generate_video', {'mode': mode}, timeout=1)
    assert result['data']['ready']
    first.send.assert_awaited_once()
    second.send.assert_awaited_once()
    assert client._extension_ws is second
    assert not client._pending


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [
    {'error': 'Extension disconnected'},
    {'error': 'Timeout after submit'},
    {'error': 'UI_VIDEO: Mở đúng project Flow trong Chrome rồi thử lại'},
])
async def test_ambiguous_ui_errors_never_retry_generation(failure):
    client = FlowClient()
    first, second = AsyncMock(), AsyncMock()
    client.set_extension(first)
    client.set_extension(second)

    async def reject(payload):
        await client.handle_message({'id': json.loads(payload)['id'], **failure}, first)

    first.send.side_effect = reject
    result = await client._send('ui_generate_video', {}, timeout=1)
    assert result['error'] == failure['error']
    second.send.assert_not_awaited()
