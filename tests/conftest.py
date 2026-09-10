"""Fixtures partagees par les tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trivia_bench.config import Settings
from trivia_bench.models import LETTERS, Question


def make_question(
    *,
    question_id: str | None = None,
    category: str = "General Knowledge",
    qtype: str = "multiple",
    difficulty: str = "medium",
    question: str = 'What is the Italian word for "tomato"?',
    correct_answer: str = "Pomodoro",
    incorrect_answers: list[str] | None = None,
    options: list[str] | None = None,
    is_fewshot_example: bool = False,
) -> Question:
    """Construit une question valide, en calculant les champs derives."""
    incorrect = incorrect_answers or (
        ["Aglio", "Cipolla", "Peperoncino"] if qtype == "multiple" else ["False"]
    )
    resolved_options = options or (
        [*incorrect, correct_answer] if qtype == "multiple" else ["True", "False"]
    )
    correct_index = resolved_options.index(correct_answer)
    return Question(
        question_id=question_id or ("a" * 64),
        category_id=9,
        category=category,
        category_group=category.split(":")[0].strip(),
        type=qtype,  # type: ignore[arg-type]
        difficulty=difficulty,  # type: ignore[arg-type]
        question=question,
        correct_answer=correct_answer,
        incorrect_answers=incorrect,
        options=resolved_options,
        correct_index=correct_index,
        correct_letter=LETTERS[correct_index],
        n_options=len(resolved_options),
        question_chars=len(question),
        question_words=len(question.split()),
        is_fewshot_example=is_fewshot_example,
        scraped_at=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def mc_question() -> Question:
    """Question a choix multiples dont la bonne reponse est en position B."""
    return make_question(options=["Aglio", "Pomodoro", "Cipolla", "Peperoncino"])


@pytest.fixture
def bool_question() -> Question:
    """Question vrai/faux dont la bonne reponse est False."""
    return make_question(
        qtype="boolean",
        question="Adolf Hitler was born in Australia.",
        correct_answer="False",
        incorrect_answers=["True"],
    )


@pytest.fixture
def settings() -> Settings:
    """Parametres par defaut, sans lecture du fichier `.env` local."""
    return Settings(_env_file=None)  # type: ignore[call-arg]
