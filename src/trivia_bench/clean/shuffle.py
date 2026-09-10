"""Ordre deterministe des options proposees au modele.

Le biais de position en questions a choix multiples est documente (Zheng et al., ICLR 2024) :
melanger les options evite qu'une lettre soit systematiquement la bonne reponse. Le melange
doit rester identique entre variantes de prompt, entre modeles et entre executions, d'ou une
graine derivee du `question_id` par sha256 plutot que du `hash()` de Python, randomise par
processus (PEP 456).
"""

from __future__ import annotations

import random

from trivia_bench.ids import option_seed

BOOLEAN_OPTIONS = ("True", "False")


def shuffle_options(
    question_id: str,
    question_type: str,
    correct_answer: str,
    incorrect_answers: list[str],
) -> tuple[list[str], int]:
    """Retourne `(options, index_de_la_bonne_reponse)`.

    Les questions vrai/faux gardent un ordre fixe `True, False` : les melanger n'apporte rien
    puisque les deux options sont connues d'avance et que la reponse est donnee en toutes
    lettres, pas par une lettre d'option.
    """
    if question_type == "boolean":
        options = list(BOOLEAN_OPTIONS)
        return options, options.index(correct_answer)

    options = [*incorrect_answers, correct_answer]
    random.Random(option_seed(question_id)).shuffle(options)
    return options, options.index(correct_answer)
