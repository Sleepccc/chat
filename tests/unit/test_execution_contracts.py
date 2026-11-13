"""M02 contract checks supplied by Codex; core models belong to the learner."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from pocket_guardian.contracts.execution import SuccessResult


def successful_payload():
    return {
        'status': 'succeeded',
        'adapter': 'opencode',
        'provider': 'deepseek',
        'requested_model': 'deepseek-chat',
        'text': 'Generators produce values lazily.',
        'finished_at': datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc),
    }


def test_success_preserves_answer_and_source_without_inventing_reported_model():
    result = SuccessResult.model_validate(successful_payload())
    assert result.status == 'succeeded'
    assert result.adapter == 'opencode'
    assert result.provider == 'deepseek'
    assert result.requested_model == 'deepseek-chat'
    assert result.reported_model is None
    assert result.text == 'Generators produce values lazily.'
    assert result.finished_at.utcoffset().total_seconds() == 0


@pytest.mark.parametrize('answer', ['', '   ', None])
def test_success_requires_a_real_answer(answer):
    payload = successful_payload()
    payload['text'] = answer
    with pytest.raises(ValidationError):
        SuccessResult.model_validate(payload)


def test_success_cannot_also_carry_failure_information():
    payload = successful_payload()
    payload['error_code'] = 'authentication_failed'
    with pytest.raises(ValidationError):
        SuccessResult.model_validate(payload)


def test_success_cannot_be_relabelled_as_failed():
    payload = successful_payload()
    payload['status'] = 'failed'
    with pytest.raises(ValidationError):
        SuccessResult.model_validate(payload)


def test_finished_at_requires_an_explicit_timezone():
    payload = successful_payload()
    payload['finished_at'] = datetime(2026, 11, 10, 12, 0)
    with pytest.raises(ValidationError):
        SuccessResult.model_validate(payload)
