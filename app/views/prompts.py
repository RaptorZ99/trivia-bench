"""Variantes de prompt : ce que change la formulation de la question."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from lib import charts, components, db, queries, stats, theme
from trivia_bench.bench.prompts import PROMPT_VARIANTS

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "trivia_bench" / "prompts"


def render(selection: queries.Selection | None) -> None:
    """Compare les variantes entre elles, avec un test apparie."""
    theme.page_header(
        "Variantes de prompt",
        "Une meme question posee de trois facons differentes : qu'est-ce qui change vraiment ?",
    )

    if selection is None:
        components.empty_state("Aucune donnee disponible.")
        return

    try:
        summary = selection.apply(queries.run_summary())
        pairwise = selection.apply(queries.variant_pairwise())
        grades = selection.apply(queries.grade_breakdown())
        lengths = selection.apply(queries.answer_length())
    except db.DatabaseUnavailableError as exc:
        st.error(str(exc), icon=":material/database_off:")
        return

    if summary.height == 0:
        components.empty_state("Aucun run ne correspond aux filtres selectionnes.")
        return

    comparison, breakdown, length, templates = st.tabs(
        ["Comparaison appariee", "Modes de reconnaissance", "Longueur des reponses", "Gabarits"]
    )

    with comparison:
        _render_comparison(summary, pairwise)

    with breakdown:
        _render_breakdown(summary, grades)

    with length:
        _render_length(summary, lengths)

    with templates:
        _render_templates(summary)


def _render_comparison(summary: pl.DataFrame, pairwise: pl.DataFrame) -> None:
    """Test de McNemar entre deux variantes choisies."""
    if pairwise.height == 0:
        components.empty_state(
            "Il faut au moins deux runs du meme modele pour comparer des variantes."
        )
        return

    labels = dict(
        zip(summary["prompt_variant"].to_list(), summary["variant_label"].to_list(), strict=True)
    )
    options = sorted(labels)

    # Une paire de variantes existe pour chaque modele : sans ce choix, la page en retiendrait
    # un au hasard et afficherait un ecart sans dire de quel modele il parle.
    modeles = sorted(pairwise["model_short"].unique().to_list())
    if len(modeles) > 1:
        modele = st.selectbox("Modele", modeles, index=0)
        pairwise = pairwise.filter(pl.col("model_short") == modele)
    else:
        modele = modeles[0]

    left, right = st.columns(2, gap="medium")
    with left:
        variant_a = st.selectbox(
            "Variante A", options, index=0, format_func=lambda v: labels.get(v, v)
        )
    with right:
        default_b = 1 if len(options) > 1 else 0
        variant_b = st.selectbox(
            "Variante B", options, index=default_b, format_func=lambda v: labels.get(v, v)
        )

    if variant_a == variant_b:
        components.empty_state("Choisir deux variantes differentes.")
        return

    low, high = min(variant_a, variant_b), max(variant_a, variant_b)
    row = pairwise.filter((pl.col("variant_a") == low) & (pl.col("variant_b") == high))
    if row.height == 0:
        components.empty_state("Ces deux variantes n'ont pas ete evaluees sur le meme modele.")
        return

    record = row.row(0, named=True)
    flipped = variant_a != low
    a_only = record["b_only"] if flipped else record["a_only"]
    b_only = record["a_only"] if flipped else record["b_only"]
    accuracy_a = record["accuracy_b"] if flipped else record["accuracy_a"]
    accuracy_b = record["accuracy_a"] if flipped else record["accuracy_b"]

    result = stats.mcnemar(a_only, b_only)

    paired = queries.paired_answers(
        record["run_b"] if flipped else record["run_a"],
        record["run_a"] if flipped else record["run_b"],
    )
    ci_low, ci_high = stats.bootstrap_diff_ci(
        paired["correct_a"].to_list(), paired["correct_b"].to_list()
    )

    verdict = "significatif" if result.significant else "non significatif"
    prefixe = f"Sur <strong>{modele}</strong>, " if len(modeles) > 1 else ""
    theme.lede(
        f"{prefixe}sur {components.number(record['n'])} questions communes, "
        f"<strong>{labels[variant_a]}</strong> atteint "
        f"{components.percent(accuracy_a)} et <strong>{labels[variant_b]}</strong> "
        f"{components.percent(accuracy_b)}. L'ecart de "
        f"{components.percent(accuracy_a - accuracy_b)} "
        f"[{components.percent(ci_low)} · {components.percent(ci_high)}] est "
        f"<strong>{verdict}</strong> ({stats.format_p_value(result.p_value)}, "
        f"{result.method})."
    )

    components.kpi_row(
        [
            {
                "label": f"{labels[variant_a]} seule",
                "value": components.number(a_only),
                "help": "Questions reussies par A et ratees par B.",
                "icon": ":material/arrow_upward:",
            },
            {
                "label": f"{labels[variant_b]} seule",
                "value": components.number(b_only),
                "help": "Questions reussies par B et ratees par A.",
                "icon": ":material/arrow_downward:",
            },
            {
                "label": "Les deux justes",
                "value": components.number(record["both_correct"]),
                "icon": ":material/done_all:",
            },
            {
                "label": "Les deux fausses",
                "value": components.number(record["both_wrong"]),
                "icon": ":material/close:",
            },
        ],
        key="kpi_mcnemar",
    )
    theme.note(
        "Seules les paires discordantes departagent deux variantes : les questions reussies "
        "ou ratees par les deux n'apportent aucune information sur leur difference."
    )

    st.space("medium")
    st.subheader("Toutes les paires")
    _render_pairwise_matrix(pairwise, labels)


def _render_pairwise_matrix(pairwise: pl.DataFrame, labels: dict[str, str]) -> None:
    """Matrice des p-values de toutes les comparaisons deux a deux."""
    variants = sorted({*pairwise["variant_a"].to_list(), *pairwise["variant_b"].to_list()})
    lookup: dict[tuple[str, str], dict[str, object]] = {
        (row["variant_a"], row["variant_b"]): row for row in pairwise.iter_rows(named=True)
    }

    matrix: list[list[float | None]] = []
    text: list[list[str]] = []
    for row_variant in variants:
        matrix_row: list[float | None] = []
        text_row: list[str] = []
        for column_variant in variants:
            if row_variant == column_variant:
                matrix_row.append(None)
                text_row.append("—")
                continue
            key = (min(row_variant, column_variant), max(row_variant, column_variant))
            record = lookup.get(key)
            if record is None:
                matrix_row.append(None)
                text_row.append("—")
                continue
            result = stats.mcnemar(int(record["a_only"]), int(record["b_only"]))
            matrix_row.append(result.p_value)
            text_row.append(stats.format_p_value(result.p_value).replace("p = ", ""))
        matrix.append(matrix_row)
        text.append(text_row)

    figure = charts.matrix_annotated(
        matrix,
        labels=[labels.get(variant, variant) for variant in variants],
        text=text,
        height=420,
    )
    components.chart(figure, key="pairwise_matrix")
    theme.note(
        "p-value du test de McNemar pour chaque paire. En vert, les differences "
        "statistiquement significatives au seuil de 5 %."
    )


def _choisir_modele(summary: pl.DataFrame, *, key: str) -> str | None:
    """Selecteur de modele, affiche seulement quand la selection en contient plusieurs.

    Une barre empilee ou une moyenne de longueur vaut pour un run : superposer les modeles
    ferait depasser 100 % dans un cas et melangerait des enveloppes de reponse differentes
    dans l'autre.
    """
    modeles = sorted(summary["model_short"].unique().to_list())
    if len(modeles) == 1:
        return None
    choix = st.segmented_control("Modele", modeles, default=modeles[0], key=key)
    return str(choix or modeles[0])


def _rate_bar(summary: pl.DataFrame, column: str, *, color: str) -> go.Figure:
    """Un taux par run : barres groupees par modele des qu'il y en a plusieurs.

    Une barre simple par variante superposerait les modeles sur la meme abscisse et ne
    laisserait voir que le dernier trace.
    """
    if summary["model_short"].n_unique() > 1:
        return charts.grouped_accuracy_bar(
            summary,
            x="model_short",
            group="variant_label",
            y=column,
            lo=None,
            hi=None,
            height=340,
            text=True,
            y_label="Taux",
        )
    return charts.accuracy_bar(
        summary.sort(column, descending=True),
        x="variant_label",
        y=column,
        lo=None,
        hi=None,
        color=color,
        height=340,
    )


def _render_breakdown(summary: pl.DataFrame, grades: pl.DataFrame) -> None:
    """Repartition des modes de reconnaissance et taux d'echec de format."""
    st.subheader("Comment les reponses sont reconnues")
    modele = _choisir_modele(summary, key="breakdown_model")
    if modele is not None:
        grades = grades.filter(pl.col("model_short") == modele)

    order = ["letter", "exact", "fuzzy", "contains", "wrong", "unparseable", "error"]
    figure = charts.stacked_shares(
        grades,
        x="variant_label",
        category="grade",
        value="share",
        colors=theme.GRADE_COLORS,
        labels=theme.GRADE_LABELS,
        order=order,
        height=400,
    )
    components.chart(figure, key="grade_breakdown")
    theme.note(
        "Le format demande depend du type de question : une lettre en choix multiples, le mot "
        "lui-meme en vrai/faux. « Lettre extraite » et « Texte exact » correspondent donc au "
        "format attendu, chacun pour son type. « Rapprochement approche » et « Reponse "
        "contenue » signalent une reponse juste mais hors format. « Inexploitable » est un "
        "echec de format, pas de connaissance : le modele repond le plus souvent qu'aucune "
        "option ne convient."
    )

    st.space("medium")
    left, right = st.columns(2, gap="medium")

    with left:
        st.subheader("Conformite au format demande")
        figure = _rate_bar(summary, "format_compliance_rate", color=theme.PRIMARY)
        components.chart(figure, key="format_compliance")
        theme.note("Part des reponses rendues exactement dans le format demande, sans rattrapage.")

    with right:
        st.subheader("Taux de reponses inexploitables")
        figure = _rate_bar(summary, "unparseable_rate", color=theme.UNPARSEABLE)
        figure.update_yaxes(range=None, autorange=True)
        components.chart(figure, key="unparseable_rate")

    st.space("medium")
    st.subheader("Exactitude sur les seules reponses exploitables")
    figure = _rate_bar(summary, "accuracy_parsed_only", color=theme.CORRECT)
    components.chart(figure, key="accuracy_parsed")
    theme.note(
        "En excluant les reponses inexploitables du denominateur, on isole la connaissance "
        "de la capacite a respecter un format."
    )


