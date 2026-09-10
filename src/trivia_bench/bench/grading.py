"""Notation deterministe des reponses du modele (SPEC.md section 9).

Deux colonnes en sortent :

- `ai_correct` (booleen) : la reponse correspond a la bonne reponse, au sens de l'enonce ;
- `grade` (enumeration) : *comment* la reponse a ete reconnue, ce qui permet de distinguer un
  echec de connaissance (`wrong`) d'un echec de format (`unparseable`) et d'auditer les
  reconnaissances approximatives (`fuzzy`, `contains`).

La notation est calculee une seule fois en Python, jamais en SQL : le rapprochement approche
de rapidfuzz n'a pas d'equivalent SQL identique, et une implementation unique evite deux
logiques divergentes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from trivia_bench.clean.normalize import normalize_answer
from trivia_bench.models import LETTERS, Grade, Question

# Une lettre en tete de reponse : « B », « B) », « (b) », « B. Pomodoro ».
_LETTER_ANCHORED = re.compile(r"^\s*\(?([A-Da-d])\)?(?:[.):\-\s]|$)")
# Convention du harnais OpenAI simple-evals.
_ANSWER_CUE = re.compile(r"(?i)\banswer\s*(?::|is)\s*\$?\**\s*\(?([A-Da-d])\)?\b")
_ANSWER_CUE_TEXT = re.compile(r"(?i)answer\s*:\s*\**\s*([A-Za-z]+)")
# Une lettre isolee en fin de reponse courte.
_TRAILING_LETTER = re.compile(r"(?i)(?:^|\s)([A-D])\s*[.)]?\s*$")

_NEGATIONS = frozenset(
    {"not", "n't", "never", "except", "neither", "nor", "isn", "wasn", "aren", "no"}
)
_REFUSAL_EXACT = frozenset({"n a", "na", "unknown", "none", "no answer", "not sure", "no comment"})
_REFUSAL_PHRASES = (
    "i don t know",
    "i do not know",
    "i m not sure",
    "i am not sure",
    "not certain",
    "cannot answer",
    "can t answer",
    "cannot determine",
    "no idea",
    "unable to",
    "no information",
    "impossible to say",
)

_TRUE_TOKENS = frozenset({"true"})
_FALSE_TOKENS = frozenset({"false"})
# Les synonymes d'une seule lettre ne valent que si la reponse entiere s'y reduit : cherchees
# au milieu d'une phrase, elles produisent des faux positifs (« I don't know » se normalise
# en « i don t know », dont le « t » n'a rien d'une affirmation).
_TRUE_SYNONYMS = frozenset({"yes", "y", "t", "correct"})
_FALSE_SYNONYMS = frozenset({"no", "n", "f", "incorrect"})
_TRUE_WORDS = frozenset({"true", "yes", "correct"})
_FALSE_WORDS = frozenset({"false", "no", "incorrect"})


@dataclass(frozen=True, slots=True)
class GradeResult:
    """Resultat de la notation d'une reponse."""

    grade: Grade
    ai_correct: bool
    predicted_letter: str | None = None
    predicted_text: str | None = None
    score: float | None = None


def _looks_like_refusal(normalized: str) -> bool:
    """Reconnait un refus de repondre, sans confondre avec une reponse qui en contient les mots."""
    return normalized in _REFUSAL_EXACT or any(phrase in normalized for phrase in _REFUSAL_PHRASES)


def _has_negation_before(normalized_response: str, span: str, window: int = 2) -> bool:
    """Detecte une negation juste avant le segment reconnu (« not Mercury, but Venus »)."""
    index = normalized_response.find(span)
    if index == -1:
        return False
    preceding = normalized_response[:index].split()[-window:]
    return any(token in _NEGATIONS for token in preceding)


