"""Construction de la couche silver a partir du CSV bronze."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import polars as pl
import pytest

from trivia_bench.clean.builder import build_questions
from trivia_bench.ids import question_id
from trivia_bench.scrape.runner import CSV_FIELDS

ROWS = [
    {
        "category": "General Knowledge",
        "type": "multiple",
        "difficulty": "easy",
        "question": "What is the Italian word for &quot;tomato&quot;?",
        "correct_answer": "Pomodoro",
        "incorrect_answers": ["Aglio", "Cipolla", "Peperoncino"],
    },
    {
        "category": "General Knowledge",
        "type": "boolean",
        "difficulty": "easy",
        "question": "Adolf Hitler was born in Australia. ",
        "correct_answer": "False",
        "incorrect_answers": ["True"],
    },
    {
        "category": "Entertainment: Film",
        "type": "multiple",
        "difficulty": "hard",
        "question": "Who directed &eacute;lite?",
        "correct_answer": "Beyonc&eacute;",
        "incorrect_answers": ["A", "B", "C"],
    },
    {
        # Doublon exact de la premiere ligne, mais avec des espaces parasites.
        "category": "General Knowledge",
        "type": "multiple",
        "difficulty": "easy",
        "question": "What is the Italian word for &quot;tomato&quot;?  ",
        "correct_answer": " Pomodoro ",
        "incorrect_answers": ["Aglio", "Cipolla", "Peperoncino"],
    },
]


@pytest.fixture
def bronze_csv(tmp_path: Path) -> Path:
    path = tmp_path / "questions_raw.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for index, row in enumerate(ROWS):
            writer.writerow(
                {
                    "scraped_at": "2026-09-10T12:00:00+00:00",
                    "category_id": 9,
                    "category": row["category"],
                    "type": row["type"],
                    "difficulty": row["difficulty"],
                    "question": row["question"],
                    "correct_answer": row["correct_answer"],
                    "incorrect_answers": json.dumps(row["incorrect_answers"]),
                    "batch_index": 1,
                    "result_index": index,
                }
            )
    return path


@pytest.fixture
def silver(bronze_csv: Path, tmp_path: Path) -> pl.DataFrame:
    return build_questions(bronze_csv, tmp_path / "questions.parquet")


def test_duplicates_are_removed(silver: pl.DataFrame) -> None:
    assert silver.height == 3
    assert silver["question_id"].n_unique() == 3


def test_html_entities_are_decoded(silver: pl.DataFrame) -> None:
    questions = set(silver["question"].to_list())
    assert 'What is the Italian word for "tomato"?' in questions
    assert "Who directed élite?" in questions
    assert "Beyoncé" in set(silver["correct_answer"].to_list())


def test_trailing_whitespace_is_stripped(silver: pl.DataFrame) -> None:
    assert "Adolf Hitler was born in Australia." in set(silver["question"].to_list())


def test_schema_and_enums(silver: pl.DataFrame) -> None:
    assert silver.schema["type"] == pl.Enum(["multiple", "boolean"])
    assert silver.schema["difficulty"] == pl.Enum(["easy", "medium", "hard"])
    assert silver.schema["incorrect_answers"] == pl.List(pl.String())
    assert silver.schema["options"] == pl.List(pl.String())


def test_options_contain_correct_answer_at_declared_index(silver: pl.DataFrame) -> None:
    for row in silver.iter_rows(named=True):
        assert row["options"][row["correct_index"]] == row["correct_answer"]
        assert "ABCD"[row["correct_index"]] == row["correct_letter"]
        assert len(row["options"]) == row["n_options"]


def test_boolean_options_are_true_false(silver: pl.DataFrame) -> None:
    boolean = silver.filter(pl.col("type") == "boolean")
    assert boolean["options"].to_list() == [["True", "False"]]
    assert boolean["correct_letter"].to_list() == ["B"]


def test_category_group_is_derived(silver: pl.DataFrame) -> None:
    groups = dict(zip(silver["category"], silver["category_group"], strict=True))
    assert groups["Entertainment: Film"] == "Entertainment"
    assert groups["General Knowledge"] == "General Knowledge"


def test_question_id_matches_helper(silver: pl.DataFrame) -> None:
    row = silver.filter(pl.col("type") == "boolean").row(0, named=True)
    assert row["question_id"] == question_id(
        row["category"], "boolean", row["difficulty"], row["question"], row["correct_answer"]
    )


def test_parquet_is_written_and_reloadable(bronze_csv: Path, tmp_path: Path) -> None:
    destination = tmp_path / "out" / "questions.parquet"
    build_questions(bronze_csv, destination)
    assert destination.exists()
    assert pl.read_parquet(destination).height == 3


def test_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_questions(tmp_path / "absent.csv", tmp_path / "out.parquet")
