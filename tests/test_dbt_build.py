"""Construction de la couche gold sur un jeu de donnees miniature.

Ce test verifie de bout en bout que le projet dbt compile, que les tables gold sont creees
avec les bons schemas, et que les tests de donnees passent.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import polars as pl
import pytest

from tests.conftest import make_question
from trivia_bench.bench.silver import ANSWERS_SCHEMA, RUNS_SCHEMA
from trivia_bench.build.dbt import run_dbt_build
from trivia_bench.clean.builder import SILVER_SCHEMA
from trivia_bench.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    ("run_a", "v2_letter", [True, True, False, True]),
    ("run_b", "v3_simple_evals", [True, False, False, True]),
]


def _questions() -> list[dict[str, object]]:
    rows = []
    for index in range(4):
        qtype = "boolean" if index == 3 else "multiple"
        rows.append(
            make_question(
                question_id=str(index) * 64,
                category="General Knowledge" if index < 2 else "Science: Computers",
                qtype=qtype,
                difficulty=["easy", "medium", "hard", "easy"][index],
                question=f"Question {index} ?",
                correct_answer="Pomodoro" if qtype == "multiple" else "False",
                incorrect_answers=(
                    ["Aglio", "Cipolla", "Peperoncino"] if qtype == "multiple" else ["True"]
                ),
                options=(
                    ["Aglio", "Pomodoro", "Cipolla", "Peperoncino"] if qtype == "multiple" else None
                ),
            ).model_dump()
        )
    return rows


def _answers(run_id: str, variant: str, correctness: list[bool]) -> list[dict[str, object]]:
    return [
        {
            "run_id": run_id,
            "question_id": str(index) * 64,
            "model_key": "google/gemma-4-12b-qat",
            "model_quant": "Q4_0",
            "prompt_variant": variant,
            "prompt_version": "test",
            "reasoning_mode": "off",
            "transport": "native",
            "prompt_sha256": "abc",
            "ai_answer": "B" if correct else "A",
            "ai_reasoning": None,
            "predicted_letter": "B" if correct else "A",
            "predicted_text": "Pomodoro" if correct else "Aglio",
            "ai_correct": correct,
            "grade": "letter" if correct else "wrong",
            "grade_score": None,
            "response_time": 0.2 + index * 0.1,
            "ttft_s": 0.13,
            "tokens_per_second": 21.0,
            "prompt_tokens": 70,
            "completion_tokens": 2,
            "reasoning_tokens": 0,
            "finish_reason": "stop",
            "run_order": index,
            "attempt": 1,
            "called_at": datetime.now(UTC),
            "error": None,
        }
        for index, correct in enumerate(correctness)
    ]


def _run_row(run_id: str, variant: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "model_key": "google/gemma-4-12b-qat",
        "model_display_name": "Gemma 4 12B QAT",
        "model_quant": "Q4_0",
        "model_size_bytes": 7151067268,
        "instance_identifier": "trivia-bench",
        "context_length": 4096,
        "parallel": 1,
        "prompt_variant": variant,
        "prompt_version": "test",
        "reasoning_mode": "off",
        "transport": "native",
        "generation_params": json.dumps({"temperature": 0}),
        "lmstudio_version": "0.4.24",
        "runtime_engine": "llama.cpp",
        "python_version": "3.12.0",
        "package_version": "1.0.0",
        "git_sha": None,
        "dataset_sha256": "deadbeef",
        "sample_spec": "all",
        "n_questions_planned": 4,
        "n_questions_done": 4,
        "n_errors": 0,
        "warmup_time_s": 1.0,
        "machine": json.dumps({"cpu": "Apple M2 Pro"}),
        "started_at": datetime.now(UTC),
        "finished_at": datetime.now(UTC),
        "status": "complete",
    }


@pytest.fixture(scope="module")
def gold(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Construit une couche gold complete depuis des fixtures silver."""
    workspace = tmp_path_factory.mktemp("dbt_build")
    silver = workspace / "silver"
    (silver / "answers").mkdir(parents=True)

    pl.DataFrame(_questions(), schema=SILVER_SCHEMA).write_parquet(silver / "questions.parquet")
    pl.DataFrame(
        [_run_row(run, variant) for run, variant, _ in RUNS], schema=RUNS_SCHEMA
    ).write_parquet(silver / "runs.parquet")
    for run_id, variant, correctness in RUNS:
        partition = silver / "answers" / f"run_id={run_id}"
        partition.mkdir()
        pl.DataFrame(_answers(run_id, variant, correctness), schema=ANSWERS_SCHEMA).write_parquet(
            partition / "part-0.parquet"
        )

    # dbt resout ses chemins relatifs depuis le repertoire courant : on copie le projet.
    project = workspace / "dbt"
    shutil.copytree(PROJECT_ROOT / "dbt", project, ignore=shutil.ignore_patterns("target", "logs"))

    duckdb_path = workspace / "gold" / "benchmark.duckdb"
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        duckdb_path=duckdb_path,
        silver_dir=silver,
    )
    ok = run_dbt_build(settings, project_dir=str(project))
    assert ok, "dbt build a echoue sur les fixtures"
    return duckdb_path


