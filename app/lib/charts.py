"""Fabrique de figures Plotly homogenes.

Toutes les figures du dashboard passent par ce module : memes marges, meme grille discrete,
meme facon d'afficher les pourcentages et les intervalles de confiance. Les couleurs de fond
sont transparentes pour que le theme clair ou sombre de Streamlit s'applique tel quel.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import polars as pl

from lib import theme

GRID = "rgba(128,128,128,0.16)"


def with_alpha(color: str, alpha: float) -> str:
    """Convertit une couleur hexadecimale en rgba : Plotly n'accepte pas la notation #RRGGBBAA."""
    value = color.lstrip("#")
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red},{green},{blue},{alpha})"


def base_figure(height: int = 380, *, showlegend: bool = False) -> go.Figure:
    """Figure vide deja mise en forme."""
    figure = go.Figure()
    figure.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 28, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=showlegend,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "title": None,
        },
        hoverlabel={"font_size": 13},
        bargap=0.28,
    )
    figure.update_xaxes(showgrid=False, zeroline=False)
    figure.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    return figure


def accuracy_bar(
    frame: pl.DataFrame,
    *,
    x: str,
    y: str = "accuracy",
    lo: str | None = "wilson_lo",
    hi: str | None = "wilson_hi",
    n: str | None = "n",
    baseline: float | None = None,
    baseline_label: str = "hasard",
    color: str | list[str] = theme.PRIMARY,
    height: int = 400,
    horizontal: bool = False,
) -> go.Figure:
    """Barres d'exactitude avec barres d'erreur de Wilson et ligne du niveau du hasard."""
    figure = base_figure(height)
    values = frame[y].to_list()
    labels = frame[x].to_list()
    counts = frame[n].to_list() if n and n in frame.columns else [None] * len(values)

    error = None
    if lo and hi and lo in frame.columns and hi in frame.columns:
        error = {
            "type": "data",
            "symmetric": False,
            "array": [
                (h - v) if h is not None and v is not None else 0
                for h, v in zip(frame[hi].to_list(), values, strict=True)
            ],
            "arrayminus": [
                (v - low) if low is not None and v is not None else 0
                for low, v in zip(frame[lo].to_list(), values, strict=True)
            ],
            "color": "rgba(128,128,128,0.65)",
            "thickness": 1.4,
            "width": 4,
        }

    # Une barre seule occuperait toute la largeur de l'axe : on la borne pour rester lisible.
    bar_width = 0.4 if len(values) <= 2 else None

    hover = (
        "<b>%{customdata[0]}</b><br>Exactitude : %{y:.1%}"
        "<br>Questions : %{customdata[1]}<extra></extra>"
    )
    if horizontal:
        hover = (
            "<b>%{customdata[0]}</b><br>Exactitude : %{x:.1%}"
            "<br>Questions : %{customdata[1]}<extra></extra>"
        )

    custom = list(zip(labels, counts, strict=True))

    if horizontal:
        figure.add_trace(
            go.Bar(
                x=values,
                y=labels,
                orientation="h",
                width=bar_width,
                marker_color=color,
                error_x=error,
                customdata=custom,
                hovertemplate=hover,
                texttemplate="%{x:.0%}",
                textposition="outside",
                cliponaxis=False,
            )
        )
        figure.update_xaxes(tickformat=".0%", showgrid=True, gridcolor=GRID, range=[0, 1.08])
        figure.update_yaxes(showgrid=False)
        if baseline is not None:
            figure.add_vline(
                x=baseline,
                line_dash="dot",
                line_color=theme.NEUTRAL,
                annotation_text=baseline_label,
                annotation_position="top",
            )
    else:
        figure.add_trace(
            go.Bar(
                x=labels,
                y=values,
                width=bar_width,
                marker_color=color,
                error_y=error,
                customdata=custom,
                hovertemplate=hover,
                texttemplate="%{y:.1%}",
                textposition="outside",
                cliponaxis=False,
            )
        )
        figure.update_yaxes(tickformat=".0%", range=[0, 1.12])
        if baseline is not None:
            figure.add_hline(
                y=baseline,
                line_dash="dot",
                line_color=theme.NEUTRAL,
                annotation_text=baseline_label,
                annotation_position="top right",
                annotation_font_size=11,
            )
        figure.update_layout(margin={"l": 8, "r": 96, "t": 28, "b": 8})
    return figure


