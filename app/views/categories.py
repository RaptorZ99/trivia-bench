"""Themes et difficulte : ou le modele sait, ou il ne sait pas."""

from __future__ import annotations

import polars as pl
import streamlit as st

from lib import charts, components, db, queries, stats, theme


def render(selection: queries.Selection | None) -> None:
    """Analyse par categorie et par difficulte."""
    theme.page_header(
        "Themes et difficulte",
        "Reussite par domaine de connaissance et confrontation a la difficulte declaree.",
    )

    if selection is None:
        components.empty_state("Aucune donnee disponible.")
        return

    try:
        by_category = selection.apply(queries.accuracy_by_category())
        by_cross = selection.apply(queries.accuracy_by_category_difficulty())
        by_difficulty = selection.apply(queries.accuracy_by_difficulty())
        summary = selection.apply(queries.run_summary())
    except db.DatabaseUnavailableError as exc:
        st.error(str(exc), icon=":material/database_off:")
        return

    if by_category.height == 0:
        components.empty_state("Aucun run ne correspond aux filtres selectionnes.")
        return

    labels = dict(zip(summary["run_id"].to_list(), summary["variant_label"].to_list(), strict=True))
    run_ids = summary.sort("accuracy", descending=True)["run_id"].to_list()
    run_id = st.segmented_control(
        "Run analyse",
        options=run_ids,
        default=run_ids[0],
        format_func=lambda value: labels.get(value, value),
        help="Les analyses par theme portent sur un run a la fois pour rester lisibles.",
    )
    if run_id is None:
        run_id = run_ids[0]

    category_run = by_category.filter(pl.col("run_id") == run_id).sort("accuracy")
    cross_run = by_cross.filter(pl.col("run_id") == run_id)
    difficulty_run = by_difficulty.filter(pl.col("run_id") == run_id).sort("difficulty_rank")

    if category_run.height == 0:
        components.empty_state("Ce run ne contient pas encore de donnees par categorie.")
        return

    hardest = category_run.row(0, named=True)
    easiest = category_run.row(category_run.height - 1, named=True)
    n_low = int(category_run["n_flag_low"].sum())

    theme.lede(
        f"Le theme le mieux maitrise est <strong>{easiest['category']}</strong> "
        f"({components.percent(easiest['accuracy'])} sur "
        f"{components.number(easiest['n'])} questions), le plus difficile "
        f"<strong>{hardest['category']}</strong> "
        f"({components.percent(hardest['accuracy'])} sur "
        f"{components.number(hardest['n'])}). "
        + (
            f"{n_low} categorie(s) comptent moins de 30 questions : leur intervalle de "
            "confiance est trop large pour conclure."
            if n_low
            else "Toutes les categories comptent au moins 30 questions."
        )
    )

    st.space("small")
    st.subheader("Carte de chaleur · theme et difficulte")
    _render_heatmap(cross_run)

    st.space("medium")
    left, right = st.columns([3, 2], gap="medium")

    with left:
        st.subheader("Classement des themes")
        top = category_run.head(12)
        figure = charts.accuracy_bar(
            top,
            x="category",
            baseline=float(top["chance_baseline"].mean() or 0.25),
            baseline_label="hasard",
            horizontal=True,
            height=max(360, 26 * top.height + 90),
        )
        components.chart(figure, key="hardest_categories")
        theme.note("Les douze themes les plus difficiles, du plus faible au plus fort.")

    with right:
        st.subheader("Exactitude par difficulte declaree")
        figure = charts.accuracy_bar(
            difficulty_run.with_columns(
                pl.col("difficulty")
                .replace_strict(theme.DIFFICULTY_LABELS, default="?")
                .alias("difficulty_label")
            ),
            x="difficulty_label",
            baseline=float(difficulty_run["chance_baseline"].mean() or 0.25),
            baseline_label="hasard",
            height=340,
        )
        components.chart(figure, key="by_difficulty")
        _render_calibration(difficulty_run)

    st.space("medium")
    st.subheader("Detail par theme")

    display = category_run.sort("accuracy", descending=True).select(
        pl.col("category").alias("Theme"),
        pl.col("n").alias("Questions"),
        pl.col("accuracy").alias("Exactitude"),
        pl.col("wilson_lo").alias("IC bas"),
        pl.col("wilson_hi").alias("IC haut"),
        pl.col("accuracy_above_chance").alias("Au-dessus du hasard"),
        pl.col("median_response_time").alias("Temps median"),
        pl.col("n_flag_low").alias("Effectif faible"),
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
            "Temps median": st.column_config.NumberColumn("Temps median", format="%.2f s"),
            "Effectif faible": st.column_config.CheckboxColumn(
                "Effectif faible", help="Moins de 30 questions : resultat non concluant."
            ),
        },
    )
    components.download(display, filename="exactitude_par_theme.csv")


def _render_heatmap(cross: pl.DataFrame) -> None:
    """Carte de chaleur categorie par difficulte."""
    if cross.height == 0:
        components.empty_state("Pas de croisement disponible pour ce run.")
        return

    difficulties = ["easy", "medium", "hard"]
    categories = sorted(cross["category"].unique().to_list())
    lookup = {(row["category"], row["difficulty"]): row for row in cross.iter_rows(named=True)}

    matrix: list[list[float | None]] = []
    counts: list[list[int]] = []
    for category in categories:
        row_values: list[float | None] = []
        row_counts: list[int] = []
        for difficulty in difficulties:
            record = lookup.get((category, difficulty))
            row_values.append(float(record["accuracy"]) if record else None)
            row_counts.append(int(record["n"]) if record else 0)
        matrix.append(row_values)
        counts.append(row_counts)

    figure = charts.heatmap(
        matrix,
        x_labels=[theme.DIFFICULTY_LABELS[d] for d in difficulties],
        y_labels=categories,
        counts=counts,
        height=max(420, 22 * len(categories) + 120),
    )
    components.chart(figure, key="category_heatmap")
    theme.note(
        "Les cases vides correspondent a des combinaisons absentes du jeu de questions. "
        "Une case sombre signale une bonne reussite."
    )


def _render_calibration(difficulty_run: pl.DataFrame) -> None:
    """Correlation entre difficulte declaree et difficulte constatee."""
    if difficulty_run.height < 3:
        return
    ranks = difficulty_run["difficulty_rank"].to_list()
    accuracies = difficulty_run["accuracy"].to_list()
    rho, p_value = stats.spearman([float(r) for r in ranks], [float(a) for a in accuracies])
    if rho != rho:  # NaN
        return
    direction = "decroit" if rho < 0 else "croit"
    theme.note(
        f"L'exactitude {direction} avec la difficulte declaree "
        f"(correlation de rang de Spearman : {rho:.2f}, {stats.format_p_value(p_value)}). "
        "Une correlation nettement negative indique que l'etiquetage d'OpenTDB predit bien "
        "la difficulte reelle pour ce modele."
    )
