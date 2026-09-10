"""Interface en ligne de commande du pipeline.

Les imports lourds (polars, duckdb, dbt, httpx) sont faits dans les commandes pour garder
`trivia --help` instantane.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from trivia_bench import __version__

app = typer.Typer(
    help="trivia-bench : scraping OpenTDB, benchmark d'un LLM local, couche gold dbt, dashboard.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"trivia-bench {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Version."),
    ] = False,
) -> None:
    """Pipeline de benchmark de LLM sur les questions Open Trivia Database."""


@app.command()
def scrape(
    categories: Annotated[
        str | None,
        typer.Option("--categories", help="IDs de categories separes par des virgules."),
    ] = None,
    fresh: Annotated[
        bool, typer.Option("--fresh", help="Ignore le checkpoint et repart de zero.")
    ] = False,
    min_interval: Annotated[
        float | None, typer.Option("--min-interval", help="Secondes entre deux appels API.")
    ] = None,
) -> None:
    """Telecharge toutes les questions verifiees d'OpenTDB vers la couche bronze."""
    from rich.console import Console

    from trivia_bench.config import get_settings
    from trivia_bench.logging import logger, setup_logging
    from trivia_bench.paths import DataPaths
    from trivia_bench.scrape import BlockedByNetworkError, OpenTDBClient, scrape_all

    setup_logging("scrape", log_dir=Path("logs"))
    settings = get_settings()
    paths = DataPaths(settings.data_dir)
    console = Console()

    category_ids = [int(part) for part in categories.split(",")] if categories else None
    client = OpenTDBClient(
        settings.opentdb_base_url,
        min_interval=min_interval or settings.opentdb_min_interval,
    )
    try:
        with client:
            scrape_all(
                client,
                paths,
                token=settings.opentdb_session_token,
                category_ids=category_ids,
                fresh=fresh,
                console=console,
            )
    except BlockedByNetworkError as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=2) from exc


@app.command(name="clean")
def clean_command(
    source: Annotated[Path | None, typer.Option("--in", help="CSV bronze.")] = None,
    destination: Annotated[Path | None, typer.Option("--out", help="Parquet silver.")] = None,
) -> None:
    """Nettoie la couche bronze et produit `data/silver/questions.parquet`."""
    from rich.console import Console

    from trivia_bench.clean.builder import build_questions
    from trivia_bench.config import get_settings
    from trivia_bench.logging import setup_logging
    from trivia_bench.paths import DataPaths

    setup_logging("clean")
    settings = get_settings()
    paths = DataPaths(settings.data_dir)
    build_questions(
        source or paths.questions_raw_csv,
        destination or paths.questions_parquet,
        console=Console(),
    )


@app.command()
def check(
    model: Annotated[str | None, typer.Option("--model", help="Cle du modele a verifier.")] = None,
) -> None:
    """Verifie LM Studio : serveur, modele charge, raisonnement, parametres, determinisme."""
    from rich.console import Console

    from trivia_bench.bench.check import run_checks
    from trivia_bench.config import get_settings
    from trivia_bench.logging import setup_logging

    setup_logging("check")
    settings = get_settings()
    ok = run_checks(settings, model_key=model, console=Console())
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def bench(
    variant: Annotated[
        str | None, typer.Option("--variant", help="Identifiant de variante de prompt.")
    ] = None,
    all_variants: Annotated[
        bool, typer.Option("--all-variants", help="Enchaine les cinq variantes.")
    ] = False,
    model: Annotated[str | None, typer.Option("--model", help="Cle du modele LM Studio.")] = None,
    reasoning: Annotated[
        str, typer.Option("--reasoning", help="Mode de raisonnement : off ou on.")
    ] = "off",
    limit: Annotated[
        int | None, typer.Option("--limit", help="Limite le nombre de questions.")
    ] = None,
    sample: Annotated[
        str | None,
        typer.Option("--sample", help="Echantillon, par exemple 'stratified:400'."),
    ] = None,
    resume: Annotated[
        str | None, typer.Option("--resume", help="Identifiant de run a reprendre.")
    ] = None,
    max_tokens: Annotated[
        int | None, typer.Option("--max-tokens", help="Surcharge la longueur maximale.")
    ] = None,
) -> None:
    """Interroge le modele pour chaque question et ecrit les reponses brutes en bronze."""
    from rich.console import Console

    from trivia_bench.bench.prompts import PROMPT_VARIANTS, VARIANT_ORDER
    from trivia_bench.bench.runner import run_benchmark
    from trivia_bench.config import get_settings
    from trivia_bench.logging import setup_logging
    from trivia_bench.paths import DataPaths

    if not variant and not all_variants:
        typer.echo("Preciser --variant <id> ou --all-variants.", err=True)
        raise typer.Exit(code=1)
    if reasoning not in ("off", "on"):
        typer.echo("--reasoning attend 'off' ou 'on'.", err=True)
        raise typer.Exit(code=1)

    setup_logging("bench", log_dir=Path("logs"))
    settings = get_settings()
    paths = DataPaths(settings.data_dir)
    console = Console()

    variants = list(VARIANT_ORDER) if all_variants else [variant or ""]
    for name in variants:
        if name not in PROMPT_VARIANTS:
            typer.echo(f"Variante inconnue : {name}", err=True)
            raise typer.Exit(code=1)
        run_benchmark(
            settings=settings,
            paths=paths,
            variant_id=name,
            model_key=model or settings.lmstudio_model_key,
            reasoning_mode=reasoning,  # type: ignore[arg-type]
            limit=limit,
            sample=sample,
            resume=resume,
            max_tokens=max_tokens,
            console=console,
        )


