"""Emplacements des fichiers des trois couches du medaillon."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DataPaths:
    """Chemins derives de la racine `data/`."""

    root: Path

    @property
    def bronze(self) -> Path:
        return self.root / "bronze"

    @property
    def silver(self) -> Path:
        return self.root / "silver"

    @property
    def gold(self) -> Path:
        return self.root / "gold"

    # --- Bronze ---
    @property
    def questions_raw_csv(self) -> Path:
        return self.bronze / "questions_raw.csv"

    @property
    def opentdb_dir(self) -> Path:
        return self.bronze / "opentdb"

    @property
    def opentdb_responses(self) -> Path:
        return self.opentdb_dir / "responses.jsonl"

    @property
    def opentdb_checkpoint(self) -> Path:
        return self.opentdb_dir / "checkpoint.json"

    @property
    def llm_responses_dir(self) -> Path:
        return self.bronze / "llm_responses"

    def run_jsonl(self, run_id: str) -> Path:
        return self.llm_responses_dir / f"{run_id}.jsonl"

    def run_manifest(self, run_id: str) -> Path:
        return self.llm_responses_dir / f"{run_id}.manifest.json"

    # --- Silver ---
    @property
    def questions_parquet(self) -> Path:
        return self.silver / "questions.parquet"

    @property
    def runs_parquet(self) -> Path:
        return self.silver / "runs.parquet"

    @property
    def answers_dir(self) -> Path:
        return self.silver / "answers"

    def answers_partition(self, run_id: str) -> Path:
        return self.answers_dir / f"run_id={run_id}" / "part-0.parquet"

    # --- Gold ---
    @property
    def duckdb(self) -> Path:
        return self.gold / "benchmark.duckdb"

    def ensure_dirs(self) -> None:
        """Cree l'arborescence de donnees si elle n'existe pas."""
        for directory in (
            self.bronze,
            self.opentdb_dir,
            self.llm_responses_dir,
            self.silver,
            self.answers_dir,
            self.gold,
        ):
            directory.mkdir(parents=True, exist_ok=True)