def grouped_accuracy_bar(
    frame: pl.DataFrame,
    *,
    x: str,
    group: str,
    y: str = "accuracy",
    lo: str | None = "wilson_lo",
    hi: str | None = "wilson_hi",
    baselines: dict[str, float] | None = None,
    height: int = 400,
    text: bool = False,
    y_label: str = "Exactitude",
) -> go.Figure:
    """Barres groupees : une couleur par serie, intervalles de confiance quand ils existent.

    Des que plusieurs runs partagent une abscisse, une barre simple les superposerait et ne
    laisserait voir que le dernier trace : le groupage est la seule facon de montrer chaque
    run. `lo` et `hi` valent `None` pour les taux sans intervalle (conformite, longueur).
    """
    figure = base_figure(height, showlegend=True)
    with_error = lo is not None and hi is not None and lo in frame.columns and hi in frame.columns
    for index, (key, part) in enumerate(sorted(frame.group_by(group), key=lambda item: item[0])):
        label = key[0] if isinstance(key, tuple) else key
        error_y = None
        if with_error:
            error_y = {
                "type": "data",
                "symmetric": False,
                "array": [
                    h - v for h, v in zip(part[hi].to_list(), part[y].to_list(), strict=True)
                ],
                "arrayminus": [
                    v - low for low, v in zip(part[lo].to_list(), part[y].to_list(), strict=True)
                ],
                "color": "rgba(128,128,128,0.6)",
                "thickness": 1.3,
                "width": 3,
            }
        figure.add_trace(
            go.Bar(
                name=str(label),
                x=part[x].to_list(),
                y=part[y].to_list(),
                marker_color=theme.CATEGORICAL[index % len(theme.CATEGORICAL)],
                error_y=error_y,
                texttemplate="%{y:.1%}" if text else None,
                textposition="outside" if text else None,
                cliponaxis=False,
                hovertemplate=f"<b>{label}</b> · %{{x}}<br>{y_label} : %{{y:.1%}}<extra></extra>",
            )
        )
    figure.update_layout(barmode="group")
    figure.update_yaxes(tickformat=".0%", range=[0, 1.1])

    for index, (label, value) in enumerate(sorted((baselines or {}).items(), key=lambda i: i[1])):
        figure.add_hline(
            y=value,
            line_dash="dot",
            line_color=theme.NEUTRAL,
            annotation_text=label,
            annotation_position="top right" if index else "bottom right",
            annotation_font_size=11,
        )
    if baselines:
        figure.update_layout(margin={"l": 8, "r": 128, "t": 28, "b": 8})
    return figure


def heatmap(
    matrix: list[list[float | None]],
    *,
    x_labels: list[str],
    y_labels: list[str],
    counts: list[list[int]] | None = None,
    height: int = 520,
) -> go.Figure:
    """Carte de chaleur d'exactitude, annotee des valeurs."""
    figure = base_figure(height)
    custom = counts if counts is not None else [[0] * len(x_labels) for _ in y_labels]
    figure.add_trace(
        go.Heatmap(
            z=matrix,
            x=x_labels,
            y=y_labels,
            customdata=custom,
            colorscale=[[index / 9, color] for index, color in enumerate(theme.SEQUENTIAL)],
            zmin=0,
            zmax=1,
            texttemplate="%{z:.0%}",
            textfont={"size": 11},
            hovertemplate=(
                "<b>%{y}</b> · %{x}<br>Exactitude : %{z:.1%}"
                "<br>Questions : %{customdata}<extra></extra>"
            ),
            colorbar={"tickformat": ".0%", "thickness": 12, "outlinewidth": 0, "title": None},
            hoverongaps=False,
        )
    )
    figure.update_xaxes(showgrid=False, side="top")
    figure.update_yaxes(showgrid=False, autorange="reversed")
    figure.update_layout(margin={"l": 8, "r": 8, "t": 42, "b": 8})
    return figure


def stacked_shares(
    frame: pl.DataFrame,
    *,
    x: str,
    category: str,
    value: str,
    colors: dict[str, str],
    labels: dict[str, str] | None = None,
    order: list[str] | None = None,
    height: int = 380,
) -> go.Figure:
    """Barres empilees en pourcentage (repartition des modes de notation)."""
    figure = base_figure(height, showlegend=True)
    keys = order or sorted(frame[category].unique().to_list())
    for key in keys:
        part = frame.filter(pl.col(category) == key).sort(x)
        if part.height == 0:
            continue
        label = (labels or {}).get(key, key)
        figure.add_trace(
            go.Bar(
                name=label,
                x=part[x].to_list(),
                y=part[value].to_list(),
                marker_color=colors.get(key, theme.NEUTRAL),
                hovertemplate=f"<b>{label}</b> · %{{x}}<br>%{{y:.1%}}<extra></extra>",
            )
        )
    figure.update_layout(barmode="stack")
    figure.update_yaxes(tickformat=".0%", range=[0, 1])
    return figure


