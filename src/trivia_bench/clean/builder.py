"""Construction de `data/silver/questions.parquet` a partir du CSV bronze."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import polars as pl
from rich.console import Console
from rich.table import Table

from trivia_bench.clean.normalize import category_group, clean_text
from trivia_bench.clean.shuffle import shuffle_options
from trivia_bench.ids import question_id
from trivia_bench.logging import logger
from trivia_bench.models import LETTERS, Question

DIFFICULTY = pl.Enum(["easy", "medium", "hard"])
QUESTION_TYPE = pl.Enum(["multiple", "boolean"])

SILVER_SCHEMA: dict[str, pl.DataType] = {
    "question_id": pl.String(),
    "category_id": pl.Int16(),
    "category": pl.String(),
    "category_group": pl.String(),
    "type": QUESTION_TYPE,
    "difficulty": DIFFICULTY,
    "question": pl.String(),
    "correct_answer": pl.String(),
    "incorrect_answers": pl.List(pl.String()),
    "options": pl.List(pl.String()),
    "correct_index": pl.Int8(),
    "correct_letter": pl.String(),
    "n_options": pl.Int8(),
    "question_chars": pl.Int32(),
    "question_words": pl.Int32(),
    "is_fewshot_example": pl.Boolean(),
    "scraped_at": pl.Datetime(time_zone="UTC"),
}

FEWSHOT_CATEGORY = "General Knowledge"
FEWSHOT_PER_TYPE = 2


def _select_fewshot_ids(rows: list[dict[str, object]]) -> dict[str, list[str]]:
    """Choisit les exemples few-shot : les premiers identifiants de la categorie generale.

    La selection est une fonction pure du jeu de donnees (identifiants tries, donc stables d'une
    reconstruction a l'autre), et le resultat est persiste dans la colonne `is_fewshot_example`
    de la couche silver : aucun fichier d'etat supplementaire n'est necessaire.
    """
    selected: dict[str, list[str]] = {}
    for qtype in ("multiple", "boolean"):
        candidates = sorted(
            str(row["question_id"])
            for row in rows
            if row["type"] == qtype and row["category"] == FEWSHOT_CATEGORY
        )
        if not candidates:
            # Jeu de donnees restreint (tests, sous-ensemble) : on retombe sur le type demande.
            candidates = sorted(str(row["question_id"]) for row in rows if row["type"] == qtype)
        selected[qtype] = candidates[:FEWSHOT_PER_TYPE]
    return selected


def build_questions(
    source: Path,
    destination: Path,
    *,
    console: Console | None = None,
) -> pl.DataFrame:
    """Nettoie, valide et enrichit les questions brutes, puis ecrit le Parquet silver."""
    console = console or Console()
    if not source.exists():
        raise FileNotFoundError(f"CSV bronze introuvable : {source}")

    raw = pl.read_csv(
        source,
        schema_overrides={
            "scraped_at": pl.String(),
            "category_id": pl.Int16(),
            "category": pl.String(),
            "type": pl.String(),
            "difficulty": pl.String(),
            "question": pl.String(),
            "correct_answer": pl.String(),
            "incorrect_answers": pl.String(),
        },
    )
    logger.info("{} lignes lues depuis {}", raw.height, source)

    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    n_duplicates = 0

    for record in raw.iter_rows(named=True):
        category = clean_text(str(record["category"]))
        question_text = clean_text(str(record["question"]))
        correct = clean_text(str(record["correct_answer"]))
        incorrect = [clean_text(item) for item in json.loads(str(record["incorrect_answers"]))]
        qtype = str(record["type"])
        difficulty = str(record["difficulty"])

        qid = question_id(category, qtype, difficulty, question_text, correct)
        if qid in seen:
            n_duplicates += 1
            continue
        seen.add(qid)

        options, correct_index = shuffle_options(qid, qtype, correct, incorrect)
        rows.append(
            {
                "question_id": qid,
                "category_id": int(record["category_id"]),
                "category": category,
                "category_group": category_group(category),
                "type": qtype,
                "difficulty": difficulty,
                "question": question_text,
                "correct_answer": correct,
                "incorrect_answers": incorrect,
                "options": options,
                "correct_index": correct_index,
                "correct_letter": LETTERS[correct_index],
                "n_options": len(options),
                "question_chars": len(question_text),
                "question_words": len(question_text.split()),
                "is_fewshot_example": False,
                "scraped_at": datetime.fromisoformat(str(record["scraped_at"])),
            }
        )

    fewshot = _select_fewshot_ids(rows)
    fewshot_ids = {qid for ids in fewshot.values() for qid in ids}
    for row in rows:
        row["is_fewshot_example"] = row["question_id"] in fewshot_ids

    for row in rows:
        Question.model_validate(row)

    frame = pl.DataFrame(rows, schema=SILVER_SCHEMA)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(destination, compression="zstd", statistics=True)
    logger.info("{} questions ecrites dans {}", frame.height, destination)

    _print_summary(frame, console, n_duplicates=n_duplicates)
    return frame


def _print_summary(frame: pl.DataFrame, console: Console, *, n_duplicates: int) -> None:
    """Affiche un resume par categorie, type et difficulte."""
    table = Table(title="Couche silver — questions", header_style="bold")
    table.add_column("Categorie")
    table.add_column("Total", justify="right")
    table.add_column("QCM", justify="right")
    table.add_column("Vrai/Faux", justify="right")
    table.add_column("Facile", justify="right")
    table.add_column("Moyen", justify="right")
    table.add_column("Difficile", justify="right")

    grouped = (
        frame.group_by("category")
        .agg(
            pl.len().alias("total"),
            (pl.col("type") == "multiple").sum().alias("multiple"),
            (pl.col("type") == "boolean").sum().alias("boolean"),
            (pl.col("difficulty") == "easy").sum().alias("easy"),
            (pl.col("difficulty") == "medium").sum().alias("medium"),
            (pl.col("difficulty") == "hard").sum().alias("hard"),
        )
        .sort("category")
    )
    for row in grouped.iter_rows(named=True):
        table.add_row(
            str(row["category"]),
            str(row["total"]),
            str(row["multiple"]),
            str(row["boolean"]),
            str(row["easy"]),
            str(row["medium"]),
            str(row["hard"]),
        )
    table.add_section()
    table.add_row(
        "[bold]Total",
        f"[bold]{frame.height}",
        f"[bold]{(frame['type'] == 'multiple').sum()}",
        f"[bold]{(frame['type'] == 'boolean').sum()}",
        f"[bold]{(frame['difficulty'] == 'easy').sum()}",
        f"[bold]{(frame['difficulty'] == 'medium').sum()}",
        f"[bold]{(frame['difficulty'] == 'hard').sum()}",
    )
    console.print(table)
    console.print(
        f"[dim]Doublons ignores : {n_duplicates} · exemples few-shot reserves : "
        f"{int(frame['is_fewshot_example'].sum())}[/dim]"
    )
