"""Comparaison de modeles et effet du mode de raisonnement.

Les deux comparaisons sont **appariees** : elles portent sur les questions communes aux runs
compares, ce qui reste equitable meme quand un modele secondaire n'a ete evalue que sur un
echantillon du jeu de questions.
"""

from __future__ import annotations

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from lib import charts, components, db, queries, stats, theme


def render(selection: queries.Selection | None) -> None:
    """Compare les modeles evalues et les modes de raisonnement."""
    theme.page_header(
        "Comparaison de modeles",
        "Memes questions, memes prompts : ce qui distingue les modeles et les modes.",
    )

    if selection is None:
        components.empty_state("Aucune donnee disponible.")
        return

    try:
        summary = selection.apply(queries.run_summary())
        by_category = selection.apply(queries.accuracy_by_category())
        runs = selection.apply(queries.runs())
        bias = selection.apply(queries.position_bias())
        model_pairs = queries.model_pairwise()
        reasoning_pairs = queries.reasoning_pairwise()
    except db.DatabaseUnavailableError as exc:
        st.error(str(exc), icon=":material/database_off:")
        return

    if summary.height == 0:
        components.empty_state("Aucun run ne correspond aux filtres selectionnes.")
        return

    if model_pairs.height == 0 and reasoning_pairs.height == 0:
        components.empty_state(
            "Un seul modele a ete evalue.",
            "Ajouter un modele : `scripts/chain.sh <cle>` charge, verifie et lance les trois "
            "variantes.",
        )
    else:
        if model_pairs.height:
            _render_model_comparison(model_pairs, by_category)
        if reasoning_pairs.height:
            _render_reasoning_comparison(reasoning_pairs)

    st.space("medium")
    _render_position_bias(bias, summary)

    st.space("medium")
    _render_configurations(runs)


def _render_position_bias(bias: pl.DataFrame, summary: pl.DataFrame) -> None:
    """Le modele prefere-t-il une lettre, independamment de la bonne reponse ?

    L'ordre des options est melange de facon deterministe : les bonnes reponses se repartissent
    a parts egales entre A, B, C et D. Toute lettre sur-representee dans les reponses du modele
    est donc un biais de position, pas un effet du jeu de questions.
    """
    st.subheader("Biais de position en choix multiples")
    if bias.height == 0:
        components.empty_state("Pas de donnees de position pour cette selection.")
        return

    labels = components.run_labels(summary)
    disponibles = set(bias["run_id"].to_list())
    run_ids = [
        run
        for run in summary.sort("accuracy", descending=True)["run_id"].to_list()
        if run in disponibles
    ]
    if not run_ids:
        components.empty_state("Pas de donnees de position pour cette selection.")
        return
    choix = st.segmented_control(
        "Run",
        options=run_ids,
        default=run_ids[0],
        format_func=lambda value: labels.get(value, value),
        key="bias_run",
    )
    part = (
        bias.filter(pl.col("run_id") == (choix or run_ids[0]))
        .with_columns(
            (pl.col("share_predicted") - pl.col("share_is_correct_letter")).alias("ecart")
        )
        .sort("letter")
    )

    def signe(value: float) -> str:
        return ("+" if value >= 0 else "") + components.percent(value)

    plus = part.sort("ecart", descending=True).row(0, named=True)
    moins = part.sort("ecart").row(0, named=True)
    n_sans_lettre = int(part["n_no_letter"].max() or 0)
    theme.lede(
        "Les bonnes reponses se repartissent a parts egales entre les quatre lettres. Le modele, "
        f"lui, repond <strong>{plus['letter']}</strong> dans "
        f"{components.percent(plus['share_predicted'])} des cas "
        f"({signe(plus['ecart'])} par rapport a la part de bonnes reponses en {plus['letter']}) "
        f"et <strong>{moins['letter']}</strong> dans "
        f"{components.percent(moins['share_predicted'])} ({signe(moins['ecart'])})."
    )

    long = pl.concat(
        [
            part.select(
                pl.col("letter"),
                pl.col("share_is_correct_letter").alias("share"),
                pl.lit("Bonne reponse").alias("serie"),
            ),
            part.select(
                pl.col("letter"),
                pl.col("share_predicted").alias("share"),
                pl.lit("Reponse du modele").alias("serie"),
            ),
        ]
    )
    left, right = st.columns(2, gap="medium")
    with left:
        figure = charts.grouped_accuracy_bar(
            long,
            x="letter",
            group="serie",
            y="share",
            lo=None,
            hi=None,
            text=True,
            y_label="Part",
            height=340,
        )
        figure.update_yaxes(range=[0, 0.5])
        components.chart(figure, key="bias_shares")
        theme.note(
            "Part de chaque lettre parmi les bonnes reponses, et parmi les reponses du modele."
            + (
                f" {n_sans_lettre} reponse(s) sans lettre extractible ne sont pas comptees."
                if n_sans_lettre
                else ""
            )
        )
    with right:
        figure = charts.accuracy_bar(
            part.rename({"accuracy_when_correct_letter": "accuracy", "n_is_correct_letter": "n"}),
            x="letter",
            lo=None,
            hi=None,
            height=340,
        )
        components.chart(figure, key="bias_accuracy")
        theme.note(
            "Exactitude selon la position de la bonne reponse. Un modele sans biais reussit "
            "autant quelle que soit la lettre ; une lettre delaissee est aussi moins souvent "
            "trouvee quand elle est la bonne."
        )


