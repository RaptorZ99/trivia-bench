"""Table de verite de la notation des reponses.

La bonne reponse de `mc_question` est en position B (`Pomodoro`), celle de `bool_question`
est `False`.
"""

from __future__ import annotations

import pytest

from trivia_bench.bench.grading import extract_letter, grade_answer
from trivia_bench.models import Question

# --- Questions a choix multiples, variantes attendant une lettre ---


@pytest.mark.parametrize(
    ("answer", "grade", "correct"),
    [
        # Lettre bien formee, sous toutes ses formes courantes
        ("B", "letter", True),
        ("b", "letter", True),
        ("B)", "letter", True),
        ("(B)", "letter", True),
        ("(b)", "letter", True),
        ("B.", "letter", True),
        (" B ", "letter", True),
        ("B. Pomodoro", "letter", True),
        ("B) Pomodoro", "letter", True),
        ("Answer: B", "letter", True),
        ("answer: B", "letter", True),
        ("The answer is B", "letter", True),
        ("Answer: $B$", "letter", True),
        # Lettre bien formee mais fausse
        ("A", "wrong", False),
        ("C)", "wrong", False),
        ("Answer: D", "wrong", False),
        ("A. Aglio", "wrong", False),
        # Texte de l'option au lieu de la lettre
        ("Pomodoro", "exact", True),
        ("pomodoro", "exact", True),
        ("Pomodoro.", "exact", True),
        ("  Pomodoro  ", "exact", True),
        ("**Pomodoro**", "exact", True),
        ("Aglio", "wrong", False),
        ("The answer is Pomodoro", "contains", True),
        ("It's Pomodoro, of course.", "contains", True),
        ("Not Aglio, but Pomodoro", "contains", True),
        # Rapprochement approche
        ("Pomodorro", "fuzzy", True),
        # Reponses inexploitables
        ("", "unparseable", False),
        ("   ", "unparseable", False),
        ("I don't know", "unparseable", False),
        ("N/A", "unparseable", False),
        ("Something entirely unrelated", "unparseable", False),
    ],
)
def test_grade_multiple_choice(
    mc_question: Question, answer: str, grade: str, correct: bool
) -> None:
    result = grade_answer(answer, mc_question, expects_letter=True)
    assert (result.grade, result.ai_correct) == (grade, correct), result


def test_negation_guard_rejects_cited_answer(mc_question: Question) -> None:
    """Citer la bonne reponse pour la refuter ne doit pas etre credite."""
    result = grade_answer("It is not Pomodoro", mc_question, expects_letter=True)
    assert result.ai_correct is False


def test_letter_is_preferred_over_option_text(mc_question: Question) -> None:
    """Quand la lettre et le texte se contredisent, la lettre fait foi."""
    result = grade_answer("A) Pomodoro", mc_question, expects_letter=True)
    assert (result.grade, result.predicted_letter) == ("wrong", "A")


# --- Variante JSON contrainte ---


@pytest.mark.parametrize(
    ("answer", "grade", "correct"),
    [
        ('{"answer": "B"}', "letter", True),
        ('{"answer":"B"}', "letter", True),
        ('  {"answer": "b"}  ', "letter", True),
        ('{"answer": "A"}', "wrong", False),
        ('Here you go: {"answer": "B"}', "letter", True),
        ('{"answer": "Pomodoro"}', "exact", True),
        ("{not json", "unparseable", False),
        ("{}", "unparseable", False),
    ],
)
def test_grade_structured(mc_question: Question, answer: str, grade: str, correct: bool) -> None:
    result = grade_answer(answer, mc_question, expects_letter=True, structured=True)
    assert (result.grade, result.ai_correct) == (grade, correct), result


# --- Questions vrai/faux ---


@pytest.mark.parametrize(
    ("answer", "grade", "correct"),
    [
        ("False", "exact", True),
        ("false", "exact", True),
        ("FALSE.", "exact", True),
        (" False ", "exact", True),
        ("True", "wrong", False),
        ("No", "fuzzy", True),
        ("no", "fuzzy", True),
        ("Yes", "wrong", False),
        ("False, he was born in Austria.", "contains", True),
        ("That statement is false.", "contains", True),
        ("True, he was Austrian", "wrong", False),
        ("Neither true nor false", "unparseable", False),
        ("", "unparseable", False),
        ("I don't know", "unparseable", False),
    ],
)
def test_grade_boolean(bool_question: Question, answer: str, grade: str, correct: bool) -> None:
    result = grade_answer(answer, bool_question, expects_letter=True)
    assert (result.grade, result.ai_correct) == (grade, correct), result


