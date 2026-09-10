"""Boucle de collecte : dimensionnement des lots, reprise, deduplication."""

from __future__ import annotations

import base64
import csv
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from trivia_bench.paths import DataPaths
from trivia_bench.scrape.checkpoint import Checkpoint
from trivia_bench.scrape.client import OpenTDBClient
from trivia_bench.scrape.runner import scrape_all

BASE = "https://opentdb.test"


def encode(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def question(index: int, category: str = "General Knowledge") -> dict[str, Any]:
    return {
        "category": encode(category),
        "type": encode("multiple"),
        "difficulty": encode("easy"),
        "question": encode(f"Question {index} ?"),
        "correct_answer": encode(f"Right {index}"),
        "incorrect_answers": [encode("W1"), encode("W2"), encode("W3")],
    }


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "data")


@pytest.fixture
def client() -> OpenTDBClient:
    return OpenTDBClient(BASE, min_interval=0.0, client=httpx.Client(base_url=BASE))


def _read_csv(paths: DataPaths) -> list[dict[str, str]]:
    with paths.questions_raw_csv.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _mock_two_categories(httpx_mock: HTTPXMock) -> None:
    """Deux categories : 60 questions (deux lots) et 3 questions (un lot)."""
    httpx_mock.add_response(
        url=f"{BASE}/api_category.php",
        json={
            "trivia_categories": [
                {"id": 9, "name": "General Knowledge"},
                {"id": 13, "name": "Entertainment: Musicals & Theatres"},
            ]
        },
        is_reusable=True,
    )
    for category_id, total in ((9, 60), (13, 3)):
        httpx_mock.add_response(
            url=f"{BASE}/api_count.php?category={category_id}",
            json={
                "category_id": category_id,
                "category_question_count": {
                    "total_question_count": total,
                    "total_easy_question_count": total,
                    "total_medium_question_count": 0,
                    "total_hard_question_count": 0,
                },
            },
            is_reusable=True,
        )


def test_full_collection(client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock) -> None:
    _mock_two_categories(httpx_mock)
    # Categorie 9 : un lot de 50 puis un lot de 10, dimensionnes sur le compte annonce.
    httpx_mock.add_response(json={"response_code": 0, "results": [question(i) for i in range(50)]})
    httpx_mock.add_response(
        json={"response_code": 0, "results": [question(i) for i in range(50, 60)]}
    )
    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    summary = scrape_all(client, paths, token="tok")

    assert summary["total_received"] == 63
    assert summary["n_unique"] == 63
    assert len(_read_csv(paths)) == 63


def test_batch_sizes_never_exceed_remaining_pool(
    client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock
) -> None:
    """Demander plus que le pool restant renverrait un tableau vide : les lots sont calibres."""
    _mock_two_categories(httpx_mock)
    httpx_mock.add_response(json={"response_code": 0, "results": [question(i) for i in range(50)]})
    httpx_mock.add_response(
        json={"response_code": 0, "results": [question(i) for i in range(50, 60)]}
    )
    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    scrape_all(client, paths, token="tok")

    amounts = [
        int(request.url.params["amount"])
        for request in httpx_mock.get_requests()
        if request.url.path == "/api.php"
    ]
    assert amounts == [50, 10, 3]


def test_exhausted_pool_stops_the_category(
    client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock
) -> None:
    """Le compte annonce peut etre obsolete : le code 1 termine proprement la categorie."""
    _mock_two_categories(httpx_mock)
    httpx_mock.add_response(json={"response_code": 0, "results": [question(i) for i in range(50)]})
    httpx_mock.add_response(json={"response_code": 1, "results": []})
    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    summary = scrape_all(client, paths, token="tok")

    assert summary["total_received"] == 53
    # La categorie suivante est bien traitee malgre l'epuisement de la precedente.
    assert summary["categories"]["Entertainment: Musicals & Theatres"]["received"] == 3


