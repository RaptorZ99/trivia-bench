"""Client LM Studio : transport unique, parsing des statistiques, gestion des erreurs."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from trivia_bench.bench.lmstudio import LMStudioClient, ReasoningLeakError
from trivia_bench.models import LLMRequest

BASE = "http://lmstudio.test"

V0_OK: dict[str, Any] = {
    "id": "chatcmpl-test",
    "model": "trivia-bench",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "B", "reasoning_content": ""},
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 70,
        "completion_tokens": 2,
        "total_tokens": 72,
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


def test_every_variant_uses_the_same_endpoint(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    """Texte libre et sortie contrainte passent par le meme endpoint.

    C'est la condition pour que les temps des variantes se comparent : deux endpoints
    produiraient des colonnes qui ne mesurent pas la meme chose.
    """
    httpx_mock.add_response(json=V0_OK, is_reusable=True)
    client.complete(make_request())
    client.complete(make_request(json_schema=SCHEMA, max_tokens=24))
    chemins = {request.url.path for request in httpx_mock.get_requests()}
    assert chemins == {"/api/v0/chat/completions"}


def test_response_carries_engine_statistics(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json=V0_OK)
    response = client.complete(make_request())
    assert response.content == "B"
    assert response.prompt_tokens == 70
    assert response.tokens_per_second == pytest.approx(21.3)
    assert response.ttft_s == pytest.approx(0.13)
    assert response.finish_reason == "stop"
    assert response.response_time > 0


def test_body_disables_reasoning_and_pins_greedy_decoding(
    client: LMStudioClient, httpx_mock: HTTPXMock
) -> None:
    """L'endpoint ignore les cles inconnues : leurs noms ne sont gardes que par ce test."""
    httpx_mock.add_response(json=V0_OK)
    client.complete(make_request())
    body = body_of(httpx_mock)
    assert body["reasoning_effort"] == "none"
    assert body["temperature"] == 0
    assert body["top_k"] == 1
    assert body["top_p"] == 1.0
    assert body["min_p"] == 0.0
    assert body["repeat_penalty"] == 1.0
    assert body["max_tokens"] == 8
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_structured_request_keeps_statistics(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    """La sortie contrainte livre les memes statistiques que le texte libre."""
    structured = dict(V0_OK)
    structured["choices"] = [
        {
            "index": 0,
            "message": {"role": "assistant", "content": '{"answer": "B"}'},
            "finish_reason": "stop",
        }
    ]
    httpx_mock.add_response(json=structured)
    response = client.complete(make_request(json_schema=SCHEMA, max_tokens=24))
    body = body_of(httpx_mock)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["response_format"]["json_schema"]["strict"] is True
    assert response.content == '{"answer": "B"}'
    assert response.ttft_s == pytest.approx(0.13)
    assert response.tokens_per_second == pytest.approx(21.3)


def test_reasoning_is_captured_when_enabled(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        json={
            "choices": [
                {
                    "index": 0,
                    "message": {"content": "B", "reasoning_content": "thinking..."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 70,
                "completion_tokens": 40,
                "completion_tokens_details": {"reasoning_tokens": 38},
            },
            "stats": {"tokens_per_second": 20.0, "time_to_first_token": 0.2},
        }
    )
    response = client.complete(make_request(reasoning_mode="on", max_tokens=1024))
    assert response.reasoning == "thinking..."
    assert response.content == "B"
    assert response.reasoning_tokens == 38


def test_reasoning_leak_raises(client: LMStudioClient, httpx_mock: HTTPXMock) -> None:
    """Un raisonnement produit alors qu'il est desactive invalide le protocole du benchmark."""
    leaked = dict(V0_OK)
    leaked["usage"] = {
        **V0_OK["usage"],
        "completion_tokens_details": {"reasoning_tokens": 12},
    }
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
    httpx_mock.add_response(json=V0_OK)
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
