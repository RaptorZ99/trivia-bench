"""Client de l'API REST locale de LM Studio.

Choix du transport (ADR-04, verifie le 2026-09-10 sur LM Studio 0.4.24) :

- l'endpoint natif `POST /api/v1/chat` accepte `reasoning: "off"`, indispensable avec Gemma 4
  dont le raisonnement est actif par defaut, et renvoie le temps jusqu'au premier token ainsi
  que le debit ; il refuse en revanche `response_format` ;
- l'endpoint compatible OpenAI `POST /v1/chat/completions` accepte la sortie structuree par
  schema JSON, avec `reasoning_effort: "none"` pour desactiver le raisonnement ; il ne renvoie
  pas de statistiques de debit.

Le SDK Python `lmstudio` n'est pas utilise pour l'inference : dans sa derniere version publiee,
il n'expose aucun moyen de desactiver le raisonnement et melange celui-ci au texte de reponse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from trivia_bench.logging import logger
from trivia_bench.models import LLMRequest, LLMResponse


class LMStudioError(RuntimeError):
    """Erreur renvoyee par le serveur LM Studio."""


class ReasoningLeakError(RuntimeError):
    """Le modele a produit des tokens de raisonnement alors qu'il devait etre desactive."""


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Description d'un modele expose par le serveur."""

    key: str
    display_name: str | None
    quantization: str | None
    size_bytes: int | None
    architecture: str | None
    max_context_length: int | None
    loaded: bool
    instance_identifier: str | None
    context_length: int | None
    parallel: int | None
    reasoning_options: list[str]
    raw: dict[str, Any]


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    logger.warning("Appel LM Studio en echec (tentative {}) : {}", state.attempt_number, exc)


class LMStudioClient:
    """Client synchrone, une requete a la fois (mesures de latence non biaisees)."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234",
        *,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(10.0, read=timeout),
            headers={"User-Agent": "trivia-bench/1.0"},
        )

    def __enter__(self) -> LMStudioClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # --- Etat du serveur ---

    def list_models(self) -> list[ModelInfo]:
        """Liste les modeles connus du serveur et leur etat de chargement."""
        response = self._client.get("/api/v1/models")
        response.raise_for_status()
        payload = response.json()
        models: list[ModelInfo] = []
        for item in payload.get("models", []):
            instances = item.get("loaded_instances") or []
            instance = instances[0] if instances else {}
            config = instance.get("config", {}) if isinstance(instance, dict) else {}
            capabilities = item.get("capabilities") or {}
            reasoning = capabilities.get("reasoning") or {}
            models.append(
                ModelInfo(
                    key=str(item.get("key", "")),
                    display_name=item.get("display_name"),
                    quantization=(item.get("quantization") or {}).get("name"),
                    size_bytes=item.get("size_bytes"),
                    architecture=item.get("architecture"),
                    max_context_length=item.get("max_context_length"),
                    loaded=bool(instances),
                    instance_identifier=instance.get("id") if isinstance(instance, dict) else None,
                    context_length=config.get("context_length"),
                    parallel=config.get("parallel"),
                    reasoning_options=list(reasoning.get("allowed_options") or []),
                    raw=item,
                )
            )
        return models

    def get_model(self, model_key: str) -> ModelInfo | None:
        """Retourne les informations d'un modele donne, ou `None` s'il est inconnu."""
        for model in self.list_models():
            if model.key == model_key:
                return model
        return None

    # --- Inference ---

    def complete(self, request: LLMRequest, *, max_retries: int = 3) -> LLMResponse:
        """Envoie une requete et renvoie une reponse normalisee, quel que soit le transport."""
        call = self._complete_openai if request.transport == "openai" else self._complete_native
        started = time.perf_counter()
        attempt = 0

        @retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPError, LMStudioError)),
            before_sleep=_log_retry,
            reraise=True,
        )
        def _call() -> LLMResponse:
            nonlocal attempt
            attempt += 1
            return call(request)

        try:
            response = _call()
        except Exception as exc:
            elapsed = time.perf_counter() - started
            logger.error("Appel abandonne apres {} tentative(s) : {}", attempt, exc)
            return LLMResponse(
                content="",
                response_time=elapsed,
                attempt=attempt,
                error=f"{type(exc).__name__}: {exc}",
            )

        elapsed = time.perf_counter() - started
        if request.reasoning_mode == "off" and response.reasoning_tokens > 0:
            raise ReasoningLeakError(
                "Le modele a produit des tokens de raisonnement alors que le mode est desactive : "
                "verifier le transport et les parametres envoyes."
            )
        return response.model_copy(update={"response_time": elapsed, "attempt": attempt})

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(path, json=body)
        if response.status_code >= 500:
            raise LMStudioError(f"HTTP {response.status_code} : {response.text[:300]}")
        if response.status_code >= 400:
            # Erreur de requete : inutile de retenter, la correction est cote appelant.
            raise ValueError(f"HTTP {response.status_code} : {response.text[:300]}")
        payload: dict[str, Any] = response.json()
        return payload

    def _complete_native(self, request: LLMRequest) -> LLMResponse:
        """Transport natif : reponse texte, statistiques de debit, controle du raisonnement."""
        body: dict[str, Any] = {
            "model": request.model_key,
            "input": request.user,
            "reasoning": request.reasoning_mode,
            "temperature": 0,
            "top_k": 1,
            "top_p": 1.0,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
            "max_output_tokens": request.max_tokens,
            "store": False,
        }
        if request.system:
            body["system_prompt"] = request.system

        payload = self._post("/api/v1/chat", body)
        stats = payload.get("stats") or {}
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        for item in payload.get("output", []):
            kind = item.get("type")
            text = str(item.get("content", ""))
            if kind == "message":
                content_parts.append(text)
            elif kind == "reasoning":
                reasoning_parts.append(text)

        return LLMResponse(
            content="".join(content_parts),
            reasoning="".join(reasoning_parts) or None,
            prompt_tokens=int(stats.get("input_tokens") or 0),
            completion_tokens=int(stats.get("total_output_tokens") or 0),
            reasoning_tokens=int(stats.get("reasoning_output_tokens") or 0),
            tokens_per_second=stats.get("tokens_per_second"),
            ttft_s=stats.get("time_to_first_token_seconds"),
            finish_reason=payload.get("finish_reason"),
            raw=payload,
        )

    def _complete_openai(self, request: LLMRequest) -> LLMResponse:
        """Transport compatible OpenAI : necessaire pour la sortie structuree."""
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.user})

        body: dict[str, Any] = {
            "model": request.model_key,
            "messages": messages,
            "temperature": 0,
            "top_p": 1.0,
            "top_k": 1,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
            "max_tokens": request.max_tokens,
        }
        if request.reasoning_mode == "off":
            body["reasoning_effort"] = "none"
        if request.json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "trivia_answer",
                    "strict": True,
                    "schema": request.json_schema,
                },
            }

        payload = self._post("/v1/chat/completions", body)
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = payload.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}

        return LLMResponse(
            content=str(message.get("content") or ""),
            reasoning=message.get("reasoning_content") or None,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            reasoning_tokens=int(details.get("reasoning_tokens") or 0),
            tokens_per_second=None,
            ttft_s=None,
            finish_reason=choice.get("finish_reason"),
            raw=payload,
        )