def _render_length(summary: pl.DataFrame, lengths: pl.DataFrame) -> None:
    """Longueur des reponses selon leur verdict : le modele s'etend-il quand il se trompe ?"""
    if lengths.height == 0:
        components.empty_state("Aucune donnee de longueur pour cette selection.")
        return

    modele = _choisir_modele(summary, key="length_model")
    if modele is not None:
        lengths = lengths.filter(pl.col("model_short") == modele)

    # Trois verdicts : juste, fausse (une reponse a bien ete lue), inexploitable (rien de
    # lisible). Les moyennes sont ponderees par l'effectif de chaque mode de notation.
    verdict = (
        pl.when(pl.col("ai_correct"))
        .then(pl.lit("Juste"))
        .when(pl.col("grade").is_in(["unparseable", "error"]))
        .then(pl.lit("Inexploitable"))
        .otherwise(pl.lit("Fausse"))
    )
    agg = (
        lengths.with_columns(verdict.alias("verdict"))
        .group_by(["prompt_variant", "variant_label", "verdict"])
        .agg(
            ((pl.col("mean_completion_tokens") * pl.col("n")).sum() / pl.col("n").sum()).alias(
                "tokens"
            ),
            ((pl.col("mean_answer_chars") * pl.col("n")).sum() / pl.col("n").sum()).alias("chars"),
            pl.col("n").sum().alias("n"),
        )
        .sort(["variant_label", "verdict"])
    )

    # La phrase de synthese porte sur les variantes en texte court : la variante JSON produit
    # une quinzaine de tokens d'enveloppe quel que soit le verdict, et une moyenne qui la
    # melangerait aux deux autres ne dirait plus rien. Repli sur toute la selection si elle
    # ne contient que des variantes a sortie contrainte.
    structurees = [key for key, variant in PROMPT_VARIANTS.items() if variant.structured]
    courtes = agg.filter(~pl.col("prompt_variant").is_in(structurees))
    base, cadre = (courtes, "Sur les variantes en texte court, ") if courtes.height else (agg, "")

    def moyenne(frame: pl.DataFrame) -> float:
        if frame.height == 0:
            return 0.0
        return float((frame["tokens"] * frame["n"]).sum() / max(int(frame["n"].sum()), 1))

    def nombre(value: float) -> str:
        return f"{value:.1f}".replace(".", ",")

    justes = moyenne(base.filter(pl.col("verdict") == "Juste"))
    fausses = moyenne(base.filter(pl.col("verdict") == "Fausse"))
    inexploitables = base.filter(pl.col("verdict") == "Inexploitable")
    phrase = (
        f"{cadre}une reponse juste fait en moyenne <strong>{nombre(justes)} tokens</strong>, "
        f"une reponse fausse {nombre(fausses)} : la longueur ne trahit pas l'erreur."
    )
    if inexploitables.height:
        phrase += (
            f" Les reponses inexploitables montent a <strong>{nombre(moyenne(inexploitables))} "
            "tokens</strong> : le modele ne s'etend pas quand il se trompe, il s'etend quand il "
            "refuse de repondre."
        )
    theme.lede(phrase[0].upper() + phrase[1:])

    colors = {"Juste": theme.CORRECT, "Fausse": theme.WRONG, "Inexploitable": theme.UNPARSEABLE}
    left, right = st.columns(2, gap="medium")
    with left:
        st.subheader("Tokens generes")
        figure = charts.grouped_value_bar(
            agg,
            x="variant_label",
            group="verdict",
            y="tokens",
            y_title="Tokens (moyenne)",
            colors=colors,
            height=360,
        )
        components.chart(figure, key="length_tokens")
    with right:
        st.subheader("Caracteres de la reponse")
        figure = charts.grouped_value_bar(
            agg,
            x="variant_label",
            group="verdict",
            y="chars",
            y_title="Caracteres (moyenne)",
            colors=colors,
            height=360,
        )
        components.chart(figure, key="length_chars")
    theme.note(
        "La variante JSON produit une quinzaine de tokens quel que soit le verdict : c'est "
        "l'enveloppe imposee par le schema, pas une hesitation. Les deux variantes en texte "
        "court tiennent en deux tokens quand elles repondent, et debordent quand elles refusent."
    )


