"""Client OpenTDB : codes applicatifs, decodage, limitation de debit, blocage reseau."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from trivia_bench.scrape.client import (
    BlockedByNetworkError,
    InvalidParameterError,
    OpenTDBClient,
    RateLimitedError,
    TokenNotFoundError,
    decode_question,
)

BASE = "https://opentdb.test"


def encode(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def question_payload(question: str = "Q?", correct: str = "Right") -> dict[str, Any]:
    return {
        "category": encode("General Knowledge"),
        "type": encode("multiple"),
        "difficulty": encode("easy"),
        "question": encode(question),
        "correct_answer": encode(correct),
        "incorrect_answers": [encode("W1"), encode("W2"), encode("W3")],
    }


@pytest.fixture
def client() -> OpenTDBClient:
    """Client sans temporisation, pour des tests rapides."""
    return OpenTDBClient(BASE, min_interval=0.0, client=httpx.Client(base_url=BASE))


def test_decode_question_round_trip() -> None:
    decoded = decode_question(question_payload("Qu'est-ce ?", "Réponse"))
    assert decoded["question"] == "Qu'est-ce ?"
    assert decoded["correct_answer"] == "Réponse"
    assert decoded["incorrect_answers"] == ["W1", "W2", "W3"]


def test_request_token(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"response_code": 0, "token": "abc123"})
    assert client.request_token() == "abc123"


def test_get_categories(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"trivia_categories": [{"id": 9, "name": "General Knowledge"}]})
    categories = client.get_categories()
    assert (categories[0].id, categories[0].name) == (9, "General Knowledge")


def test_get_category_count(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        json={
            "category_id": 13,
            "category_question_count": {
                "total_question_count": 36,
                "total_easy_question_count": 11,
                "total_medium_question_count": 14,
                "total_hard_question_count": 11,
            },
        }
    )
    count = client.get_category_count(13)
    assert (count.total, count.easy, count.medium, count.hard) == (36, 11, 14, 11)


def test_get_questions_decodes_results(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"response_code": 0, "results": [question_payload()]})
    code, questions = client.get_questions(1, category_id=9, token="tok")
    assert code == 0
    assert questions[0]["question"] == "Q?"


@pytest.mark.parametrize("code", [1, 4])
def test_exhausted_pool_returns_empty(
    client: OpenTDBClient, httpx_mock: HTTPXMock, code: int
) -> None:
    """Les codes 1 et 4 signalent un pool epuise : liste vide, pas d'exception."""
    httpx_mock.add_response(json={"response_code": code, "results": []})
    returned, questions = client.get_questions(50, category_id=9)
    assert (returned, questions) == (code, [])


def test_rate_limit_is_retried_then_succeeds(
    client: OpenTDBClient, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    httpx_mock.add_response(json={"response_code": 5})
    httpx_mock.add_response(json={"response_code": 0, "results": [question_payload()]})
    code, questions = client.get_questions(1)
    assert (code, len(questions)) == (0, 1)


def test_rate_limit_eventually_raises(
    client: OpenTDBClient, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    httpx_mock.add_response(json={"response_code": 5}, is_reusable=True)
    with pytest.raises(RateLimitedError):
        client.get_questions(1)


def test_token_not_found_raises(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"response_code": 3})
    with pytest.raises(TokenNotFoundError):
        client.get_questions(1, token="expired")


def test_invalid_parameter_raises(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"response_code": 2})
    with pytest.raises(InvalidParameterError):
        client.get_questions(1)


def test_corporate_block_page_is_detected(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    """Un portail d'entreprise renvoie du HTML avec un statut 200 ou 403."""
    httpx_mock.add_response(
        status_code=403,
        text="<html><body>Corporate Internet policy violation</body></html>",
    )
    with pytest.raises(BlockedByNetworkError):
        client.get_questions(1)


def test_http_status_is_not_trusted_alone(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    """L'API renvoie 200 meme sur une erreur applicative : c'est response_code qui compte."""
    httpx_mock.add_response(status_code=200, json={"response_code": 3})
    with pytest.raises(TokenNotFoundError):
        client.get_questions(1)


def test_throttling_waits_between_calls(httpx_mock: HTTPXMock) -> None:
    slept: list[float] = []
    client = OpenTDBClient(BASE, min_interval=5.2, client=httpx.Client(base_url=BASE))
    httpx_mock.add_response(json={"response_code": 0, "results": []}, is_reusable=True)

    import trivia_bench.scrape.client as module

    original_sleep = module.time.sleep
    module.time.sleep = lambda seconds: slept.append(seconds)  # type: ignore[assignment]
    try:
        client.get_questions(1)
        client.get_questions(1)
    finally:
        module.time.sleep = original_sleep  # type: ignore[assignment]

    assert len(slept) == 1
    assert 0 < slept[0] <= 5.2


def test_request_body_uses_base64_encoding(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"response_code": 0, "results": []})
    client.get_questions(50, category_id=11, token="tok")
    request = httpx_mock.get_requests()[0]
    assert request.url.params["encode"] == "base64"
    assert request.url.params["category"] == "11"
    assert request.url.params["amount"] == "50"
    assert request.url.params["token"] == "tok"


def test_json_error_is_not_swallowed(client: OpenTDBClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(text=json.dumps({"response_code": 0, "results": []}))
    code, questions = client.get_questions(1)
    assert (code, questions) == (0, [])
