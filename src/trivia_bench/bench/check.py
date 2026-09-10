"""Verifications prealables a un run de benchmark (`trivia check`).

Rien ne coute plus cher qu'un run de plusieurs heures invalide : ces controles verifient en
quelques secondes que le serveur repond, que le modele est charge avec la configuration
attendue, que le raisonnement est bien desactivable, que les parametres de decodage glouton
sont acceptes et que deux appels identiques donnent la meme reponse.

Deux controles visent des invariants dont depend la validite des comparaisons : la sortie
contrainte doit livrer les memes statistiques moteur que le texte court, sans quoi une
variante serait mesuree autrement que les autres ; et la longueur de contexte appliquee doit
etre celle demandee, faute de quoi deux modeles ne seraient pas compares a configuration egale.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from rich.console import Console
from rich.table import Table

from trivia_bench.bench.grading import grade_answer
from trivia_bench.bench.lmstudio import LMStudioClient
from trivia_bench.bench.manifest import lmstudio_version, runtime_engine
from trivia_bench.config import Settings
from trivia_bench.models import LLMRequest, Question

_SYSTEM = "You are a trivia expert. Answer with the letter of the correct option only."
_USER = (
    "Question: Which planet is known as the Red Planet?\n"
    "A) Venus\nB) Jupiter\nC) Mars\nD) Saturn\nAnswer:"
)
_EXPECTED = "C"

# Marqueurs de tokenizer qui ne devraient jamais apparaitre dans le texte de reponse.
# Un gabarit de chat mal defini les laisse fuiter : avec un budget de 8 tokens, un
# « <|im_end|> » parasite suffit a rendre la reponse inexploitable sur tout un run.
_MARQUEURS = ("<|", "|>", "</s>", "<s>", "[INST]", "[/INST]", "<end_of_turn>", "<eos>")


_QUESTION_TEST = Question(
    question_id="c" * 64,
    category_id=0,
    category="Verification",
    category_group="Verification",
    type="multiple",
    difficulty="easy",
    question="Which planet is known as the Red Planet?",
    correct_answer="Mars",
    incorrect_answers=["Venus", "Jupiter", "Saturn"],
    options=["Venus", "Jupiter", "Mars", "Saturn"],
    correct_index=2,
    correct_letter="C",
    n_options=4,
    question_chars=39,
    question_words=7,
    is_fewshot_example=False,
    scraped_at=datetime(2026, 9, 10, tzinfo=UTC),
)


@dataclass(slots=True)
class CheckResult:
    """Resultat d'un controle unitaire."""

    name: str
    ok: bool
    detail: str


