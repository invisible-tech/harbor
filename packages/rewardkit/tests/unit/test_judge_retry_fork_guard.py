"""Fork guards for rewardkit's transient judge retry policy."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import litellm
import pytest

from rewardkit.judges import _acompletion_with_retry

pytestmark = pytest.mark.unit


_TRANSIENT_ERROR_TYPES = [
    litellm.InternalServerError,
    litellm.BadGatewayError,
    litellm.ServiceUnavailableError,
    litellm.RateLimitError,
    litellm.APIConnectionError,
]


def _error(error_type):
    return error_type(message="temporary failure", llm_provider="p", model="m")


@pytest.mark.parametrize("error_type", _TRANSIENT_ERROR_TYPES)
async def test_transient_errors_are_retried_three_times_then_propagated(error_type):
    error = _error(error_type)
    completion = AsyncMock(side_effect=error)
    with (
        patch("rewardkit.judges.litellm.acompletion", completion),
        patch("rewardkit.judges._transport_backoff", return_value=0.0),
        pytest.raises(error_type) as raised,
    ):
        await _acompletion_with_retry({"model": "m"}, 30)

    assert raised.value is error
    assert completion.call_count == 3


@pytest.mark.parametrize(
    "error_type", [litellm.BadRequestError, litellm.AuthenticationError]
)
async def test_client_errors_are_not_retried(error_type):
    error = _error(error_type)
    completion = AsyncMock(side_effect=error)
    with (
        patch("rewardkit.judges.litellm.acompletion", completion),
        pytest.raises(error_type) as raised,
    ):
        await _acompletion_with_retry({"model": "m"}, 30)

    assert raised.value is error
    assert completion.call_count == 1
