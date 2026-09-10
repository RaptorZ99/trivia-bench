"""Acces aux tables gold et filtres partages entre les pages."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from lib import db


@dataclass(frozen=True, slots=True)
class Selection:
    """Filtres globaux choisis dans la barre laterale."""

    models: tuple[str, ...]
    reasoning: tuple[str, ...]
    variants: tuple[str, ...]

    def apply(self, frame: pl.DataFrame) -> pl.DataFrame:
        """Restreint une table gold aux runs selectionnes."""
        result = frame
        if "model_short" in frame.columns and self.models:
            result = result.filter(pl.col("model_short").is_in(list(self.models)))
        if "reasoning_mode" in frame.columns and self.reasoning:
            result = result.filter(pl.col("reasoning_mode").is_in(list(self.reasoning)))
        if "prompt_variant" in frame.columns and self.variants:
            result = result.filter(pl.col("prompt_variant").is_in(list(self.variants)))
        return result


def runs() -> pl.DataFrame:
    """Referentiel des runs, du plus recent au plus ancien."""
    return db.table("gold.dim_run").sort("started_at", descending=True)


def run_summary() -> pl.DataFrame:
    return db.table("gold.mart_run_summary")


def accuracy_by_category() -> pl.DataFrame:
    return db.table("gold.mart_accuracy_by_category")


def accuracy_by_category_difficulty() -> pl.DataFrame:
    return db.table("gold.mart_accuracy_by_category_difficulty")


def accuracy_by_difficulty() -> pl.DataFrame:
    return db.table("gold.mart_accuracy_by_difficulty")


def accuracy_by_type() -> pl.DataFrame:
    return db.table("gold.mart_accuracy_by_type")


def grade_breakdown() -> pl.DataFrame:
    return db.table("gold.mart_grade_breakdown")


def position_bias() -> pl.DataFrame:
    return db.table("gold.mart_position_bias")


def latency_by_run() -> pl.DataFrame:
    return db.table("gold.mart_latency_by_run")


def latency_drift() -> pl.DataFrame:
    return db.table("gold.mart_latency_drift")


def variant_pairwise() -> pl.DataFrame:
    return db.table("gold.mart_variant_pairwise")


def question_consistency() -> pl.DataFrame:
    return db.table("gold.mart_question_consistency")


def answer_length() -> pl.DataFrame:
    return db.table("gold.mart_answer_length")


def questions() -> pl.DataFrame:
    return db.table("gold.dim_question")


def dataset_overview() -> dict[str, int]:
    """Volumetrie du jeu de questions, hors exemples few-shot."""
    frame = db.query(
        """
        select
            count(*) filter (where not is_fewshot_example)                        as n_questions,
            count(*) filter (where not is_fewshot_example and type = 'multiple')  as n_multiple,
            count(*) filter (where not is_fewshot_example and type = 'boolean')   as n_boolean,
            count(distinct category)                                              as n_categories
        from gold.dim_question
        """
    )
    return {key: int(value) for key, value in frame.row(0, named=True).items()}


def latency_samples(run_ids: list[str], limit_per_run: int = 4000) -> pl.DataFrame:
    """Echantillon de temps de reponse par run, pour les distributions."""
    if not run_ids:
        return pl.DataFrame(
            schema={"run_id": pl.String, "variant_label": pl.String, "response_time": pl.Float64}
        )
    placeholders = ", ".join("?" for _ in run_ids)
    return db.query(
        f"""
        select run_id, variant_label, type, response_time, prompt_tokens, completion_tokens
        from (
            select *, row_number() over (partition by run_id order by run_order) as rn
            from gold.fct_answer
            where run_id in ({placeholders}) and error is null
        )
        where rn <= {limit_per_run}
        """,
        tuple(run_ids),
    )


def paired_answers(run_a: str, run_b: str) -> pl.DataFrame:
    """Reponses appariees de deux runs, pour le test de McNemar et le bootstrap."""
    return db.query(
        """
        select
            a.question_id,
            a.ai_correct as correct_a,
            b.ai_correct as correct_b
        from gold.fct_answer as a
        inner join gold.fct_answer as b using (question_id)
        where a.run_id = ? and b.run_id = ?
        """,
        (run_a, run_b),
    )


def answers_for_question(question_id: str) -> pl.DataFrame:
    """Toutes les reponses obtenues pour une question donnee."""
    return db.query(
        """
        select
            run_id, model_short, variant_label, prompt_variant, reasoning_mode,
            ai_answer, ai_reasoning, predicted_letter, predicted_text,
            ai_correct, grade, response_time, completion_tokens
        from gold.fct_answer
        where question_id = ?
        order by prompt_variant
        """,
        (question_id,),
    )


def explorer_rows(
    run_ids: list[str],
    *,
    categories: list[str] | None = None,
    difficulties: list[str] | None = None,
    types: list[str] | None = None,
    grades: list[str] | None = None,
    search: str = "",
    limit: int = 500,
) -> pl.DataFrame:
    """Lignes de l'explorateur de questions, filtrees cote base."""
    if not run_ids:
        return pl.DataFrame()

    clauses = [f"run_id in ({', '.join('?' for _ in run_ids)})"]
    params: list[object] = list(run_ids)

    for column, values in (
        ("category", categories),
        ("difficulty", difficulties),
        ("type", types),
        ("grade", grades),
    ):
        if values:
            clauses.append(f"{column} in ({', '.join('?' for _ in values)})")
            params.extend(values)

    if search:
        clauses.append("(question ilike ? or correct_answer ilike ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    return db.query(
        f"""
        select
            question_id, variant_label, category, difficulty, type,
            question, correct_answer, ai_answer, predicted_text,
            ai_correct, grade, response_time, completion_tokens
        from gold.fct_answer
        where {" and ".join(clauses)}
        order by question_id
        limit {limit}
        """,
        tuple(params),
    )
