"""Constantes visuelles et feuille de style du dashboard.

Les couleurs sont dupliquees ici et dans `.streamlit/config.toml` : le fichier de configuration
pilote les composants Streamlit, ces constantes pilotent les figures Plotly construites a la
main (barres d'erreur, annotations, lignes de reference).
"""

from __future__ import annotations

import streamlit as st

PRIMARY = "#5B5BD6"
CORRECT = "#46A758"
WRONG = "#E5484D"
UNPARSEABLE = "#FFB224"
ERROR = "#8B8B9E"
NEUTRAL = "#8B8B9E"

CATEGORICAL = [
    "#5B5BD6",
    "#12A594",
    "#FFB224",
    "#E5484D",
    "#0091FF",
    "#8E4EC6",
    "#46A758",
    "#F76B15",
    "#00A2C7",
    "#E93D82",
]

SEQUENTIAL = [
    "#F2F2FD",
    "#E5E5FA",
    "#D4D4F6",
    "#C0C0F1",
    "#A9A9EB",
    "#9090E4",
    "#7676DD",
    "#5B5BD6",
    "#4646B8",
    "#33338F",
]

# Une seule definition par couleur : la table des notations reference les constantes
# semantiques plutot que de repeter leurs valeurs.
GRADE_COLORS = {
    "letter": PRIMARY,
    "exact": "#12A594",
    "fuzzy": CORRECT,
    "contains": "#0091FF",
    "wrong": WRONG,
    "unparseable": UNPARSEABLE,
    "error": ERROR,
}

GRADE_LABELS = {
    "letter": "Lettre extraite",
    "exact": "Texte exact",
    "fuzzy": "Rapprochement approche",
    "contains": "Reponse contenue",
    "wrong": "Fausse",
    "unparseable": "Inexploitable",
    "error": "Erreur d'appel",
}

DIFFICULTY_LABELS = {"easy": "Facile", "medium": "Moyen", "hard": "Difficile"}
TYPE_LABELS = {"multiple": "Choix multiples", "boolean": "Vrai / Faux"}

_CSS = """
<style>
/* Titre de page : une seule respiration verticale, pas de marge doublee */
.block-container { padding-top: 4.2rem; padding-bottom: 4rem; max-width: 1500px; }

/* En-tete de page */
.tb-header { margin-bottom: .25rem; }
.tb-header h1 { font-size: 1.9rem; font-weight: 650; letter-spacing: -.02em; margin: 0; }
.tb-header p { opacity: .72; margin: .35rem 0 0; font-size: .95rem; }

/* Phrase de synthese en tete de page */
.tb-lede {
    border-left: 3px solid #5B5BD6;
    padding: .1rem 0 .1rem .85rem;
    margin: .1rem 0 .2rem;
    font-size: 1.02rem;
    line-height: 1.5;
}
.tb-lede strong { font-weight: 640; }

/* Cartes de metriques : bordure discrete, coin arrondi, survol leger */
div[data-testid="stMetric"] {
    border-radius: 14px;
    padding: 1rem 1.1rem;
    transition: border-color .15s ease;
}
div[data-testid="stMetric"]:hover { border-color: #5B5BD6; }
div[data-testid="stMetricValue"] { font-weight: 650; letter-spacing: -.02em; }

/* Legende sous un graphique */
.tb-note { opacity: .72; font-size: .84rem; line-height: 1.45; margin-top: -.4rem; }

/* Pastille de grade dans les tableaux et le detail de question */
.tb-pill {
    display: inline-block; padding: .12rem .6rem; border-radius: 999px;
    font-size: .78rem; font-weight: 600; letter-spacing: .01em;
}

/* Bloc de reponse dans l'explorateur */
.tb-answer {
    border-radius: 10px; padding: .7rem .9rem; margin: .3rem 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .86rem;
    white-space: pre-wrap; word-break: break-word;
}
</style>
"""


def inject_css() -> None:
    """Injecte la feuille de style globale, une seule fois par execution."""
    st.html(_CSS)


def page_header(title: str, subtitle: str, icon: str = "") -> None:
    """Affiche un titre de page homogene."""
    prefix = f"{icon} " if icon else ""
    st.html(f'<div class="tb-header"><h1>{prefix}{title}</h1><p>{subtitle}</p></div>')


def lede(html: str) -> None:
    """Affiche la phrase de synthese calculee a partir des donnees."""
    st.html(f'<div class="tb-lede">{html}</div>')


def note(text: str) -> None:
    """Affiche une note explicative sous un graphique."""
    st.html(f'<div class="tb-note">{text}</div>')


def grade_pill(grade: str) -> str:
    """Retourne le HTML d'une pastille coloree pour un mode de notation."""
    color = GRADE_COLORS.get(grade, NEUTRAL)
    label = GRADE_LABELS.get(grade, grade)
    return (
        f'<span class="tb-pill" style="background:{color}22;color:{color};'
        f'border:1px solid {color}55">{label}</span>'
    )
