"""Passage des reponses brutes a la couche silver, et manifeste de run."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from tests.conftest import make_question
from trivia_bench.bench.manifest import build_manifest, load_manifest, save_manifest
from trivia_bench.bench.prompts import PROMPT_VARIANTS
from trivia_bench.bench.silver import grade_run, write_runs_table
from trivia_bench.clean.builder import SILVER_SCHEMA
from trivia_bench.config import Settings
from trivia_bench.models import Question
from trivia_bench.paths import DataPaths

RUN_ID = "gemma-4-12b-qat__v2_letter__roff__20260910-1200"


@pytest.fixture
def questions() -> list[Question]:
    return [
        make_question(
            question_id="1" * 64,
            question="Q1?",
            options=["Aglio", "Pomodoro", "Cipolla", "Peperoncino"],
        ),
        make_question(
            question_id="2" * 64,
            qtype="boolean",
            question="Q2?",
            correct_answer="False",
            incorrect_answers=["True"],
        ),
        make_question(
            question_id="3" * 64,
            question="Q3?",
            options=["Aglio", "Pomodoro", "Cipolla", "Peperoncino"],
        ),
    ]


@pytest.fixture
def paths(tmp_path: Path, questions: list[Question]) -> DataPaths:
    data_paths = DataPaths(tmp_path / "data")
    data_paths.ensure_dirs()

    frame = pl.DataFrame([q.model_dump() for q in questions], schema=SILVER_SCHEMA)
    frame.write_parquet(data_paths.questions_parquet)

    records = [
        # Reponse conforme et juste.
        {"question_id": "1" * 64, "content": "B", "response_time": 0.21, "run_order": 0},
        # Reponse juste mais hors format.
        {"question_id": "2" * 64, "content": "False, he was Austrian.", "response_time": 0.42,
         "run_order": 1},
        # Appel en echec.
        {"question_id": "3" * 64, "content": "", "response_time": 12.0, "run_order": 2,
         "error": "TimeoutError: boom"},
    ]
    with data_paths.run_jsonl(RUN_ID).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    {
                        "run_id": RUN_ID,
                        "prompt_variant": "v2_letter",
                        "prompt_version": "test",
                        "prompt_sha256": "abc",
                        "transport": "native",
                        "reasoning_mode": "off",
                        "prompt_tokens": 70,
                        "completion_tokens": 2,
                        "reasoning_tokens": 0,
                        "tokens_per_second": 21.0,
                        "ttft_s": 0.13,
                        "finish_reason": "stop",
                        "attempt": 1,
                        "called_at": datetime.now(UTC).isoformat(),
                        "error": None,
                        **record,
                    }
                )
                + "\n"
            )

    manifest = build_manifest(
        run_id=RUN_ID,
        variant=PROMPT_VARIANTS["v2_letter"],
        model_key="google/gemma-4-12b-qat",
        reasoning_mode="off",
        model_info=None,
        generation_params={"temperature": 0},
        dataset_path=data_paths.questions_parquet,
        sample_spec="all",
        sample_question_ids=None,
        n_questions_planned=3,
    )
    manifest.n_questions_done = 3
    manifest.n_errors = 1
    manifest.finished_at = datetime.now(UTC)
    manifest.status = "complete"
    save_manifest(manifest, data_paths.run_manifest(RUN_ID))
    return data_paths


@pytest.fixture
def graded(paths: DataPaths, settings: Settings) -> pl.DataFrame:
    return grade_run(RUN_ID, settings=settings, paths=paths)


def test_partition_is_written(paths: DataPaths, graded: pl.DataFrame) -> None:
    assert paths.answers_partition(RUN_ID).exists()
    assert graded.height == 3


def test_grades_are_assigned(graded: pl.DataFrame) -> None:
    by_question = {
        row["question_id"]: (row["grade"], row["ai_correct"])
        for row in graded.iter_rows(named=True)
    }
    assert by_question["1" * 64] == ("letter", True)
    assert by_question["2" * 64] == ("contains", True)
    assert by_question["3" * 64] == ("error", False)


def test_error_row_keeps_its_message(graded: pl.DataFrame) -> None:
    row = graded.filter(pl.col("question_id") == "3" * 64).row(0, named=True)
    assert row["error"] is not None
    assert row["ai_correct"] is False


def test_metadata_is_carried_over(graded: pl.DataFrame) -> None:
    row = graded.row(0, named=True)
    assert row["run_id"] == RUN_ID
    assert row["model_key"] == "google/gemma-4-12b-qat"
    assert row["prompt_variant"] == "v2_letter"
    assert row["reasoning_mode"] == "off"
    assert row["transport"] == "native"


def test_timing_columns(graded: pl.DataFrame) -> None:
    assert graded["response_time"].to_list() == [0.21, 0.42, 12.0]
    assert graded["ttft_s"].to_list() == [0.13, 0.13, 0.13]


def test_grading_is_idempotent(paths: DataPaths, settings: Settings) -> None:
    first = grade_run(RUN_ID, settings=settings, paths=paths)
    second = grade_run(RUN_ID, settings=settings, paths=paths)
    assert first.equals(second)


def test_runs_table(paths: DataPaths, graded: pl.DataFrame) -> None:
    runs = write_runs_table(paths)
    assert runs.height == 1
    row = runs.row(0, named=True)
    assert row["run_id"] == RUN_ID
    assert row["status"] == "complete"
    assert row["n_errors"] == 1
    assert json.loads(row["generation_params"])["temperature"] == 0
    assert row["dataset_sha256"]


def test_manifest_round_trip(paths: DataPaths) -> None:
    manifest = load_manifest(paths.run_manifest(RUN_ID))
    assert manifest.prompt_variant == "v2_letter"
    assert manifest.python_version
    assert manifest.package_version
    assert manifest.machine
