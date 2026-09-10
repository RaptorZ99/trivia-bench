"""Modeles de donnees valides par pydantic."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

QuestionType = Literal["multiple", "boolean"]
Difficulty = Literal["easy", "medium", "hard"]
Grade = Literal["letter", "exact", "fuzzy", "contains", "wrong", "unparseable", "error"]
ReasoningMode = Literal["off", "on"]
Transport = Literal["native", "openai"]

LETTERS = "ABCD"


class RawQuestion(BaseModel):
    """Question telle que renvoyee par l'API OpenTDB, apres decodage base64."""

    model_config = ConfigDict(frozen=True)

    category: str = Field(min_length=1)
    type: QuestionType
    difficulty: Difficulty
    question: str = Field(min_length=1)
    correct_answer: str = Field(min_length=1)
    incorrect_answers: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_answers(self) -> Self:
        if self.correct_answer in self.incorrect_answers:
            raise ValueError("correct_answer ne doit pas figurer dans incorrect_answers")
        expected = 3 if self.type == "multiple" else 1
        if len(self.incorrect_answers) != expected:
            raise ValueError(
                f"type={self.type} attend {expected} mauvaise(s) reponse(s), "
                f"recu {len(self.incorrect_answers)}"
            )
        if self.type == "boolean" and self.correct_answer not in {"True", "False"}:
            raise ValueError("une question boolean attend correct_answer dans {True, False}")
        return self


class Question(BaseModel):
    """Question nettoyee de la couche silver, avec ordre des options fige."""

    model_config = ConfigDict(frozen=True)

    question_id: str = Field(min_length=64, max_length=64)
    category_id: int = Field(ge=0)
    category: str = Field(min_length=1)
    category_group: str = Field(min_length=1)
    type: QuestionType
    difficulty: Difficulty
    question: str = Field(min_length=1)
    correct_answer: str = Field(min_length=1)
    incorrect_answers: list[str] = Field(min_length=1)
    options: list[str] = Field(min_length=2)
    correct_index: int = Field(ge=0)
    correct_letter: str = Field(min_length=1, max_length=1)
    n_options: int = Field(ge=2, le=4)
    question_chars: int = Field(ge=1)
    question_words: int = Field(ge=1)
    is_fewshot_example: bool = False
    scraped_at: datetime

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if len(self.options) != self.n_options:
            raise ValueError("n_options doit correspondre a la longueur de options")
        if not 0 <= self.correct_index < self.n_options:
            raise ValueError("correct_index hors bornes")
        if self.options[self.correct_index] != self.correct_answer:
            raise ValueError("options[correct_index] doit valoir correct_answer")
        if self.correct_letter != LETTERS[self.correct_index]:
            raise ValueError("correct_letter incoherent avec correct_index")
        return self


class LLMRequest(BaseModel):
    """Requete preparee pour LM Studio."""

    model_config = ConfigDict(frozen=True)

    model_key: str
    system: str | None
    user: str
    max_tokens: int = Field(gt=0)
    reasoning_mode: ReasoningMode = "off"
    json_schema: dict[str, Any] | None = None

    @property
    def transport(self) -> Transport:
        """L'endpoint natif ne supporte pas la sortie structuree (verifie le 2026-09-10)."""
        return "openai" if self.json_schema is not None else "native"


class LLMResponse(BaseModel):
    """Reponse normalisee, quel que soit le transport utilise."""

    model_config = ConfigDict(frozen=True)

    content: str
    reasoning: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    tokens_per_second: float | None = None
    ttft_s: float | None = None
    finish_reason: str | None = None
    response_time: float = 0.0
    attempt: int = 1
    error: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RunManifest(BaseModel):
    """Description complete d'un run de benchmark (reproductibilite)."""

    run_id: str
    model_key: str
    model_display_name: str | None = None
    model_quant: str | None = None
    model_size_bytes: int | None = None
    instance_identifier: str | None = None
    context_length: int | None = None
    parallel: int | None = None
    prompt_variant: str
    variant_label: str = ""
    prompt_version: str
    reasoning_mode: ReasoningMode
    transport: Transport
    generation_params: dict[str, Any]
    lmstudio_version: str | None = None
    runtime_engine: str | None = None
    python_version: str
    package_version: str
    git_sha: str | None = None
    dataset_sha256: str | None = None
    sample_spec: str = "all"
    sample_question_ids: list[str] | None = None
    n_questions_planned: int = 0
    n_questions_done: int = 0
    n_errors: int = 0
    warmup_time_s: float | None = None
    # Configuration de l'instance relue en fin de run : LM Studio peut recharger un modele
    # avec ses reglages par defaut si l'instance est evincee (chargement d'un autre modele,
    # expiration du TTL). Comparer debut et fin rend cette derive visible.
    context_length_end: int | None = None
    parallel_end: int | None = None
    instance_identifier_end: str | None = None
    config_changed: bool = False
    machine: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["running", "partial", "complete"] = "running"