def extract_letter(answer: str, *, structured: bool) -> str | None:
    """Extrait la lettre choisie, par ordre de fiabilite decroissante."""
    text = answer.strip()
    if not text:
        return None

    if structured:
        letter = _from_json(text)
        if letter and letter in LETTERS:
            return letter

    match = _LETTER_ANCHORED.match(text)
    if match:
        return match.group(1).upper()

    match = _ANSWER_CUE.search(text)
    if match:
        return match.group(1).upper()

    if len(text.split()) <= 3:
        match = _TRAILING_LETTER.search(text)
        if match:
            return match.group(1).upper()

    return None


def _from_json(text: str) -> str | None:
    """Lit le champ `answer` d'une reponse JSON, y compris entouree de texte."""
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict) and "answer" in payload:
            value = str(payload["answer"]).strip()
            return value.upper() if len(value) == 1 else value
    return None


def _match_option_text(
    answer: str,
    options: list[str],
    *,
    threshold: float,
    margin: float,
) -> tuple[int, Grade, float | None] | None:
    """Rapproche une reponse en toutes lettres d'une des options proposees."""
    normalized = normalize_answer(answer)
    if not normalized:
        return None
    normalized_options = [normalize_answer(option) for option in options]

    if normalized in normalized_options:
        return normalized_options.index(normalized), "exact", 100.0

    scores = sorted(
        (
            (index, fuzz.ratio(normalized, option))
            for index, option in enumerate(normalized_options)
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    if scores and scores[0][1] >= threshold:
        runner_up = scores[1][1] if len(scores) > 1 else 0.0
        if scores[0][1] - runner_up >= margin:
            return scores[0][0], "fuzzy", float(scores[0][1])

    contained = [
        index
        for index, option in enumerate(normalized_options)
        if len(option) >= 3 and option in normalized
    ]
    if len(contained) > 1:
        # Plusieurs options citees : « Not Aglio, but Pomodoro » designe bien Pomodoro.
        contained = [
            index
            for index in contained
            if not _has_negation_before(normalized, normalized_options[index])
        ]
    if len(contained) == 1 and not _has_negation_before(
        normalized, normalized_options[contained[0]]
    ):
        return contained[0], "contains", None

    return None


def _grade_boolean(answer: str, question: Question, *, use_cue: bool) -> GradeResult:
    """Note une question vrai/faux."""
    text = answer.strip()
    if use_cue:
        match = _ANSWER_CUE_TEXT.search(text)
        if match:
            text = match.group(1)

    normalized = normalize_answer(text)
    if not normalized:
        return GradeResult("unparseable", False)

    gold = question.correct_answer.casefold() == "true"

    if normalized in _TRUE_TOKENS or normalized in _FALSE_TOKENS:
        predicted = normalized in _TRUE_TOKENS
        return _boolean_result("exact", predicted, gold)

    if normalized in _TRUE_SYNONYMS or normalized in _FALSE_SYNONYMS:
        predicted = normalized in _TRUE_SYNONYMS
        return _boolean_result("fuzzy", predicted, gold)

    words = set(normalized.split())
    found_true = bool(words & _TRUE_WORDS)
    found_false = bool(words & _FALSE_WORDS)
    if found_true ^ found_false:
        return _boolean_result("contains", found_true, gold)

    # Comme en texte libre, le refus n'est reconnu qu'apres avoir cherche une reponse.
    return GradeResult("unparseable", False)


def _boolean_result(grade: Grade, predicted: bool, gold: bool) -> GradeResult:
    label = "True" if predicted else "False"
    if predicted == gold:
        return GradeResult(grade, True, predicted_text=label)
    return GradeResult("wrong", False, predicted_text=label)


def _fuzzy_score(left: str, right: str) -> float:
    """Similarite de deux reponses normalisees.

    Deux mesures se completent : `token_sort_ratio` absorbe un ordre de mots different,
    `ratio` absorbe une espace manquante ou une faute de frappe. « leonardo davinci » contre
    « leonardo da vinci » n'obtient que 67 avec la premiere, mais 97 avec la seconde.
    """
    return float(max(fuzz.ratio(left, right), fuzz.token_sort_ratio(left, right)))


def _grade_free_text(answer: str, question: Question, *, threshold: float) -> GradeResult:
    """Note une reponse en texte libre (variante V1)."""
    normalized = normalize_answer(answer)
    if not normalized:
        return GradeResult("unparseable", False)

    gold = normalize_answer(question.correct_answer)

    if normalized == gold:
        return GradeResult("exact", True, predicted_text=question.correct_answer, score=100.0)

    score = _fuzzy_score(normalized, gold)
    if score >= threshold:
        return GradeResult("fuzzy", True, predicted_text=question.correct_answer, score=score)

    if len(gold) >= 3 and gold in normalized and not _has_negation_before(normalized, gold):
        return GradeResult("contains", True, predicted_text=question.correct_answer)

    # La reponse ne correspond pas : verifier si elle designe explicitement une mauvaise option,
    # ce qui distingue une erreur de connaissance d'une reponse hors sujet.
    for wrong in question.incorrect_answers:
        normalized_wrong = normalize_answer(wrong)
        if not normalized_wrong:
            continue
        if normalized == normalized_wrong or (
            len(normalized_wrong) >= 3
            and normalized_wrong in normalized
            and not _has_negation_before(normalized, normalized_wrong)
        ):
            return GradeResult("wrong", False, predicted_text=wrong)

    # Le refus n'est teste qu'en dernier : une reponse hesitante qui contient malgre tout la
    # bonne reponse (« je ne suis pas sur, mais Leonard de Vinci ») doit etre creditee.
    if _looks_like_refusal(normalized):
        return GradeResult("unparseable", False)

    return GradeResult("wrong", False, predicted_text=answer.strip()[:200] or None)


def grade_answer(
    answer: str,
    question: Question,
    *,
    expects_letter: bool = True,
    structured: bool = False,
    answer_cue: bool = False,
    error: str | None = None,
    fuzzy_threshold: float = 90.0,
    fuzzy_margin: float = 5.0,
) -> GradeResult:
    """Note une reponse du modele.

    `expects_letter` distingue les variantes a choix affiches (V2 a V5) de la variante ouverte
    (V1), `structured` active la lecture JSON, `answer_cue` la recherche du marqueur
    « Answer: » utilise par V3 et V4.
    """
    if error:
        return GradeResult("error", False)

    if not expects_letter:
        if question.type == "boolean":
            return _grade_boolean(answer, question, use_cue=answer_cue)
        return _grade_free_text(answer, question, threshold=fuzzy_threshold)

    if question.type == "boolean":
        return _grade_boolean(answer, question, use_cue=answer_cue)

    letter = extract_letter(answer, structured=structured)
    if letter is not None and letter in LETTERS:
        correct = letter == question.correct_letter
        return GradeResult(
            "letter" if correct else "wrong",
            correct,
            predicted_letter=letter,
            predicted_text=question.options[LETTERS.index(letter)],
        )

    # Le modele a ignore la consigne et ecrit le texte de l'option : on le rattrape.
    candidate = answer
    if structured:
        from_json = _from_json(answer.strip())
        if from_json:
            candidate = from_json

    matched = _match_option_text(
        candidate, question.options, threshold=fuzzy_threshold, margin=fuzzy_margin
    )
    if matched is not None:
        index, grade, score = matched
        correct = index == question.correct_index
        return GradeResult(
            grade if correct else "wrong",
            correct,
            predicted_letter=LETTERS[index],
            predicted_text=question.options[index],
            score=score,
        )

    normalized = normalize_answer(candidate)
    if not normalized or _looks_like_refusal(normalized):
        return GradeResult("unparseable", False)
    return GradeResult("unparseable", False, predicted_text=candidate.strip()[:200] or None)