def _query(gold: Path, sql: str) -> list[tuple[object, ...]]:
    with duckdb.connect(str(gold), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def test_schemas_are_clean(gold: Path) -> None:
    """Les modeles doivent atterrir dans `staging` et `gold`, jamais dans `main`."""
    schemas = {
        row[0]
        for row in _query(gold, "select distinct table_schema from information_schema.tables")
    }
    assert schemas == {"staging", "gold"}


def test_all_marts_exist(gold: Path) -> None:
    tables = {
        row[0]
        for row in _query(
            gold, "select table_name from information_schema.tables where table_schema = 'gold'"
        )
    }
    expected = {
        "dim_question",
        "dim_run",
        "fct_answer",
        "mart_run_summary",
        "mart_accuracy_by_category",
        "mart_accuracy_by_category_difficulty",
        "mart_accuracy_by_difficulty",
        "mart_accuracy_by_type",
        "mart_grade_breakdown",
        "mart_position_bias",
        "mart_latency_by_run",
        "mart_latency_drift",
        "mart_variant_pairwise",
        "mart_question_consistency",
        "mart_answer_length",
    }
    assert expected <= tables


def test_run_summary_values(gold: Path) -> None:
    rows = _query(
        gold,
        "select run_id, n, n_correct, accuracy, wilson_lo, wilson_hi, chance_baseline "
        "from gold.mart_run_summary order by run_id",
    )
    assert [(row[0], row[1], row[2]) for row in rows] == [("run_a", 4, 3), ("run_b", 4, 2)]
    for _, n, n_correct, accuracy, lo, hi, baseline in rows:
        assert accuracy == pytest.approx(n_correct / n)
        assert 0 <= lo <= accuracy <= hi <= 1
        # Trois questions a choix multiples et une vrai/faux : (3 * 0.25 + 0.5) / 4.
        assert baseline == pytest.approx((3 * 0.25 + 0.5) / 4)


def test_chance_baseline_by_type(gold: Path) -> None:
    rows = dict(
        _query(
            gold,
            "select type, chance_baseline from gold.mart_accuracy_by_type where run_id = 'run_a'",
        )
    )
    assert rows == {"multiple": pytest.approx(0.25), "boolean": pytest.approx(0.5)}


def test_pairwise_contingency(gold: Path) -> None:
    """Les deux runs partagent les memes questions : la comparaison doit etre appariee."""
    rows = _query(
        gold,
        "select n, both_correct, a_only, b_only, both_wrong from gold.mart_variant_pairwise",
    )
    assert len(rows) == 1
    n, both_correct, a_only, b_only, both_wrong = rows[0]
    assert n == 4
    assert both_correct + a_only + b_only + both_wrong == n
    # run_a a bon aux questions 0,1,3 ; run_b aux questions 0,3.
    assert (both_correct, a_only, b_only, both_wrong) == (2, 1, 0, 1)


def test_low_sample_flag(gold: Path) -> None:
    flags = _query(
        gold,
        "select distinct n_flag_low from gold.mart_accuracy_by_category",
    )
    assert flags == [(True,)]


def test_question_consistency(gold: Path) -> None:
    rows = _query(
        gold,
        "select question_id, n_runs, n_correct, all_correct, all_wrong, is_mixed "
        "from gold.mart_question_consistency order by question_id",
    )
    assert len(rows) == 4
    assert all(row[1] == 2 for row in rows)
    # La question 2 est ratee par les deux runs.
    wrong_everywhere = [row[0] for row in rows if row[4]]
    assert wrong_everywhere == ["2" * 64]


def test_staging_views_are_readable(gold: Path) -> None:
    assert _query(gold, "select count(*) from staging.stg_questions") == [(4,)]
    assert _query(gold, "select count(*) from staging.stg_answers") == [(8,)]
    assert _query(gold, "select count(*) from staging.stg_runs") == [(2,)]
