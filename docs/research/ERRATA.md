# ERRATA — corrections apportées aux rapports de recherche

Les six rapports de ce dossier ont été produits le 2026-09-10 par des agents de recherche (documentation officielle, Context7, code source, tests). Les points ci-dessous ont été **vérifiés directement** sur la machine cible après coup et corrigent ou précisent les rapports. La spec (`SPEC.md`) fait foi en cas de divergence.

## 02_lmstudio_gemma4.md

- `lms load --help` (LM Studio 0.4.24) expose bien `-y, --yes` et `--parallel <count>` (le rapport indiquait « pas de flag -y documenté »). Aucune option liée au raisonnement.
- Les numéros de version « 1.0.x / 1.1.x (Bionic) » cités pour LM Studio ne correspondent pas à l'application installée : `/Applications/LM Studio.app` est en **0.4.24**, runtime `llama.cpp-mac-arm64-apple-metal-advsimd@2.34.0`.
- L'endpoint natif `POST /api/v1/chat` **rejette** `response_format` (HTTP 400, `unrecognized_keys`). La sortie structurée passe par `POST /v1/chat/completions` avec `response_format: json_schema` **et** `reasoning_effort: "none"`.
- Sur l'endpoint OpenAI, le champ `reasoning: "off"` est ignoré (raisonnement toujours actif) ; seul `reasoning_effort: "none"` désactive le raisonnement.
- Le SDK Python `lmstudio` 1.5.0 renvoie, avec Gemma 4 et le raisonnement actif par défaut, un `content` contenant le raisonnement suivi d'un marqueur interne `__LM_STUDIO_INTERNAL_LSEP_SYNTHETIC_REASONING_END_…__`. Il est inutilisable tel quel pour ce benchmark.
- Le champ `parallel` de l'instance chargée vaut 4 par défaut (`lms ps --json`), d'où le choix `--parallel 1`.

## 04_streamlit_plotly.md

Signatures lues sur Streamlit 1.63.0 installé (`inspect.signature`) :

- `st.plotly_chart(figure_or_data, use_container_width=None, *, width="stretch", height="content", theme="streamlit", key, on_select, selection_mode, config)` : `width`, `height` et `config` sont des paramètres nommés ; `use_container_width` est déprécié.
- `st.metric(label, value, delta, delta_color, *, help, icon, label_visibility, border, width, height, chart_data, chart_type, delta_arrow, format, delta_description)` : `chart_data`, `chart_type` (`line`/`bar`/`area`), `format` (`percent`, `compact`, `localized`, printf…) et `icon` existent.
- `st.pills(..., default=...)` : même paramètre `default` que `st.segmented_control` (le rapport indiquait `value=`).
- `st.space(size="small")` existe (`xxsmall` … `xxlarge`, `stretch`, int).
- `st.container(*, border, key, width, height, horizontal, wrap, horizontal_alignment, vertical_alignment, gap, autoscroll)`.
- `st.column_config.NumberColumn(format=...)` et `ProgressColumn(format=...)` acceptent `"plain"`, `"localized"`, `"percent"`, `"dollar"`, `"euro"`, `"yen"`, `"accounting"`, `"bytes"`, `"compact"`, `"scientific"`, `"engineering"` ou une chaîne printf.
- Types de colonnes disponibles : `Column`, `Text`, `Number`, `Progress`, `Checkbox`, `Selectbox`, `Multiselect`, `Datetime`, `Date`, `Time`, `Link`, `Image`, `Audio`, `Video`, `List`, `Json`, `Markdown`, `Button`, `LineChart`, `BarChart`, `AreaChart`.

## 05_python_tooling.md

- L'exemple de partitionnement Hive est placé sous `data/gold/answers/` ; dans ce projet les réponses partitionnées sont en couche **silver** (`data/silver/answers/run_id=*/`).
- OpenTDB compte **24** catégories (IDs 9 à 32), pas 52.

## 06_benchmark_methodology.md

- `ai_correct` est retenu **non nul** (définition des consignes) ; la nuance « non parsable » est portée par la colonne `grade` et par `accuracy_parsed_only` en gold.
- Les fonctions DuckDB `jaro_winkler_similarity` et `levenshtein` existent bien en 1.5.5 mais ne sont pas utilisées : la notation est faite une seule fois en Python.

## 01_opentdb.md et 03_dbt_duckdb.md

Aucune correction. Note : `opentdb.com` est bloqué sur le réseau d'entreprise (Cato Networks, catégorie « Games ») ; le rapport 01 a été produit via un proxy de lecture, ses chiffres sont cohérents entre endpoints.
