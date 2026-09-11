"""Rendu sans interface des sept pages du dashboard.

Chaque page est executee par `streamlit.testing.v1.AppTest` sur la couche gold versionnee,
avec tous les modeles et toutes les variantes selectionnes. C'est la configuration la plus
exigeante : une page ecrite en pensant a un seul modele y superpose des barres, relie des
runs distincts sur une meme courbe ou affiche des lignes de tableau indiscernables. Le test
echoue des qu'une page leve une exception ; il ne juge pas le contenu, seulement le fait que
la page se rend.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
GOLD_DB = PROJECT_ROOT / "data" / "gold" / "benchmark.duckdb"

PAGES = ["overview", "prompts", "categories", "latency", "explorer", "models", "methodology"]

# La page est rendue comme `app.py` le ferait, mais sans `st.navigation` : chaque page est
# une fonction, on l'appelle avec la selection la plus large possible.
SCRIPT = """
import os
import sys

os.environ["TRIVIA_DUCKDB_PATH"] = {db!r}
sys.path.insert(0, {app_dir!r})

from lib import queries
from views import {page}

if {page!r} == "methodology":
    {page}.render()
else:
    runs = queries.runs()
    selection = queries.Selection(
        models=tuple(sorted(runs["model_short"].unique().to_list())),
        reasoning=tuple(sorted(runs["reasoning_mode"].unique().to_list())),
        variants=tuple(sorted(runs["prompt_variant"].unique().to_list())),
    )
    {page}.render(selection)
"""


@pytest.mark.skipif(not GOLD_DB.exists(), reason="couche gold absente : lancer `make build`")
@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page: str) -> None:
    script = SCRIPT.format(db=str(GOLD_DB), app_dir=str(APP_DIR), page=page)
    app = AppTest.from_string(script, default_timeout=120)
    app.run()
    assert not app.exception, "\n".join(str(item.value) for item in app.exception)
