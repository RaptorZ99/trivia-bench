"""Vue d'ensemble : ce que le benchmark dit en une page."""

from __future__ import annotations

import polars as pl
import streamlit as st

from lib import charts, components, db, queries, theme


def render(selection: queries.Selection | None) -> None:
    """Affiche la synthese du benchmark."""
    theme.page_header(
        "Vue d'ensemble",
        "Performance globale du modele selon la facon dont la question lui est posee.",
    )

    if selection is None:
        components.empty_state(
            "Aucune donnee disponible.",
            "Lancer `uv run trivia bench --all-variants` puis `uv run trivia build`.",
        )
        return

    try:
        summary = selection.apply(queries.run_summary())
        by_type = selection.apply(queries.accuracy_by_type())
        runs = selection.apply(queries.runs())
    except db.DatabaseUnavailableError as exc:
        st.error(str(exc), icon=":material/database_off:")
        return

    if summary.height == 0:
        components.empty_state("Aucun run ne correspond aux filtres selectionnes.")
        return

    summary = summary.sort("accuracy", descending=True)
    best = summary.row(0, named=True)
    worst = summary.row(summary.height - 1, named=True)
    fastest = summary.sort("median_response_time").row(0, named=True)

    lede = (
        f"La variante <strong>{best['variant_label']}</strong> obtient "
        f"<strong>{components.percent(best['accuracy'])}</strong> de bonnes reponses "
        f"{components.interval(best['wilson_lo'], best['wilson_hi'])} sur "
        f"{components.number(best['n'])} questions, soit "
        f"{components.percent(best['accuracy_above_chance'])} au-dessus du hasard."
    )
    if summary.height > 1:
        lede += (
            f" L'ecart avec la variante la moins performante "
            f"(<strong>{worst['variant_label']}</strong>, "
            f"{components.percent(worst['accuracy'])}) atteint "
            f"{components.percent(best['accuracy'] - worst['accuracy'])}."
        )
    else:
        lede += " C'est pour l'instant la seule variante evaluee."
    theme.lede(lede)

    # La courbe de contexte n'a de sens qu'a partir de deux variantes comparees.
    accuracy_series = (
        summary.sort("prompt_variant")["accuracy"].to_list() if summary.height > 1 else None
    )
    components.kpi_row(
        [
            {
                "label": "Meilleure exactitude",
                "value": components.percent(best["accuracy"]),
                "help": f"{best['variant_label']} · intervalle de Wilson a 95 % "
                f"{components.interval(best['wilson_lo'], best['wilson_hi'])}",
                "icon": ":material/trophy:",
                "chart_data": accuracy_series,
                "chart_type": "bar",
            },
            {
                "label": "Au-dessus du hasard",
                "value": components.percent(best["accuracy_above_chance"]),
                "help": "Le hasard donne 25 % aux choix multiples et 50 % au vrai/faux. "
                "La reference est ponderee par le nombre de questions de chaque type.",
                "icon": ":material/casino:",
            },
            {
                "label": "Reponses inexploitables",
                "value": components.percent(best["unparseable_rate"], 2),
                "help": "Reponses dont aucune option n'a pu etre extraite : c'est un echec de "
                "format, distinct d'un echec de connaissance.",
                "icon": ":material/help:",
                "delta_color": "inverse",
            },
            {
                "label": "Temps median",
                "value": components.seconds(best["median_response_time"]),
                "help": f"Variante la plus rapide : {fastest['variant_label']} a "
                f"{components.seconds(fastest['median_response_time'])}.",
                "icon": ":material/timer:",
            },
            {
                "label": "Questions evaluees",
                "value": components.number(best["n"]),
                "help": "Les quatre questions servant d'exemples few-shot sont exclues.",
                "icon": ":material/quiz:",
            },
        ],
        key="kpi_overview",
    )

    st.space("medium")

    left, right = st.columns([3, 2], gap="medium")

    with left:
        st.subheader("Exactitude par variante de prompt")
        figure = charts.accuracy_bar(
            summary.sort("accuracy", descending=True),
            x="variant_label",
            baseline=float(summary["chance_baseline"].mean() or 0.25),
            baseline_label="niveau du hasard",
            height=380,
        )
        components.chart(figure, key="overview_variants")
        theme.note(
            "Les moustaches representent l'intervalle de Wilson a 95 %. Deux barres dont les "
            "intervalles se chevauchent ne sont pas necessairement equivalentes : la page "
            "« Variantes de prompt » applique un test apparie, plus sensible."
        )

    with right:
        st.subheader("Choix multiples contre vrai/faux")
        if by_type.height:
            figure = charts.grouped_accuracy_bar(
                by_type.with_columns(
                    pl.col("type")
                    .replace_strict(theme.TYPE_LABELS, default="?")
                    .alias("type_label")
                ),
                x="variant_label",
                group="type_label",
                baselines={"hasard QCM : 25 %": 0.25, "hasard vrai/faux : 50 %": 0.5},
                height=380,
            )
            components.chart(figure, key="overview_types")
            theme.note(
                "Une bonne reponse sur deux au vrai/faux ne vaut pas une bonne reponse sur "
                "deux au QCM : le hasard rapporte deja 50 % dans le premier cas."
            )

    st.space("medium")
    st.subheader("Detail des runs")

    display = summary.select(
        pl.col("variant_label").alias("Variante"),
        pl.col("model_short").alias("Modele"),
        pl.col("reasoning_mode")
        .replace_strict({"off": "desactive", "on": "actif"}, default="?")
        .alias("Raisonnement"),
        pl.col("n").alias("Questions"),
        pl.col("accuracy").alias("Exactitude"),
        pl.col("wilson_lo").alias("IC bas"),
        pl.col("wilson_hi").alias("IC haut"),
        pl.col("accuracy_above_chance").alias("Au-dessus du hasard"),
        pl.col("unparseable_rate").alias("Inexploitables"),
        pl.col("median_response_time").alias("Temps median"),
        pl.col("median_tokens_per_second").alias("Tokens/s"),
        pl.col("total_duration_s").alias("Duree totale"),
    )

    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "Exactitude": st.column_config.ProgressColumn(
                "Exactitude", format="percent", min_value=0, max_value=1
            ),
            "IC bas": st.column_config.NumberColumn("IC bas", format="percent"),
            "IC haut": st.column_config.NumberColumn("IC haut", format="percent"),
            "Au-dessus du hasard": st.column_config.NumberColumn(
                "Au-dessus du hasard", format="percent"
            ),
            "Inexploitables": st.column_config.NumberColumn("Inexploitables", format="percent"),
            "Temps median": st.column_config.NumberColumn("Temps median", format="%.2f s"),
            "Tokens/s": st.column_config.NumberColumn("Tokens/s", format="%.1f"),
            "Duree totale": st.column_config.NumberColumn("Duree totale", format="%.0f s"),
            "Questions": st.column_config.NumberColumn("Questions", format="localized"),
        },
    )
    components.download(display, filename="runs.csv")

    with st.expander("Conditions d'execution", icon=":material/settings:"):
        conditions = runs.select(
            pl.col("variant_label").alias("Variante"),
            pl.col("model_key").alias("Modele"),
            pl.col("model_quant").alias("Quantification"),
            pl.col("context_length").alias("Contexte"),
            pl.col("parallel").alias("Requetes simultanees"),
            pl.col("lmstudio_version").alias("LM Studio"),
            pl.col("runtime_engine").alias("Moteur"),
            pl.col("status").alias("Etat"),
            pl.col("started_at").alias("Debut"),
        )
        st.dataframe(conditions, hide_index=True, width="stretch")
        theme.note(
            "Chaque run est decrit par un manifeste complet (versions, parametres de "
            "generation, empreinte du jeu de questions, commit git) conserve dans "
            "`data/bronze/llm_responses/`."
        )