def _render_model_comparison(pairs: pl.DataFrame, by_category: pl.DataFrame) -> None:
    """Exactitude appariee entre deux modeles, variante par variante."""
    st.subheader("Modele contre modele, a formulation identique")

    combinations = pairs.select("model_a", "model_b").unique().sort(["model_a", "model_b"]).rows()
    if len(combinations) > 1:
        choice = st.selectbox(
            "Paire de modeles",
            options=combinations,
            format_func=lambda pair: f"{pair[0]} contre {pair[1]}",
        )
    else:
        choice = combinations[0]

    subset = pairs.filter((pl.col("model_a") == choice[0]) & (pl.col("model_b") == choice[1])).sort(
        "prompt_variant"
    )

    totals = subset.select(
        pl.col("n").sum().alias("n"),
        pl.col("a_only").sum().alias("a_only"),
        pl.col("b_only").sum().alias("b_only"),
    ).row(0, named=True)
    overall = stats.mcnemar(int(totals["a_only"]), int(totals["b_only"]))
    mean_a = float((subset["accuracy_a"] * subset["n"]).sum() / max(totals["n"], 1))
    mean_b = float((subset["accuracy_b"] * subset["n"]).sum() / max(totals["n"], 1))
    leader, trailer = (choice[0], choice[1]) if mean_a >= mean_b else (choice[1], choice[0])
    verdict = "significatif" if overall.significant else "non significatif"

    theme.lede(
        f"Sur {components.number(subset['n'].max())} questions communes et "
        f"{subset.height} variante(s), <strong>{leader}</strong> devance "
        f"<strong>{trailer}</strong> de "
        f"{components.percent(abs(mean_a - mean_b))} en moyenne. "
        f"L'ecart est <strong>{verdict}</strong> ({stats.format_p_value(overall.p_value)}, "
        f"{overall.method})."
    )

    figure = _paired_bars(
        subset,
        label_a=choice[0],
        label_b=choice[1],
        column_a="accuracy_a",
        column_b="accuracy_b",
    )
    components.chart(figure, key="models_paired_accuracy")
    theme.note(
        "Chaque paire de barres porte sur les memes questions, posees avec le meme prompt. "
        "Les modeles n'ayant pas forcement ete evalues sur l'ensemble du jeu, la comparaison "
        "se limite a leur intersection."
    )

    st.space("medium")
    left, right = st.columns(2, gap="medium")

    with left:
        st.subheader("Vitesse comparee")
        figure = _paired_bars(
            subset,
            label_a=choice[0],
            label_b=choice[1],
            column_a="median_time_a",
            column_b="median_time_b",
            as_percent=False,
        )
        components.chart(figure, key="models_paired_latency")

    with right:
        st.subheader("Profil par famille de themes")
        _render_group_profile(by_category, models=(choice[0], choice[1]))

    st.space("medium")
    st.subheader("Detail par variante")
    display = subset.select(
        pl.col("variant_label").alias("Variante"),
        pl.col("n").alias("Questions"),
        pl.col("accuracy_a").alias(choice[0]),
        pl.col("accuracy_b").alias(choice[1]),
        pl.col("accuracy_diff").alias("Ecart"),
        pl.col("a_only").alias(f"{choice[0]} seul"),
        pl.col("b_only").alias(f"{choice[1]} seul"),
        pl.col("median_time_a").alias(f"Temps {choice[0]}"),
        pl.col("median_time_b").alias(f"Temps {choice[1]}"),
    )
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            choice[0]: st.column_config.NumberColumn(choice[0], format="percent"),
            choice[1]: st.column_config.NumberColumn(choice[1], format="percent"),
            "Ecart": st.column_config.NumberColumn("Ecart", format="percent"),
            f"Temps {choice[0]}": st.column_config.NumberColumn(
                f"Temps {choice[0]}", format="%.2f s"
            ),
            f"Temps {choice[1]}": st.column_config.NumberColumn(
                f"Temps {choice[1]}", format="%.2f s"
            ),
        },
    )
    components.download(display, filename="comparaison_modeles.csv")


