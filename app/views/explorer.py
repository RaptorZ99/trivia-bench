"""Explorateur : descendre a la question, voir ce que le modele a repondu."""

from __future__ import annotations

import polars as pl
import streamlit as st

from lib import components, db, queries, theme


def render(selection: queries.Selection | None) -> None:
    """Recherche et inspection des reponses question par question."""
    theme.page_header(
        "Explorateur de questions",
        "Chercher une question, comparer les reponses des variantes, reperer les cas litigieux.",
    )

    if selection is None:
        components.empty_state("Aucune donnee disponible.")
        return

    try:
        summary = selection.apply(queries.run_summary())
        questions = queries.questions()
        consistency = queries.question_consistency()
    except db.DatabaseUnavailableError as exc:
        st.error(str(exc), icon=":material/database_off:")
        return

    if summary.height == 0:
        components.empty_state("Aucun run ne correspond aux filtres selectionnes.")
        return

    browse, consistency_tab = st.tabs(["Parcourir", "Questions revelatrices"])

    with browse:
        _render_browser(summary, questions)

    with consistency_tab:
        _render_consistency(consistency)


def _render_browser(summary: pl.DataFrame, questions: pl.DataFrame) -> None:
    """Tableau filtrable des reponses, avec panneau de detail."""
    labels = components.run_labels(summary)
    run_ids = summary.sort("accuracy", descending=True)["run_id"].to_list()

    filters = st.columns([2, 2, 2, 2, 3], gap="small")
    with filters[0]:
        selected_runs = st.multiselect(
            "Runs",
            options=run_ids,
            default=run_ids[:1],
            format_func=lambda value: labels.get(value, value),
            placeholder="Choisir un ou plusieurs runs",
        )
    with filters[1]:
        selected_categories = st.multiselect(
            "Themes",
            options=sorted(questions["category"].unique().to_list()),
            placeholder="Tous les themes",
        )
    with filters[2]:
        selected_difficulties = st.multiselect(
            "Difficulte",
            options=["easy", "medium", "hard"],
            format_func=lambda value: theme.DIFFICULTY_LABELS.get(value, value),
            placeholder="Toutes",
        )
    with filters[3]:
        selected_grades = st.multiselect(
            "Notation",
            options=list(theme.GRADE_LABELS),
            format_func=lambda value: theme.GRADE_LABELS.get(value, value),
            placeholder="Toutes",
        )
    with filters[4]:
        search = st.text_input(
            "Recherche", placeholder="Mot-cle dans la question ou la reponse attendue"
        )

    if not selected_runs:
        components.empty_state("Selectionner au moins un run.")
        return

    rows = queries.explorer_rows(
        selected_runs,
        categories=selected_categories or None,
        difficulties=selected_difficulties or None,
        grades=selected_grades or None,
        search=search,
        limit=500,
    )

    if rows.height == 0:
        components.empty_state("Aucune question ne correspond a ces filtres.")
        return

    st.caption(f"{rows.height} ligne(s) affichee(s), limite a 500.")

    display = rows.select(
        pl.col("question").alias("Question"),
        pl.col("correct_answer").alias("Reponse attendue"),
        pl.col("ai_answer").alias("Reponse du modele"),
        pl.col("ai_correct").alias("Juste"),
        pl.col("grade").replace_strict(theme.GRADE_LABELS, default="?").alias("Notation"),
        pl.col("variant_label").alias("Variante"),
        pl.col("category").alias("Theme"),
        pl.col("difficulty")
        .replace_strict(theme.DIFFICULTY_LABELS, default="?")
        .alias("Difficulte"),
        pl.col("response_time").alias("Temps"),
    )

    event = st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=420,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Question": st.column_config.TextColumn("Question", width="large"),
            "Juste": st.column_config.CheckboxColumn("Juste"),
            "Temps": st.column_config.NumberColumn("Temps", format="%.2f s"),
        },
    )
    components.download(display, filename="reponses.csv")

    selected_rows = event.selection.rows if event and event.selection else []
    if not selected_rows:
        theme.note("Selectionner une ligne pour voir le detail de la question.")
        return

    question_id = rows.row(selected_rows[0], named=True)["question_id"]
    _render_detail(question_id, questions)


