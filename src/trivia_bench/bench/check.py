"""Verifications prealables a un run de benchmark (`trivia check`).

Rien ne coute plus cher qu'un run de plusieurs heures invalide : ces controles verifient en
quelques secondes que le serveur repond, que le modele est charge avec la configuration
attendue, que le raisonnement est bien desactivable, que les parametres de decodage glouton
sont acceptes et que deux appels identiques donnent la meme reponse.

Un controle vise specifiquement l'invariant qui a motive le choix du transport : la sortie
contrainte doit livrer les memes statistiques moteur que le texte libre. Sans cela, une
variante serait mesuree autrement que les autres et l'ecart observe ne voudrait rien dire.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from trivia_bench.bench.lmstudio import LMStudioClient
from trivia_bench.bench.manifest import lmstudio_version, runtime_engine
from trivia_bench.config import Settings
from trivia_bench.models import LLMRequest

_SYSTEM = "You are a trivia expert. Answer with the letter of the correct option only."
_USER = (
    "Question: Which planet is known as the Red Planet?\n"
    "A) Venus\nB) Jupiter\nC) Mars\nD) Saturn\nAnswer:"
)
_EXPECTED = "C"


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

        # 4. Raisonnement desactivable
        plain = LLMRequest(
            model_key=key, system=_SYSTEM, user=_USER, max_tokens=8, reasoning_mode="off"
        )
        first = client.complete(plain)
        ok_plain = first.error is None and first.reasoning_tokens == 0 and first.content.strip()
        results.append(
            CheckResult(
                "Raisonnement desactive",
                bool(ok_plain),
                f"reponse {first.content.strip()!r} · {first.completion_tokens} tokens · "
                f"{first.reasoning_tokens} token(s) de raisonnement"
                + (f" · erreur : {first.error}" if first.error else ""),
            )
        )

        # 5. Moteur reellement utilise, lu dans la reponse plutot que dans la CLI
        runtime = first.raw.get("runtime") or {}
        model_meta = first.raw.get("model_info") or {}
        results.append(
            CheckResult(
                "Moteur d'inference",
                bool(runtime.get("name")),
                f"{runtime.get('name', '?')} {runtime.get('version', '')} · "
                f"format {model_meta.get('format', '?')} · "
                f"contexte {model_meta.get('context_length', '?')}",
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

        # 8. Sortie structuree, sur le meme transport que le reste
        structured = LLMRequest(
            model_key=key,
            system=_SYSTEM,
            user=_USER,
            max_tokens=24,
            reasoning_mode="off",
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

        # 9. Le point qui a motive le transport unique : la sortie contrainte doit livrer les
        # memes statistiques que le texte libre, sans quoi les variantes ne se comparent pas.
        results.append(
            CheckResult(
                "Statistiques sur sortie contrainte",
                json_response.ttft_s is not None and json_response.tokens_per_second is not None,
                f"TTFT {json_response.ttft_s:.3f} s · {json_response.tokens_per_second:.1f} tok/s"
                if json_response.ttft_s and json_response.tokens_per_second
                else "absentes — les variantes ne seraient pas comparables",
            )
        )

        # 10. Estimation de duree d'un run complet
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