def test_boolean_answer_cue(bool_question: Question) -> None:
    """Les variantes V3 et V4 attendent un marqueur « Answer: »."""
    result = grade_answer(
        "Let me think.\nAnswer: False", bool_question, expects_letter=True, answer_cue=True
    )
    assert (result.grade, result.ai_correct) == ("exact", True)


# --- Variante ouverte (texte libre) ---


@pytest.mark.parametrize(
    ("answer", "grade", "correct"),
    [
        ("Pomodoro", "exact", True),
        ("pomodoro.", "exact", True),
        ("The Italian word is Pomodoro.", "contains", True),
        ("**Pomodoro**", "exact", True),
        ("Pomodorro", "fuzzy", True),
        ("Aglio", "wrong", False),
        ("The word is Aglio", "wrong", False),
        ("Basilico", "wrong", False),
        ("", "unparseable", False),
        ("I don't know", "unparseable", False),
    ],
)
def test_grade_free_text(mc_question: Question, answer: str, grade: str, correct: bool) -> None:
    result = grade_answer(answer, mc_question, expects_letter=False)
    assert (result.grade, result.ai_correct) == (grade, correct), result


@pytest.mark.parametrize(
    ("answer", "grade", "correct"),
    [
        # Faute de frappe ou espace manquante : `ratio` rattrape la ou `token_sort_ratio` echoue.
        ("Pomodorro", "fuzzy", True),
        ("Pomo doro", "fuzzy", True),
        # Un refus reste un refus, quelle que soit sa formulation.
        ("I am not sure.", "unparseable", False),
        ("I have no idea", "unparseable", False),
        ("I cannot answer that", "unparseable", False),
        ("No information is available", "unparseable", False),
        # Mais une reponse hesitante qui donne quand meme la bonne reponse est creditee :
        # le refus n'est teste qu'apres avoir cherche une reponse.
        ("I am not sure, but I think Pomodoro.", "contains", True),
        ("Not certain, probably Pomodoro", "contains", True),
    ],
)
def test_free_text_hedging_and_refusals(
    mc_question: Question, answer: str, grade: str, correct: bool
) -> None:
    result = grade_answer(answer, mc_question, expects_letter=False)
    assert (result.grade, result.ai_correct) == (grade, correct), result


def test_boolean_refusal_is_not_read_as_true(bool_question: Question) -> None:
    """« I don't know » se normalise en « i don t know » : le « t » isole ne vaut pas True."""
    result = grade_answer("I don't know", bool_question, expects_letter=True)
    assert (result.grade, result.ai_correct) == ("unparseable", False)


def test_boolean_hedged_answer_is_credited(bool_question: Question) -> None:
    result = grade_answer("I'm not sure, but False.", bool_question, expects_letter=True)
    assert (result.grade, result.ai_correct) == ("contains", True)


def test_free_text_negation_guard(mc_question: Question) -> None:
    result = grade_answer("It is not Pomodoro at all", mc_question, expects_letter=False)
    assert result.ai_correct is False


def test_free_text_on_boolean_question(bool_question: Question) -> None:
    result = grade_answer("False", bool_question, expects_letter=False)
    assert (result.grade, result.ai_correct) == ("exact", True)


# --- Cas transverses ---


def test_error_is_reported_as_such(mc_question: Question) -> None:
    result = grade_answer("", mc_question, error="TimeoutError: boom")
    assert (result.grade, result.ai_correct) == ("error", False)


def test_predicted_fields_are_filled(mc_question: Question) -> None:
    result = grade_answer("Answer: C", mc_question, expects_letter=True)
    assert result.predicted_letter == "C"
    assert result.predicted_text == "Cipolla"


def test_fuzzy_margin_rejects_ambiguous_match() -> None:
    """Deux options tres proches ne doivent pas etre departagees par le rapprochement flou."""
    from tests.conftest import make_question

    question = make_question(
        correct_answer="Pomodoro",
        incorrect_answers=["Pomodori", "Aglio", "Cipolla"],
        options=["Pomodoro", "Pomodori", "Aglio", "Cipolla"],
    )
    result = grade_answer("Pomodorx", question, expects_letter=True)
    assert result.grade == "unparseable"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("B", "B"),
        ("b)", "B"),
        ("Answer: C", "C"),
        ("blah blah", None),
        ("", None),
        ("E", None),
    ],
)
def test_extract_letter(text: str, expected: str | None) -> None:
    assert extract_letter(text, structured=False) == expected
