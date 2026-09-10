"""Normalisation des textes de questions et de reponses.

`normalize_answer` est un sur-ensemble de la normalisation canonique de SQuAD : elle ajoute le
decodage des entites HTML (present dans les donnees OpenTDB) et la suppression des accents.
Elle retire aussi la mise en forme Markdown que les modeles produisent spontanement
(par exemple `**Leonardo da Vinci**`), puisque la ponctuation devient un espace.
"""

from __future__ import annotations

import html
import re
import unicodedata

_ARTICLES = frozenset({"a", "an", "the"})
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def clean_text(value: str) -> str:
    """Nettoyage d'affichage : entites HTML decodees, espaces normalises."""
    return " ".join(html.unescape(value).split()).strip()


def strip_accents(value: str) -> str:
    """Retire les diacritiques par decomposition NFKD."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_answer(value: str) -> str:
    """Normalise une reponse pour la comparaison (casse, accents, ponctuation, articles)."""
    text = html.unescape(value)
    text = strip_accents(text)
    text = text.casefold()
    text = _PUNCTUATION.sub(" ", text)
    tokens = [token for token in text.split() if token not in _ARTICLES]
    return " ".join(tokens)


def category_group(category: str) -> str:
    """Famille d'une categorie OpenTDB (`Entertainment: Film` donne `Entertainment`)."""
    head, separator, _ = category.partition(":")
    return head.strip() if separator else category.strip()
