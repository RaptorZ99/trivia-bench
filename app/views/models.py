"""Comparaison de modeles et effet du mode de raisonnement."""

from __future__ import annotations

import polars as pl
import streamlit as st

from lib import charts, components, db, queries, theme


def render(selection: queries.Selection | None) -> None:
    """Compare les modeles evalues, a variante egale."""
    theme.page_header(
        "Comparaison de modeles",
        "Meme jeu de questions, memes prompts : ce qui distingue les modeles et les modes.",
    )

    if selection is None:
        components.empty_state("Aucune donnee disponible.")
        return

    try:
        summary = selection.apply(queries.run_summary())
        by_category = selection.apply(queries.accuracy_by_category())
        runs = selection.apply(queries.runs())
    except db.DatabaseUnavailableError as exc:
        st.error(str(exc), icon=":material/database_off:")
        return

    if summary.height == 0:
        components.empty_state("Aucun run ne correspond aux filtres selectionnes.")
        return

    n_models = summary["model_short"].n_unique()
    n_modes = summary["reasoning_mode"].n_unique()

    if n_models < 2 and n_modes < 2:
        components.empty_state(
            "Un seul modele et un seul mode de raisonnement sont disponibles.",
            "Lancer un second modele avec `uv run trivia bench --model <cle> "
            "--sample stratified:400`, ou activer le raisonnement avec `--reasoning on`.",
        )
        _render_configurations(runs)
        return

    if n_models >= 2:
        _render_model_comparison(summary, by_category)
    if n_modes >= 2:
        _render_reasoning_comparison(summary)

    st.space("medium")
    _render_configurations(runs)


def _render_model_comparison(summary: pl.DataFrame, by_category: pl.DataFrame) -> None:
    """Exactitude et latence par modele, variante par variante."""
    st.subheader("Exactitude par modele et variante")

    common = _common_variants(summary, "model_short")
    if common.height == 0:
        components.empty_state("Aucune variante n'est commune aux modeles selectionnes.")
        return

    best_by_model = (
        common.group_by("model_short")
        .agg(pl.col("accuracy").max().alias("accuracy"))
        .sort("accuracy", descending=True)
    )
    leader = best_by_model.row(0, named=True)
    runner_up = best_by_model.row(min(1, best_by_model.height - 1), named=True)
    theme.lede(
        f"Sur les variantes communes, <strong>{leader['model_short']}</strong> atteint au mieux "
        f"{components.percent(leader['accuracy'])}"
        + (
            f", contre {components.percent(runner_up['accuracy'])} pour "
            f"<strong>{runner_up['model_short']}</strong>."
            if best_by_model.height > 1
            else "."
        )
    )

    figure = charts.grouped_accuracy_bar(common, x="variant_label", group="model_short", height=400)
    components.chart(figure, key="models_accuracy")
    theme.note(
        "Comparaison a variante egale : seules les variantes evaluees par tous les modeles "
        "affiches sont retenues."
    )

    st.space("medium")
    left, right = st.columns(2, gap="medium")

    with left:
        st.subheader("Vitesse")
        figure = charts.accuracy_bar(
            common.sort("median_response_time"),
            x="variant_label",
            y="median_response_time",
            lo=None,
            hi=None,
            n=None,
            color=theme.CATEGORICAL[1],
            height=340,
        )
        figure.update_yaxes(tickformat=None, ticksuffix=" s", range=None, autorange=True)
        figure.update_traces(texttemplate="%{y:.2f} s")
        components.chart(figure, key="models_latency")

    with right:
        st.subheader("Profil par famille de themes")
        _render_group_profile(by_category)


def _render_group_profile(by_category: pl.DataFrame) -> None:
    """Exactitude par famille de categories, un trace par modele."""
    if by_category.height == 0:
        return
    grouped = (
        by_category.group_by(["model_short", "category_group"])
        .agg(
            pl.col("n_correct").sum().alias("n_correct"),
            pl.col("n").sum().alias("n"),
        )
        .with_columns((pl.col("n_correct") / pl.col("n")).alias("accuracy"))
        .sort("category_group")
    )

    figure = charts.base_figure(340, showlegend=True)
    import plotly.graph_objects as go

    for index, model in enumerate(sorted(grouped["model_short"].unique().to_list())):
        part = grouped.filter(pl.col("model_short") == model)
        figure.add_trace(
            go.Scatterpolar(
                name=str(model),
                r=part["accuracy"].to_list(),
                theta=part["category_group"].to_list(),
                fill="toself",
                opacity=0.55,
                line={"color": theme.CATEGORICAL[index % len(theme.CATEGORICAL)]},
                hovertemplate=f"<b>{model}</b> · %{{theta}}<br>%{{r:.1%}}<extra></extra>",
            )
        )
    figure.update_layout(
        polar={
            "radialaxis": {"range": [0, 1], "tickformat": ".0%", "gridcolor": charts.GRID},
            "angularaxis": {"gridcolor": charts.GRID},
            "bgcolor": "rgba(0,0,0,0)",
        }
    )
    components.chart(figure, key="models_radar")


