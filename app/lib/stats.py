"""Statistiques calculees a la volee pour le dashboard.

Les intervalles de Wilson sont deja calcules dans la couche gold ; ce module couvre les tests
qui dependent d'une selection faite par l'utilisateur : comparaison appariee de deux variantes
et intervalle de confiance de leur ecart.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import streamlit as st
from scipy import stats


@dataclass(frozen=True, slots=True)
class McNemarResult:
    """Resultat d'un test de McNemar sur donnees appariees."""

    n_discordant: int
    a_only: int
    b_only: int
    p_value: float
    method: str

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05


def mcnemar(a_only: int, b_only: int) -> McNemarResult:
    """Compare deux variantes evaluees sur les memes questions.

    Seules les paires discordantes portent de l'information : les questions reussies ou ratees
    par les deux variantes n'aident pas a les departager. En dessous de 25 paires discordantes,
    le test binomial exact est prefere a l'approximation du khi-deux.

    Les comptages arrivent de DuckDB en decimal ; scipy refuse ce type. La conversion est faite
    ici plutot que chez chaque appelant, la signature promettant deja des entiers.
    """
    a_only, b_only = int(a_only), int(b_only)
    n = a_only + b_only
    if n == 0:
        return McNemarResult(0, a_only, b_only, 1.0, "aucune paire discordante")

    if n < 25:
        p_value = float(stats.binomtest(min(a_only, b_only), n, 0.5).pvalue)
        return McNemarResult(n, a_only, b_only, p_value, "test binomial exact")

    statistic = (abs(a_only - b_only) - 1) ** 2 / n
    p_value = float(stats.chi2.sf(statistic, df=1))
    return McNemarResult(n, a_only, b_only, p_value, "khi-deux avec correction de continuite")


@st.cache_data(ttl=600, show_spinner=False)
def bootstrap_diff_ci(
    correct_a: list[bool],
    correct_b: list[bool],
    *,
    iterations: int = 5000,
    seed: int = 42,
) -> tuple[float, float]:
    """Intervalle de confiance a 95 % de l'ecart d'exactitude entre deux variantes.

    Le reechantillonnage porte sur les questions, pas sur les reponses independamment :
    les deux variantes repondent aux memes questions, l'appariement doit etre conserve.
    """
    array_a = np.asarray(correct_a, dtype=float)
    array_b = np.asarray(correct_b, dtype=float)
    size = array_a.size
    if size == 0:
        return (0.0, 0.0)

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, size, size=(iterations, size))
    diffs = array_a[indices].mean(axis=1) - array_b[indices].mean(axis=1)
    low, high = np.percentile(diffs, [2.5, 97.5])
    return (float(low), float(high))


def spearman(x: list[float], y: list[float]) -> tuple[float, float]:
    """Correlation de rang, utilisee pour juger la calibration de la difficulte declaree."""
    if len(x) < 3:
        return (float("nan"), float("nan"))
    result = stats.spearmanr(x, y)
    return (float(result.statistic), float(result.pvalue))


def format_p_value(p_value: float) -> str:
    """Met en forme une p-value pour l'affichage."""
    if p_value < 0.001:
        return "p < 0,001"
    return f"p = {p_value:.3f}".replace(".", ",")
