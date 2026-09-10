"""Configuration du projet, lue depuis l'environnement et le fichier `.env`.

Les noms de variables d'environnement sont explicites (pas de prefixe global) pour rester
lisibles dans le `.env` et compatibles avec ceux attendus par dbt (`TRIVIA_DUCKDB_PATH`,
`TRIVIA_SILVER_DIR`).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parametres du pipeline."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- OpenTDB ---
    opentdb_base_url: str = "https://opentdb.com"
    opentdb_session_token: str | None = None
    opentdb_min_interval: float = Field(
        default=5.2,
        description="Intervalle minimal entre deux appels (limite officielle : 1 / 5 s / IP).",
    )
    opentdb_max_amount: int = 50

    # --- LM Studio ---
    lmstudio_base_url: str = "http://localhost:1234"
    lmstudio_model_key: str = "google/gemma-4-12b-qat"
    lmstudio_timeout: float = 120.0
    lmstudio_timeout_reasoning: float = 600.0

    # --- Chemins ---
    data_dir: Path = Path("data")
    duckdb_path: Path = Field(
        default=Path("data/gold/benchmark.duckdb"),
        validation_alias=AliasChoices("TRIVIA_DUCKDB_PATH", "DUCKDB_PATH"),
    )
    silver_dir: Path = Field(
        default=Path("data/silver"),
        validation_alias=AliasChoices("TRIVIA_SILVER_DIR", "SILVER_DIR"),
    )

    # --- Notation (SPEC.md section 9) ---
    fuzzy_threshold: float = 90.0
    fuzzy_margin: float = 5.0
    low_sample_threshold: int = 30

    # --- Echantillonnage / reproductibilite ---
    sample_seed: int = 20260910


def get_settings() -> Settings:
    """Retourne les parametres (relus a chaque appel, pour rester testable)."""
    return Settings()
