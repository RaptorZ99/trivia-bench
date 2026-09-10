"""Chargement et echantillonnage du jeu de questions de la couche silver."""

from __future__ import annotations

import random
import re
from pathlib import Path

import polars as pl

from trivia_bench.models import Question

_STRATIFIED = re.compile(r"^stratified:(\d+)$")


def load_questions(path: Path) -> list[Question]:
    """Charge toutes les questions silver sous forme de modeles valides."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} est introuvable : lancer `trivia scrape` puis `trivia clean`."
        )
    frame = pl.read_parquet(path).with_columns(
        pl.col("type").cast(pl.String),
        pl.col("difficulty").cast(pl.String),
    )
    return [Question.model_validate(row) for row in frame.iter_rows(named=True)]


def fewshot_examples(questions: list[Question], question_type: str) -> list[Question]:
    """Exemples few-shot du type demande, dans un ordre stable."""
    return sorted(
        (q for q in questions if q.is_fewshot_example and q.type == question_type),
        key=lambda q: q.question_id,
    )


def select_questions(
    questions: list[Question],
    *,
    limit: int | None = None,
    sample: str | None = None,
    seed: int = 20260910,
) -> tuple[list[Question], str]:
    """Selectionne les questions a evaluer et retourne `(questions, description)`.

    Les exemples few-shot sont toujours exclus : ils apparaissent dans les prompts de la
    variante V4 et ne peuvent donc pas servir de questions d'evaluation.
    """
    pool = sorted(
        (q for q in questions if not q.is_fewshot_example),
        key=lambda q: q.question_id,
    )

    if sample:
        match = _STRATIFIED.match(sample)
        if not match:
            raise ValueError(f"Echantillon non reconnu : {sample!r} (attendu 'stratified:N')")
        size = int(match.group(1))
        return _stratified(pool, size, seed=seed), f"stratified:{size}"

    if limit is not None:
        return pool[:limit], f"limit:{limit}"

    return pool, "all"


def _stratified(pool: list[Question], size: int, *, seed: int) -> list[Question]:
    """Echantillon stratifie par categorie, difficulte et type, avec au moins un par strate."""
    if size >= len(pool):
        return pool

    strata: dict[tuple[str, str, str], list[Question]] = {}
    for question in pool:
        strata.setdefault((question.category, question.difficulty, question.type), []).append(
            question
        )

    rng = random.Random(seed)
    quotas: dict[tuple[str, str, str], int] = {}
    total = len(pool)
    for key, group in strata.items():
        quotas[key] = max(1, round(size * len(group) / total))

    # Ajuste les quotas pour retomber exactement sur la taille demandee.
    keys = sorted(strata, key=lambda key: (-len(strata[key]), key))
    while sum(quotas.values()) > size:
        for key in keys:
            if sum(quotas.values()) <= size:
                break
            if quotas[key] > 1:
                quotas[key] -= 1
    while sum(quotas.values()) < size:
        for key in keys:
            if sum(quotas.values()) >= size:
                break
            if quotas[key] < len(strata[key]):
                quotas[key] += 1

    selected: list[Question] = []
    for key in sorted(strata):
        group = sorted(strata[key], key=lambda q: q.question_id)
        take = min(quotas[key], len(group))
        selected.extend(rng.sample(group, take))

    return sorted(selected, key=lambda q: q.question_id)