def violin_latency(
    frame: pl.DataFrame,
    *,
    group: str,
    value: str = "response_time",
    height: int = 420,
    log_scale: bool = False,
) -> go.Figure:
    """Distribution des temps de reponse : violon et boite par serie."""
    figure = base_figure(height)
    for index, key in enumerate(sorted(frame[group].unique().to_list())):
        part = frame.filter(pl.col(group) == key)
        color = theme.CATEGORICAL[index % len(theme.CATEGORICAL)]
        figure.add_trace(
            go.Violin(
                name=str(key),
                y=part[value].to_list(),
                line_color=color,
                fillcolor=with_alpha(color, 0.22),
                box_visible=True,
                meanline_visible=False,
                points=False,
                hovertemplate="<b>%{x}</b><br>%{y:.2f} s<extra></extra>",
            )
        )
    figure.update_yaxes(
        title="Temps de reponse (s)", type="log" if log_scale else "linear", ticksuffix=" s"
    )
    return figure


def ecdf(
    series: dict[str, list[float]],
    *,
    x_title: str = "Temps de reponse (s)",
    height: int = 380,
) -> go.Figure:
    """Fonction de repartition empirique : lit directement les quantiles."""
    figure = base_figure(height, showlegend=True)
    for index, (label, values) in enumerate(series.items()):
        if not values:
            continue
        ordered = sorted(values)
        cumulative = [(rank + 1) / len(ordered) for rank in range(len(ordered))]
        figure.add_trace(
            go.Scatter(
                name=label,
                x=ordered,
                y=cumulative,
                mode="lines",
                line={"color": theme.CATEGORICAL[index % len(theme.CATEGORICAL)], "width": 2},
                hovertemplate=f"<b>{label}</b><br>%{{x:.2f}} s · %{{y:.0%}}<extra></extra>",
            )
        )
    figure.update_xaxes(title=x_title, ticksuffix=" s")
    figure.update_yaxes(tickformat=".0%", title="Part des reponses", range=[0, 1])
    return figure


def lines(
    frame: pl.DataFrame,
    *,
    x: str,
    y: str,
    group: str,
    y_title: str,
    y_format: str | None = None,
    height: int = 360,
) -> go.Figure:
    """Courbes par serie (derive du debit au fil d'un run)."""
    figure = base_figure(height, showlegend=True)
    for index, key in enumerate(sorted(frame[group].unique().to_list())):
        part = frame.filter(pl.col(group) == key).sort(x)
        figure.add_trace(
            go.Scatter(
                name=str(key),
                x=part[x].to_list(),
                y=part[y].to_list(),
                mode="lines+markers",
                line={"color": theme.CATEGORICAL[index % len(theme.CATEGORICAL)], "width": 2},
                marker={"size": 5},
                hovertemplate=f"<b>{key}</b><br>%{{x}} · %{{y:.2f}}<extra></extra>",
            )
        )
    figure.update_xaxes(title="Rang d'execution dans le run", showgrid=True, gridcolor=GRID)
    figure.update_yaxes(title=y_title, tickformat=y_format)
    return figure


def scatter(
    frame: pl.DataFrame,
    *,
    x: str,
    y: str,
    group: str,
    x_title: str,
    y_title: str,
    height: int = 400,
    opacity: float = 0.45,
) -> go.Figure:
    """Nuage de points par serie."""
    figure = base_figure(height, showlegend=True)
    for index, key in enumerate(sorted(frame[group].unique().to_list())):
        part = frame.filter(pl.col(group) == key)
        figure.add_trace(
            go.Scattergl(
                name=str(key),
                x=part[x].to_list(),
                y=part[y].to_list(),
                mode="markers",
                marker={
                    "size": 5,
                    "color": theme.CATEGORICAL[index % len(theme.CATEGORICAL)],
                    "opacity": opacity,
                },
                hovertemplate=f"<b>{key}</b><br>%{{x}} · %{{y:.2f}} s<extra></extra>",
            )
        )
    figure.update_xaxes(title=x_title, showgrid=True, gridcolor=GRID)
    figure.update_yaxes(title=y_title)
    return figure