@app.command()
def grade(
    run_id: Annotated[str | None, typer.Option("--run-id", help="Run a noter.")] = None,
    all_runs: Annotated[bool, typer.Option("--all", help="Note tous les runs.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Recalcule meme si deja note.")] = False,
) -> None:
    """Note les reponses brutes et ecrit la couche silver (`answers/`, `runs.parquet`)."""
    from rich.console import Console

    from trivia_bench.bench.silver import grade_runs
    from trivia_bench.config import get_settings
    from trivia_bench.logging import setup_logging
    from trivia_bench.paths import DataPaths

    if not run_id and not all_runs:
        typer.echo("Preciser --run-id <id> ou --all.", err=True)
        raise typer.Exit(code=1)

    setup_logging("grade")
    settings = get_settings()
    paths = DataPaths(settings.data_dir)
    grade_runs(
        settings=settings,
        paths=paths,
        run_id=run_id,
        force=force,
        console=Console(),
    )


@app.command()
def build(
    full_refresh: Annotated[
        bool, typer.Option("--full-refresh", help="Reconstruit tous les modeles.")
    ] = False,
    select: Annotated[str | None, typer.Option("--select", help="Selecteur dbt.")] = None,
) -> None:
    """Construit la couche gold avec dbt (schemas `staging` et `gold` dans DuckDB)."""
    from rich.console import Console

    from trivia_bench.build.dbt import run_dbt_build
    from trivia_bench.config import get_settings
    from trivia_bench.logging import setup_logging

    setup_logging("build")
    settings = get_settings()
    ok = run_dbt_build(settings, full_refresh=full_refresh, select=select, console=Console())
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def prompt(
    variant: Annotated[str, typer.Option("--variant", help="Identifiant de variante.")],
    question_id_arg: Annotated[
        str | None, typer.Option("--question-id", help="Question a rendre.")
    ] = None,
    question_type: Annotated[
        str, typer.Option("--type", help="Type si aucune question n'est fournie.")
    ] = "multiple",
) -> None:
    """Affiche le prompt rendu pour une variante (debogage et documentation)."""
    from rich.console import Console

    from trivia_bench.bench.preview import preview_prompt
    from trivia_bench.config import get_settings
    from trivia_bench.paths import DataPaths

    settings = get_settings()
    preview_prompt(
        DataPaths(settings.data_dir),
        variant_id=variant,
        question_id=question_id_arg,
        question_type=question_type,
        console=Console(),
    )


@app.command()
def dashboard(
    port: Annotated[int, typer.Option("--port", help="Port d'ecoute.")] = 8501,
) -> None:
    """Lance le dashboard Streamlit."""
    import subprocess
    import sys

    raise typer.Exit(
        subprocess.call(
            [sys.executable, "-m", "streamlit", "run", "app/app.py", "--server.port", str(port)]
        )
    )


if __name__ == "__main__":
    app()
