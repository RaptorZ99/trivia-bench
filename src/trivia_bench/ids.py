"""Identifiants deterministes et empreintes.

OpenTDB ne fournit aucun identifiant de question : on en derive un par hachage stable du
contenu (ADR-08). `hashlib` est utilise plutot que `hash()`, randomise par processus (PEP 456).
"""

from __future__ import annotations

import hashlib
import html
from pathlib import Path

_SEED_MODULUS = 2**32


def normalize_key(value: str) -> str:
    """Normalise une chaine pour le calcul d'identifiant : entites HTML, espaces, casse."""
    return " ".join(html.unescape(value).split()).casefold()


def question_id(
    category: str,
    qtype: str,
    difficulty: str,
    question: str,
    correct_answer: str,
) -> str:
    """Identifiant stable d'une question (sha256 hexadecimal, 64 caracteres).

    Les mauvaises reponses n'entrent pas dans le hachage : leur ordre n'est pas garanti
    d'un appel API a l'autre.
    """
    key = "||".join(
        normalize_key(part) for part in (category, qtype, difficulty, question, correct_answer)
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def option_seed(qid: str) -> int:
    """Graine deterministe pour melanger les options d'une question."""
    return int(hashlib.sha256(qid.encode("utf-8")).hexdigest(), 16) % _SEED_MODULUS


def prompt_hash(system: str | None, user: str) -> str:
    """Empreinte du prompt effectivement envoye (systeme + utilisateur)."""
    payload = f"{system or ''}\x00{user}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    """Empreinte d'un fichier, lue par blocs."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
