"""Dashboard de benchmark LLM sur les questions Open Trivia Database.

Point d'entree : configuration de la page, style global, filtres partages entre les pages,
puis navigation. Les filtres sont definis ici pour survivre au changement de page.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import db, queries, theme
from views import (
    categories,
    explorer,
    latency,
    methodology,
    models,
    overview,
    prompts,
)

VARIANT_LABELS = {
    "v1_open": "V1 · Ouverte",
    "v2_letter": "V2 · Lettre",
    "v3_simple_evals": "V3 · Contrat",
    "v4_fewshot": "V4 · Few-shot",
    "v5_json": "V5 · JSON",
}


def sidebar_filters() -> queries.Selection | None:
    """Filtres globaux, appliques a toutes les pages."""
    try:
        runs = queries.runs()
    except db.DatabaseUnavailableError as exc:
        with st.sidebar:
            st.error(str(exc), icon=":material/database_off:")
        return None

    if runs.height == 0:
        with st.sidebar:
            st.warning("Aucun run de benchmark n'a encore ete enregistre.", icon=":material/info:")
        return None

    with st.sidebar:
        st.subheader("Filtres", divider="gray")

        available_models = sorted(runs["model_short"].unique().to_list())
        selected_models = st.multiselect(
            "Modeles",
            options=available_models,
            default=available_models,
            placeholder="Choisir un ou plusieurs modeles",
            help="Modeles a inclure dans toutes les analyses.",
        )

        available_reasoning = sorted(runs["reasoning_mode"].unique().to_list())
        selected_reasoning = st.pills(
            "Raisonnement",
            options=available_reasoning,
            default=available_reasoning,
            selection_mode="multi",
            format_func=lambda value: "active" if value == "on" else "desactive",
            help=(
                "Gemma 4 raisonne par defaut. Le benchmark principal desactive ce mode : "
                "il multiplie le temps de reponse sans changer la nature de la tache."
            ),
        )

        available_variants = sorted(runs["prompt_variant"].unique().to_list())
        selected_variants = st.pills(
            "Variantes de prompt",
            options=available_variants,
            default=available_variants,
            selection_mode="multi",
            format_func=lambda value: VARIANT_LABELS.get(value, value),
        )

        st.space("small")
        with st.expander("Jeu de donnees", icon=":material/dataset:"):
            overview_counts = queries.dataset_overview()
            st.caption(
                f"{overview_counts['n_questions']} questions evaluees · "
                f"{overview_counts['n_multiple']} a choix multiples · "
                f"{overview_counts['n_boolean']} vrai/faux · "
                f"{overview_counts['n_categories']} categories."
            )
            st.caption("Source : Open Trivia Database, licence CC BY-SA 4.0 · https://opentdb.com")

        if st.button(
            "Recharger les donnees",
            icon=":material/refresh:",
            help="A utiliser apres une reconstruction de la couche gold.",
            width="stretch",
        ):
            db.clear_cache()
            st.rerun()

    return queries.Selection(
        models=tuple(selected_models),
        reasoning=tuple(selected_reasoning),
        variants=tuple(selected_variants),
    )


def main() -> None:
    """Assemble et lance l'application."""
    st.set_page_config(
        page_title="Benchmark LLM · Trivial Poursuite",
        page_icon=":material/quiz:",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": (
                "Benchmark d'un LLM local sur les questions de culture generale "
                "d'Open Trivia Database. Projet M2 DEV."
            )
        },
    )
    theme.inject_css()

    selection = sidebar_filters()

    pages = {
        "Benchmark": [
            st.Page(
                lambda: overview.render(selection),
                title="Vue d'ensemble",
                icon=":material/dashboard:",
                url_path="overview",
                default=True,
            ),
            st.Page(
                lambda: prompts.render(selection),
                title="Variantes de prompt",
                icon=":material/chat:",
                url_path="prompts",
            ),
            st.Page(
                lambda: categories.render(selection),
                title="Themes et difficulte",
                icon=":material/category:",
                url_path="categories",
            ),
            st.Page(
                lambda: latency.render(selection),
                title="Temps de reponse",
                icon=":material/timer:",
                url_path="latency",
            ),
        ],
        "Detail": [
            st.Page(
                lambda: explorer.render(selection),
                title="Explorateur de questions",
                icon=":material/search:",
                url_path="explorer",
            ),
            st.Page(
                lambda: models.render(selection),
                title="Comparaison de modeles",
                icon=":material/memory:",
                url_path="models",
            ),
        ],
        "A propos": [
            st.Page(
                methodology.render,
                title="Methodologie",
                icon=":material/science:",
                url_path="methodology",
            ),
        ],
    }

    st.navigation(pages).run()


main()
