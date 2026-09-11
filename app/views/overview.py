"""Vue d'ensemble : ce que le benchmark dit en une page."""

from __future__ import annotations

import polars as pl
import streamlit as st

from lib import charts, components, db, queries, theme


def render(selection: queries.Selection | None) -> None:
    """Affiche la synthese du benchmark."""
    theme.page_header(
        "Vue d'ensemble",
        "Performance des modeles evalues, selon la facon dont la question leur est posee.",
    )

    if selection is None:
        components.empty_state(
            "Aucune donnee disponible.",
            "Lancer `uv run trivia bench --all-variants` puis `uv run trivia build`.",
        )
        return

    try:
        summary = selection.apply(queries.run_summary())
        by_type = selection.apply(queries.accuracy_by_type())
        runs = selection.apply(queries.runs())
    except db.DatabaseUnavailableError as exc:
        st.error(str(exc), icon=":material/database_off:")
        return

    if summary.height == 0:
        components.empty_state("Aucun run ne correspond aux filtres selectionnes.")
        return

    summary = summary.sort("accuracy", descending=True)
    best = summary.row(0, named=True)
    worst = summary.row(summary.height - 1, named=True)
    fastest = summary.sort("median_response_time").row(0, named=True)

    # Un run est un couple modele x variante : le nommer par sa seule variante prete a
    # confusion des que plusieurs modeles sont evalues.
    multi_modeles = summary["model_short"].n_unique() > 1

    def nomme(ligne: dict[str, object]) -> str:
        if multi_modeles:
            return f"<strong>{ligne['model_short']}</strong> en {ligne['variant_label']}"
        return f"<strong>{ligne['variant_label']}</strong>"

    lede = (
        f"{nomme(best)} obtient "
        f"<strong>{components.percent(best['accuracy'])}</strong> de bonnes reponses "
        f"{components.interval(best['wilson_lo'], best['wilson_hi'])} sur "
        f"{components.number(best['n'])} questions, soit "
        f"{components.percent(best['accuracy_above_chance'])} au-dessus du hasard."
    )
    if summary.height > 1:
        lede += (
            f" L'ecart avec le run le moins performant ({nomme(worst)}, "
            f"{components.percent(worst['accuracy'])}) atteint "
            f"{components.percent(best['accuracy'] - worst['accuracy'])}."
        )
    else:
        lede += " C'est pour l'instant le seul run evalue."
    theme.lede(lede)

    def nomme_texte(ligne: dict[str, object]) -> str:
        """Meme regle que `nomme`, sans balise : pour les infobulles des cartes."""
        if multi_modeles:
            return f"{ligne['model_short']} en {ligne['variant_label']}"
        return str(ligne["variant_label"])

    # La mini-courbe compare les variantes d'un meme modele. Avec plusieurs modeles, elle
    # alignerait douze runs sans ordre lisible : elle est reservee au cas a un seul modele.
    accuracy_series = (
        summary.sort("prompt_variant")["accuracy"].to_list()
        if summary.height > 1 and not multi_modeles
        else None
    )

    # Ces cartes decrivent un run, pas la campagne : le titre le dit, sans quoi « 0,00 % de
    # reponses inexploitables » se lirait comme un resultat d'ensemble alors que d'autres runs
    # en produisent. Chaque infobulle rappelle en plus l'etendue sur la selection.
    st.subheader(f"Meilleur run · {nomme_texte(best)}")

    etendue_inexploitables = ""
    etendue_temps = ""
    if summary.height > 1:
        pire = summary.sort("unparseable_rate", descending=True).row(0, named=True)
        etendue_inexploitables = (
            f" Sur les runs selectionnes, le taux va de "
            f"{components.percent(summary['unparseable_rate'].min(), 2)} a "
            f"{components.percent(pire['unparseable_rate'], 2)} "
            f"({nomme_texte(pire)}) : le detail par variante est sur la page "
            "« Variantes de prompt »."
        )
        etendue_temps = (
            f" Le run le plus rapide de la selection est {nomme_texte(fastest)}, a "
            f"{components.seconds(fastest['median_response_time'])}."
        )

    components.kpi_row(
        [
            {
                "label": "Exactitude",
                "value": components.percent(best["accuracy"]),
                "help": f"{nomme_texte(best)} · intervalle de Wilson a 95 % "
                f"{components.interval(best['wilson_lo'], best['wilson_hi'])}",
                "icon": ":material/trophy:",
                "chart_data": accuracy_series,
                "chart_type": "bar",
            },
            {
                "label": "Au-dessus du hasard",
                "value": components.percent(best["accuracy_above_chance"]),
                "help": "Exactitude de ce run moins le niveau du hasard : 25 % aux choix "
                "multiples et 50 % au vrai/faux, pondere par le nombre de questions de "
                "chaque type.",
                "icon": ":material/casino:",
            },
            {
                "label": "Reponses inexploitables",
                "value": components.percent(best["unparseable_rate"], 2),
                "help": "Part des reponses de ce run dont aucune option n'a pu etre extraite : "
                "un echec de format, distinct d'un echec de connaissance." + etendue_inexploitables,
                "icon": ":material/help:",
                "delta_color": "inverse",
            },
            {
                "label": "Temps median",
                "value": components.seconds(best["median_response_time"]),
                "help": "Temps de reponse median de ce run, mesure de bout en bout cote client."
                + etendue_temps,
                "icon": ":material/timer:",
            },
            {
                "label": "Questions evaluees",
                "value": components.number(best["n"]),
                "help": "Posees a l'identique a tous les runs. Les quatre questions servant "
                "d'exemples few-shot sont exclues.",
                "icon": ":material/quiz:",
            },
        ],
        key="kpi_overview",
    )

    st.space("medium")

    left, right = st.columns([3, 2], gap="medium")

    with left:
        titre = (
            "Exactitude par modele et par variante"
            if multi_modeles
            else ("Exactitude par variante de prompt")
        )
        st.subheader(titre)
        socle = float(summary["chance_baseline"].mean() or 0.25)
        if multi_modeles:
            # Grouper par variante : sans cela plusieurs runs partageraient la meme abscisse
            # et leurs barres se superposeraient.
            figure = charts.grouped_accuracy_bar(
                summary,
                x="model_short",
                group="variant_label",
                baselines={"niveau du hasard": socle},
                height=380,
            )
        else:
            figure = charts.accuracy_bar(
                summary.sort("accuracy", descending=True),
                x="variant_label",
                baseline=socle,
                baseline_label="niveau du hasard",
                height=380,
            )
        components.chart(figure, key="overview_variants")
        theme.note(
            "Les moustaches representent l'intervalle de Wilson a 95 %. Deux barres dont les "
            "intervalles se chevauchent ne sont pas necessairement equivalentes : la page "
            "« Variantes de prompt » applique un test apparie, plus sensible."
        )

    with right:
        st.subheader("Choix multiples contre vrai/faux")
        if by_type.height:
            # A variante fixee, sans quoi chaque abscisse porterait plusieurs runs.
            variante = str(best["prompt_variant"])
            libelle = str(best["variant_label"])
            trace = by_type.filter(pl.col("prompt_variant") == variante).with_columns(
                pl.col("type").replace_strict(theme.TYPE_LABELS, default="?").alias("type_label")
            )
            figure = charts.grouped_accuracy_bar(
                trace,
                x="model_short" if multi_modeles else "variant_label",
                group="type_label",
                baselines={"hasard QCM : 25 %": 0.25, "hasard vrai/faux : 50 %": 0.5},
                height=380,
            )
            components.chart(figure, key="overview_types")
            note = (
                "Une bonne reponse sur deux au vrai/faux ne vaut pas une bonne reponse sur "
                "deux au QCM : le hasard rapporte deja 50 % dans le premier cas."
            )
            if multi_modeles:
                note += f" Comparaison faite a variante egale, sur {libelle}."
            theme.note(note)

    if multi_modeles:
        st.space("medium")
        st.subheader("Ce que coute chaque point d'exactitude")
        # Un point par run : a variante egale (meme couleur), le compromis exactitude contre
        # vitesse se lit directement, et la taille du disque rappelle le cout memoire.
        frontier = summary.join(
            runs.select("run_id", "model_size_bytes"), on="run_id", how="inner"
        ).with_columns((pl.col("model_size_bytes") / 1e9).alias("size_gb"))
        figure = charts.tradeoff_scatter(
            frontier,
            x="median_response_time",
            y="accuracy",
            size="size_gb",
            label="model_short",
            group="variant_label",
            x_title="Temps de reponse median",
            y_title="Exactitude",
            size_title="Taille sur disque",
            height=440,
        )
        components.chart(figure, key="overview_tradeoff")
        slowest = summary.sort("median_response_time", descending=True).row(0, named=True)
        facteur = float(slowest["median_response_time"]) / max(
            float(fastest["median_response_time"]), 1e-9
        )
        theme.note(
            "Un point par run, la surface du disque suivant la taille du modele sur disque. A "
            "variante egale (meme couleur), plus haut et plus a gauche est meilleur. "
            f"{nomme_texte(fastest)} repond en "
            f"{components.seconds(fastest['median_response_time'])} contre "
            f"{components.seconds(slowest['median_response_time'])} pour "
            f"{nomme_texte(slowest)}, soit un facteur {facteur:.0f}, pour un ecart "
            f"d'exactitude de {components.percent(slowest['accuracy'] - fastest['accuracy'])}."
        )

    st.space("medium")
    st.subheader("Detail des runs")

    display = summary.select(
        pl.col("variant_label").alias("Variante"),
        pl.col("model_short").alias("Modele"),
        pl.col("reasoning_mode")
        .replace_strict({"off": "desactive", "on": "actif"}, default="?")
        .alias("Raisonnement"),
        pl.col("n").alias("Questions"),
        pl.col("accuracy").alias("Exactitude"),
        pl.col("wilson_lo").alias("IC bas"),
        pl.col("wilson_hi").alias("IC haut"),
        pl.col("accuracy_above_chance").alias("Au-dessus du hasard"),
        pl.col("unparseable_rate").alias("Inexploitables"),
        pl.col("median_response_time").alias("Temps median"),
        pl.col("median_tokens_per_second").alias("Tokens/s"),
        pl.col("total_duration_s").alias("Duree totale"),
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
            "Inexploitables": st.column_config.NumberColumn("Inexploitables", format="percent"),
            "Temps median": st.column_config.NumberColumn("Temps median", format="%.2f s"),
            "Tokens/s": st.column_config.NumberColumn("Tokens/s", format="%.1f"),
            "Duree totale": st.column_config.NumberColumn("Duree totale", format="%.0f s"),
            "Questions": st.column_config.NumberColumn("Questions", format="localized"),
        },
    )
    components.download(display, filename="runs.csv")

    with st.expander("Conditions d'execution", icon=":material/settings:"):
        conditions = runs.select(
            pl.col("variant_label").alias("Variante"),
            pl.col("model_key").alias("Modele"),
            pl.col("model_quant").alias("Quantification"),
            pl.col("context_length").alias("Contexte"),
            pl.col("parallel").alias("Requetes simultanees"),
            pl.col("lmstudio_version").alias("LM Studio"),
            pl.col("runtime_engine").alias("Moteur"),
            pl.col("status").alias("Etat"),
            pl.col("started_at").alias("Debut"),
        )
        st.dataframe(conditions, hide_index=True, width="stretch")
        theme.note(
            "Chaque run est decrit par un manifeste complet (versions, parametres de "
            "generation, empreinte du jeu de questions, commit git) conserve dans "
            "`data/bronze/llm_responses/`."
        )
