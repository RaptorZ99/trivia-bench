"""Variantes de prompt evaluees par le benchmark (SPEC.md section 8.2).

Chaque variante isole un mecanisme different :

- `v1_open`   : connaissance brute, sans options affichees (rappel actif) ;
- `v2_letter` : conformite de format sur instruction nue, avec options (reconnaissance) ;
- `v3_simple_evals` : cadrage systeme et contrat de sortie explicite, convention OpenAI
  simple-evals, sans la clause de raisonnement pas a pas ;
- `v4_fewshot` : demonstration du format par deux exemples fixes ;
- `v5_json`   : decodage contraint par schema JSON, format garanti parsable.

Les gabarits sont des fichiers texte versionnes (`prompts/*.txt`) : leur empreinte est
enregistree avec chaque reponse, ce qui rend la formulation du prompt tracable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from trivia_bench.ids import prompt_hash
from trivia_bench.models import LETTERS, LLMRequest, Question, QuestionType

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@cache
def prompt_version() -> str:
    """Version des gabarits, enregistree dans chaque reponse."""
    return (PROMPTS_DIR / "VERSION").read_text(encoding="utf-8").strip()


@cache
def _template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _json_schema(question_type: QuestionType) -> dict[str, Any]:
    """Schema de sortie structuree pour la variante `v5_json`."""
    values = list(LETTERS) if question_type == "multiple" else ["True", "False"]
    return {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": values}},
        "required": ["answer"],
        "additionalProperties": False,
    }


@dataclass(frozen=True, slots=True)
class PromptVariant:
    """Definition d'une variante de prompt."""

    id: str
    label: str
    description: str
    max_tokens: dict[QuestionType, int]
    has_system: bool = False
    use_fewshot: bool = False
    structured: bool = False
    expects_letter: bool = True
    answer_cue: bool = False
    order: int = 0
    aliases: tuple[str, ...] = field(default=())

    def system_prompt(self) -> str | None:
        """Prompt systeme de la variante, ou `None` si elle n'en a pas."""
        if not self.has_system:
            return None
        return _template(f"{self.id}.system.txt")

    def user_template(self, question_type: QuestionType) -> str:
        """Gabarit du tour utilisateur pour un type de question."""
        return _template(f"{self.id}.{question_type}.txt")

    def json_schema(self, question_type: QuestionType) -> dict[str, Any] | None:
        """Schema JSON impose, le cas echeant."""
        return _json_schema(question_type) if self.structured else None


PROMPT_VARIANTS: dict[str, PromptVariant] = {
    variant.id: variant
    for variant in (
        PromptVariant(
            id="v1_open",
            label="V1 · Question ouverte",
            description=(
                "La question seule, sans options ni consigne de format. Mesure la connaissance "
                "en rappel actif, sans la bequille de la reconnaissance parmi des propositions."
            ),
            # Seule variante ou le modele repond en toutes lettres, souvent en placant le mot
            # cle en fin de phrase. Un budget trop court couperait la reponse avant lui et la
            # ferait passer pour fausse. Le budget n'est consomme que si le modele l'utilise :
            # l'elargir ne coute rien sur les reponses breves.
            max_tokens={"multiple": 160, "boolean": 160},
            expects_letter=False,
            order=1,
        ),
        PromptVariant(
            id="v2_letter",
            label="V2 · Lettre seule",
            description=(
                "Les quatre options et une consigne nue : repondre par la lettre uniquement. "
                "Mesure la conformite de format sans cadrage supplementaire."
            ),
            max_tokens={"multiple": 8, "boolean": 8},
            order=2,
        ),
        PromptVariant(
            id="v3_simple_evals",
            label="V3 · Contrat de sortie",
            description=(
                "Prompt systeme de cadrage et contrat de sortie explicite se terminant par "
                "'Answer: X', convention du harnais OpenAI simple-evals."
            ),
            max_tokens={"multiple": 64, "boolean": 64},
            has_system=True,
            answer_cue=True,
            order=3,
        ),
        PromptVariant(
            id="v4_fewshot",
            label="V4 · Few-shot",
            description=(
                "Deux exemples resolus avant la question cible : le format est demontre plutot "
                "qu'explique. Les exemples sont fixes et exclus du jeu evalue."
            ),
            max_tokens={"multiple": 8, "boolean": 8},
            use_fewshot=True,
            answer_cue=True,
            order=4,
        ),
        PromptVariant(
            id="v5_json",
            label="V5 · JSON contraint",
            description=(
                "Sortie contrainte par un schema JSON : le format est garanti par le decodage, "
                "ce qui isole l'effet de la contrainte sur l'exactitude."
            ),
            max_tokens={"multiple": 24, "boolean": 24},
            has_system=True,
            structured=True,
            order=5,
        ),
    )
}

VARIANT_ORDER: list[str] = sorted(PROMPT_VARIANTS, key=lambda key: PROMPT_VARIANTS[key].order)


def format_fewshot_block(examples: list[Question]) -> str:
    """Met en forme les exemples few-shot dans le meme format que la question cible."""
    blocks: list[str] = []
    for example in examples:
        if example.type == "multiple":
            lines = [f"Question: {example.question}"]
            lines += [f"{LETTERS[index]}) {option}" for index, option in enumerate(example.options)]
            lines.append(f"Answer: {example.correct_letter}")
        else:
            lines = [
                f"Statement: {example.question}",
                f"Answer: {example.correct_answer}",
            ]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_prompt(
    variant: PromptVariant,
    question: Question,
    *,
    fewshot: list[Question] | None = None,
) -> tuple[str | None, str]:
    """Rend le couple `(prompt systeme, prompt utilisateur)` pour une question."""
    template = variant.user_template(question.type)
    values: dict[str, str] = {"question": question.question}

    if question.type == "multiple":
        for index, option in enumerate(question.options):
            values[LETTERS[index]] = option

    if variant.use_fewshot:
        if not fewshot:
            raise ValueError(f"La variante {variant.id} exige des exemples few-shot")
        values["examples"] = format_fewshot_block(fewshot)

    return variant.system_prompt(), template.format(**values)


def render_request(
    variant: PromptVariant,
    question: Question,
    *,
    model_key: str,
    reasoning_mode: str = "off",
    fewshot: list[Question] | None = None,
    max_tokens: int | None = None,
) -> tuple[LLMRequest, str]:
    """Construit la requete LM Studio et l'empreinte du prompt rendu."""
    system, user = render_prompt(variant, question, fewshot=fewshot)
    request = LLMRequest(
        model_key=model_key,
        system=system,
        user=user,
        max_tokens=max_tokens or variant.max_tokens[question.type],
        reasoning_mode=reasoning_mode,  # type: ignore[arg-type]
        json_schema=variant.json_schema(question.type),
    )
    return request, prompt_hash(system, user)
