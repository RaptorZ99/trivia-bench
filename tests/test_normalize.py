"""Normalisation des reponses."""

from __future__ import annotations

import pytest

from trivia_bench.clean.normalize import (
    category_group,
    clean_text,
    normalize_answer,
    strip_accents,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pomodoro", "pomodoro"),
        ("  Pomodoro  ", "pomodoro"),
        ("POMODORO!", "pomodoro"),
        ("The Beatles", "beatles"),
        ("A Clockwork Orange", "clockwork orange"),
        ("An Apple", "apple"),
        ("Leonardo da Vinci.", "leonardo da vinci"),
        ("**Leonardo da Vinci**", "leonardo da vinci"),
        ("*Mona Lisa*", "mona lisa"),
        ("It&#039;s", "it s"),
        ("Beyonc&eacute;", "beyonce"),
        ("Café", "cafe"),
        ("ROLEX watches", "rolex watches"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_answer(raw: str, expected: str) -> None:
    assert normalize_answer(raw) == expected


def test_strip_accents() -> None:
    assert strip_accents("éàüô") == "eauo"


def test_clean_text_preserves_case_and_punctuation() -> None:
    assert clean_text("Adolf Hitler was born in Australia. ") == (
        "Adolf Hitler was born in Australia."
    )
    assert clean_text("What is the Italian word for &quot;tomato&quot;?") == (
        'What is the Italian word for "tomato"?'
    )


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("Entertainment: Film", "Entertainment"),
        ("Science: Computers", "Science"),
        ("General Knowledge", "General Knowledge"),
        ("Sports", "Sports"),
    ],
)
def test_category_group(category: str, expected: str) -> None:
    assert category_group(category) == expected