def _render_reasoning_comparison(summary: pl.DataFrame) -> None:
    """Effet de l'activation du raisonnement, a variante et modele egaux."""
    st.space("medium")
    st.subheader("Avec et sans raisonnement")

    common = _common_variants(summary, "reasoning_mode")
    if common.height == 0:
        components.empty_state(
            "Aucune variante n'a ete evaluee dans les deux modes de raisonnement."
        )
        return

    pivot = common.select(
        "variant_label", "reasoning_mode", "accuracy", "median_response_time"
    ).pivot(on="reasoning_mode", index="variant_label", values=["accuracy", "median_response_time"])

    accuracy_off = f"accuracy_{'off'}"
    accuracy_on = f"accuracy_{'on'}"
    time_off = f"median_response_time_{'off'}"
    time_on = f"median_response_time_{'on'}"

    if accuracy_off in pivot.columns and accuracy_on in pivot.columns:
        gains = pivot.with_columns(
            (pl.col(accuracy_on) - pl.col(accuracy_off)).alias("gain"),
            (pl.col(time_on) / pl.col(time_off)).alias("cost_factor"),
        ).drop_nulls("gain")
        if gains.height:
            mean_gain = float(gains["gain"].mean() or 0)
            mean_cost = float(gains["cost_factor"].mean() or 0)
            direction = "gagne" if mean_gain >= 0 else "perd"
            theme.lede(
                f"Activer le raisonnement fait {direction} en moyenne "
                f"<strong>{components.percent(abs(mean_gain))}</strong> d'exactitude, "
                f"pour un temps de reponse multiplie par <strong>{mean_cost:.1f}</strong>."
            )

    figure = charts.grouped_accuracy_bar(
        common.with_columns(
            pl.col("reasoning_mode")
            .replace_strict({"off": "sans raisonnement", "on": "avec raisonnement"}, default="?")
            .alias("mode_label")
        ),
        x="variant_label",
        group="mode_label",
        height=380,
    )
    components.chart(figure, key="reasoning_accuracy")
    theme.note(
        "Le raisonnement fait produire au modele une reflexion avant sa reponse. Sur des "
        "questions factuelles, il coute surtout du temps ; l'interet est de mesurer si le "
        "gain d'exactitude le justifie."
    )


def _common_variants(summary: pl.DataFrame, dimension: str) -> pl.DataFrame:
    """Restreint aux variantes presentes pour toutes les valeurs d'une dimension."""
    n_values = summary[dimension].n_unique()
    counts = (
        summary.group_by("prompt_variant")
        .agg(pl.col(dimension).n_unique().alias("covered"))
        .filter(pl.col("covered") == n_values)
    )
    return summary.join(counts.select("prompt_variant"), on="prompt_variant", how="inner").sort(
        "prompt_variant"
    )


def _render_configurations(runs: pl.DataFrame) -> None:
    """Tableau des configurations d'execution."""
    st.subheader("Configurations evaluees")
    display = runs.select(
        pl.col("model_key").alias("Modele"),
        pl.col("model_quant").alias("Quantification"),
        (pl.col("model_size_bytes") / 1024**3).alias("Taille"),
        pl.col("context_length").alias("Contexte"),
        pl.col("variant_label").alias("Variante"),
        pl.col("reasoning_label").alias("Raisonnement"),
        pl.col("n_questions_done").alias("Questions"),
        pl.col("sample_spec").alias("Echantillon"),
        pl.col("lmstudio_version").alias("LM Studio"),
        pl.col("runtime_engine").alias("Moteur"),
        pl.col("status").alias("Etat"),
    )
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "Taille": st.column_config.NumberColumn("Taille", format="%.2f Go"),
            "Contexte": st.column_config.NumberColumn("Contexte", format="localized"),
            "Questions": st.column_config.NumberColumn("Questions", format="localized"),
        },
    )