def _render_templates(summary: pl.DataFrame) -> None:
    """Affiche les gabarits de prompt versionnes."""
    variants = summary.select("prompt_variant", "variant_label").unique().sort("prompt_variant")
    for row in variants.iter_rows(named=True):
        variant_id = row["prompt_variant"]
        with st.container(border=True, key=f"tpl_{variant_id}"):
            st.markdown(f"**{row['variant_label']}**")
            variant = PROMPT_VARIANTS.get(variant_id)
            st.caption(variant.description if variant else "")

            system_path = PROMPTS_DIR / f"{variant_id}.system.txt"
            if system_path.exists():
                st.caption("Prompt systeme")
                st.code(system_path.read_text(encoding="utf-8"), language="text", wrap_lines=True)

            for question_type, label in (("multiple", "Choix multiples"), ("boolean", "Vrai/Faux")):
                path = PROMPTS_DIR / f"{variant_id}.{question_type}.txt"
                if path.exists():
                    st.caption(f"Gabarit · {label}")
                    st.code(path.read_text(encoding="utf-8"), language="text", wrap_lines=True)

    version_file = PROMPTS_DIR / "VERSION"
    if version_file.exists():
        theme.note(
            f"Version des gabarits : {version_file.read_text(encoding='utf-8').strip()}. "
            "L'empreinte du prompt effectivement envoye est enregistree avec chaque reponse."
        )
