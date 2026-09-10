"""Boucle de collecte complete des questions OpenTDB.

Strategie (SPEC.md section 6) : un token de session pour tout le run, un dimensionnement des
lots via `api_count.php` pour ne jamais demander plus que le pool disponible, un checkpoint
par categorie pour la reprise, et une deduplication par identifiant deterministe.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from trivia_bench.ids import question_id
from trivia_bench.logging import logger
from trivia_bench.models import RawQuestion
from trivia_bench.paths import DataPaths
from trivia_bench.scrape.checkpoint import Checkpoint
from trivia_bench.scrape.client import Category, OpenTDBClient

CSV_FIELDS = [
    "scraped_at",
    "category_id",
    "category",
    "type",
    "difficulty",
    "question",
    "correct_answer",
    "incorrect_answers",
    "batch_index",
    "result_index",
]


def _existing_ids(csv_path: Path) -> set[str]:
    """Identifiants deja presents dans le CSV bronze (deduplication a la reprise)."""
    if not csv_path.exists():
        return set()
    ids: set[str] = set()
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ids.add(
                question_id(
                    row["category"],
                    row["type"],
                    row["difficulty"],
                    row["question"],
                    row["correct_answer"],
                )
            )
    return ids


def _open_csv(csv_path: Path) -> tuple[Any, csv.DictWriter[str]]:
    """Ouvre le CSV bronze en ajout, en ecrivant l'entete si le fichier est neuf."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not csv_path.exists() or csv_path.stat().st_size == 0
    handle = csv_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
    if is_new:
        writer.writeheader()
    return handle, writer


def scrape_all(
    client: OpenTDBClient,
    paths: DataPaths,
    *,
    token: str | None = None,
    category_ids: list[int] | None = None,
    fresh: bool = False,
    console: Console | None = None,
) -> dict[str, Any]:
    """Telecharge toutes les questions verifiees et alimente la couche bronze.

    Retourne un resume par categorie.
    """
    console = console or Console()
    paths.ensure_dirs()

    if fresh and paths.opentdb_checkpoint.exists():
        paths.opentdb_checkpoint.unlink()

    checkpoint = Checkpoint.load(paths.opentdb_checkpoint)
    checkpoint.token = token or checkpoint.token or client.request_token()
    checkpoint.save(paths.opentdb_checkpoint)
    logger.info("Token de session utilise : {}…", (checkpoint.token or "")[:8])

    categories: list[Category] = client.get_categories()
    if category_ids:
        wanted = set(category_ids)
        categories = [category for category in categories if category.id in wanted]
    logger.info("{} categories a traiter", len(categories))

    seen_ids = _existing_ids(paths.questions_raw_csv)
    if seen_ids:
        logger.info("{} questions deja presentes dans le CSV bronze", len(seen_ids))

    csv_handle, writer = _open_csv(paths.questions_raw_csv)
    responses_handle = paths.opentdb_responses.open("a", encoding="utf-8")
    n_duplicates = 0

    try:
        counts: dict[int, int] = {}
        for category in categories:
            state = checkpoint.state(category.id)
            if state.done:
                counts[category.id] = state.received
                continue
            count = client.get_category_count(category.id)
            state.expected = count.total
            counts[category.id] = count.total
            checkpoint.save(paths.opentdb_checkpoint)

        total_expected = sum(counts.values())
        already = checkpoint.total_received

        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("{task.fields[category]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Scraping", total=total_expected, completed=already, category=""
            )

            for category in categories:
                state = checkpoint.state(category.id)
                progress.update(task, category=category.name[:32])
                if state.done:
                    continue

                while state.received < state.expected:
                    amount = min(client_max_amount(client), state.expected - state.received)
                    code, questions = client.get_questions(
                        amount, category_id=category.id, token=checkpoint.token
                    )
                    responses_handle.write(
                        json.dumps(
                            {
                                "called_at": datetime.now(UTC).isoformat(),
                                "category_id": category.id,
                                "amount": amount,
                                "response_code": code,
                                "n_results": len(questions),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    responses_handle.flush()
                    state.calls += 1

                    if code in (1, 4) or not questions:
                        logger.warning(
                            "Categorie {} ({}) epuisee a {}/{} (response_code={})",
                            category.id,
                            category.name,
                            state.received,
                            state.expected,
                            code,
                        )
                        break

                    now = datetime.now(UTC).isoformat()
                    for index, payload in enumerate(questions):
                        try:
                            question = RawQuestion.model_validate(payload)
                        except ValidationError as exc:
                            logger.warning("Question invalide ignoree : {}", exc.errors()[:1])
                            continue
                        qid = question_id(
                            question.category,
                            question.type,
                            question.difficulty,
                            question.question,
                            question.correct_answer,
                        )
                        if qid in seen_ids:
                            n_duplicates += 1
                            continue
                        seen_ids.add(qid)
                        writer.writerow(
                            {
                                "scraped_at": now,
                                "category_id": category.id,
                                "category": question.category,
                                "type": question.type,
                                "difficulty": question.difficulty,
                                "question": question.question,
                                "correct_answer": question.correct_answer,
                                "incorrect_answers": json.dumps(
                                    question.incorrect_answers, ensure_ascii=False
                                ),
                                "batch_index": state.calls,
                                "result_index": index,
                            }
                        )
                    csv_handle.flush()

                    state.received += len(questions)
                    progress.update(task, completed=checkpoint.total_received)
                    checkpoint.save(paths.opentdb_checkpoint)

                state.done = True
                checkpoint.save(paths.opentdb_checkpoint)
    finally:
        csv_handle.close()
        responses_handle.close()

    summary = {
        "categories": {
            name: checkpoint.categories[str(cid)].model_dump()
            for cid, name in ((category.id, category.name) for category in categories)
            if str(cid) in checkpoint.categories
        },
        "total_received": checkpoint.total_received,
        "n_duplicates": n_duplicates,
        "n_calls": client.n_calls,
        "n_unique": len(seen_ids),
    }

    table = Table(title="Scraping OpenTDB", header_style="bold")
    table.add_column("Categorie")
    table.add_column("Attendu", justify="right")
    table.add_column("Recu", justify="right")
    table.add_column("Appels", justify="right")
    for category in categories:
        state = checkpoint.state(category.id)
        table.add_row(category.name, str(state.expected), str(state.received), str(state.calls))
    table.add_section()
    table.add_row(
        "[bold]Total",
        f"[bold]{sum(checkpoint.state(c.id).expected for c in categories)}",
        f"[bold]{checkpoint.total_received}",
        f"[bold]{client.n_calls}",
    )
    console.print(table)
    console.print(
        f"[dim]Questions uniques ecrites : {len(seen_ids)} · "
        f"doublons ignores : {n_duplicates}[/dim]"
    )
    console.print(
        "[dim]Donnees Open Trivia Database, licence CC BY-SA 4.0 (https://opentdb.com).[/dim]"
    )
    return summary


def client_max_amount(client: OpenTDBClient) -> int:
    """Taille maximale d'un lot (limite dure de l'API)."""
    return getattr(client, "max_amount", 50)
