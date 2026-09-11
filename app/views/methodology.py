"""Methodologie : comment les chiffres du dashboard sont obtenus."""

from __future__ import annotations

import streamlit as st

from lib import theme

PIPELINE = """
```
OpenTDB ──scrape──▶  bronze : questions_raw.csv, reponses HTTP brutes
                        │
                     clean │  nettoyage, identifiants, ordre des options fige
                        ▼
LM Studio ──bench──▶  bronze : une ligne JSON par appel au modele
                        │
                     grade │  notation deterministe en Python
                        ▼
                     silver : questions.parquet, answers/run_id=*/, runs.parquet
                        │
                      dbt   │  vues staging puis tables gold
                        ▼
                     gold : benchmark.duckdb  ──▶  ce dashboard
```
"""


def render() -> None:
    """Documente le protocole, les definitions et les limites."""
    theme.page_header(
        "Methodologie",
        "Protocole, definitions et limites du benchmark.",
    )

    pipeline, definitions, protocol, limits = st.tabs(
        ["Pipeline", "Definitions", "Protocole", "Limites"]
    )

    with pipeline:
        st.markdown("### De l'API au dashboard")
        st.markdown(PIPELINE)
        st.markdown(
            """
Le projet suit une architecture en medaillon. Chaque couche a une responsabilite unique :

- **Bronze** conserve la donnee telle qu'elle est arrivee, sans interpretation. On peut
  toujours revenir a la reponse exacte du modele, mot pour mot.
- **Silver** contient des observations propres et typees : une ligne par question, une ligne
  par couple (run, question). C'est la que la notation est figee.
- **Gold** repond a des questions metier precises. Chaque table correspond a une question
  posee dans le rapport, et se lit sans jointure supplementaire.

La notation est calculee **une seule fois, en Python**, jamais en SQL. Le rapprochement
approche des reponses n'a pas d'equivalent SQL identique, et une seule implementation evite
que deux logiques divergent silencieusement.
            """
        )

    with definitions:
        st.markdown("### Ce que mesure chaque colonne")
        st.markdown(
            """
**`ai_correct`** vaut vrai lorsque la reponse du modele correspond a la bonne reponse, quelle
que soit la maniere dont elle a ete formulee.

**`grade`** precise *comment* cette correspondance a ete etablie, ce qui permet de separer
deux echecs de nature differente :

| Notation | Signification |
|---|---|
| Lettre extraite | Le modele a repondu par la lettre attendue. |
| Texte exact | Il a ecrit le texte de l'option, apres normalisation. |
| Rapprochement approche | Similarite d'au moins 90 avec l'option, et un ecart d'au moins 5 points avec la deuxieme meilleure. |
| Reponse contenue | La bonne reponse figure dans une phrase, sans negation devant. |
| Fausse | Une reponse a bien ete identifiee, mais elle est incorrecte. |
| Inexploitable | Aucune reponse identifiable : echec de format, pas de connaissance. |
| Erreur d'appel | L'appel au modele a echoue apres plusieurs tentatives. |

**`response_time`** est mesure cote client, au chronometre, autour de l'appel HTTP complet.
C'est la seule mesure de temps disponible pour toutes les variantes, donc la seule sur
laquelle les comparer.

**`ttft_s`** est le temps de traitement du prompt avant le premier token genere ; il croit
avec la longueur du prompt. **`tokens_per_second`** est le debit de generation. Les deux
viennent du moteur d'inference et sont renseignes pour toutes les variantes.

### Statistiques

**Intervalle de Wilson** plutot que l'approximation normale : il reste valide quand
l'effectif est faible ou la proportion proche de 0 ou 1, ce qui arrive dans les petites
categories. Toutes les proportions du dashboard sont accompagnees de leur intervalle a 95 %.

**Test de McNemar** pour comparer deux variantes : elles repondent aux memes questions, la
comparaison est donc appariee. Seules les paires discordantes portent de l'information. En
dessous de 25 paires discordantes, le test binomial exact remplace l'approximation.

**Bootstrap apparie** pour l'intervalle de confiance de l'ecart entre deux variantes : le
reechantillonnage porte sur les questions, ce qui preserve l'appariement.

**Niveau du hasard** : 25 % aux choix multiples a quatre options, 50 % au vrai/faux. Une
exactitude brute de 55 % en vrai/faux vaut moins qu'une exactitude de 45 % en choix
multiples ; le dashboard affiche donc systematiquement l'ecart au hasard.

**Effectif faible** : en dessous de 30 questions, l'intervalle devient trop large pour
conclure. Ces categories sont signalees plutot que masquees.
            """
        )

    with protocol:
        st.markdown("### Conditions d'execution")
        st.markdown(
            """
**Decodage glouton.** Temperature a 0, `top_k` a 1, `top_p` a 1, `min_p` a 0, penalite de
repetition a 1. Un benchmark cherche la reponse la plus probable du modele, pas de la
diversite. Trois appels identiques donnent la meme reponse, ce qui est verifie avant chaque
campagne.

**Une requete a la fois.** Le modele est charge avec un seul emplacement de prediction. Le
traitement par lots du serveur ferait se recouvrir plusieurs generations et fausserait le
temps mesure pour chaque question.

**Appel de chauffe.** Le premier appel de chaque run paie la mise en cache du prompt systeme
et l'allocation memoire. Il est effectue sur une question hors jeu et exclu des mesures.

**Raisonnement desactive partout.** Deux des quatre modeles evalues raisonnent par defaut :
sur une question factuelle, ce mode consomme l'essentiel du budget de tokens en reflexion,
environ 5 s par question au lieu de 0,9. Les deux autres sont publies par leur editeur en deux
modeles distincts, l'un raisonnant, l'autre non : la version evaluee ne contient aucune chaine
de pensee, il n'y a donc rien a desactiver. L'axe « avec ou sans raisonnement » a ete abandonne
plutot que traite a une autre echelle : mesure sur le jeu complet il aurait demande plus de
quatre-vingts heures pour quatre modeles, et mesure sur un echantillon il n'aurait plus ete
comparable au reste.

**L'endpoint decoule de ce que la variante exige.** LM Studio expose trois endpoints de
completion. Les variantes en texte court passent par l'endpoint natif, qui renvoie les
statistiques moteur et rejette les cles inconnues. La variante a sortie contrainte ne peut pas
y rester, cet endpoint refusant la contrainte de format : elle passe par le seul autre endpoint
qui accepte un schema JSON **et** publie les statistiques moteur. Toutes les variantes portent
ainsi les memes colonnes, et deux modeles se comparent toujours a endpoint egal, puisque la
regle ne depend que de la variante.

Comparer deux variantes traverse en revanche deux endpoints. Leur equivalence est mesuree sur
40 questions appariees, en alternant l'ordre des appels pour neutraliser le cache de prompt :
reponses identiques 40 fois sur 40, temps au premier token de 0,139 s contre 0,138 s, debit de
21,4 tokens par seconde de part et d'autre.

**Ordre des options fige.** Les options sont melangees une fois pour toutes, avec une graine
derivee de l'identifiant de la question. Toutes les variantes et tous les modeles voient donc
exactement la meme presentation, et la bonne reponse n'est pas systematiquement en premiere
position. Le biais de position est mesure dans la page « Comparaison de modeles » : lettres
predites contre lettres attendues, run par run.

**Exemples few-shot exclus.** Les quatre questions servant d'exemples dans la variante
few-shot ne sont jamais evaluees : le modele en a vu la reponse dans son propre contexte.

**Tracabilite.** Chaque run est decrit par un manifeste : cle et quantification du modele,
longueur de contexte, parametres de generation, version des gabarits de prompt, empreinte du
jeu de questions, versions logicielles, machine et commit git.
            """
        )

    with limits:
        st.markdown("### Ce que ce benchmark ne dit pas")
        st.markdown(
            """
**Contamination probable du jeu de donnees.** Open Trivia Database est public depuis 2014 et
largement republie. Une partie des questions a vraisemblablement ete vue pendant
l'entrainement du modele. Les scores melangent donc connaissance et memorisation.

**Quantification.** Les modeles evalues sont des versions quantifiees sur quatre bits. Une perte de
rappel factuel par rapport a la version pleine precision est plausible, en particulier sur les
faits rares.

**Questions datees ou ambigues.** Certaines questions ont plusieurs reponses defendables, ou
ont vieilli. L'onglet « Questions revelatrices » de l'explorateur sert de detecteur : celles
que toutes les variantes ratent meritent une relecture.

**Categories desequilibrees.** Le jeu va de quelques dizaines de questions pour certains
themes a plus d'un millier pour d'autres. Les intervalles de confiance des petites categories
sont larges, et signales comme tels.

**Machine unique.** Les temps mesures valent pour un MacBook Pro M2 Pro a un instant donne.
Un ralentissement thermique sur plusieurs heures est possible ; il est mesure et affiche dans
la page « Temps de reponse ».

**Reproductibilite a la virgule pres.** Meme en decodage glouton, l'arithmetique flottante sur
GPU ne garantit pas des sorties strictement identiques d'une execution a l'autre. Le protocole
minimise cet effet sans pouvoir le supprimer.

**Notation automatique.** Le rapprochement approche et la regle de reponse contenue peuvent
produire de rares faux positifs. Le mode de reconnaissance est conserve pour chaque reponse,
ce qui permet de les auditer.
            """
        )

    st.space("medium")
    st.divider()
    st.caption(
        "Donnees de questions : Open Trivia Database, licence CC BY-SA 4.0 · https://opentdb.com "
        "· Modeles executes localement via LM Studio."
    )
