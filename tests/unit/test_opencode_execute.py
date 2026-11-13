"""Normal execution and final-evidence checks; fake HTTP only, supplied by Codex."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx
import pytest

from pocket_guardian.adapters.opencode import OpenCodeAdapter
from pocket_guardian.contracts.execution import FailureResult, SuccessResult, UnknownResult

SESSION_ID = 'ses_m02_test'
MODEL = 'deepseek-chat'
PROMPT = 'Explain generators.'
DENY_TOOLS = [{'permission': '*', 'pattern': '*', 'action': 'deny'}]


def session_response():
    return {
        'id': SESSION_ID, 'slug': 'm02-test', 'projectID': 'global',
        'directory': 'C:/discardable-test', 'title': 'M02 test',
        'version': '1.18.21', 'time': {'created': 1760000000000, 'updated': 1760000001000},
    }


def part(part_id, kind, text, **extra):
    return {'id': part_id, 'sessionID': SESSION_ID, 'messageID': 'msg_assistant_test',
            'type': kind, 'text': text, **extra}


def completed_response():
    return {
        'info': {
            'id': 'msg_assistant_test', 'sessionID': SESSION_ID, 'role': 'assistant',
            'parentID': 'msg_user_test', 'providerID': 'deepseek', 'modelID': MODEL,
            'mode': 'build', 'agent': 'build',
            'path': {'cwd': 'C:/discardable-test', 'root': 'C:/discardable-test'},
            'cost': 0, 'tokens': {'input': 1, 'output': 1, 'reasoning': 0, 'cache': {'read': 0, 'write': 0}},
            'time': {'created': 1760000000000, 'completed': 1760000001000}, 'finish': 'stop',
        },
        'parts': [part('prt_reason', 'reasoning', 'Not the final answer.'),
                  part('prt_ignored', 'text', 'Ignore this.', ignored=True),
                  part('prt_one', 'text', 'Generators produce values lazily.'),
                  part('prt_two', 'text', 'Iteration requests the next value.')],
    }


def execute_fake(reply=None, created=None, create_status=200, message_times_out=False, connect_fails=False, message_status=200, workspace=None):
    reply = completed_response() if reply is None else deepcopy(reply)
    created = session_response() if created is None else deepcopy(created)
    requests = []

    def server(request):
        requests.append(request)
        assert request.method == 'POST'
        if connect_fails:
            raise httpx.ConnectError('test-only connection failure', request=request)
        if request.url.path == '/session':
            return httpx.Response(create_status, json=created)
        assert request.url.path == f'/session/{SESSION_ID}/message'
        if message_times_out:
            raise httpx.ReadTimeout('test-only timeout', request=request)
        return httpx.Response(message_status, json=reply)

    async def scenario():
        async with httpx.AsyncClient(base_url='http://opencode.test',
                                     transport=httpx.MockTransport(server)) as client:
            return await OpenCodeAdapter(client, workspace=workspace).execute(PROMPT, provider='deepseek', model=MODEL)

    return asyncio.run(scenario()), requests


def test_submits_two_requests_and_returns_a_unified_success():
    started = datetime.now(timezone.utc)
    result, requests = execute_fake()
    assert isinstance(result, SuccessResult)
    assert len(requests) == 2
    assert json.loads(requests[0].content)['permission'] == DENY_TOOLS
    body = json.loads(requests[1].content)
    assert body['model'] == {'providerID': 'deepseek', 'modelID': MODEL}
    assert body['parts'] == [{'type': 'text', 'text': PROMPT}]
    assert result.adapter == 'opencode' and result.provider == 'deepseek'
    assert result.requested_model == MODEL and result.reported_model == MODEL
    assert result.text == 'Generators produce values lazily.\nIteration requests the next value.'
    assert started <= result.finished_at <= datetime.now(timezone.utc)


def test_preserves_requested_model_separately_from_opencode_reported_model():
    reply = completed_response()
    reply['info']['modelID'] = 'reported-model-test-only'
    result, _ = execute_fake(reply)
    assert result.requested_model == MODEL
    assert result.reported_model == 'reported-model-test-only'


@pytest.mark.parametrize('created', [{}, {'id': ''}, {'id': 12}])
def test_rejects_missing_or_invalid_session_identity(created):
    result, requests = execute_fake(created=created)
    assert isinstance(result, UnknownResult)
    assert result.error_code == 'opencode_invalid_response'
    assert len(requests) == 1


@pytest.mark.parametrize('case', ['unfinished', 'wrong-role', 'missing-finish',
                                 'tool-calls', 'no-answer', 'invalid-parts'])
def test_http_200_without_valid_final_evidence_is_not_success(case):
    reply = completed_response()
    if case == 'unfinished':
        reply['info']['time'].pop('completed')
    elif case == 'wrong-role':
        reply['info']['role'] = 'user'
    elif case == 'missing-finish':
        reply['info'].pop('finish')
    elif case == 'tool-calls':
        reply['info']['finish'] = 'tool-calls'
    elif case == 'no-answer':
        reply['parts'] = [part('prt_only_reasoning', 'reasoning', 'Not a final answer.')]
    elif case == 'invalid-parts':
        reply['parts'] = 'invalid'
    result, requests = execute_fake(reply)
    assert isinstance(result, UnknownResult)
    assert result.error_code == 'opencode_invalid_response'
    assert len(requests) == 2


def test_provider_failure_takes_priority_over_missing_completion_fields():
    reply = completed_response()
    reply.pop('parts')
    reply['info'].pop('time')
    reply['info']['error'] = {
        'name': 'ProviderAuthError',
        'data': {'providerID': 'deepseek', 'message': 'test-only private diagnostics'},
    }

    result, requests = execute_fake(reply)
    assert isinstance(result, FailureResult)
    assert result.error_code == 'opencode_reported_error'
    assert result.reported_model == MODEL
    assert '认证失败' in result.message
    assert 'private diagnostics' not in result.message
    assert len(requests) == 2


def test_session_auth_rejection_returns_failure():
    result, requests = execute_fake(create_status=401)
    assert isinstance(result, FailureResult)
    assert result.error_code == 'opencode_authentication_failed'
    assert result.adapter == 'opencode'
    assert result.provider == 'deepseek'
    assert result.requested_model == MODEL
    assert len(requests) == 1


def test_message_read_timeout_returns_unknown_without_resubmitting():
    result, requests = execute_fake(message_times_out=True)
    assert isinstance(result, UnknownResult)
    assert result.error_code == 'opencode_read_timeout'
    assert result.adapter == 'opencode'
    assert result.provider == 'deepseek'
    assert result.requested_model == MODEL
    assert len(requests) == 2


def test_both_posts_share_one_deadline():
    requests = []

    async def server(request):
        requests.append(request.url.path)
        await asyncio.sleep(0.2)
        body = session_response() if request.url.path == '/session' else completed_response()
        return httpx.Response(200, json=body)

    async def scenario():
        async with httpx.AsyncClient(base_url='http://opencode.test',
                                     transport=httpx.MockTransport(server)) as client:
            adapter = OpenCodeAdapter(client, total_timeout_seconds=0.3)
            return await asyncio.wait_for(adapter.execute(PROMPT, provider='deepseek', model=MODEL), 2)

    result = asyncio.run(scenario())
    assert isinstance(result, UnknownResult)
    assert result.error_code == 'opencode_deadline_exceeded'
    assert requests == ['/session', f'/session/{SESSION_ID}/message']


def test_oversized_reply_stops_reading():
    requests = []
    read_chunks = []
    stream_closed = []

    class OversizedBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            for chunk in (b'x' * 600, b'y' * 600, b'z' * 600):
                read_chunks.append(chunk)
                yield chunk

        async def aclose(self):
            stream_closed.append(True)

    def server(request):
        requests.append(request.url.path)
        if request.url.path == '/session':
            return httpx.Response(200, json=session_response())
        return httpx.Response(200, stream=OversizedBody())

    async def scenario():
        async with httpx.AsyncClient(base_url='http://opencode.test',
                                     transport=httpx.MockTransport(server)) as client:
            adapter = OpenCodeAdapter(client, max_response_bytes=1024)
            return await adapter.execute(PROMPT, provider='deepseek', model=MODEL)

    result = asyncio.run(scenario())
    assert isinstance(result, UnknownResult)
    assert result.error_code == 'opencode_response_too_large'
    assert requests == ['/session', f'/session/{SESSION_ID}/message']
    assert len(read_chunks) == 2
    assert stream_closed == [True]


def test_connect_error_returns_failure():
    result, requests = execute_fake(connect_fails=True)
    assert isinstance(result, FailureResult)
    assert result.error_code == 'opencode_connection_failed'
    assert len(requests) == 1


def test_forbidden_returns_failure():
    result, requests = execute_fake(create_status=403)
    assert isinstance(result, FailureResult)
    assert result.error_code == 'opencode_http_403'
    assert len(requests) == 1


def test_message_server_error_returns_unknown_without_retry():
    result, requests = execute_fake(message_status=503)
    assert isinstance(result, UnknownResult)
    assert result.error_code == 'opencode_http_503'
    assert len(requests) == 2

def test_server_selected_workspace_is_sent_on_both_requests(tmp_path):
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    result, requests = execute_fake(workspace=workspace)

    assert isinstance(result, SuccessResult)
    assert [request.url.params["directory"] for request in requests] == [str(workspace.resolve())] * 2
    assert json.loads(requests[1].content)["parts"] == [{"type": "text", "text": PROMPT}]


def test_relative_workspace_is_rejected():
    async def scenario():
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError, match="absolute path"):
                OpenCodeAdapter(client, workspace=Path("relative"))

    asyncio.run(scenario())
