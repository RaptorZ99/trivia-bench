"""Client LM Studio : choix du transport, parsing des statistiques, gestion des erreurs."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from trivia_bench.bench.lmstudio import LMStudioClient, ReasoningLeakError
from trivia_bench.models import LLMRequest

BASE = "http://lmstudio.test"

NATIVE_OK: dict[str, Any] = {
    "model_instance_id": "trivia-bench",
    "output": [{"type": "message", "content": "B"}],
    "stats": {
        "input_tokens": 70,
        "total_output_tokens": 2,
        "reasoning_output_tokens": 0,
        "tokens_per_second": 21.3,
        "time_to_first_token_seconds": 0.13,
    },
}

OPENAI_OK: dict[str, Any] = {
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": '{"answer": "B"}'},
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 70,
        "completion_tokens": 14,
        "total_tokens": 84,
        "completion_tokens_details": {"reasoning_tokens": 0},
    },
}


@pytest.fixture
def client() -> LMStudioClient:
    return LMStudioClient(BASE, client=httpx.Client(base_url=BASE))


def make_request(**overrides: Any) -> LLMRequest:
    payload: dict[str, Any] = {
        "model_key": "google/gemma-4-12b-qat",
        "system": "sys",
        "user": "usr",
        "max_tokens": 8,
        "reasoning_mode": "off",
    }
    payload.update(overrides)
    return LLMRequest(**payload)


def test_text_variant_uses_native_endpoint(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json=NATIVE_OK)
    response = client.complete(make_request())
    request = httpx_mock.get_requests()[0]
    assert request.url.path == "/api/v1/chat"
    assert response.content == "B"
    assert response.prompt_tokens == 70
    assert response.tokens_per_second == pytest.approx(21.3)
    assert response.ttft_s == pytest.approx(0.13)
    assert response.response_time > 0


def test_native_body_disables_reasoning_and_sampling(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json=NATIVE_OK)
    client.complete(make_request())
    import json as json_module

    body = json_module.loads(httpx_mock.get_requests()[0].content)
    assert body["reasoning"] == "off"
    assert body["temperature"] == 0
    assert body["top_k"] == 1
    assert body["top_p"] == 1.0
    assert body["min_p"] == 0.0
    assert body["repeat_penalty"] == 1.0
    assert body["max_output_tokens"] == 8
    assert body["system_prompt"] == "sys"


def test_structured_variant_uses_openai_endpoint(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json=OPENAI_OK)
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    response = client.complete(make_request(json_schema=schema, max_tokens=24))
    request = httpx_mock.get_requests()[0]
    assert request.url.path == "/v1/chat/completions"

    import json as json_module

    body = json_module.loads(request.content)
    assert body["reasoning_effort"] == "none"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == schema
    assert response.content == '{"answer": "B"}'
    assert response.tokens_per_second is None


def test_native_captures_reasoning_when_enabled(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        json={
            "output": [
                {"type": "reasoning", "content": "thinking..."},
                {"type": "message", "content": "B"},
            ],
            "stats": {
                "input_tokens": 70,
                "total_output_tokens": 40,
                "reasoning_output_tokens": 38,
            },
        }
    )
    response = client.complete(make_request(reasoning_mode="on", max_tokens=1024))
    assert response.reasoning == "thinking..."
    assert response.content == "B"
    assert response.reasoning_tokens == 38


def test_reasoning_leak_raises(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    """Un raisonnement produit alors qu'il est desactive invalide le protocole du benchmark."""
    leaked = dict(NATIVE_OK)
    leaked["stats"] = {**NATIVE_OK["stats"], "reasoning_output_tokens": 12}
    httpx_mock.add_response(json=leaked)
    with pytest.raises(ReasoningLeakError):
        client.complete(make_request())


def test_client_error_is_not_retried(
    client: LMStudioClient, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    httpx_mock.add_response(status_code=400, text="Unrecognized key(s)")
    response = client.complete(make_request())
    assert response.error is not None
    assert "400" in response.error
    assert len(httpx_mock.get_requests()) == 1


def test_server_error_is_retried_then_reported(
    client: LMStudioClient, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    httpx_mock.add_response(status_code=503, text="busy", is_reusable=True)
    response = client.complete(make_request())
    assert response.error is not None
    assert response.attempt == 3
    assert len(httpx_mock.get_requests()) == 3


def test_transient_error_then_success(
    client: LMStudioClient, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    httpx_mock.add_response(status_code=503, text="busy")
    httpx_mock.add_response(json=NATIVE_OK)
    response = client.complete(make_request())
    assert (response.content, response.error, response.attempt) == ("B", None, 2)


def test_list_models_reads_loaded_instance(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        json={
            "models": [
                {
                    "type": "llm",
                    "key": "google/gemma-4-12b-qat",
                    "display_name": "Gemma 4 12B QAT",
                    "architecture": "gemma4",
                    "quantization": {"name": "Q4_0", "bits_per_weight": 4},
                    "size_bytes": 7151067268,
                    "max_context_length": 262144,
                    "format": "gguf",
                    "loaded_instances": [
                        {"id": "trivia-bench", "config": {"context_length": 4096, "parallel": 1}}
                    ],
                    "capabilities": {"reasoning": {"allowed_options": ["off", "on"]}},
                }
            ]
        }
    )
    model = client.get_model("google/gemma-4-12b-qat")
    assert model is not None
    assert model.loaded is True
    assert model.context_length == 4096
    assert model.parallel == 1
    assert model.quantization == "Q4_0"
    assert "off" in model.reasoning_options


def test_unknown_model_returns_none(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"models": []})
    assert client.get_model("absent") is None
