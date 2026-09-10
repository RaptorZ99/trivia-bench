"""Acces en lecture seule a la couche gold.

DuckDB n'autorise qu'un seul ecrivain ou plusieurs lecteurs : une connexion gardee ouverte par
le dashboard bloquerait `dbt build`. Les connexions sont donc ouvertes et refermees a chaque
requete, et c'est le resultat qui est mis en cache.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import streamlit as st

DB_PATH = Path(os.environ.get("TRIVIA_DUCKDB_PATH", "data/gold/benchmark.duckdb"))


class DatabaseUnavailableError(RuntimeError):
    """La base gold est absente ou momentanement verrouillee par une reconstruction."""


@st.cache_data(ttl=600, show_spinner=False)
def query(sql: str, params: tuple[Any, ...] = ()) -> pl.DataFrame:
    """Execute une requete en lecture seule et renvoie un DataFrame Polars."""
    if not DB_PATH.exists():
        raise DatabaseUnavailableError(
            f"{DB_PATH} est introuvable. Lancer `uv run trivia build` pour construire "
            "la couche gold."
        )
    try:
        with duckdb.connect(str(DB_PATH), read_only=True) as connection:
            return connection.execute(sql, list(params)).pl()
    except duckdb.IOException as exc:  # verrou pose par un `dbt build` en cours
        raise DatabaseUnavailableError(
            "La base est momentanement verrouillee par une reconstruction. "
            "Reessayer dans quelques secondes."
        ) from exc


@st.cache_data(ttl=600, show_spinner=False)
def table(name: str) -> pl.DataFrame:
    """Charge une table gold complete (les marts sont petits, quelques milliers de lignes)."""
    return query(f"select * from {name}")


def clear_cache() -> None:
    """Vide le cache de donnees, par exemple apres une reconstruction."""
    query.clear()
    table.clear()
