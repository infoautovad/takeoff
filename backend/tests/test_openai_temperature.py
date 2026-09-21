from __future__ import annotations

import pytest

from app.services.openai_client import (
    _create_dropping_unsupported,
    _supports_custom_temperature,
    _unsupported_param_name,
)


def test_terra_and_gpt5_do_not_send_temperature():
    assert _supports_custom_temperature("gpt-5.6-terra") is False
    assert _supports_custom_temperature("gpt-5") is False
    assert _supports_custom_temperature("gpt-4o") is True


def test_parses_unsupported_temperature_error():
    exc = Exception(
        "Error code: 400 - {'error': {'message': \"Unsupported parameter: 'temperature' is not supported with this model.\"}}"
    )
    assert _unsupported_param_name(exc) == "temperature"


def test_retries_without_rejected_temperature():
    calls: list[dict] = []

    def create(**kwargs):
        calls.append(dict(kwargs))
        if "temperature" in kwargs:
            raise Exception("Unsupported parameter: 'temperature' is not supported with this model.")
        return "ok"

    result = _create_dropping_unsupported(create, {"model": "gpt-5.6-terra", "temperature": 0.1})
    assert result == "ok"
    assert len(calls) == 2
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]


def test_reraises_unrelated_errors():
    def create(**kwargs):
        raise RuntimeError("insufficient_quota")

    with pytest.raises(RuntimeError, match="insufficient_quota"):
        _create_dropping_unsupported(create, {"model": "gpt-5.6-terra", "temperature": 0.1})
