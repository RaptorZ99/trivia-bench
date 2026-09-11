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
# Marqueur « Answer: X », que le modele produit spontanement ou en reponse a un gabarit
# qui se termine par « Answer: » (convention du harnais OpenAI simple-evals).
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


def extract_letter(answer: str) -> str | None:
    """Extrait la lettre choisie, par ordre de fiabilite decroissante.

    La lecture du JSON n'a pas sa place ici : `grade_answer` deballe le champ `answer` avant
    tout autre traitement, si bien que cette fonction ne voit jamais qu'un texte deja reduit.
    """
    text = answer.strip()
    if not text:
        return None

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
    allow_contains: bool,
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

    # Le rapprochement par sous-chaine est la seule regle dont la suite manquante d'une
    # reponse tronquee peut inverser le verdict : « The character Daryl Dixon does not have a »
    # cite l'option juste avant de la nier, et la negation tombe hors du texte recu.
    if not allow_contains:
        return None

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

    # Le refus n'est reconnu qu'apres avoir cherche une reponse : une reponse hesitante
    # mais juste (« je ne suis pas sur, mais False ») doit etre creditee.
    return GradeResult("unparseable", False)


def _boolean_result(grade: Grade, predicted: bool, gold: bool) -> GradeResult:
    label = "True" if predicted else "False"
    if predicted == gold:
        return GradeResult(grade, True, predicted_text=label)
    return GradeResult("wrong", False, predicted_text=label)


def grade_answer(
    answer: str,
    question: Question,
    *,
    structured: bool = False,
    answer_cue: bool = False,
    error: str | None = None,
    truncated: bool = False,
    fuzzy_threshold: float = 90.0,
    fuzzy_margin: float = 5.0,
) -> GradeResult:
    """Note une reponse du modele.

    Les trois variantes affichent les options : la reponse attendue est une lettre en choix
    multiples, le mot lui-meme en vrai/faux. `structured` active la lecture prealable du JSON,
    `answer_cue` la recherche du marqueur « Answer: », utile quand le gabarit se termine par lui.

    `truncated` signale une reponse coupee par le budget de tokens : le rapprochement par
    sous-chaine y est desactive, faute de pouvoir lire la suite qui la contredirait.
    """
    if error:
        return GradeResult("error", False)

    # La sortie structuree est contrainte par un schema : le champ `answer` est lu avant tout
    # autre traitement, quel que soit le type de question. Sans cela, une reponse vrai/faux
    # parfaitement conforme (`{"answer": "False"}`) serait notee par rapprochement approximatif
    # au lieu d'etre reconnue comme exacte.
    if structured:
        payload = _from_json(answer.strip())
        if payload is not None:
            answer = payload

    if question.type == "boolean":
        return _grade_boolean(answer, question, use_cue=answer_cue)

    letter = extract_letter(answer)
    if letter is not None and letter in LETTERS:
        correct = letter == question.correct_letter
        return GradeResult(
            "letter" if correct else "wrong",
            correct,
            predicted_letter=letter,
            predicted_text=question.options[LETTERS.index(letter)],
        )

    # Le modele a ignore la consigne et ecrit le texte de l'option : on le rattrape. Le JSON
    # eventuel a deja ete deballe plus haut, `answer` porte donc directement le texte a comparer.
    candidate = answer

    matched = _match_option_text(
        candidate,
        question.options,
        threshold=fuzzy_threshold,
        margin=fuzzy_margin,
        allow_contains=not truncated,
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
