"""Client LM Studio : choix de l'endpoint, parsing des statistiques, gestion des erreurs."""

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

V0_OK: dict[str, Any] = {
    "id": "chatcmpl-test",
    "model": "trivia-bench",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": '{"answer": "B"}'},
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 70,
        "completion_tokens": 7,
        "total_tokens": 77,
        "completion_tokens_details": {"reasoning_tokens": 0},
    },
    "stats": {
        "tokens_per_second": 21.3,
        "time_to_first_token": 0.13,
        "generation_time": 0.09,
        "stop_reason": "eosFound",
    },
    "model_info": {"arch": "gemma4", "quant": "Q4_0", "format": "gguf", "context_length": 4096},
    "runtime": {"name": "llama.cpp-mac-arm64-apple-metal-advsimd", "version": "2.34.0"},
}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string", "enum": ["A", "B", "C", "D"]}},
    "required": ["answer"],
    "additionalProperties": False,
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


def body_of(httpx_mock: HTTPXMock, index: int = 0) -> dict[str, Any]:
    import json as json_module

    content: dict[str, Any] = json_module.loads(httpx_mock.get_requests()[index].content)
    return content


def test_endpoint_follows_what_the_variant_requires(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    """L'endpoint natif rejette la sortie contrainte : celle-ci passe donc par /api/v0."""
    httpx_mock.add_response(url=f"{BASE}/api/v1/chat", json=NATIVE_OK)
    httpx_mock.add_response(url=f"{BASE}/api/v0/chat/completions", json=V0_OK)
    client.complete(make_request())
    client.complete(make_request(json_schema=SCHEMA, max_tokens=24))
    chemins = [request.url.path for request in httpx_mock.get_requests()]
    assert chemins == ["/api/v1/chat", "/api/v0/chat/completions"]


def test_native_body_disables_reasoning_and_pins_greedy_decoding(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json=NATIVE_OK)
    client.complete(make_request())
    body = body_of(httpx_mock)
    assert body["reasoning"] == "off"
    assert body["temperature"] == 0
    assert body["top_k"] == 1
    assert body["top_p"] == 1.0
    assert body["min_p"] == 0.0
    assert body["repeat_penalty"] == 1.0
    assert body["max_output_tokens"] == 8
    assert body["system_prompt"] == "sys"


def test_native_response_carries_engine_statistics(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json=NATIVE_OK)
    response = client.complete(make_request())
    assert response.content == "B"
    assert response.prompt_tokens == 70
    assert response.tokens_per_second == pytest.approx(21.3)
    assert response.ttft_s == pytest.approx(0.13)
    assert response.response_time > 0


def test_structured_body_carries_the_schema(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json=V0_OK)
    client.complete(make_request(json_schema=SCHEMA, max_tokens=24))
    body = body_of(httpx_mock)
    assert body["reasoning_effort"] == "none"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["max_tokens"] == 24


def test_structured_response_carries_the_same_statistics(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    """Colonnes identiques pour toutes les variantes : c'est ce qui rend V3 comparable."""
    httpx_mock.add_response(json=V0_OK)
    response = client.complete(make_request(json_schema=SCHEMA, max_tokens=24))
    assert response.content == '{"answer": "B"}'
    assert response.ttft_s == pytest.approx(0.13)
    assert response.tokens_per_second == pytest.approx(21.3)
    assert response.finish_reason == "stop"


def test_reasoning_is_captured_when_enabled(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
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


def test_loaded_runtime_reports_format_and_context(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    """Le format servi decide du moteur d'inference : il conditionne la comparaison."""
    httpx_mock.add_response(
        json={
            "data": [
                {"id": "autre", "state": "not-loaded", "compatibility_type": "mlx"},
                {
                    "id": "trivia-bench",
                    "state": "loaded",
                    "arch": "gemma4",
                    "compatibility_type": "gguf",
                    "quantization": "Q4_0",
                    "loaded_context_length": 4096,
                },
            ]
        }
    )
    loaded = client.loaded_runtime()
    assert loaded is not None
    assert loaded["compatibility_type"] == "gguf"
    assert loaded["loaded_context_length"] == 4096


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