def run_checks(
    settings: Settings,
    *,
    model_key: str | None = None,
    console: Console | None = None,
) -> bool:
    """Execute la serie de controles et affiche un tableau de synthese."""
    console = console or Console()
    key = model_key or settings.lmstudio_model_key
    results: list[CheckResult] = []

    try:
        client = LMStudioClient(settings.lmstudio_base_url, timeout=settings.lmstudio_timeout)
    except Exception as exc:
        console.print(f"[red]Impossible de creer le client : {exc}[/red]")
        return False

    with client:
        # 1. Serveur joignable
        try:
            models = client.list_models()
            results.append(
                CheckResult("Serveur LM Studio", True, f"{len(models)} modele(s) connus")
            )
        except Exception as exc:
            results.append(CheckResult("Serveur LM Studio", False, str(exc)))
            _render(results, console)
            console.print("[yellow]Demarrer le serveur : ~/.lmstudio/bin/lms server start[/yellow]")
            return False

        # 2. Modele present et charge
        info = client.get_model(key)
        if info is None:
            results.append(CheckResult("Modele present", False, f"{key} introuvable"))
            _render(results, console)
            return False
        results.append(
            CheckResult(
                "Modele present",
                True,
                f"{info.display_name or info.key} · {info.quantization} · "
                f"{(info.size_bytes or 0) / 1024**3:.2f} Go",
            )
        )
        results.append(
            CheckResult(
                "Modele charge",
                info.loaded,
                (
                    f"instance {info.instance_identifier} · contexte {info.context_length} · "
                    f"parallel {info.parallel}"
                )
                if info.loaded
                else f"charger avec : lms load {key} --context-length 4096 --parallel 1 -y",
            )
        )
        results.append(
            CheckResult(
                "Parallelisme a 1",
                info.parallel == 1 if info.loaded else False,
                "recharger avec --parallel 1 pour des latences non biaisees"
                if info.parallel != 1
                else "une requete a la fois",
            )
        )

        # 3. Versions
        results.append(
            CheckResult(
                "Versions",
                True,
                f"LM Studio {lmstudio_version() or '?'} · runtime {runtime_engine() or '?'}",
            )
        )

        if not info.loaded:
            _render(results, console)
            return False

        # 4. Raisonnement desactivable, sur l'endpoint des variantes en texte court
        supports_reasoning = bool(info.reasoning_options)
        plain = LLMRequest(
            model_key=key,
            system=_SYSTEM,
            user=_USER,
            max_tokens=8,
            reasoning_mode="off",
            supports_reasoning=supports_reasoning,
        )
        first = client.complete(plain)
        ok_plain = first.error is None and first.reasoning_tokens == 0 and first.content.strip()
        results.append(
            CheckResult(
                "Raisonnement desactive",
                bool(ok_plain),
                (
                    f"reponse {first.content.strip()!r} · {first.completion_tokens} tokens · "
                    f"{first.reasoning_tokens} token(s) de raisonnement"
                    if supports_reasoning
                    else f"reponse {first.content.strip()!r} · {first.completion_tokens} tokens · "
                    "le modele n'expose aucun raisonnement, rien a desactiver"
                )
                + (f" · erreur : {first.error}" if first.error else ""),
            )
        )

        # 5. Format servi et contexte applique, releves sur l'instance elle-meme.
        # Le format decide du moteur d'inference : comparer deux modeles servis par deux
        # moteurs mesurerait le moteur autant que le modele.
        loaded = client.loaded_runtime() or {}
        applique = loaded.get("loaded_context_length")
        results.append(
            CheckResult(
                "Format et contexte servis",
                bool(loaded) and applique == info.context_length,
                f"format {loaded.get('compatibility_type', '?')} · "
                f"contexte applique {applique} · demande {info.context_length}"
                + (
                    "" if applique == info.context_length else " — longueur reecrite par le serveur"
                ),
            )
        )

        # 6. Statistiques de debit sur une reponse texte
        results.append(
            CheckResult(
                "Statistiques moteur",
                first.ttft_s is not None and first.tokens_per_second is not None,
                f"TTFT {first.ttft_s:.3f} s · {first.tokens_per_second:.1f} tok/s"
                if first.ttft_s and first.tokens_per_second
                else "absentes",
            )
        )

        # 7. Determinisme sur trois appels identiques
        answers = [first.content.strip()]
        for _ in range(2):
            answers.append(client.complete(plain).content.strip())
        results.append(
            CheckResult(
                "Determinisme (3 appels)",
                len(set(answers)) == 1,
                " / ".join(answers),
            )
        )
        results.append(
            CheckResult(
                "Reponse attendue",
                answers[0].upper().startswith(_EXPECTED),
                f"attendu {_EXPECTED}, obtenu {answers[0]!r}",
            )
        )

        # La notation reconnait-elle la reponse comme une lettre ? C'est l'invariant dont
        # depend toute la campagne : une reponse juste mais mal reconnue compte comme fausse.
        note = grade_answer(first.content, _QUESTION_TEST)
        results.append(
            CheckResult(
                "Notation de la reponse",
                note.grade == "letter" and note.ai_correct,
                f"grade {note.grade!r} · correct {note.ai_correct}",
            )
        )

        # 8. Sortie structuree : elle exige l'autre endpoint, l'endpoint natif la refusant
        structured = LLMRequest(
            model_key=key,
            system=_SYSTEM,
            user=_USER,
            max_tokens=24,
            reasoning_mode="off",
            supports_reasoning=supports_reasoning,
            json_schema={
                "type": "object",
                "properties": {"answer": {"type": "string", "enum": ["A", "B", "C", "D"]}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        )
        json_response = client.complete(structured)
        ok_json = json_response.error is None and json_response.content.strip().startswith("{")
        results.append(
            CheckResult(
                "Sortie structuree JSON",
                ok_json,
                f"{json_response.content.strip()!r} · {json_response.response_time:.2f} s"
                + (f" · erreur : {json_response.error}" if json_response.error else ""),
            )
        )

        # 9. Invariant des colonnes : la sortie contrainte doit livrer les memes statistiques
        # que le texte court, sans quoi les variantes ne porteraient pas les memes mesures.
        results.append(
            CheckResult(
                "Statistiques sur sortie contrainte",
                json_response.ttft_s is not None and json_response.tokens_per_second is not None,
                f"TTFT {json_response.ttft_s:.3f} s · {json_response.tokens_per_second:.1f} tok/s"
                if json_response.ttft_s and json_response.tokens_per_second
                else "absentes — les variantes ne seraient pas comparables",
            )
        )

        # 10. Un marqueur de tokenizer qui fuit invalide la notation sur tout un run : la
        # reponse cesse d'etre une lettre nue et tombe en « inexploitable ». Le detecter ici
        # coute une seconde, le decouvrir apres coup coute la campagne.
        fuites = sorted({m for m in _MARQUEURS if m in first.content or m in json_response.content})
        results.append(
            CheckResult(
                "Sortie exempte de marqueurs de tokenizer",
                not fuites,
                "aucun marqueur dans le texte de reponse"
                if not fuites
                else f"marqueur(s) {fuites} presents — le gabarit de chat du modele fuit",
            )
        )

        # 11. Estimation de duree d'un run complet
        per_call = max(first.response_time, 0.01)
        results.append(
            CheckResult(
                "Duree estimee (5 257 questions)",
                True,
                f"~{per_call * 5257 / 60:.0f} min par variante a {per_call:.2f} s/question",
            )
        )

    _render(results, console)
    return all(result.ok for result in results)


def _render(results: list[CheckResult], console: Console) -> None:
    table = Table(title="Verification LM Studio", header_style="bold")
    table.add_column("Controle")
    table.add_column("Etat", justify="center")
    table.add_column("Detail")
    for result in results:
        table.add_row(
            result.name,
            "[green]OK[/green]" if result.ok else "[red]ECHEC[/red]",
            result.detail,
        )
    console.print(table)