def matrix_annotated(
    matrix: list[list[float | None]],
    *,
    labels: list[str],
    text: list[list[str]],
    height: int = 460,
    colorscale: list[list[Any]] | None = None,
) -> go.Figure:
    """Matrice carree annotee (p-values des comparaisons appariees)."""
    figure = base_figure(height)
    figure.add_trace(
        go.Heatmap(
            z=matrix,
            x=labels,
            y=labels,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 11},
            colorscale=colorscale
            or [[0, "#46A758"], [0.05, "#FFB224"], [0.2, "#EDEDF2"], [1, "#EDEDF2"]],
            zmin=0,
            zmax=1,
            hovertemplate="<b>%{y}</b> contre <b>%{x}</b><br>%{text}<extra></extra>",
            showscale=False,
            hoverongaps=False,
        )
    )
    figure.update_xaxes(showgrid=False, side="top")
    figure.update_yaxes(showgrid=False, autorange="reversed")
    figure.update_layout(margin={"l": 8, "r": 8, "t": 42, "b": 8})
    return figure


def grouped_value_bar(
    frame: pl.DataFrame,
    *,
    x: str,
    group: str,
    y: str,
    y_title: str,
    y_suffix: str = "",
    colors: dict[str, str] | None = None,
    height: int = 360,
) -> go.Figure:
    """Barres groupees pour une grandeur qui n'est pas un pourcentage (tokens, caracteres)."""
    figure = base_figure(height, showlegend=True)
    for index, (key, part) in enumerate(sorted(frame.group_by(group), key=lambda item: item[0])):
        label = str(key[0] if isinstance(key, tuple) else key)
        color = (colors or {}).get(label, theme.CATEGORICAL[index % len(theme.CATEGORICAL)])
        figure.add_trace(
            go.Bar(
                name=label,
                x=part[x].to_list(),
                y=part[y].to_list(),
                marker_color=color,
                texttemplate="%{y:.1f}",
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    f"<b>{label}</b> · %{{x}}<br>{y_title} : %{{y:.2f}}{y_suffix}<extra></extra>"
                ),
            )
        )
    figure.update_layout(barmode="group")
    figure.update_yaxes(title=y_title, ticksuffix=y_suffix, rangemode="tozero")
    return figure


def tradeoff_scatter(
    frame: pl.DataFrame,
    *,
    x: str,
    y: str,
    size: str,
    label: str,
    group: str,
    x_title: str,
    y_title: str,
    size_title: str,
    height: int = 440,
) -> go.Figure:
    """Nuage exactitude contre vitesse : un point par run, une couleur par variante.

    La surface du disque suit la taille du modele sur disque, pour que le compromis se lise
    d'un coup d'oeil : plus haut et plus a gauche est meilleur, plus gros est plus lourd.
    """
    figure = base_figure(height, showlegend=True)
    sizes = frame[size].to_list()
    smallest, largest = min(sizes), max(sizes)
    span = max(largest - smallest, 1e-9)

    def diameter(value: float) -> float:
        return 14 + 22 * (value - smallest) / span

    for index, key in enumerate(sorted(frame[group].unique().to_list())):
        part = frame.filter(pl.col(group) == key)
        color = theme.CATEGORICAL[index % len(theme.CATEGORICAL)]
        figure.add_trace(
            go.Scatter(
                name=str(key),
                x=part[x].to_list(),
                y=part[y].to_list(),
                mode="markers+text",
                text=part[label].to_list(),
                textposition="top center",
                textfont={"size": 11},
                customdata=part[size].to_list(),
                marker={
                    "size": [diameter(value) for value in part[size].to_list()],
                    "color": with_alpha(color, 0.55),
                    "line": {"width": 1.5, "color": color},
                },
                hovertemplate=(
                    "<b>%{text}</b> · " + str(key) + "<br>"
                    f"{y_title} : %{{y:.1%}}<br>{x_title} : %{{x:.2f}} s<br>"
                    f"{size_title} : %{{customdata:.2f}} Go<extra></extra>"
                ),
            )
        )
    figure.update_xaxes(
        title=x_title, ticksuffix=" s", showgrid=True, gridcolor=GRID, rangemode="tozero"
    )
    figure.update_yaxes(title=y_title, tickformat=".0%")
    figure.update_layout(margin={"l": 8, "r": 24, "t": 28, "b": 8})
    return figure
