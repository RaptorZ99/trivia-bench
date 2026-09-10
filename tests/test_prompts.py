"""Rendu des variantes de prompt."""

from __future__ import annotations

import pytest

from tests.conftest import make_question
from trivia_bench.bench.prompts import (
    PROMPT_VARIANTS,
    VARIANT_ORDER,
    format_fewshot_block,
    prompt_version,
    render_prompt,
    render_request,
)
from trivia_bench.models import Question


def test_five_variants_are_declared() -> None:
    assert VARIANT_ORDER == ["v1_open", "v2_letter", "v3_simple_evals", "v4_fewshot", "v5_json"]


def test_prompt_version_is_readable() -> None:
    assert prompt_version()


def test_v1_shows_no_options(mc_question: Question) -> None:
    system, user = render_prompt(PROMPT_VARIANTS["v1_open"], mc_question)
    assert system is None
    assert user == mc_question.question
    assert "Pomodoro" not in user


def test_v2_lists_options_in_silver_order(mc_question: Question) -> None:
    system, user = render_prompt(PROMPT_VARIANTS["v2_letter"], mc_question)
    assert system is None
    assert "A) Aglio" in user
    assert "B) Pomodoro" in user
    assert user.rstrip().endswith("Do not explain.")


def test_v3_has_system_and_answer_contract(mc_question: Question) -> None:
    system, user = render_prompt(PROMPT_VARIANTS["v3_simple_evals"], mc_question)
    assert system is not None
    assert "rigorous trivia quiz solver" in system
    assert "'Answer: $LETTER'" in user
    assert user.rstrip().endswith("D) Peperoncino")


def test_v4_includes_two_examples(mc_question: Question) -> None:
    examples = [
        make_question(question_id="1" * 64, question="Q1?", correct_answer="Pomodoro"),
        make_question(question_id="2" * 64, question="Q2?", correct_answer="Pomodoro"),
    ]
    _, user = render_prompt(PROMPT_VARIANTS["v4_fewshot"], mc_question, fewshot=examples)
    assert user.count("Question:") == 3
    assert user.count("Answer:") == 3
    assert user.rstrip().endswith("Answer:")


def test_v4_without_examples_fails(mc_question: Question) -> None:
    with pytest.raises(ValueError, match="few-shot"):
        render_prompt(PROMPT_VARIANTS["v4_fewshot"], mc_question, fewshot=[])


def test_v5_declares_json_schema(mc_question: Question, bool_question: Question) -> None:
    variant = PROMPT_VARIANTS["v5_json"]
    assert variant.json_schema("multiple") == {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": ["A", "B", "C", "D"]}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    schema = variant.json_schema("boolean")
    assert schema is not None
    assert schema["properties"]["answer"]["enum"] == ["True", "False"]


@pytest.mark.parametrize("variant_id", VARIANT_ORDER)
def test_boolean_templates_never_show_letters(variant_id: str, bool_question: Question) -> None:
    examples = [
        make_question(
            question_id="3" * 64,
            qtype="boolean",
            question="Q?",
            correct_answer="True",
            incorrect_answers=["False"],
        )
    ]
    _, user = render_prompt(PROMPT_VARIANTS[variant_id], bool_question, fewshot=examples)
    assert "A)" not in user
    assert bool_question.question in user


def test_fewshot_block_formats_both_types() -> None:
    mc = make_question(question_id="4" * 64, question="Q1?")
    boolean = make_question(
        question_id="5" * 64,
        qtype="boolean",
        question="Q2?",
        correct_answer="True",
        incorrect_answers=["False"],
    )
    block = format_fewshot_block([mc, boolean])
    assert "Question: Q1?" in block
    assert "Statement: Q2?" in block
    assert "Answer: True" in block


def test_render_request_selects_transport(mc_question: Question) -> None:
    native, native_hash = render_request(PROMPT_VARIANTS["v2_letter"], mc_question, model_key="m")
    structured, structured_hash = render_request(
        PROMPT_VARIANTS["v5_json"], mc_question, model_key="m"
    )
    assert native.transport == "native"
    assert structured.transport == "openai"
    assert native.max_tokens == 8
    assert native_hash != structured_hash


def test_prompt_hash_is_stable(mc_question: Question) -> None:
    first = render_request(PROMPT_VARIANTS["v3_simple_evals"], mc_question, model_key="m")[1]
    second = render_request(PROMPT_VARIANTS["v3_simple_evals"], mc_question, model_key="m")[1]
    assert first == second
