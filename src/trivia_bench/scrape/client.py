"""Client HTTP de l'API OpenTDB.

Points de vigilance (verifies le 2026-09-10) :
- la limite est de 1 requete / 5 s / IP, tous endpoints confondus ;
- le statut HTTP reste 200 meme en cas d'erreur applicative : c'est `response_code` qui fait foi ;
- demander plus de questions qu'il n'en reste renvoie un tableau vide (`response_code=1`),
  jamais un resultat partiel ;
- `encode=base64` evite tout probleme d'entites HTML en transit.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from trivia_bench.logging import logger

# Signification des codes applicatifs renvoyes par l'API.
RESPONSE_CODES: dict[int, str] = {
    0: "Success",
    1: "No Results",
    2: "Invalid Parameter",
    3: "Token Not Found",
    4: "Token Empty",
    5: "Rate Limit",
}

_BLOCK_MARKERS = ("Corporate Internet policy violation", "Access Notification")


class OpenTDBError(RuntimeError):
    """Erreur applicative renvoyee par l'API."""

    def __init__(self, code: int, message: str = "") -> None:
        self.code = code
        label = RESPONSE_CODES.get(code, "Unknown")
        super().__init__(f"OpenTDB response_code={code} ({label}) {message}".strip())


class RateLimitedError(OpenTDBError):
    """`response_code=5` : trop de requetes."""

    def __init__(self) -> None:
        super().__init__(5)


class TokenNotFoundError(OpenTDBError):
    """`response_code=3` : token inconnu ou expire."""

    def __init__(self) -> None:
        super().__init__(3)


class InvalidParameterError(OpenTDBError):
    """`response_code=2` : parametre invalide, il s'agit d'un bug applicatif."""

    def __init__(self) -> None:
        super().__init__(2)


class BlockedByNetworkError(RuntimeError):
    """Le reseau intercepte ou bloque l'acces a opentdb.com."""


@dataclass(frozen=True, slots=True)
class Category:
    """Categorie OpenTDB."""

    id: int
    name: str


@dataclass(frozen=True, slots=True)
class CategoryCount:
    """Comptage des questions verifiees d'une categorie."""

    category_id: int
    total: int
    easy: int
    medium: int
    hard: int


def _decode(value: str) -> str:
    """Decode un champ transmis en base64."""
    return base64.b64decode(value).decode("utf-8")


def decode_question(payload: dict[str, Any]) -> dict[str, Any]:
    """Decode tous les champs texte d'une question renvoyee avec `encode=base64`."""
    return {
        "category": _decode(payload["category"]),
        "type": _decode(payload["type"]),
        "difficulty": _decode(payload["difficulty"]),
        "question": _decode(payload["question"]),
        "correct_answer": _decode(payload["correct_answer"]),
        "incorrect_answers": [_decode(item) for item in payload["incorrect_answers"]],
    }


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    logger.warning(
        "Appel OpenTDB en echec (tentative {}) : {} — nouvelle tentative",
        state.attempt_number,
        exc,
    )


class OpenTDBClient:
    """Client synchrone avec limitation de debit globale et reprises automatiques."""

    def __init__(
        self,
        base_url: str = "https://opentdb.com",
        *,
        min_interval: float = 5.2,
        timeout: float = 30.0,
        user_agent: str = "trivia-bench/1.0 (+https://github.com/)",
        client: httpx.Client | None = None,
    ) -> None:
        self.min_interval = min_interval
        self._last_call: float | None = None
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(10.0, read=timeout),
            headers={"User-Agent": user_agent},
            transport=httpx.HTTPTransport(retries=2),
            follow_redirects=True,
        )
        self.n_calls = 0

    def __enter__(self) -> OpenTDBClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _throttle(self) -> None:
        """Garantit `min_interval` secondes entre deux appels, tous endpoints confondus."""
        if self._last_call is None:
            return
        elapsed = time.monotonic() - self._last_call
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @retry(
        stop=stop_after_attempt(6),
        wait=wait_exponential_jitter(initial=5, max=60),
        retry=retry_if_exception_type((httpx.HTTPError, RateLimitedError)),
        before_sleep=_log_retry,
        reraise=True,
    )
    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._throttle()
        response = self._client.get(path, params=params)
        self._last_call = time.monotonic()
        self.n_calls += 1

        text = response.text
        if any(marker in text for marker in _BLOCK_MARKERS) or "<html" in text[:200].lower():
            raise BlockedByNetworkError(
                "opentdb.com semble bloque ou intercepte par le reseau courant "
                "(page HTML recue au lieu du JSON). Relancer depuis un autre reseau."
            )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()

        code = int(payload.get("response_code", 0))
        if code == 5:
            raise RateLimitedError
        if code == 3:
            raise TokenNotFoundError
        if code == 2:
            raise InvalidParameterError
        return payload

    # --- Endpoints ---

    def request_token(self) -> str:
        """Demande un nouveau token de session."""
        payload = self._get("/api_token.php", {"command": "request"})
        token = str(payload["token"])
        logger.info("Nouveau token de session OpenTDB obtenu ({}…)", token[:8])
        return token

    def get_categories(self) -> list[Category]:
        """Liste des categories disponibles."""
        payload = self._get("/api_category.php")
        return [
            Category(id=int(item["id"]), name=str(item["name"]))
            for item in payload["trivia_categories"]
        ]

    def get_category_count(self, category_id: int) -> CategoryCount:
        """Nombre de questions verifiees d'une categorie (= pool interrogeable)."""
        payload = self._get("/api_count.php", {"category": category_id})
        counts = payload["category_question_count"]
        return CategoryCount(
            category_id=int(payload["category_id"]),
            total=int(counts["total_question_count"]),
            easy=int(counts["total_easy_question_count"]),
            medium=int(counts["total_medium_question_count"]),
            hard=int(counts["total_hard_question_count"]),
        )

    def get_questions(
        self,
        amount: int,
        category_id: int | None = None,
        token: str | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Recupere un lot de questions.

        Retourne `(response_code, questions_decodees)`. Les codes 1 et 4 signalent un pool
        epuise pour ce filtre : la liste est alors vide et l'appelant decide de la suite.
        """
        params: dict[str, Any] = {"amount": amount, "encode": "base64"}
        if category_id is not None:
            params["category"] = category_id
        if token:
            params["token"] = token
        payload = self._get("/api.php", params)
        code = int(payload.get("response_code", 0))
        if code in (1, 4):
            return code, []
        return code, [decode_question(item) for item in payload.get("results", [])]
