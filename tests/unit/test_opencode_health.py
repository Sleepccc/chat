"""HTTP boundary checks supplied by Codex; no real network or model calls."""
import asyncio

import httpx
import pytest

from pocket_guardian.adapters.opencode import OpenCodeAdapter


def read_health(handler):
    async def scenario():
        async with httpx.AsyncClient(
            base_url='http://opencode.test',
            transport=httpx.MockTransport(handler),
        ) as client:
            adapter = OpenCodeAdapter(client)
            return await adapter.check_health()
    return asyncio.run(scenario())


def test_reads_health_from_the_documented_get_endpoint():
    def server(request):
        assert request.method == 'GET'
        assert request.url.path == '/global/health'
        return httpx.Response(200, json={'healthy': True, 'version': '1.18.21'})
    assert read_health(server) == {'healthy': True, 'version': '1.18.21'}


def test_unhealthy_server_is_not_reported_as_healthy():
    result = read_health(lambda request: httpx.Response(
        200, json={'healthy': False, 'version': '1.18.21'}))
    assert result['healthy'] is False


def test_authentication_failure_is_not_parsed_as_success():
    with pytest.raises(httpx.HTTPStatusError) as caught:
        read_health(lambda request: httpx.Response(401, json={'error': 'unauthorized'}))
    assert caught.value.response.status_code == 401


def test_transport_failure_preserves_the_original_exception_type():
    def disconnected(request):
        raise httpx.ConnectError('test-only connection failure', request=request)
    with pytest.raises(httpx.ConnectError):
        read_health(disconnected)


@pytest.mark.parametrize('payload', [
    [],
    {'version': '1.18.21'},
    {'healthy': 'yes', 'version': '1.18.21'},
    {'healthy': True, 'version': ''},
    {'healthy': True, 'version': '   '},
])
def test_rejects_responses_that_do_not_match_the_health_contract(payload):
    with pytest.raises(ValueError):
        read_health(lambda request: httpx.Response(200, json=payload))


def test_rejects_non_json_response_body():
    with pytest.raises(ValueError):
        read_health(lambda request: httpx.Response(200, text='not JSON'))
