"""Temps de reponse : ce que coute chaque facon de poser la question."""

from __future__ import annotations

import polars as pl
import streamlit as st

from lib import charts, components, db, queries, theme


def render(selection: queries.Selection | None) -> None:
    """Distribution et derive des temps de reponse."""
    theme.page_header(
        "Temps de reponse",
        "Latence par variante, cout du prompt et stabilite du debit au fil d'un run.",
    )

    if selection is None:
        components.empty_state("Aucune donnee disponible.")
        return

    try:
        summary = selection.apply(queries.run_summary())
        by_run = selection.apply(queries.latency_by_run())
        drift = selection.apply(queries.latency_drift())
    except db.DatabaseUnavailableError as exc:
        st.error(str(exc), icon=":material/database_off:")
        return

    if summary.height == 0:
        components.empty_state("Aucun run ne correspond aux filtres selectionnes.")
        return

    fastest = summary.sort("median_response_time").row(0, named=True)
    slowest = summary.sort("median_response_time", descending=True).row(0, named=True)
    total_hours = float(summary["total_duration_s"].sum() or 0) / 3600

    # Le run le plus rapide n'est pas « une variante » des que plusieurs modeles sont
    # evalues : le nommer ainsi attribuerait a la formulation ce qui vient du modele.
    multi_modeles = summary["model_short"].n_unique() > 1

    def nomme(ligne: dict[str, object]) -> str:
        if multi_modeles:
            return f"<strong>{ligne['model_short']}</strong> en {ligne['variant_label']}"
        return f"<strong>{ligne['variant_label']}</strong>"

    theme.lede(
        f"Le run le plus rapide est {nomme(fastest)} "
        f"({components.seconds(fastest['median_response_time'])} en mediane), le plus lent "
        f"{nomme(slowest)} "
        f"({components.seconds(slowest['median_response_time'])}), soit un facteur "
        f"{slowest['median_response_time'] / max(fastest['median_response_time'], 1e-9):.1f}. "
        f"L'ensemble des runs affiches represente {total_hours:.1f} h de calcul."
    )

    components.kpi_row(
        [
            {
                "label": "Temps median",
                "value": components.seconds(float(summary["median_response_time"].median() or 0)),
                "help": "Mediane des medianes de chaque run. La mediane resiste aux quelques "
                "reponses tres longues qui tireraient la moyenne.",
                "icon": ":material/timer:",
            },
            {
                "label": "9e decile",
                "value": components.seconds(float(summary["p90_response_time"].median() or 0)),
                "help": "Une reponse sur dix depasse cette duree.",
                "icon": ":material/speed:",
            },
            {
                "label": "Debit median",
                "value": f"{float(summary['median_tokens_per_second'].median() or 0):.1f} tok/s",
                "help": "Debit de generation mesure par le moteur d'inference.",
                "icon": ":material/bolt:",
            },
            {
                "label": "Temps au premier token",
                "value": components.seconds(float(summary["median_ttft_s"].median() or 0), 3),
                "help": "Duree de traitement du prompt avant le premier token genere. "
                "Elle croit avec la longueur du prompt : c'est la ou se paient les exemples "
                "d'une variante few-shot.",
                "icon": ":material/hourglass_top:",
            },
        ],
        key="kpi_latency",
    )

    st.space("medium")

    run_ids = summary["run_id"].to_list()
    samples = queries.latency_samples(run_ids)

    left, right = st.columns([3, 2], gap="medium")

    with left:
        st.subheader("Distribution par variante")
        log_scale = st.toggle(
            "Echelle logarithmique",
            value=False,
            help="Utile quand une variante est bien plus lente que les autres.",
        )
        if samples.height:
            figure = charts.violin_latency(
                samples, group="variant_label", height=420, log_scale=log_scale
            )
            components.chart(figure, key="latency_violin")
            theme.note(
                "Le trait epais est l'intervalle interquartile, le trait fin l'etendue. "
                "Le premier appel de chaque run, qui paie la mise en cache, est exclu."
                + (
                    " Chaque violon agrege les modeles selectionnes, dont les vitesses "
                    "different : une forme a plusieurs bosses traduit cet ecart, pas une "
                    "instabilite de la variante."
                    if multi_modeles
                    else ""
                )
            )

    with right:
        st.subheader("Fonction de repartition")
        if samples.height:
            series = {
                str(label): part["response_time"].to_list()
                for label, part in (
                    (key[0] if isinstance(key, tuple) else key, part)
                    for key, part in samples.group_by("variant_label")
                )
            }
            figure = charts.ecdf(series, height=420)
            components.chart(figure, key="latency_ecdf")
            theme.note(
                "Se lit ainsi : pour un temps donne en abscisse, la courbe indique la part "
                "des reponses obtenues en moins de ce temps."
            )

    st.space("medium")
    left, right = st.columns(2, gap="medium")

    with left:
        st.subheader("Cout du prompt")
        if samples.height:
            figure = charts.scatter(
                samples,
                x="prompt_tokens",
                y="response_time",
                group="variant_label",
                x_title="Tokens du prompt",
                y_title="Temps de reponse (s)",
                height=400,
            )
            components.chart(figure, key="latency_prompt_tokens")
            theme.note(
                "Les variantes n'ont pas la meme longueur de prompt : le few-shot en ajoute "
                "beaucoup. Comparer les temps bruts sans tenir compte de cette difference "
                "melangerait le cout du prompt et celui de la generation."
            )

    with right:
        st.subheader("Derive au fil du run")
        if drift.height:
            figure = charts.lines(
                drift,
                x="run_order_bucket",
                y="median_tokens_per_second",
                group="variant_label",
                y_title="Debit median (tokens/s)",
                height=400,
            )
            components.chart(figure, key="latency_drift")
            theme.note(
                "Un debit qui baisse regulierement au fil des milliers d'appels signale un "
                "ralentissement thermique de la machine, pas une propriete du modele. Le "
                "debit est mesure par le moteur : il est insensible a ce qui se passe cote "
                "client, la ou le temps de reponse total, lui, absorbe le moindre appel "
                "concurrent."
            )

    st.space("medium")
    st.subheader("Detail par variante et type de question")

    display = by_run.sort(["variant_label", "type"]).select(
        pl.col("variant_label").alias("Variante"),
        pl.col("type").replace_strict(theme.TYPE_LABELS, default="?").alias("Type"),
        pl.col("n").alias("Questions"),
        pl.col("median_response_time").alias("Mediane"),
        pl.col("p90_response_time").alias("9e decile"),
        pl.col("p95_response_time").alias("95e centile"),
        pl.col("mean_response_time").alias("Moyenne"),
        pl.col("median_ttft_s").alias("Premier token"),
        pl.col("median_tokens_per_second").alias("Tokens/s"),
        pl.col("median_time_per_token").alias("Temps par token"),
        pl.col("median_completion_tokens").alias("Tokens generes"),
    )
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "Mediane": st.column_config.NumberColumn("Mediane", format="%.2f s"),
            "9e decile": st.column_config.NumberColumn("9e decile", format="%.2f s"),
            "95e centile": st.column_config.NumberColumn("95e centile", format="%.2f s"),
            "Moyenne": st.column_config.NumberColumn("Moyenne", format="%.2f s"),
            "Premier token": st.column_config.NumberColumn("Premier token", format="%.3f s"),
            "Tokens/s": st.column_config.NumberColumn("Tokens/s", format="%.1f"),
            "Temps par token": st.column_config.NumberColumn(
                "Temps par token", format="%.3f s", help="Isole le cout de generation."
            ),
            "Tokens generes": st.column_config.NumberColumn("Tokens generes", format="%.0f"),
        },
    )
    components.download(display, filename="latences.csv")
