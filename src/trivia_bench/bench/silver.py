"""Passage de la couche bronze (JSONL bruts) a la couche silver (Parquet notes).

La notation est refaite integralement a chaque appel : elle est deterministe et rapide, ce qui
permet de faire evoluer les regles de notation sans reinterroger le modele.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
from rich.console import Console
from rich.table import Table

from trivia_bench.bench.grading import grade_answer
from trivia_bench.bench.manifest import load_manifest
from trivia_bench.bench.prompts import PROMPT_VARIANTS
from trivia_bench.config import Settings
from trivia_bench.logging import logger
from trivia_bench.models import Question
from trivia_bench.paths import DataPaths

GRADE_ENUM = pl.Enum(["letter", "exact", "fuzzy", "contains", "wrong", "unparseable", "error"])
VARIANT_ENUM = pl.Enum(list(PROMPT_VARIANTS))
REASONING_ENUM = pl.Enum(["off", "on"])
# Une valeur absente de l'enumeration est convertie en nul sans erreur : elle doit donc
# lister tous les endpoints ayant servi un run, pas seulement celui du dernier.
TRANSPORT_ENUM = pl.Enum(["native", "api_v0"])

ANSWERS_SCHEMA: dict[str, pl.DataType] = {
    "run_id": pl.String(),
    "question_id": pl.String(),
    "model_key": pl.String(),
    "model_quant": pl.String(),
    "prompt_variant": VARIANT_ENUM,
    "prompt_version": pl.String(),
    "reasoning_mode": REASONING_ENUM,
    "transport": TRANSPORT_ENUM,
    "prompt_sha256": pl.String(),
    "ai_answer": pl.String(),
    "ai_reasoning": pl.String(),
    "predicted_letter": pl.String(),
    "predicted_text": pl.String(),
    "ai_correct": pl.Boolean(),
    "grade": GRADE_ENUM,
    "grade_score": pl.Float32(),
    "response_time": pl.Float64(),
    "ttft_s": pl.Float64(),
    "tokens_per_second": pl.Float64(),
    "prompt_tokens": pl.Int32(),
    "completion_tokens": pl.Int32(),
    "reasoning_tokens": pl.Int32(),
    "max_tokens": pl.Int32(),
    "is_truncated": pl.Boolean(),
    "finish_reason": pl.String(),
    "run_order": pl.Int32(),
    "attempt": pl.Int8(),
    "called_at": pl.Datetime(time_zone="UTC"),
    "error": pl.String(),
}

RUNS_SCHEMA: dict[str, pl.DataType] = {
    "run_id": pl.String(),
    "model_key": pl.String(),
    "model_display_name": pl.String(),
    "model_quant": pl.String(),
    "model_format": pl.String(),
    "model_size_bytes": pl.Int64(),
    "instance_identifier": pl.String(),
    "context_length": pl.Int32(),
    "parallel": pl.Int32(),
    "prompt_variant": VARIANT_ENUM,
    "variant_label": pl.String(),
    "prompt_version": pl.String(),
    "reasoning_mode": REASONING_ENUM,
    "transport": TRANSPORT_ENUM,
    "generation_params": pl.String(),
    "lmstudio_version": pl.String(),
    "runtime_engine": pl.String(),
    "python_version": pl.String(),
    "package_version": pl.String(),
    "git_sha": pl.String(),
    "dataset_sha256": pl.String(),
    "sample_spec": pl.String(),
    "n_questions_planned": pl.Int32(),
    "n_questions_done": pl.Int32(),
    "n_errors": pl.Int32(),
    "warmup_time_s": pl.Float64(),
    "context_length_end": pl.Int32(),
    "parallel_end": pl.Int32(),
    "instance_identifier_end": pl.String(),
    "config_changed": pl.Boolean(),
    "machine": pl.String(),
    "started_at": pl.Datetime(time_zone="UTC"),
    "finished_at": pl.Datetime(time_zone="UTC"),
    "status": pl.String(),
}


def _load_questions_index(path: Path) -> dict[str, Question]:
    frame = pl.read_parquet(path).with_columns(
        pl.col("type").cast(pl.String),
        pl.col("difficulty").cast(pl.String),
    )
    return {
        str(row["question_id"]): Question.model_validate(row) for row in frame.iter_rows(named=True)
    }


def _iter_records(path: Path) -> list[dict[str, Any]]:
    """Derniere reponse retenue pour chaque question du run.

    Une reprise re-interroge les questions restees en erreur : le JSONL, ecrit en ajout,
    contient alors deux lignes pour la meme question. La couche silver a pour grain
    (run_id, question_id) — garder les deux violerait cette cle. La derniere ligne fait foi,
    c'est la tentative la plus recente ; la position de la premiere est conservee pour que
    l'ordre du fichier reste celui du run.
    """
    latest: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            latest[str(record["question_id"])] = record
    return list(latest.values())


def grade_run(
    run_id: str,
    *,
    settings: Settings,
    paths: DataPaths,
    questions: dict[str, Question] | None = None,
) -> pl.DataFrame:
    """Note un run et ecrit sa partition silver."""
    jsonl_path = paths.run_jsonl(run_id)
    manifest_path = paths.run_manifest(run_id)
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Aucune reponse brute pour le run {run_id}")

    manifest = load_manifest(manifest_path)
    variant = PROMPT_VARIANTS[manifest.prompt_variant]
    index = questions if questions is not None else _load_questions_index(paths.questions_parquet)

    rows: list[dict[str, Any]] = []
    n_missing = 0
    for record in _iter_records(jsonl_path):
        question = index.get(str(record["question_id"]))
        if question is None:
            n_missing += 1
            continue

        # La troncature se deduit du budget de tokens atteint, plus fiable qu'un
        # `finish_reason` dont la valeur depend du moteur. Elle est calculee ici parce qu'elle
        # pese sur la notation, et transmise telle quelle a la couche gold.
        max_tokens = int(record.get("max_tokens") or 0)
        completion_tokens = int(record.get("completion_tokens") or 0)
        is_truncated = max_tokens > 0 and completion_tokens >= max_tokens

        result = grade_answer(
            str(record.get("content") or ""),
            question,
            structured=variant.structured,
            answer_cue=variant.answer_cue,
            error=record.get("error"),
            truncated=is_truncated,
            fuzzy_threshold=settings.fuzzy_threshold,
            fuzzy_margin=settings.fuzzy_margin,
        )

        rows.append(
            {
                "run_id": run_id,
                "question_id": question.question_id,
                "model_key": manifest.model_key,
                "model_quant": manifest.model_quant,
                "prompt_variant": manifest.prompt_variant,
                "prompt_version": str(record.get("prompt_version") or manifest.prompt_version),
                "reasoning_mode": manifest.reasoning_mode,
                "transport": str(record.get("transport") or manifest.transport),
                "prompt_sha256": record.get("prompt_sha256"),
                "ai_answer": str(record.get("content") or ""),
                "ai_reasoning": record.get("reasoning"),
                "predicted_letter": result.predicted_letter,
                "predicted_text": result.predicted_text,
                "ai_correct": result.ai_correct,
                "grade": result.grade,
                "grade_score": result.score,
                "response_time": float(record.get("response_time") or 0.0),
                "ttft_s": record.get("ttft_s"),
                "tokens_per_second": record.get("tokens_per_second"),
                "prompt_tokens": int(record.get("prompt_tokens") or 0),
                "completion_tokens": completion_tokens,
                "reasoning_tokens": int(record.get("reasoning_tokens") or 0),
                "max_tokens": max_tokens,
                "is_truncated": is_truncated,
                "finish_reason": record.get("finish_reason"),
                "run_order": int(record.get("run_order") or 0),
                "attempt": int(record.get("attempt") or 1),
                "called_at": datetime.fromisoformat(str(record["called_at"])),
                "error": record.get("error"),
            }
        )

    if n_missing:
        logger.warning("{} reponse(s) sans question correspondante ignoree(s)", n_missing)

    frame = pl.DataFrame(rows, schema=ANSWERS_SCHEMA)
    destination = paths.answers_partition(run_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(destination, compression="zstd", statistics=True)
    logger.info("{} reponses notees ecrites dans {}", frame.height, destination)
    return frame


def _manifest_row(path: Path) -> dict[str, Any]:
    manifest = load_manifest(path)
    payload = manifest.model_dump(mode="python")
    payload["generation_params"] = json.dumps(manifest.generation_params, ensure_ascii=False)
    payload["machine"] = json.dumps(manifest.machine, ensure_ascii=False)
    payload.pop("sample_question_ids", None)
    return {key: payload.get(key) for key in RUNS_SCHEMA}


def write_runs_table(paths: DataPaths) -> pl.DataFrame:
    """Reconstruit `runs.parquet` a partir de tous les manifestes disponibles."""
    manifests = sorted(paths.llm_responses_dir.glob("*.manifest.json"))
    rows = [_manifest_row(path) for path in manifests]
    frame = pl.DataFrame(rows, schema=RUNS_SCHEMA)
    paths.runs_parquet.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(paths.runs_parquet, compression="zstd")
    logger.info("{} run(s) decrits dans {}", frame.height, paths.runs_parquet)
    return frame


def grade_runs(
    *,
    settings: Settings,
    paths: DataPaths,
    run_id: str | None = None,
    console: Console | None = None,
) -> None:
    """Note un run precis ou tous les runs disponibles, puis met a jour `runs.parquet`.

    La notation est toujours refaite, meme si la partition silver existe deja : elle est
    deterministe et coute quelques secondes, alors qu'une partition conservee au motif qu'elle
    existe pourrait avoir ete produite par une regle de notation anterieure.
    """
    console = console or Console()
    if run_id:
        run_ids = [run_id]
    else:
        run_ids = sorted(path.stem for path in paths.llm_responses_dir.glob("*.jsonl"))
    if not run_ids:
        console.print("[yellow]Aucun run a noter.[/yellow]")
        return

    index = _load_questions_index(paths.questions_parquet)
    summaries: list[dict[str, Any]] = []

    for identifier in run_ids:
        frame = grade_run(identifier, settings=settings, paths=paths, questions=index)
        summaries.append(_summarize(identifier, frame))

    write_runs_table(paths)
    _render_summary(summaries, console)


def _summarize(run_id: str, frame: pl.DataFrame) -> dict[str, Any]:
    if frame.height == 0:
        return {"run_id": run_id, "n": 0}
    grades = frame["grade"].cast(pl.String)
    return {
        "run_id": run_id,
        "n": frame.height,
        "accuracy": _as_float(frame["ai_correct"].mean()),
        "unparseable": _as_float((grades == "unparseable").mean()),
        "errors": int(_as_float((grades == "error").sum())),
        "median_time": _as_float(frame["response_time"].median()),
    }


def _as_float(value: object) -> float:
    """Convertit une agregation Polars, dont le type declare est volontairement large."""
    return float(value) if isinstance(value, int | float) else 0.0


def _render_summary(summaries: list[dict[str, Any]], console: Console) -> None:
    table = Table(title="Runs notes", header_style="bold")
    table.add_column("Run")
    table.add_column("N", justify="right")
    table.add_column("Exactitude", justify="right")
    table.add_column("Non parsable", justify="right")
    table.add_column("Erreurs", justify="right")
    table.add_column("Temps median", justify="right")
    for item in summaries:
        if not item.get("n"):
            table.add_row(item["run_id"], "0", "-", "-", "-", "-")
            continue
        table.add_row(
            item["run_id"],
            str(item["n"]),
            f"{item['accuracy']:.1%}",
            f"{item['unparseable']:.1%}",
            str(item["errors"]),
            f"{item['median_time']:.2f} s",
        )
    console.print(table)
