"""Composants d'interface reutilises par les pages."""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl
import streamlit as st

from lib import theme


def kpi_row(
    metrics: Sequence[dict[str, object]],
    *,
    key: str,
    gap: str = "small",
) -> None:
    """Rangee de cartes de metriques.

    Chaque entree accepte `label`, `value`, et optionnellement `delta`, `help`, `icon`,
    `chart_data` (petite courbe de contexte) et `chart_type`.
    """
    with st.container(key=key):
        columns = st.columns(len(metrics), gap=gap)
        for column, metric in zip(columns, metrics, strict=True):
            with column:
                st.metric(
                    label=str(metric["label"]),
                    value=metric["value"],
                    delta=metric.get("delta"),
                    delta_color=str(metric.get("delta_color", "normal")),
                    help=metric.get("help"),  # type: ignore[arg-type]
                    icon=metric.get("icon"),  # type: ignore[arg-type]
                    border=True,
                    chart_data=metric.get("chart_data"),  # type: ignore[arg-type]
                    chart_type=str(metric.get("chart_type", "bar")),  # type: ignore[arg-type]
                    height="stretch",
                )


def percent(value: float | None, digits: int = 1) -> str:
    """Met en forme un pourcentage a la francaise."""
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f} %".replace(".", ",")


def seconds(value: float | None, digits: int = 2) -> str:
    """Met en forme une duree en secondes."""
    if value is None:
        return "—"
    return f"{value:.{digits}f} s".replace(".", ",")


def number(value: float | int | None, digits: int = 0) -> str:
    """Met en forme un nombre avec un espace comme separateur de milliers."""
    if value is None:
        return "—"
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def interval(lo: float | None, hi: float | None) -> str:
    """Met en forme un intervalle de confiance."""
    if lo is None or hi is None:
        return "—"
    return f"[{percent(lo, 1)} · {percent(hi, 1)}]"


def empty_state(message: str, hint: str = "") -> None:
    """Message affiche quand une selection ne renvoie aucune donnee."""
    st.info(message, icon=":material/filter_alt_off:")
    if hint:
        theme.note(hint)


def download(frame: pl.DataFrame, *, filename: str, label: str = "Telecharger en CSV") -> None:
    """Bouton d'export CSV d'un tableau affiche."""
    st.download_button(
        label,
        data=frame.write_csv(),
        file_name=filename,
        mime="text/csv",
        icon=":material/download:",
        width="content",
    )


def chart(figure: object, *, height: int | None = None, key: str | None = None) -> None:
    """Affiche une figure Plotly avec les reglages communs."""
    extra = {"height": height} if height is not None else {}
    st.plotly_chart(
        figure,
        width="stretch",
        theme="streamlit",
        key=key,
        config={"displayModeBar": False, "scrollZoom": False},
        **extra,
    )