def _render_detail(question_id: str, questions: pl.DataFrame) -> None:
    """Panneau de detail d'une question : options, et reponse de chaque variante."""
    match = questions.filter(pl.col("question_id") == question_id)
    if match.height == 0:
        return
    question = match.row(0, named=True)
    answers = queries.answers_for_question(question_id)

    st.space("medium")
    with st.container(border=True, key="question_detail"):
        st.markdown(f"### {question['question']}")
        st.caption(
            f"{question['category']} · "
            f"{theme.DIFFICULTY_LABELS.get(question['difficulty'], question['difficulty'])} · "
            f"{theme.TYPE_LABELS.get(question['type'], question['type'])} · "
            f"identifiant {question['question_id'][:12]}"
        )

        st.space("xsmall")
        option_columns = st.columns(len(question["options"]), gap="small")
        for index, (column, option) in enumerate(
            zip(option_columns, question["options"], strict=True)
        ):
            letter = "ABCD"[index]
            is_correct = index == question["correct_index"]
            with column, st.container(border=True):
                st.markdown(
                    f"**{letter}.** {option}"
                    + ("  \n:material/check_circle: bonne reponse" if is_correct else "")
                )

        st.space("small")
        st.markdown("**Reponses obtenues**")
        for row in answers.iter_rows(named=True):
            verdict = ":material/check_circle:" if row["ai_correct"] else ":material/cancel:"
            columns = st.columns([3, 5, 2], gap="small", vertical_alignment="center")
            with columns[0]:
                st.markdown(f"{verdict} **{row['variant_label']}**")
                st.caption(f"{row['model_short']} · {components.seconds(row['response_time'])}")
            with columns[1]:
                st.html(
                    f'<div class="tb-answer" style="background:rgba(128,128,128,.08)">'
                    f"{_escape(row['ai_answer']) or '<em>(vide)</em>'}</div>"
                )
            with columns[2]:
                st.html(theme.grade_pill(row["grade"]))

            if row["ai_reasoning"]:
                with st.expander("Raisonnement du modele", icon=":material/psychology:"):
                    st.text(row["ai_reasoning"])


def _render_consistency(consistency: pl.DataFrame) -> None:
    """Questions ratees par toutes les variantes, ou instables."""
    if consistency.height == 0:
        components.empty_state("Pas encore assez de runs pour analyser la coherence.")
        return

    multi = consistency.filter(pl.col("n_runs") > 1)
    if multi.height == 0:
        components.empty_state(
            "Cette analyse compare les variantes entre elles : elle demande au moins deux runs."
        )
        return

    n_all_wrong = int(multi["all_wrong"].sum())
    n_all_correct = int(multi["all_correct"].sum())
    n_mixed = int(multi["is_mixed"].sum())

    theme.lede(
        f"Sur {components.number(multi.height)} questions evaluees par plusieurs variantes, "
        f"<strong>{components.number(n_all_wrong)}</strong> sont ratees par toutes "
        f"({components.percent(n_all_wrong / multi.height)}), "
        f"{components.number(n_all_correct)} sont reussies par toutes, et "
        f"{components.number(n_mixed)} donnent des reponses divergentes selon la formulation."
    )

    components.kpi_row(
        [
            {
                "label": "Ratees par toutes",
                "value": components.number(n_all_wrong),
                "help": "Candidates a une lacune reelle ou a une question ambigue.",
                "icon": ":material/dangerous:",
            },
            {
                "label": "Reussies par toutes",
                "value": components.number(n_all_correct),
                "icon": ":material/verified:",
            },
            {
                "label": "Sensibles a la formulation",
                "value": components.number(n_mixed),
                "help": "La reponse change selon la maniere de poser la question : "
                "c'est la marge de manoeuvre du prompt.",
                "icon": ":material/shuffle:",
            },
        ],
        key="kpi_consistency",
    )

    st.space("medium")
    mode = st.segmented_control(
        "Afficher",
        options=["Ratees par toutes", "Sensibles a la formulation"],
        default="Ratees par toutes",
    )
    subset = (
        multi.filter(pl.col("all_wrong"))
        if mode == "Ratees par toutes"
        else multi.filter(pl.col("is_mixed"))
    )

    display = subset.sort(["category", "question"]).select(
        pl.col("question").alias("Question"),
        pl.col("correct_answer").alias("Reponse attendue"),
        pl.col("category").alias("Theme"),
        pl.col("difficulty")
        .replace_strict(theme.DIFFICULTY_LABELS, default="?")
        .alias("Difficulte"),
        pl.col("n_runs").alias("Variantes"),
        pl.col("correct_rate").alias("Taux de reussite"),
        pl.col("n_unparseable").alias("Inexploitables"),
    )
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=420,
        column_config={
            "Question": st.column_config.TextColumn("Question", width="large"),
            "Taux de reussite": st.column_config.ProgressColumn(
                "Taux de reussite", format="percent", min_value=0, max_value=1
            ),
        },
    )
    components.download(display, filename=f"{mode.lower().replace(' ', '_')}.csv")
    theme.note(
        "Une question ratee par toutes les variantes merite une relecture : elle peut etre "
        "datee, ambigue, ou avoir plusieurs reponses defendables."
    )


def _escape(value: str | None) -> str:
    """Echappe le texte affiche dans un bloc HTML."""
    if not value:
        return ""
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
