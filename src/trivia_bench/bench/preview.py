"""Affichage d'un prompt rendu (`trivia prompt`), pour le debogage et la documentation."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from trivia_bench.bench.dataset import fewshot_examples, load_questions
from trivia_bench.bench.prompts import PROMPT_VARIANTS, render_prompt
from trivia_bench.paths import DataPaths


def preview_prompt(
    paths: DataPaths,
    *,
    variant_id: str,
    question_id: str | None = None,
    question_type: str = "multiple",
    console: Console | None = None,
) -> None:
    """Affiche le prompt systeme et le prompt utilisateur pour une question donnee."""
    console = console or Console()
    if variant_id not in PROMPT_VARIANTS:
        console.print(f"[red]Variante inconnue : {variant_id}[/red]")
        return

    variant = PROMPT_VARIANTS[variant_id]
    questions = load_questions(paths.questions_parquet)

    if question_id:
        selected = next((q for q in questions if q.question_id.startswith(question_id)), None)
        if selected is None:
            console.print(f"[red]Question introuvable : {question_id}[/red]")
            return
    else:
        selected = next(
            (q for q in questions if q.type == question_type and not q.is_fewshot_example),
            questions[0],
        )

    system, user = render_prompt(
        variant, selected, fewshot=fewshot_examples(questions, selected.type)
    )

    console.print(f"[bold]{variant.label}[/bold] · question [dim]{selected.question_id[:12]}[/dim]")
    console.print(f"[dim]{variant.description}[/dim]\n")
    if system:
        console.print(Panel(system, title="Prompt systeme", border_style="cyan"))
    console.print(Panel(user, title="Prompt utilisateur", border_style="green"))
    console.print(
        f"[dim]Bonne reponse : {selected.correct_letter}) {selected.correct_answer} · "
        f"longueur maximale : {variant.max_tokens[selected.type]} tokens[/dim]"
    )
