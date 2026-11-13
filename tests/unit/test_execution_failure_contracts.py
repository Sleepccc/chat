"""M02 failure/uncertainty checks supplied by Codex."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from pocket_guardian.contracts.execution import FailureResult, UnknownResult


CASES = [
    (FailureResult, 'failed', 'finished_at'),
    (UnknownResult, 'unknown', 'observed_at'),
]


def payload_for(status, time_field):
    return {
        'status': status,
        'adapter': 'opencode',
        'provider': 'deepseek',
        'requested_model': 'deepseek-chat',
        'error_code': 'authentication_failed' if status == 'failed' else 'timeout',
        'message': 'Model credentials rejected.' if status == 'failed' else 'Completion not confirmed.',
        time_field: datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
    }


@pytest.mark.parametrize('model,status,time_field', CASES)
def test_error_outcome_preserves_failure_evidence(model, status, time_field):
    payload = payload_for(status, time_field)
    result = model.model_validate(payload)
    assert result.status == status
    assert result.reported_model is None
    assert result.error_code == payload['error_code']
    assert result.message == payload['message']
    assert getattr(result, time_field).tzinfo is not None


@pytest.mark.parametrize('model,status,time_field', CASES)
def test_error_outcome_requires_a_useful_explanation(model, status, time_field):
    payload = payload_for(status, time_field)
    payload['message'] = '   '
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize('model,status,time_field', CASES)
def test_error_outcome_does_not_mislabel_text_as_a_final_answer(model, status, time_field):
    payload = payload_for(status, time_field)
    payload['text'] = 'This is not a confirmed final answer.'
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_uncertainty_does_not_claim_an_external_completion_time():
    payload = payload_for('unknown', 'observed_at')
    payload['finished_at'] = payload['observed_at']
    with pytest.raises(ValidationError):
        UnknownResult.model_validate(payload)