def test_duplicates_are_skipped(
    client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock
) -> None:
    """Sans token, l'API peut resservir une question : la deduplication la rattrape."""
    _mock_two_categories(httpx_mock)
    httpx_mock.add_response(json={"response_code": 0, "results": [question(i) for i in range(50)]})
    # Le second lot renvoie dix questions deja vues.
    httpx_mock.add_response(json={"response_code": 0, "results": [question(i) for i in range(10)]})
    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    summary = scrape_all(client, paths, token="tok")

    assert summary["n_duplicates"] == 10
    assert summary["n_unique"] == 53
    assert len(_read_csv(paths)) == 53


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
# Les categories filtrees ou deja terminees ne declenchent aucun appel : certaines
# reponses enregistrees restent volontairement inutilisees.
def test_resume_skips_finished_categories(
    client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock
) -> None:
    """Une categorie deja marquee terminee n'est pas rappelee."""
    _mock_two_categories(httpx_mock)
    paths.ensure_dirs()
    checkpoint = Checkpoint(token="tok")
    state = checkpoint.state(9)
    state.expected, state.received, state.done = 60, 60, True
    checkpoint.save(paths.opentdb_checkpoint)

    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    summary = scrape_all(client, paths, token="tok")

    called = [
        request.url.params.get("category")
        for request in httpx_mock.get_requests()
        if request.url.path == "/api.php"
    ]
    assert called == ["13"]
    assert summary["total_received"] == 63


def test_checkpoint_is_written_after_each_batch(
    client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock
) -> None:
    _mock_two_categories(httpx_mock)
    httpx_mock.add_response(json={"response_code": 0, "results": [question(i) for i in range(50)]})
    httpx_mock.add_response(
        json={"response_code": 0, "results": [question(i) for i in range(50, 60)]}
    )
    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    scrape_all(client, paths, token="tok")

    checkpoint = Checkpoint.load(paths.opentdb_checkpoint)
    assert checkpoint.token == "tok"
    assert checkpoint.state(9).done is True
    assert checkpoint.state(9).received == 60
    assert checkpoint.state(13).received == 3


def test_http_audit_trail(client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock) -> None:
    """Chaque appel laisse une trace exploitable pour l'audit."""
    _mock_two_categories(httpx_mock)
    httpx_mock.add_response(json={"response_code": 0, "results": [question(i) for i in range(50)]})
    httpx_mock.add_response(
        json={"response_code": 0, "results": [question(i) for i in range(50, 60)]}
    )
    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    scrape_all(client, paths, token="tok")

    lines = paths.opentdb_responses.read_text(encoding="utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == 3
    assert [record["n_results"] for record in records] == [50, 10, 3]
    assert all(record["response_code"] == 0 for record in records)


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
# Les categories filtrees ou deja terminees ne declenchent aucun appel : certaines
# reponses enregistrees restent volontairement inutilisees.
def test_category_filter(client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock) -> None:
    _mock_two_categories(httpx_mock)
    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    summary = scrape_all(client, paths, token="tok", category_ids=[13])

    assert summary["total_received"] == 3
    assert set(summary["categories"]) == {"Entertainment: Musicals & Theatres"}


def test_token_is_requested_when_absent(
    client: OpenTDBClient, paths: DataPaths, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/api_token.php?command=request",
        json={"response_code": 0, "token": "generated"},
    )
    _mock_two_categories(httpx_mock)
    httpx_mock.add_response(json={"response_code": 0, "results": [question(i) for i in range(50)]})
    httpx_mock.add_response(
        json={"response_code": 0, "results": [question(i) for i in range(50, 60)]}
    )
    httpx_mock.add_response(
        json={
            "response_code": 0,
            "results": [question(i, "Entertainment: Musicals & Theatres") for i in range(3)],
        }
    )

    scrape_all(client, paths)

    assert Checkpoint.load(paths.opentdb_checkpoint).token == "generated"
    api_requests = [r for r in httpx_mock.get_requests() if r.url.path == "/api.php"]
    assert all(request.url.params["token"] == "generated" for request in api_requests)