def _render_reasoning_comparison(pairs: pl.DataFrame) -> None:
    """Effet de l'activation du raisonnement, a modele et variante egaux."""
    st.space("medium")
    st.subheader("Avec et sans raisonnement")

    totals = pairs.select(
        pl.col("n").sum().alias("n"),
        pl.col("off_only").sum().alias("off_only"),
        pl.col("on_only").sum().alias("on_only"),
    ).row(0, named=True)
    result = stats.mcnemar(int(totals["on_only"]), int(totals["off_only"]))
    mean_gain = float((pairs["accuracy_gain"] * pairs["n"]).sum() / max(totals["n"], 1))
    mean_factor = float(pairs["time_factor"].mean() or 0)
    median_tokens = float(pairs["median_reasoning_tokens"].median() or 0)
    verdict = "significatif" if result.significant else "non significatif"
    direction = "gagne" if mean_gain >= 0 else "perd"

    theme.lede(
        f"Sur {components.number(totals['n'])} reponses appariees, activer le raisonnement "
        f"fait <strong>{direction} {components.percent(abs(mean_gain))}</strong> d'exactitude "
        f"(ecart {verdict}, {stats.format_p_value(result.p_value)}), pour un temps de reponse "
        f"multiplie par <strong>{mean_factor:.1f}</strong> et environ "
        f"{components.number(median_tokens)} tokens de reflexion par question."
    )

    components.kpi_row(
        [
            {
                "label": "Gain d'exactitude",
                "value": components.percent(mean_gain),
                "help": "Difference d'exactitude sur les memes questions.",
                "icon": ":material/psychology:",
            },
            {
                "label": "Rattrapees par le raisonnement",
                "value": components.number(totals["on_only"]),
                "help": "Questions ratees sans raisonnement et reussies avec.",
                "icon": ":material/trending_up:",
            },
            {
                "label": "Perdues avec le raisonnement",
                "value": components.number(totals["off_only"]),
                "help": "Questions reussies sans raisonnement et ratees avec.",
                "icon": ":material/trending_down:",
            },
            {
                "label": "Cout en temps",
                "value": f"x {mean_factor:.1f}".replace(".", ","),
                "help": "Rapport des temps de reponse medians.",
                "icon": ":material/timer:",
            },
        ],
        key="kpi_reasoning",
    )

    figure = _paired_bars(
        pairs.sort("prompt_variant"),
        label_a="sans raisonnement",
        label_b="avec raisonnement",
        column_a="accuracy_off",
        column_b="accuracy_on",
    )
    components.chart(figure, key="reasoning_paired_accuracy")
    theme.note(
        "Le raisonnement fait produire au modele une reflexion avant sa reponse. Sur des "
        "questions factuelles, l'enjeu est de savoir si le gain d'exactitude justifie le "
        "temps supplementaire."
    )


def _paired_bars(
    frame: pl.DataFrame,
    *,
    label_a: str,
    label_b: str,
    column_a: str,
    column_b: str,
    as_percent: bool = True,
) -> go.Figure:
    """Barres groupees deux a deux sur les memes categories."""
    figure = charts.base_figure(380, showlegend=True)
    labels = frame["variant_label"].to_list()
    suffix = "%{y:.1%}" if as_percent else "%{y:.2f} s"

    for index, (name, column) in enumerate(((label_a, column_a), (label_b, column_b))):
        figure.add_trace(
            go.Bar(
                name=name,
                x=labels,
                y=frame[column].to_list(),
                marker_color=theme.CATEGORICAL[index],
                texttemplate=suffix,
                textposition="outside",
                cliponaxis=False,
                hovertemplate=f"<b>{name}</b> · %{{x}}<br>{suffix}<extra></extra>",
            )
        )
    figure.update_layout(barmode="group")
    if as_percent:
        figure.update_yaxes(tickformat=".0%", range=[0, 1.12])
    else:
        figure.update_yaxes(ticksuffix=" s")
    return figure


def _render_group_profile(by_category: pl.DataFrame, *, models: tuple[str, str]) -> None:
    """Exactitude par famille de categories, un trace par modele."""
    subset = by_category.filter(pl.col("model_short").is_in(list(models)))
    if subset.height == 0:
        return
    grouped = (
        subset.group_by(["model_short", "category_group"])
        .agg(pl.col("n_correct").sum().alias("n_correct"), pl.col("n").sum().alias("n"))
        .with_columns((pl.col("n_correct") / pl.col("n")).alias("accuracy"))
        .sort("category_group")
    )

    figure = charts.base_figure(360, showlegend=True)
    for index, model in enumerate(sorted(grouped["model_short"].unique().to_list())):
        part = grouped.filter(pl.col("model_short") == model)
        figure.add_trace(
            go.Scatterpolar(
                name=str(model),
                r=part["accuracy"].to_list(),
                theta=part["category_group"].to_list(),
                fill="toself",
                opacity=0.5,
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
    theme.note(
        "Toutes variantes confondues : le profil montre les familles de themes ou chaque "
        "modele est relativement plus a l'aise."
    )


def _render_configurations(runs: pl.DataFrame) -> None:
    """Tableau des configurations d'execution."""
    st.subheader("Configurations evaluees")
    display = runs.select(
        pl.col("model_key").alias("Modele"),
        pl.col("model_quant").alias("Quantification"),
        # En gigaoctets decimaux, l'unite dans laquelle LM Studio et le README annoncent les
        # tailles : 7,15 Go pour Gemma, et non 6,66 Gio.
        (pl.col("model_size_bytes") / 1e9).alias("Taille"),
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
