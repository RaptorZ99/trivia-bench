"""Selection et echantillonnage des questions."""

from __future__ import annotations

import pytest

from tests.conftest import make_question
from trivia_bench.bench.dataset import fewshot_examples, select_questions
from trivia_bench.ids import question_id


def build_pool(size: int = 200) -> list:
    """Cree un jeu de questions reparti sur plusieurs categories et difficultes."""
    categories = ["General Knowledge", "Entertainment: Film", "Science: Computers"]
    difficulties = ["easy", "medium", "hard"]
    pool = []
    for index in range(size):
        category = categories[index % len(categories)]
        difficulty = difficulties[index % len(difficulties)]
        qtype = "multiple" if index % 4 else "boolean"
        correct = "Right" if qtype == "multiple" else "True"
        pool.append(
            make_question(
                question_id=question_id(category, qtype, difficulty, f"Q{index}?", correct),
                category=category,
                qtype=qtype,
                difficulty=difficulty,
                question=f"Q{index}?",
                correct_answer=correct,
                incorrect_answers=["W1", "W2", "W3"] if qtype == "multiple" else ["False"],
                options=None if qtype == "boolean" else ["W1", "Right", "W2", "W3"],
            )
        )
    return pool


def test_fewshot_examples_are_excluded_from_evaluation() -> None:
    pool = build_pool(10)
    pool[0] = pool[0].model_copy(update={"is_fewshot_example": True})
    selected, spec = select_questions(pool)
    assert spec == "all"
    assert len(selected) == 9
    assert all(not question.is_fewshot_example for question in selected)


def test_selection_is_sorted_and_reproducible() -> None:
    pool = build_pool(50)
    first, _ = select_questions(pool)
    second, _ = select_questions(pool)
    assert [q.question_id for q in first] == [q.question_id for q in second]
    assert first == sorted(first, key=lambda q: q.question_id)


def test_limit_takes_first_questions() -> None:
    pool = build_pool(50)
    selected, spec = select_questions(pool, limit=7)
    assert (len(selected), spec) == (7, "limit:7")


def test_stratified_sample_has_exact_size_and_covers_strata() -> None:
    pool = build_pool(180)
    selected, spec = select_questions(pool, sample="stratified:60")
    assert (len(selected), spec) == (60, "stratified:60")
    strata = {(q.category, q.difficulty, q.type) for q in selected}
    all_strata = {(q.category, q.difficulty, q.type) for q in pool}
    assert strata == all_strata


def test_stratified_sample_is_reproducible() -> None:
    pool = build_pool(180)
    first, _ = select_questions(pool, sample="stratified:40", seed=123)
    second, _ = select_questions(pool, sample="stratified:40", seed=123)
    assert [q.question_id for q in first] == [q.question_id for q in second]


def test_stratified_larger_than_pool_returns_everything() -> None:
    pool = build_pool(20)
    selected, _ = select_questions(pool, sample="stratified:999")
    assert len(selected) == 20


def test_invalid_sample_spec_raises() -> None:
    with pytest.raises(ValueError, match="stratified"):
        select_questions(build_pool(10), sample="random:10")


def test_fewshot_examples_filtered_by_type() -> None:
    pool = build_pool(12)
    pool[0] = pool[0].model_copy(update={"is_fewshot_example": True, "type": "multiple"})
    examples = fewshot_examples(pool, "multiple")
    assert all(example.type == "multiple" for example in examples)
    assert all(example.is_fewshot_example for example in examples)
