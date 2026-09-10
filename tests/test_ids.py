"""Identifiants deterministes."""

from __future__ import annotations

import subprocess
import sys

from trivia_bench.ids import normalize_key, option_seed, prompt_hash, question_id

ARGS = ("General Knowledge", "multiple", "medium", "What is X?", "Y")


def test_question_id_is_stable() -> None:
    assert question_id(*ARGS) == question_id(*ARGS)
    assert len(question_id(*ARGS)) == 64


def test_question_id_ignores_html_entities_and_spacing() -> None:
    a = question_id("General Knowledge", "multiple", "easy", "It&#039;s  here ", "Yes")
    b = question_id("General Knowledge", "multiple", "easy", "It's here", "Yes")
    assert a == b


def test_question_id_is_case_insensitive() -> None:
    assert question_id(*ARGS) == question_id(
        "GENERAL KNOWLEDGE", "Multiple", "Medium", "WHAT IS X?", "y"
    )


def test_question_id_differs_on_answer() -> None:
    assert question_id(*ARGS) != question_id(
        "General Knowledge", "multiple", "medium", "What is X?", "Z"
    )


def test_question_id_stable_across_processes() -> None:
    """Le hachage ne doit pas dependre de la randomisation de `hash()` (PEP 456)."""
    code = (
        "from trivia_bench.ids import question_id;"
        "print(question_id('General Knowledge','multiple','medium','What is X?','Y'))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": ""},
        ).stdout.strip()
        for seed in ("0", "1", "12345")
    }
    assert outputs == {question_id(*ARGS)}


def test_option_seed_is_deterministic_and_bounded() -> None:
    seed = option_seed("a" * 64)
    assert seed == option_seed("a" * 64)
    assert 0 <= seed < 2**32


def test_prompt_hash_distinguishes_system_prompt() -> None:
    assert prompt_hash(None, "u") != prompt_hash("s", "u")
    assert prompt_hash("s", "u") == prompt_hash("s", "u")


def test_normalize_key_collapses_whitespace() -> None:
    assert normalize_key("  A\tB\n C ") == "a b c"
