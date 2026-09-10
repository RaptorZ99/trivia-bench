"""Melange deterministe des options."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter

from trivia_bench.clean.shuffle import shuffle_options
from trivia_bench.ids import question_id

INCORRECT = ["Aglio", "Cipolla", "Peperoncino"]


def test_shuffle_is_deterministic() -> None:
    first = shuffle_options("a" * 64, "multiple", "Pomodoro", INCORRECT)
    second = shuffle_options("a" * 64, "multiple", "Pomodoro", INCORRECT)
    assert first == second


def test_shuffle_keeps_all_options_once() -> None:
    options, index = shuffle_options("b" * 64, "multiple", "Pomodoro", INCORRECT)
    assert sorted(options) == sorted([*INCORRECT, "Pomodoro"])
    assert options[index] == "Pomodoro"


def test_boolean_options_are_fixed() -> None:
    options, index = shuffle_options("c" * 64, "boolean", "False", ["True"])
    assert options == ["True", "False"]
    assert index == 1


def test_shuffle_stable_across_processes() -> None:
    code = (
        "from trivia_bench.clean.shuffle import shuffle_options;"
        "print(shuffle_options('a'*64,'multiple','Pomodoro',['Aglio','Cipolla','Peperoncino']))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": ""},
        ).stdout.strip()
        for seed in ("0", "7", "99")
    }
    assert len(outputs) == 1


def test_correct_position_is_spread_out() -> None:
    """Sur un grand nombre de questions, la bonne reponse ne doit pas se concentrer sur A."""
    positions: Counter[int] = Counter()
    for number in range(2000):
        qid = question_id("Cat", "multiple", "easy", f"Question {number}?", "Right")
        _, index = shuffle_options(qid, "multiple", "Right", ["W1", "W2", "W3"])
        positions[index] += 1
    assert set(positions) == {0, 1, 2, 3}
    assert all(400 <= count <= 600 for count in positions.values()), positions
