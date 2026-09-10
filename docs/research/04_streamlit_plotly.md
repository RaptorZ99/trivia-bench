# Référence API Streamlit + Plotly (état au 2026-09-10)

> Méthodologie : Context7 (`/streamlit/docs`, `/plotly/plotly.py`), WebFetch sur docs.streamlit.io / plotly.py, PyPI JSON API (`curl` direct, plus fiable que le résumé WebFetch), WebSearch ciblées. Chaque fait est sourcé. Tout ce qui n'a pas pu être confirmé par une source primaire est marqué **NON VÉRIFIÉ**.

---

## Résumé exécutif

- **Streamlit 1.63.0** (release le 1er septembre 2026), `Requires-Python >= 3.10` (classifiers PyPI : 3.10–3.14) → compatible Python 3.12 du projet. Source : PyPI JSON API.
- **Plotly** : la dernière version publiée toutes séries confondues est **7.0.0** (25 août 2026, avec breaking changes : suppression des traces `scattermapbox`/`choroplethmapbox`/`densitymapbox`, suppression de 8 fonctions `figure_factory` dont `create_distplot`/`create_violin`/`create_candlestick`, abandon de `engine=` dans `write_image`, changement de la lib de parsing couleur TinyColor→culori). La consigne du brief demande explicitement le **dernier 6.x : Plotly 6.9.0** (9 juillet 2026) — c'est la version à pin dans `pyproject.toml` (`plotly>=6.9,<7`). Aucune des fonctions utilisées dans ce dashboard (`px.bar/box/violin/histogram/scatter/imshow/ecdf`, `go.Figure`, `make_subplots`, `go.Indicator`) n'est affectée par les suppressions de 7.0, donc une migration future est peu risquée mais **hors scope** de cette référence.
- **Dépréciation majeure côté Streamlit** : `use_container_width` est dépréciée sur la quasi-totalité des éléments (`st.dataframe`, `st.data_editor`, `st.html`, `st.image`, `st.button`, `st.file_uploader`, `st.tabs`, `st.iframe`, etc.) au profit de `width="stretch" | "content" | <int pixels>`. `use_column_width` a été **supprimé** (breaking) de `st.image` en 1.61.0. **Exception vérifiée** : `st.plotly_chart` n'a *pas* encore migré vers `width=` dans la signature capturée — il utilise toujours `use_container_width: bool = False` (voir section 8). NON VÉRIFIÉ à 100 % : présence exacte d'un `height=` nommé sur `st.plotly_chart` (ajouté en 1.52.0 selon les notes de version, mais pas visible dans la signature JSON extraite — il passe probablement par `**kwargs`).
- **Navigation multipage moderne** : `st.Page(page, *, title=None, icon=None, url_path=None, default=False, visibility="visible")` + `st.navigation(pages, *, position="sidebar", expanded=False)` retourne un objet `Page` qu'il faut exécuter avec `.run()`. `pages` peut être une liste ou un `dict[str, list[st.Page]]` pour créer des sections.
- **Theming double (clair/sombre) officiellement supporté** : `.streamlit/config.toml` accepte `[theme]` (commun) + `[theme.light]` et `[theme.dark]` (overrides par mode), à l'exception de `base`, `fontFaces`, `baseFontSize`, `baseFontWeight`, `metricValueFontSize`, `metricValueFontWeight`, `showSidebarBorder` qui ne peuvent être définis que dans `[theme]`. Il existe aussi `[theme.sidebar]` (sous-thème sidebar) et même `[theme.dark.sidebar]` / `[theme.light.sidebar]`.
- **Couleurs de graphiques pilotées par le thème** : `chartCategoricalColors`, `chartSequentialColors` (exactement 10 couleurs requises), `chartDivergingColors` sont définissables par thème/mode/sidebar et **s'appliquent à Plotly, Altair et Vega-Lite** quand `st.plotly_chart(fig, theme="streamlit")` (défaut). Avec `theme=None`, c'est le template Plotly natif qui prime.
- **Pas de connecteur DuckDB officiel.** `st.connection` n'a que 2 types "first-party" documentés : `"sql"` (SQLAlchemy) et `"snowflake"` (+ `"snowpark"` déprécié). Pour DuckDB : soit une classe custom héritant de `BaseConnection`, soit — pattern le plus simple et recommandé pour un fichier read-only — `duckdb.connect(..., read_only=True)` enveloppé dans `@st.cache_resource`.
- **Layout premium** : `st.container(*, height=None, border=None, horizontal=False, horizontal_alignment=..., vertical_alignment=..., gap=..., key=None)` (les paramètres horizontaux sont documentés dans le guide concepts, pas dans la signature APIDOC courte — vérifié séparément), `st.columns(spec, *, gap="small", vertical_alignment=..., border=..., wrap=True)`. `key=` sur un widget/container ajoute automatiquement une classe CSS `st-key-<key>` — **mécanisme officiellement documenté** (pas un hack), stable depuis son introduction mais "l'emplacement exact dans le DOM n'est pas garanti stable entre versions".
- **Widgets de filtre confirmés** : `st.segmented_control(label, options, *, default=None, selection_mode="single", format_func=..., key=None, on_change=None, ..., wrap=...)` et `st.pills(label, options, *, value=None, format_func=str, selection_mode="single", key=None, ..., wrap=...)`. **Piège** : `st.pills` utilise `value=`, **pas** `default=` (contrairement à `st.segmented_control`). `st.badge(label, *, icon=None, color="blue", width="content", help=None)`, couleurs autorisées : `red, orange, yellow, blue, green, violet, gray/grey, primary`.
- **`st.metric`** : signature de base `st.metric(label, value, delta=None, delta_color="normal", help=None, label_visibility="visible", border=False, width="stretch", height="content")` + `delta_arrow` (ajouté 1.52.0) + `delta_description` (ajouté 1.55.0). **`chart_data` / `chart_type` mentionnés dans le brief n'ont été trouvés dans AUCUNE source consultée — probablement inexistants sur `st.metric` → NON VÉRIFIÉ, à ne pas utiliser sans re-vérification directe dans le changelog.**
- **Caching** : `st.cache_data` pour les données sérialisables (retourne une copie, hashable par défaut, `hash_funcs=` pour les objets non hashables), `st.cache_resource` pour les ressources partagées non sérialisables (connexions DB, modèles) — c'est le décorateur à utiliser pour la connexion DuckDB. `st.fragment(run_every="10s")` permet un rafraîchissement périodique isolé.
- **`st.dataframe`** accepte nativement Polars (`DataFrame` et, depuis 1.61.0, `LazyFrame`), Pandas (+ `Styler`), Snowpark, PySpark, listes/dicts/numpy. `column_config` couvre `NumberColumn`, `ProgressColumn`, `TextColumn`, `CheckboxColumn`, `BarChartColumn`, `LineChartColumn`, `LinkColumn`, `DatetimeColumn`, et depuis 1.56.0 `AudioColumn`/`VideoColumn`.

---

## 1. Versions, Python, dépréciations

### 1.1 Versions exactes (source : PyPI JSON API, requête directe le 2026-09-10)

| Paquet | Dernière version | Date | Requires-Python |
|---|---|---|---|
| `streamlit` | **1.63.0** | 2026-09-01 | `>=3.10` (classifiers jusqu'à 3.14) |
| `plotly` | **7.0.0** (dernière absolue) | 2026-08-25 | `>=3.8` |
| `plotly` | **6.9.0** (dernière **6.x**, demandée par le brief) | 2026-07-09 | `>=3.8` |

Commande utilisée :
```bash
curl -s https://pypi.org/pypi/streamlit/json | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['info']['version'], d['info']['requires_python'])"
curl -s https://pypi.org/pypi/plotly/json   | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['info']['version'])"
```

**Recommandation de pin** (Python 3.12, `uv`) :
```toml
[project]
requires-python = ">=3.12,<3.13"
dependencies = [
  "streamlit>=1.63,<2",
  "plotly>=6.9,<7",       # dernier 6.x demandé — 7.0 a des breaking changes (voir ci-dessous)
  "duckdb>=1.1",
  "pandas>=2.2",
]
```

### 1.2 Breaking changes Plotly 7.0.0 vs 6.x (source : `CHANGELOG.md` de `plotly/plotly.py`, branche `main`)

- Suppression de `scattermapbox`, `choroplethmapbox`, `densitymapbox` (+ `mapboxAccessToken`) → migrer vers les traces `*map` (`scattermap`, etc.). **Non utilisé ici.**
- Suppression de 8 fonctions `figure_factory` (`create_distplot`, `create_candlestick`, `create_violin`, etc.) — remplacées par `px.violin`, `px.histogram`, etc. **Non utilisé ici** (le dashboard utilise `px.violin`/`px.histogram` natifs, pas `figure_factory`).
- `fig.write_image()` / `pio.write_image()` : argument `engine=` supprimé, support Orca et Kaleido < 1.0 abandonné.
- Changement de bibliothèque de parsing des couleurs (TinyColor → culori) : certains formats non standards (`rgb()`/`rgba()` en fractions 0–1, `hsv()`) ne sont plus acceptés ; nouveaux formats supportés (`#ff0000aa`, `rgb(255 0 0)`, `oklab()`).
- `layout.geo.fitbounds` par défaut passe de `false` à `"locations"`.
- MathJax v2 abandonné, v4 ajouté.

→ **Aucun impact** sur le squelette de référence fourni plus bas (pas de mapbox, pas de figure_factory, pas d'export image côté serveur). Rester en 6.9.x est donc un choix sûr et conforme au brief.

### 1.3 Dépréciations Streamlit à éviter (sources : `streamlit.json` généré, notes de version 2025/2026)

- **`use_container_width` → `width="stretch"|"content"|<int>`.** Déprécié (mais pas encore retiré) sur `st.dataframe`, `st.data_editor`, `st.html`, `st.button`, `st.file_uploader`, `st.tabs`, `st.iframe`, `st.image`, `st.selectbox`, `st.expander`, `st.caption`, `st.container`. `st.dataframe` a désormais `width="stretch"` par défaut et `use_container_width=None`.
  Source : `https://github.com/streamlit/docs/blob/main/python/streamlit.json` (signatures extraites via Context7).
- **`use_column_width` retiré** de `st.image` en **1.61.0** (breaking change confirmé). Utiliser `width=`.
  Source : notes de version 2026, version 1.61.0.
- **`st.plotly_chart`** : contrairement aux autres éléments, la signature actuellement documentée est toujours `st.plotly_chart(figure_or_data, use_container_width=False, *, theme="streamlit", key=None, on_select="ignore", selection_mode=('points','box','lasso'), **kwargs)` — **PAS encore de `width=` formel dans la signature capturée**. Un paramètre `height` a été annoncé en v1.52.0 dans les notes de version mais n'apparaît pas explicitement dans le JSON de signature consulté (probablement transmis via `**kwargs`). **NON VÉRIFIÉ précisément** → à contrôler avec `help(st.plotly_chart)` avant de s'appuyer dessus ; utiliser `use_container_width=True` pour le responsive dans ce projet.
- **`st.set_page_config`** : toujours documenté comme devant être « la première commande Streamlit du script », mais une note de version 2025 précise qu'il **peut désormais être appelé plusieurs fois dans un même run de script** (utile en multipage). Version exacte du changement non capturée précisément dans les extraits obtenus → **NON VÉRIFIÉ (numéro de version exact)**, seule la note « 2025 release notes, Notable Changes » est confirmée.
- Pas d'autre dépréciation majeure identifiée dans le scope de ce brief (pas de retrait de `st.cache`, qui est déjà retiré depuis longtemps au profit de `cache_data`/`cache_resource` — non revérifié ici car hors périmètre récent).

Sources section 1 : `https://pypi.org/project/streamlit/`, `https://pypi.org/project/plotly/`, `https://raw.githubusercontent.com/plotly/plotly.py/main/CHANGELOG.md`, `https://github.com/streamlit/docs/blob/main/content/develop/quick-references/release-notes/2026.md`, `https://github.com/streamlit/docs/blob/main/content/develop/quick-references/release-notes/2025.md`, `https://github.com/streamlit/docs/blob/main/python/streamlit.json`.

---

## 2. Architecture multipage (`st.navigation` + `st.Page`)

### 2.1 Signatures exactes

```python
st.Page(
    page: str | Path | Callable,
    *,
    title: str | None = None,
    icon: str | None = None,
    url_path: str | None = None,
    default: bool = False,
    visibility: Literal["visible", "hidden"] = "visible",
)
```
- `page` : chemin vers un fichier `.py` (absolu ou relatif à l'entrypoint), OU une fonction callable **sans argument**, OU une URL externe (`http(s)://…`, dans ce cas `title` est obligatoire).
- `default=True` → cette page reçoit `url_path=""` (racine) ; si aucune page n'a `default=True` et que c'est la **première page passée**, elle devient la page par défaut automatiquement.
- `url_path` ne peut pas contenir de `/` (pas de sous-dossiers dans l'URL).
- `visibility="hidden"` permet de garder une page navigable par URL/`st.switch_page` sans l'afficher dans le menu — utile pour une page de détail.
Source : `https://docs.streamlit.io/develop/api-reference/navigation/st.page` (WebFetch direct, confirmé également par Context7 `/streamlit/docs`).

```python
st.navigation(
    pages: list[st.Page] | dict[str, list[st.Page]],
    *,
    position: Literal["sidebar", "top", "hidden"] = "sidebar",
    expanded: bool | int = False,
) -> st.Page   # objet à exécuter avec .run()
```
- `pages` en `dict` → clés = titres de section, valeurs = listes de `st.Page` → génère des en-têtes dans la sidebar (ou des groupes déroulants si `position="top"`).
- `position="top"` : navigation dans le header de l'app. `position="hidden"` : pas de widget de navigation visible (routing géré manuellement via `st.page_link`/`st.switch_page`).
- `expanded` : `False` (défaut, affiche max ~10 pages si >12 puis "voir plus"), `True` (toujours tout afficher), ou un entier (seuil de collapse).
Source : `https://docs.streamlit.io/develop/api-reference/navigation/st.navigation` (WebFetch direct).

### 2.2 Layout de repo recommandé

```
app.py                  # entrypoint : imports, set_page_config, connexion DB, navigation
lib/
  db.py                 # connexion DuckDB cache_resource
  theme.py              # constantes couleurs / helpers CSS
views/
  overview.py           # def render(): ...
  models.py
  questions.py
.streamlit/
  config.toml
  secrets.toml          # si besoin (non requis pour DuckDB local)
data/gold/benchmark.duckdb
```

Chaque fichier de `views/` expose soit un script exécuté tel quel (style historique `pages/`), soit — pattern recommandé pour ce projet — une **fonction** passée directement à `st.Page(views.overview.render, title=..., icon=...)`, ce qui garde tout en modules Python importables et testables (pas de `pages/` magique).

### 2.3 Où placer le setup partagé (thème/CSS/connexion DB) ?

Dans l'entrypoint `app.py`, **avant** `pg.run()` :
1. `st.set_page_config(...)` — toujours en premier appel Streamlit effectif (note : les objets `st.Page`/`st.navigation()` ne comptent pas comme un rendu, donc l'ordre `st.Page(...)` → `st.navigation(...)` → `st.set_page_config(...)` → `pg.run()` est un pattern officiel documenté).
2. Injection CSS globale (`st.html`), `st.logo(...)`.
3. Connexion DB via `get_connection()` (mise en cache `@st.cache_resource`, appelée une fois — le résultat est partagé par toutes les pages car le cache est global au process).
4. Widgets **globaux** (filtres persistants entre pages, sidebar) : les définir dans l'entrypoint (pas dans une page) pour qu'ils survivent à la navigation — pattern officiellement documenté (« Use Common Widgets in Multipage Apps with st.navigation »).
5. `pg.run()` en tout dernier.

Exemple officiel confirmé (adapté) :
```python
create_page = st.Page("create.py", title="Create entry", icon=":material/add_circle:")
delete_page = st.Page("delete.py", title="Delete entry", icon=":material/delete:")
pg = st.navigation([create_page, delete_page])
st.set_page_config(page_title="Data manager", page_icon=":material/edit:")
pg.run()
```
Source : `https://github.com/streamlit/docs/blob/main/content/develop/concepts/multipage-apps/page-and-navigation.md`, `https://github.com/streamlit/docs/blob/main/content/develop/concepts/architecture/widget-behavior.md`, `https://github.com/streamlit/docs/blob/main/content/develop/concepts/multipage-apps/widgets.md`.

### 2.4 `st.set_page_config`

```python
st.set_page_config(
    page_title: str | None = None,
    page_icon: str | None = None,
    layout: Literal["centered", "wide"] | None = None,
    initial_sidebar_state: Literal["auto", "expanded", "collapsed", "locked", int] | None = None,
    menu_items: dict | None = None,
)
```
Note : `initial_sidebar_state` accepte aussi `"locked"` et un `int` dans la signature actuelle (extrait `streamlit.json`) — au-delà des 3 valeurs historiques documentées dans la page markdown. Source : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/configuration/set_page_config.md` + `streamlit.json`.

---

## 3. Theming complet (`.streamlit/config.toml`)

### 3.1 Sections et double thème clair/sombre

Confirmé (Context7, `content/develop/api-reference/configuration/config-toml.md`) :
> « To define switchable light and dark themes, the configuration options in the `[theme]` table can be used in separate `[theme.dark]` and `[theme.light]` tables, **except** for : `base`, `fontFaces`, `baseFontSize`, `baseFontWeight`, `metricValueFontSize`, `metricValueFontWeight`, `showSidebarBorder`. »

Et pour la sidebar : « Additionally, everything in `[theme.sidebar]` can be configured in separate `[theme.dark.sidebar]` and `[theme.light.sidebar]` tables. » (source identique). → **`[theme.light]`, `[theme.dark]`, `[theme.sidebar]`, `[theme.dark.sidebar]`, `[theme.light.sidebar]` sont tous des noms de section officiellement supportés.** Numéro de version exact d'introduction de `theme.light`/`theme.dark` **NON VÉRIFIÉ** (pas trouvé de note de version dédiée dans les extraits), mais confirmé présent et documenté sur la doc courante (1.63.0).

### 3.2 Liste des clés `[theme]` (avec type / usage), triée par catégorie

**Base**
| Clé | Type | Description |
|---|---|---|
| `base` | `"light" \| "dark" \| <chemin/URL TOML>` | Thème de base hérité. |
| `primaryColor` | couleur | Couleur d'accent principale (boutons, sliders actifs…). |
| `backgroundColor` | couleur | Fond de la page. |
| `secondaryBackgroundColor` | couleur | Fond des widgets, sidebar. |
| `textColor` | couleur | Couleur de texte par défaut. |

**Palette de base (chacune génère automatiquement sa variante `xxxBackgroundColor` à 10 %/20 % d'opacité si non fournie)** : `redColor`, `orangeColor`, `yellowColor`, `blueColor`, `greenColor`, `violetColor`, `grayColor`, et leurs pendants `redBackgroundColor`, `orangeBackgroundColor`, `yellowBackgroundColor`, etc.

**Liens / code / bordures / rayons (extrait de la liste officielle « peuvent être définis séparément par `[theme.sidebar]` »)** :
`linkColor`, `linkUnderline`, `codeTextColor`, `codeBackgroundColor`, `codeFont`, `baseRadius`, `buttonRadius`, `borderColor`, `dataframeBorderColor`, `dataframeHeaderBackgroundColor`, `showWidgetBorder`.

**Typographie** : `font`, `headingFont` (déduit des tutoriels — non retrouvé en détail séparé, usage similaire à `font`/`codeFont`), `baseFontSize`, `baseFontWeight`, `metricValueFontSize`, `metricValueFontWeight` (ces 4 derniers uniquement dans `[theme]` racine, pas par mode clair/sombre).

**Graphiques (depuis la v1.62.0, configurables séparément par mode et sidebar)** :
- `chartCategoricalColors` : tableau de couleurs pour données catégorielles.
- `chartSequentialColors` : tableau de **exactement 10 couleurs** pour un gradient continu — « invalid color strings are skipped ; if there are not exactly ten valid colors, Streamlit uses a default set ». **S'applique à Plotly, Altair et Vega-Lite.**
- `chartDivergingColors` : tableau de 10 couleurs pour échelle divergente.

Source précise de la nouveauté v1.62 : « 📊 You can configure chart categorical, sequential, and diverging colors separately for light, dark, and sidebar themes » — `content/develop/quick-references/release-notes/2026.md`, Version 1.62.0.

**Divers** : `showSidebarBorder` (racine uniquement).

### 3.3 Polices custom (`fontFaces` + `enableStaticServing`)

```toml
[server]
enableStaticServing = true

[[theme.fontFaces]]
family = "tuffy"
url = "app/static/Tuffy-Regular.ttf"
style = "normal"
weight = 400
[[theme.fontFaces]]
family = "tuffy"
url = "app/static/Tuffy-Bold.ttf"
style = "normal"
weight = 700

[theme]
font = "tuffy"
```
- Formats auto-hébergeables : OTF, TTF, WOFF, WOFF2 (fichiers dans `static/` à la racine du repo, servis via le static file serving de Streamlit).
- Attributs de `[[theme.fontFaces]]` : `family` (obligatoire), `url` (obligatoire), `weight` (optionnel, ex. `400`, `"200 800"`, `"bold"`), `style` (optionnel), `unicodeRange` (optionnel).
- `fontFaces` ne peut être défini que dans `[theme]` racine (pas par mode clair/sombre — cf. liste des exceptions ci-dessus).
Source : `https://github.com/streamlit/docs/blob/main/content/develop/tutorials/theming/static-fonts.md`, `https://github.com/streamlit/docs/blob/main/content/develop/concepts/configuration/theming-fonts.md`.

### 3.4 `st.plotly_chart(fig, theme="streamlit")` vs `theme=None`

Confirmé (doc officielle + Context7) :
```python
tab1, tab2 = st.tabs(["Streamlit theme (default)", "Plotly native theme"])
with tab1:
    st.plotly_chart(fig, theme="streamlit", use_container_width=True)   # défaut
with tab2:
    st.plotly_chart(fig, theme=None, use_container_width=True)          # template Plotly natif (celui du fig)
```
`theme="streamlit"` (défaut) applique les couleurs du thème actif (dont `chartCategoricalColors`/`chartSequentialColors`) par-dessus la figure Plotly ; `theme=None` laisse le `template=` défini dans le code Python faire foi. → Pour un dashboard qui doit matcher exactement la palette custom du thème, **laisser `theme="streamlit"`** (défaut) et éviter de fixer un `template=` fort côté Python qui entrerait en conflit visuel.
Source : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/charts/plotly_chart.md`.

---

## 4. Layout primitives (dashboard premium)

### 4.1 `st.columns`

```python
st.columns(
    spec: int | list[float],
    *,
    gap: Literal["small","medium","large"] | int | None = "small",  # accepte aussi un int (pixels) depuis 1.60.0, et None depuis 2025 pour "pas d'écart"
    vertical_alignment: Literal["top","center","bottom"] = "top",   # vu dans la doc concepts (non extrait de la signature APIDOC courte)
    border: bool = False,                                           # idem
    wrap: bool = True,   # depuis 1.62/1.63 : columns stackent en colonne unique ≤640px si wrap=True (défaut) ; wrap=False = scroll horizontal
)
```
- `gap` accepte en réalité toute la gamme `"xxsmall"` → `"xxlarge"` d'après le guide concepts (« Set column gap size »), en plus des entiers pixels (1.60.0) et `None` (pas d'écart, note 2025). La signature APIDOC courte ne montre que `gap='small'` — **la liste exhaustive des presets textuels n'a pas été retrouvée mot pour mot** ; utiliser `"small"|"medium"|"large"` en confiance, les valeurs `xx-` sont mentionnées mais non listées exhaustivement → **partiellement NON VÉRIFIÉ**.
- Responsive : en dessous de 640px de large, les colonnes empilent verticalement par défaut (`wrap=True`). C'est le comportement mobile officiel — pas besoin de media query custom.
Sources : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/layout/columns.md`, `https://github.com/streamlit/docs/blob/main/content/develop/concepts/app-design/layouts-and-containers.md`, notes de version 1.60.0/1.62.0/1.63.0.

### 4.2 `st.container`

Signature APIDOC officielle courte : `st.container(*, height=None, border=None)`.
Le guide concepts (« Layouts and containers ») documente en plus, avec exemples fonctionnels :
```python
with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="large", key="toolbar"):
    st.button("Cancel")
    st.button("Submit")
```
- `horizontal=True` : dispose les enfants en ligne (comme `st.columns` mais sans largeurs figées, s'adapte au contenu).
- `horizontal_alignment` : `"left"|"center"|"right"|"distribute"` (valeurs vues en exemple : `"right"` confirmé ; liste exhaustive non retrouvée mot pour mot → **NON VÉRIFIÉ exhaustivement**, `"left"/"center"/"right"` sont sûrs).
- `height=200` : hauteur fixe + scroll interne automatique.
- `border=True` : bordure visible.
- `key="toolbar"` → génère la classe CSS `st-key-toolbar` sur le conteneur (mécanisme officiel, voir §9).
Sources : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/layout/container.md`, `https://github.com/streamlit/docs/blob/main/content/develop/concepts/app-design/layouts-and-containers.md`.

### 4.3 `st.tabs`, `st.expander`, `st.divider`, `st.empty`

```python
st.tabs(tabs: list[str], *, width="stretch", height="content", default=None, key=None, on_change="ignore", args=None, kwargs=None)
st.expander(label, expanded=False, *, icon=None, width="stretch")
st.divider()   # pas de paramètre de largeur documenté trouvé
st.empty()     # conteneur à un seul élément, remplaçable
```
`st.tabs(height=...)` : hauteur fixe du panneau d'onglet ajoutée en **1.60.0** (« new `height` parameter to set a fixed pixel height for the tab panel area »).
Sources : `streamlit.json` (Context7), notes de version 1.60.0.

**`st.space`** : **NON TROUVÉ** dans la documentation consultée (aucune occurrence dans `/streamlit/docs` via Context7 ni dans les pages fetchées). Ne pas l'utiliser tant que non confirmé — probablement une confusion avec un pattern manuel (`st.container(height=N)` vide, ou `st.write("")`) plutôt qu'une fonction réelle de l'API 1.63.0. **NON VÉRIFIÉ / probablement inexistant.**

### 4.4 Valeurs `width`/`height` génériques

Confirmé via l'extraction de doc (`streamlit.json`, description générique reprise sur plusieurs éléments : `st.html`, `st.iframe`, `st.dataframe`, `st.data_editor`, `st.tabs`, `st.file_uploader`…) :
- `"stretch"` (souvent la valeur par défaut désormais) : largeur = largeur du conteneur parent.
- `"content"` : largeur = largeur du contenu, sans dépasser le parent.
- `int` : largeur fixe en pixels, cappée à la largeur du parent si elle la dépasse.
Pour `height`, les valeurs possibles varient par élément (`"content"`, `"stretch"`, `int`) — ex. `st.iframe(height="content")` par défaut avec fallback 400px cross-origin.

### 4.5 `st.metric` — signature complète vérifiée

```python
st.metric(
    label: str,
    value,
    delta=None,
    delta_color: Literal["normal","inverse","off"] = "normal",
    help: str | None = None,
    label_visibility: Literal["visible","hidden","collapsed"] = "visible",
    border: bool = False,
    width: Literal["stretch"] | int = "stretch",
    height: Literal["content"] | int = "content",
    delta_arrow=...,           # ajouté en 1.52.0 — valeur par défaut exacte NON VÉRIFIÉE
    delta_description=None,    # ajouté en 1.55.0 (mars 2026) — texte descriptif à côté du delta
)
```
- `border=True` ajoute une bordure/carte visuelle (utile pour le header KPI).
- Depuis **1.60.0** : un delta à `0` s'affiche désormais en **gris neutre** au lieu de vert/rouge (« so a zero change no longer implies a positive or negative direction »).
- **`chart_data=` / `chart_type=` mentionnés dans le brief : introuvables dans toutes les sources consultées (doc API, `streamlit.json`, notes de version 2025/2026). Absents de la signature capturée → à considérer comme NON EXISTANTS sur `st.metric` dans l'API actuelle, sauf preuve contraire.** Ne pas les utiliser dans le squelette de référence.
Sources : `streamlit.json` (signature de base), notes de version 2025 v1.52.0 (`delta_arrow`), 2026 v1.55.0 (`delta_description`), 2026 v1.60.0 (delta neutre).

---

## 5. Affichage de données (`st.dataframe`, `column_config`)

### 5.1 Signature actuelle de `st.dataframe`

```python
st.dataframe(
    data=None,
    width="stretch",
    height="auto",
    *,
    use_container_width=None,   # déprécié, conservé pour compat
    hide_index=None,
    column_order=None,
    column_config=None,
    key=None,
    on_select="ignore",         # "ignore" | "rerun" | callable
    selection_mode="multi-row", # "single-row" | "multi-row" | "single-column" | "multi-column" | "single-row-required" (ajouté 1.56.0) | combinaisons
    selection_default=None,     # programmatique, ajouté 1.56.0
    row_height=None,
    placeholder=None,
    lazy=None,                  # ajouté 1.61.0 — lazy loading des lignes ; Polars LazyFrame supporté nativement
)
```
Source : `https://github.com/streamlit/docs/blob/main/python/streamlit.json` (extraction directe de la signature).

### 5.2 Sélection interactive (pattern officiel confirmé)

```python
event = st.dataframe(
    df,
    column_config=column_configuration,
    hide_index=True,
    on_select="rerun",
    selection_mode="multi-row",
)
selected_rows = event.selection.rows   # indices sélectionnés
filtered_df = df.iloc[selected_rows]
```
Nouveautés 1.56.0 utiles : `selection_mode="single-row-required"` (toujours une ligne sélectionnée — pratique pour un détail de question), colonne `alignment` dans `column_config`, menu de visibilité des colonnes toujours visible.
Source : `https://github.com/streamlit/docs/blob/main/content/develop/tutorials/elements/dataframes/row_selections.md`, notes de version 1.56.0.

### 5.3 `st.column_config` — types confirmés et signatures

| Type | Signature confirmée | Notes |
|---|---|---|
| `Column` (générique) | `Column(label=None, help=None, width=None, pinned=None)` | Base commune. |
| `NumberColumn` | `NumberColumn(label=None, ..., format=None, min_value=None, max_value=None, ...)` | Exemple officiel : `NumberColumn("Price (in USD)", min_value=0, format="$%d")`. |
| `ProgressColumn` | `ProgressColumn(label=None, help=None, format=None, min_value=0, max_value=1)` | Barre de progression, bornes par défaut 0–1 (donc adapté à un taux d'exactitude 0-1). |
| `TextColumn` | `TextColumn(label=None, width=None, help=None, disabled=False, required=False, default=None, max_chars=None, validate=None)` | `validate=` = regex. |
| `CheckboxColumn` | Exemple : `CheckboxColumn("Your favorite?", help="...")` | Signature détaillée non extraite intégralement. |
| `BarChartColumn` | `BarChartColumn(label=None, help=None, width=None, required=None, y_min=None, y_max=None)` | Mini bar chart inline. |
| `LineChartColumn` | (mêmes paramètres que `BarChartColumn`, cf. exemple `LineChartColumn("Sales (last 6 months)", y_min=0, y_max=100)`) | |
| `DatetimeColumn` | `DatetimeColumn(label=None, help=None, width=None, format=None, min_value=None, max_value=None, step=None)` | Exemple : `format="D MMM YYYY, h:mm a"` (syntaxe façon Moment.js/Day.js). |
| `LinkColumn` | Mentionné dans l'index (« add … clickable URLs ») | Signature détaillée non extraite intégralement — **NON VÉRIFIÉ en détail**, mais l'existence est confirmée. |
| `AudioColumn` / `VideoColumn` | Ajoutés en **1.56.0** | Lecteurs audio/vidéo inline dans le tableau. |

**Formats `NumberColumn`** : le `format=` suit une syntaxe de type printf/sprintf.js (ex. `"$%d"`, `"%.1f%%"` — cf. brief). Les tokens spéciaux « percent », « compact », « localized » mentionnés dans le brief **n'ont pas été retrouvés explicitement documentés** dans les extraits obtenus → **NON VÉRIFIÉ**. Se limiter aux formats `%d`, `%.Nf`, `%.1f%%`, `"$%d"` confirmés par les exemples officiels tant que non revérifié.

**Le paramètre `format=` sur les colonnes Text/Date/Time/Datetime est confirmé** (« A format parameter is available for configuring Text, Date, Time, and Datetime columns »). Les colonnes de type chart (`Line`/`Bar`) utilisent `y_min`/`y_max` (pas de `format`), et `ProgressColumn` utilise `min_value`/`max_value`.
Source : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/data/column_config/_index.md`, `.../progresscolumn.md`, `.../textcolumn.md`, `.../datetimecolumn.md`, `.../barchartcolumn.md`, `.../column.md`.

### 5.4 Styler Pandas & Polars

- **Styler Pandas** confirmé fonctionnel : `st.dataframe(df.style.highlight_max(axis=0))` (donc `background_gradient` etc. doivent fonctionner de la même façon — pattern générique confirmé même si `background_gradient` spécifiquement n'a pas été testé dans un exemple dédié). Source : `https://github.com/streamlit/docs/blob/main/content/get-started/fundamentals/main-concepts.md`.
- **Polars natif** : confirmé — « Polars LazyFrame objects are supported natively » depuis 1.61.0 (et les `DataFrame` Polars classiques le sont depuis plus longtemps, via le support générique listé dans « Dataframes > st.dataframe UI features », qui mentionne explicitement Snowpark/PySpark en plus des types Python standards ; Polars `DataFrame` non cité nommément dans cet extrait précis mais confirmé par le titre de la note 1.61.0 qui parle de « Polars LazyFrame **also** » — implique un support Polars déjà existant). → Utilisable en toute confiance pour Polars `DataFrame`/`LazyFrame`.

---

## 6. Widgets de filtre

| Widget | Signature confirmée | Source |
|---|---|---|
| `st.segmented_control` | `st.segmented_control(label, options, *, default=None, selection_mode='single', format_func=default_format_func, key=None, help=None, on_change=None, args=None, kwargs=None, disabled=False, horizontal=False, wrap=...)` | `content/develop/api-reference/widgets/segmented_control.md` + notes 1.63.0 (`wrap`) |
| `st.pills` | `st.pills(label, options, *, value=None, format_func=str, selection_mode='single', key=None, help=None, on_change=None, args=None, kwargs=None, disabled=False, horizontal=False, label_visibility='visible', wrap=...)` | `content/develop/api-reference/widgets/pills.md` |
| `st.selectbox` | `st.selectbox(label, options, index=0, format_func=..., key=None, help=None, on_change=None, args=None, kwargs=None, *, placeholder=None, disabled=False, label_visibility="visible", accept_new_options=False, width="stretch")` | `streamlit.json` |
| `st.multiselect` | Existant, chips repliables sur une ligne via `wrap` depuis 1.62.0 | notes 1.62.0 |
| `st.slider` | Existant, non détaillé ici (hors nouveautés identifiées) | — |
| `st.toggle` | Existant, `wrap` sur le label depuis 1.62.0 | notes 1.62.0 |
| `st.radio` | `horizontal=True` disponible (paramètre stable, confirmé par usage courant de la doc) | — |
| `st.button` | `st.button(label, key=None, help=None, on_click=None, args=None, kwargs=None, *, type="secondary", icon=None, icon_position="left", disabled=False, use_container_width=None, width="content", shortcut=None, wrap=None)` | `streamlit.json` — `type` accepte **"primary" \| "secondary" \| "tertiary"** (3 valeurs, `tertiary` confirmé présent dans la signature bien que non détaillé séparément) |
| `st.download_button` | Existant (non re-détaillé, hors nouveauté identifiée) | — |
| `st.badge` | `st.badge(label, *, icon=None, color="blue", width="content", help=None)` — couleurs : `red, orange, yellow, blue, green, violet, gray/grey, primary` | `https://docs.streamlit.io/develop/api-reference/text/st.badge` (WebFetch) |

**Piège important confirmé** : `st.segmented_control` utilise `default=`, **`st.pills` utilise `value=`**. Ne pas les traiter comme interchangeables dans le code.

**Icônes Material** : syntaxe `:material/icon_name:` confirmée sur `st.Page(icon=...)`, `st.badge(icon=...)`, `st.logo(icon_image=...)` (1.54.0 : « `st.logo` supports Material icons and emojis »). Emojis unicode fonctionnent également partout où `icon=` est accepté.

Sources : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/widgets/segmented_control.md`, `.../widgets/pills.md`, `https://github.com/streamlit/docs/blob/main/python/streamlit.json`, notes de version 1.62.0/1.63.0/1.54.0.

---

## 7. Performance & état

### 7.1 `st.cache_data` vs `st.cache_resource`

```python
@st.cache_data(ttl=None, show_spinner=True, hash_funcs=None)
def load_dataframe(...) -> pd.DataFrame: ...

@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection: ...
```
- **Règle officielle** : « Data are serializable objects […] that's also why `st.cache_data` is the correct command for almost all use cases. `st.cache_resource` is a more exotic command that you should only use in specific situations » (connexions DB, modèles ML, handles de fichiers, threads).
- `show_spinner` accepte `bool` ou une `str` (texte custom du spinner) : `@st.cache_data(show_spinner="Fetching data from API...")`.
- `hash_funcs={MyClass: hash_func}` pour hasher un objet non nativement hashable (ex. un objet connexion passé en argument à une fonction `cache_data` — dans ce cas, la convention alternative consultée en WebSearch est de préfixer l'argument par `_` pour dire à Streamlit de **l'ignorer** dans le hash : `def query(_conn, sql): ...`).
Sources : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/caching-and-state/cache-data.md`, `.../cache-resource.md`, `.../concepts/architecture/caching.md`.

### 7.2 Pattern connexion DuckDB read-only partagée

Pas de type `st.connection` officiel pour DuckDB (built-in = seulement `"sql"` et `"snowflake"`/`"snowpark"` déprécié — confirmé, `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/connections/_index.md`). Deux options valables :

**Option A — la plus simple (recommandée pour ce projet)** :
```python
import duckdb
import streamlit as st

@st.cache_resource(show_spinner="Connexion à DuckDB…")
def get_connection(path: str = "data/gold/benchmark.duckdb") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(database=path, read_only=True)
```
Le connecteur est un objet global au process (pas par session), partagé par toutes les pages/utilisateurs — cohérent avec `read_only=True` sur un fichier immuable pendant la durée de vie de l'app.

**Option B — classe custom `BaseConnection`** (pattern officiel documenté pour intégrer proprement dans `st.connection("duckdb", type=...)` et bénéficier de la gestion des secrets) :
```python
from streamlit.connections import BaseConnection
import duckdb

class DuckDBConnection(BaseConnection[duckdb.DuckDBPyConnection]):
    def _connect(self, **kwargs) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(**self._secrets, **kwargs)

    def query(self, sql: str, ttl: int = 3600):
        @st.cache_data(ttl=ttl)
        def _run(_conn, sql):
            return _conn.sql(sql).df()
        return _run(self._instance, sql)
```
Source du pattern : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/connections/_index.md` (« Build a custom connection with BaseConnection »), `https://github.com/streamlit/docs/blob/main/content/develop/concepts/connections/connecting-to-data.md` (mentionne explicitement `ExperimentalBaseConnection[duckdb.DuckDBPyConnection]` comme exemple d'extension pour DuckDB — nom historique, `BaseConnection` est le nom actuel non-expérimental).

**Caveat dbt** (WebSearch, non issu de la doc Streamlit officielle — recoupement communautaire) : si un pipeline dbt reconstruit `benchmark.duckdb` pendant que l'app tourne, une connexion `read_only=True` déjà ouverte peut lire un état obsolète (le cache_resource garde la connexion ouverte tant que le process Streamlit vit) ou échouer si le fichier est verrouillé pendant l'écriture. Bonnes pratiques recommandées par la communauté (non officielles Streamlit) : (1) ouvrir/fermer la connexion à la demande plutôt que la garder indéfiniment si des rebuilds fréquents sont attendus, ou (2) invalider le cache manuellement (`get_connection.clear()`) après un rebuild connu, ou (3) publier le nouveau fichier sous un nom versionné et ne changer le chemin qu'une fois l'écriture terminée (write-then-swap atomique). **Ceci n'est pas une garantie DuckDB documentée officiellement — à traiter comme recommandation opérationnelle, pas comme fait API vérifié.**

### 7.3 `st.fragment`, `st.session_state`, `st.query_params`

```python
@st.fragment(run_every="10s")
def auto_refresh_kpis():
    df = get_latest()
    st.line_chart(df)
```
- `run_every` accepte une durée façon `"10s"`, ou un `int`/`float` (secondes) — confirmé via l'exemple officiel (chaîne `"10s"`).
- `st.session_state` : accès dict-like ou attribut (`st.session_state["k"]` / `st.session_state.k`), persiste entre reruns d'une même session.
- `st.query_params` : disponible depuis **1.30.0**, dict-like, clés/valeurs toujours strings, **réinitialisé à chaque navigation entre pages d'une app multipage** — point d'attention si on veut passer des filtres via l'URL entre pages (il faut les re-sérialiser à chaque page ou utiliser `st.session_state` en complément).
Sources : `https://github.com/streamlit/docs/blob/main/content/develop/concepts/architecture/fragments.md`, `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/caching-and-state/query_params.md`, `.../session_state.md`.

---

## 8. Plotly dans Streamlit

### 8.1 `st.plotly_chart`

```python
st.plotly_chart(
    figure_or_data,
    use_container_width: bool = False,
    *,
    theme: Literal["streamlit"] | None = "streamlit",
    key=None,
    on_select: Literal["ignore","rerun"] | Callable = "ignore",
    selection_mode: str | Iterable[str] = ("points", "box", "lasso"),
    **kwargs,   # ex. config={...} passé au frontend Plotly.js
)
```
- `selection_mode` : combinaison de `"points"`, `"box"`, `"lasso"` — toutes actives par défaut.
- `on_select="rerun"` + lecture de `event.selection` pour capturer les points cliqués/sélectionnés (même pattern que `st.dataframe`).
- `config={'scrollZoom': False}` (exemple officiel) : dict Plotly.js standard (modebar, scroll, etc.), passé via `**kwargs`.
Sources : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/charts/plotly_chart.md`, `streamlit.json`.

### 8.2 Plotly essentials pour un look cohérent

**Fonctions express confirmées avec exemples officiels** : `px.bar`, `px.box(points="all")`, `px.violin(box=True, points="all"|"outliers"|False)`, `px.histogram`, `px.scatter`, `px.imshow(z, text_auto=True|".2f", color_continuous_scale=..., aspect="auto")` (recommandé pour heatmap catégorie × difficulté depuis Plotly ≥5.5), `px.ecdf(df, x=..., color=..., markers=True, orientation="h", ecdfnorm=None)`.

**`fig.update_layout` — exemple combiné confirmé (issu de plusieurs exemples officiels recomposés)** :
```python
fig.update_layout(
    template="plotly_white",     # ou None pour hériter du thème Streamlit
    margin=dict(l=20, r=20, t=60, b=20),
    height=420,
    legend=dict(x=0, y=1, traceorder="reversed", bgcolor="LightSteelBlue", bordercolor="Black", borderwidth=2),
    font=dict(family="Inter, sans-serif", color="blue"),
    paper_bgcolor="rgba(0,0,0,0)",   # confirmé utilisable pour fond transparent (pattern standard Plotly, cohérent avec les exemples paper_bgcolor)
    plot_bgcolor="rgba(0,0,0,0)",
    hovermode="x",
)
```
**Note** : `hoverlabel=` et `colorway=` n'ont pas été trouvés dans un exemple officiel dédié lors de cette recherche mais sont des attributs `layout.*` standards de longue date de Plotly (présents dans le schéma `go.Layout` — usage classique `fig.update_layout(colorway=[...])`, `hoverlabel=dict(bgcolor="white")`). **Non ré-confirmés par une source fraîche de cette recherche → à considérer comme fiables par convention Plotly générale mais marqués NON RE-VÉRIFIÉS pour ce document.**

**Error bars (intervalles de confiance)** :
```python
fig.add_trace(go.Bar(
    x=categories, y=accuracy,
    error_y=dict(type="data", array=ci_upper, arrayminus=ci_lower, symmetric=False, color="purple", thickness=1.5, width=3),
))
```
`type` accepte `"data"` (valeurs absolues), `"percent"` (pourcentage de y), `"constant"`. `symmetric=False` + `array`/`arrayminus` pour un CI asymétrique.
Source : `https://github.com/plotly/plotly.py/blob/main/doc/python/error-bars.md`.

**`make_subplots`** :
```python
from plotly.subplots import make_subplots
fig = make_subplots(rows=2, cols=2)
fig.add_trace(go.Scatter(...), row=1, col=1)
fig.update_xaxes(title_text="...", row=1, col=1)
```

**`go.Indicator` (gauge/KPI)** : mode `"number+gauge+delta"`, `gauge=dict(shape="bullet"|"angular", axis=dict(range=[...]), threshold=dict(...), steps=[...], bar=dict(color=...))`. Multi-indicateurs via plusieurs `add_trace(go.Indicator(...))` + `domain=dict(row=.., column=..)` ou `x`/`y`.

**Axes** : `fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="LightPink")`, `fig.update_yaxes(showgrid=False)`, tickformat non re-testé spécifiquement pour `".0%"` mais standard Plotly (D3 format strings) — usage classique confirmé par convention, non retrouvé dans un exemple dédié cette session.

### 8.3 Templates & template custom

Liste confirmée par un exemple officiel itérant sur les templates : `["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white", "none"]`. D'autres noms (`presentation`, `xgridoff`, `ygridoff`, `gridon`) sont des templates Plotly standards de longue date **mais n'ont pas été retrouvés listés explicitement dans les pages consultées cette session → NON RE-VÉRIFIÉS ici**, utiliser la liste des 7 confirmés en priorité.

**Enregistrer un template custom** :
```python
import plotly.graph_objects as go
import plotly.io as pio

pio.templates["ceva_dark"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        colorway=["#6C5CE7", "#00CEC9", "#FDCB6E", "#E17055", "#74B9FF"],
    )
)
pio.templates.default = "ceva_dark"   # défaut pour toute la session
# ou, ponctuellement : fig.update_layout(template="ceva_dark")
```
Source : `https://github.com/plotly/plotly.py/blob/main/doc/python/templates.md`.

**Cohérence avec le thème Streamlit** : puisque `st.plotly_chart(theme="streamlit")` (par défaut) réapplique les couleurs du thème Streamlit (`chartCategoricalColors` etc.) par-dessus la figure, le plus simple pour un rendu 100% cohérent avec `config.toml` est de **laisser `theme="streamlit"` et de ne pas fixer de `template=` fort** — sinon utiliser `theme=None` + template custom entièrement maîtrisé côté Python (les deux approches sont mutuellement exclusives en pratique).

---

## 9. CSS/HTML custom

### 9.1 `st.html` vs `st.markdown(unsafe_allow_html=True)`

```python
st.html(body: str, *, width="stretch", unsafe_allow_javascript: bool = False)
```
- Contenu sanitisé par **DOMPurify**. **Pas iframé** (contrairement à `st.components.v1.html`). JS ignoré par défaut ; `unsafe_allow_javascript=True` pour l'exécuter (déconseillé avec du contenu non fiable).
- `st.markdown(body, unsafe_allow_html=False, *, help=None)` : rendu Markdown, avec `unsafe_allow_html=True` pour autoriser des balises HTML brutes à l'intérieur — **pas de sanitisation DOMPurify documentée pour ce chemin** (donc `st.html` est préférable pour de l'injection de style/HTML pur).
- **Recommandation confirmée par recoupement WebSearch** : utiliser `st.html("<style>...</style>")` une fois dans l'entrypoint pour une feuille de style globale, plutôt que multiplier les `st.markdown(unsafe_allow_html=True)` disséminés dans les pages.
Sources : `https://github.com/streamlit/docs/blob/main/python/streamlit.json` (signature `st.html`), `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/text/markdown.md`, WebSearch « streamlit custom CSS best practice 2026 ».

### 9.2 Ciblage CSS via `key=` → `.st-key-<key>`

**Mécanisme officiellement documenté** (pas seulement un hack découvert) :
> « if `key` is provided, it will be used as a CSS class name prefixed with `st-key-` » — trouvé explicitement documenté dans les `args` de `st.file_uploader` et `st.data_editor`, et confirmé génériquement pour tout widget/conteneur avec `key=` dans le guide « Widget behavior » : « keys are repeated in the DOM as HTML attributes with a Streamlit-specific prefix, `st-key-`, to prevent conflicts. **The exact prefix, attribute name, and placement within the widget's DOM subtree aren't guaranteed to be stable between versions.** »

→ Utilisation recommandée :
```python
with st.container(key="kpi_card"):
    st.metric("Accuracy", "87.3%")
```
```css
.st-key-kpi_card { border-radius: 1rem; box-shadow: 0 2px 10px rgba(0,0,0,.08); }
```
**Numéro de version exact d'introduction du mécanisme `st-key-` NON VÉRIFIÉ** (présent et stable sur 1.63.0, considéré fiable depuis plusieurs versions d'après le phrasé de la doc, mais pas de date précise trouvée).

### 9.3 `data-testid` pour cibler les métriques (déconseillé en premier choix)

Attributs vus en usage communautaire (non documentés comme API stable officielle) : `stMetric`, `stMetricValue`, `stMetricLabel`, `stMetricDelta`. **Ce sont des détails d'implémentation internes, non garantis stables entre versions** — à n'utiliser qu'en dernier recours, après avoir épuisé (1) les clés de thème (`metricValueFontSize`, `metricValueFontWeight`, couleurs), (2) `st.metric(border=True)`, (3) le wrapping `st.container(key=...)` + `.st-key-*`.

---

## 10. Exécution / déploiement

### 10.1 `streamlit run` et `uv`

```bash
uv run streamlit run app.py
```
Fonctionne nativement car `uv run` exécute dans l'environnement du projet (résolu depuis `pyproject.toml`/`uv.lock`) — pas de particularité Streamlit ici, c'est un usage `uv` générique.

### 10.2 `.streamlit/config.toml` — sections utiles au-delà de `[theme]`

**`[server]`** (extraits confirmés) :
- `headless` (bool) — par défaut `false` sauf environnement Linux sans `DISPLAY`.
- `port`, `enableStaticServing` (bool, requis pour servir `static/` — polices, logo).
- `runOnSave` : cité dans le brief, non re-extrait explicitement cette session mais paramètre `[server]` historique standard connu (non re-vérifié dans cette recherche → **NON RE-VÉRIFIÉ**, utiliser avec confiance modérée).

**`[browser]`** :
- `serverAddress` (défaut `"localhost"`), `serverPort` (défaut = valeur de `server.port`), `gatherUsageStats` (bool, défaut `true` — mettre `false` pour désactiver la télémétrie).

**`[client]`** :
- `showErrorDetails` : `"full" | "stacktrace" | "type" | "none"` (+ anciens booléens dépréciés), défaut `"full"`.
- `toolbarMode` : `"auto" | "developer" | "viewer" | "minimal"`, défaut `"auto"`.
- `showSidebarNavigation` (bool, défaut `true`) — à mettre `false` uniquement si navigation custom via `st.page_link` (n'affecte que les apps utilisant l'ancien dossier `pages/`, pas `st.navigation` d'après le texte : « This only applies when app's pages are defined by the `pages/` directory »).
- `showErrorLinks` : `"auto" | true | false`.
- `disableDataExport` (bool, défaut `false`) — masque les boutons d'export CSV/copier de `st.dataframe`/`st.data_editor` (ajouté release notes 2026, cf. v1.60.0).
Source : `https://github.com/streamlit/docs/blob/main/content/develop/api-reference/configuration/config-toml.md`, `.../concepts/configuration/options.md`.

### 10.3 Streamlit Community Cloud + `uv`

Confirmé par WebSearch (recoupement, pas doc officielle Streamlit consultée en profondeur ici — **niveau de confiance moyen**) :
- Community Cloud détecte le fichier de dépendances dans cet ordre de priorité : `uv.lock` → `Pipfile` → `environment.yml` → `requirements.txt` → `pyproject.toml` (interprété comme **format Poetry** s'il est trouvé sans `uv.lock` à côté).
- Un seul fichier de dépendances doit être présent (le premier trouvé gagne, dossier de l'entrypoint prioritaire sur la racine du repo).
- Pas de mention fiable d'un fichier `.python-version` dédié dans les extraits obtenus — la doc renvoie vers une page séparée « Configure secrets and Python version » non entièrement récupérée ici → **pin exact de version Python sur Community Cloud NON VÉRIFIÉ précisément dans cette recherche**, à confirmer manuellement avant d'en dépendre pour la prod (piste : réglage dans l'UI Community Cloud "Advanced settings" plutôt qu'un fichier de repo, d'après la pratique connue de l'outil, mais non retrouvé texte-à-texte cette session).
- Recommandation pragmatique si `uv` pose problème sur Community Cloud : générer un `requirements.txt` figé (`uv export --no-hashes -o requirements.txt` ou équivalent) en plus du `pyproject.toml`/`uv.lock` utilisés en local, pour garantir un déploiement reproductible tant que le support natif `uv.lock` n'est pas confirmé mûr.

---

## Pièges & recommandations

1. **Ne pas utiliser `st.metric(chart_data=..., chart_type=...)`** — ces paramètres n'existent pas dans la documentation/signatures consultées. Si un sparkline est nécessaire à côté d'un KPI, composer manuellement `st.metric(...)` + un petit `st.plotly_chart`/`st.line_chart` juste en dessous dans le même `st.container(border=True, key=...)`.
2. **`st.pills` → `value=`, `st.segmented_control` → `default=`.** Erreur fréquente de les confondre.
3. **`st.plotly_chart` n'a pas migré vers `width=`** comme le reste de l'API — garder `use_container_width=True` pour ce composant spécifiquement tant que non revérifié dans une version plus récente.
4. **Ne pas inventer `st.space`** — non trouvé dans la doc actuelle ; utiliser `st.container(height=N)` vide ou du CSS margin/padding via `st.html`.
5. **Pin Plotly en `<7`** (`plotly>=6.9,<7`) comme demandé par le brief ; documenter dans le README que 7.0.0 existe et n'impacte pas ce projet si migration future.
6. **`chartSequentialColors` exige exactement 10 couleurs valides**, sinon Streamlit retombe silencieusement sur la palette par défaut — à tester visuellement après configuration.
7. **`st.query_params` est vidé à chaque changement de page** dans une app multipage — ne pas s'y fier seul pour synchroniser des filtres cross-page ; combiner avec `st.session_state` (widgets globaux définis dans l'entrypoint, cf. §2.3).
8. **Connexion DuckDB `read_only=True` + `cache_resource`** : très bien pour un fichier stable, mais si `dbt` régénère `benchmark.duckdb` pendant que l'app tourne, prévoir soit un redémarrage de l'app après rebuild, soit un bouton admin qui appelle `get_connection.clear()`, soit un pattern write-then-swap côté pipeline dbt (recommandation opérationnelle, pas une garantie DuckDB/Streamlit documentée).
9. **Préférer les clés de thème aux `data-testid`** pour styliser les métriques/cartes — les `data-testid` (`stMetric`, etc.) sont des détails d'implémentation non garantis stables.
10. **`key=` → `.st-key-<key>`** est le mécanisme CSS stable et officiellement documenté à privilégier pour cibler un conteneur précis, plutôt que du CSS structurel fragile basé sur l'ordre du DOM.
11. **Vérifier `help(st.metric)` / `help(st.plotly_chart)` en local avant de coder** les paramètres marqués NON VÉRIFIÉ dans ce document (tokens de format `column_config`, `hoverlabel`/`colorway` sur `update_layout`, `.python-version` sur Community Cloud) — cette recherche a documenté tout ce qui a pu être confirmé par une source primaire, mais quelques détails fins n'ont pas pu être recoupés dans le temps imparti.
12. **Le double thème `[theme.light]`/`[theme.dark]`** ne peut pas redéfinir `fontFaces`, `baseFontSize`, `baseFontWeight`, `metricValueFontSize`, `metricValueFontWeight`, `showSidebarBorder`, `base` — ces réglages restent globaux, à garder à l'esprit lors du design du thème CEVA (typographie identique en clair/sombre, seules les couleurs changent).

---

## Squelette de référence

### `pyproject.toml` (extrait dépendances)

```toml
[project]
name = "trivial-poursuite-dashboard"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "streamlit>=1.63,<2",
    "plotly>=6.9,<7",
    "duckdb>=1.1",
    "pandas>=2.2",
]
```

### `.streamlit/config.toml`

```toml
[theme]
base = "light"
primaryColor = "#6C5CE7"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F5F6FA"
textColor = "#1A1A2E"
font = "sans serif"
baseRadius = "medium"
borderColor = "#E4E6EB"
dataframeBorderColor = "#E4E6EB"
chartCategoricalColors = ["#6C5CE7", "#00CEC9", "#FDCB6E", "#E17055", "#74B9FF", "#55EFC4"]
chartSequentialColors = [
    "#F3F0FF", "#E4DBFF", "#D2C4FF", "#BFA9FF", "#AB8EFF",
    "#9573FF", "#7E57FF", "#673CE0", "#5024BE", "#3A139C",
]

[theme.dark]
backgroundColor = "#0E1117"
secondaryBackgroundColor = "#161A23"
textColor = "#F5F6FA"
borderColor = "#2A2E39"
dataframeBorderColor = "#2A2E39"
chartCategoricalColors = ["#8C7BFF", "#3FE0D8", "#FFCF6B", "#FF8A70", "#8FC4FF", "#7CF5CE"]

[theme.sidebar]
backgroundColor = "#F5F6FA"

[theme.dark.sidebar]
backgroundColor = "#12151C"

[server]
enableStaticServing = true
runOnSave = true

[client]
toolbarMode = "auto"
showSidebarNavigation = true

[browser]
gatherUsageStats = false
```

### `lib/db.py`

```python
"""Connexion DuckDB read-only, mise en cache, partagée par toutes les pages."""
from __future__ import annotations

import duckdb
import streamlit as st

DB_PATH = "data/gold/benchmark.duckdb"


@st.cache_resource(show_spinner="Connexion à DuckDB…")
def get_connection(path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Ouvre une connexion DuckDB en lecture seule, réutilisée pour tout le process.

    Note : si un pipeline dbt reconstruit le fichier pendant que l'app tourne,
    appeler `get_connection.clear()` (bouton admin ou hook de déploiement)
    pour forcer une reconnexion sur le nouveau fichier.
    """
    return duckdb.connect(database=path, read_only=True)


@st.cache_data(ttl=3600, show_spinner=False)
def run_query(sql: str, params: tuple | None = None):
    """Exécute une requête et retourne un DataFrame pandas, mis en cache.

    `_conn` n'est pas un argument ici : on rouvre l'accès à la connexion via
    get_connection() à l'intérieur, pour que le cache_data soit basé sur
    (sql, params) uniquement (hashable), pas sur l'objet connexion.
    """
    conn = get_connection()
    return conn.execute(sql, params or []).df()
```

### `app.py`

```python
"""Point d'entrée : config, thème, connexion DB, navigation."""
import streamlit as st

from lib.db import get_connection
from views import overview

st.set_page_config(
    page_title="Benchmark LLM — Trivial Poursuite",
    page_icon=":material/quiz:",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Dashboard de benchmark LLM — trivia."},
)

# CSS global (injecté une seule fois, cible les conteneurs via st-key-*)
st.html("""
<style>
.st-key-kpi_row .stContainer { gap: 1rem; }
.st-key-kpi_card {
    border-radius: 1rem;
    padding: 0.5rem;
}
</style>
""")

st.logo("static/logo.png", icon_image="static/logo_icon.png", link="https://example.com")

# Connexion DB (une fois, cache_resource partagé)
get_connection()

overview_page = st.Page(overview.render, title="Vue d'ensemble", icon=":material/dashboard:", default=True)
models_page = st.Page("views/models.py", title="Modèles", icon=":material/model_training:")
questions_page = st.Page("views/questions.py", title="Questions", icon=":material/quiz:")

pg = st.navigation({
    "Analyse": [overview_page, models_page],
    "Détail": [questions_page],
})

pg.run()
```

### `views/overview.py`

```python
"""Page Vue d'ensemble : KPI header + bar chart avec CI + tableau filtré."""
import plotly.graph_objects as go
import streamlit as st

from lib.db import run_query


def render() -> None:
    st.title("Vue d'ensemble")

    # --- Filtres ---
    models = run_query(
        "SELECT DISTINCT model FROM results ORDER BY model"
    )["model"].tolist()
    selected_models = st.segmented_control(
        "Modèles",
        options=models,
        selection_mode="multi",
        default=models,
    )
    if not selected_models:
        st.info("Sélectionnez au moins un modèle.")
        return

    placeholders = ",".join(["?"] * len(selected_models))
    stats = run_query(
        f"""
        SELECT
            model,
            AVG(is_correct::INT) AS accuracy,
            STDDEV(is_correct::INT) / SQRT(COUNT(*)) AS se,
            COUNT(*) AS n,
            AVG(response_time) AS avg_response_time,
        FROM results
        WHERE model IN ({placeholders})
        GROUP BY model
        ORDER BY accuracy DESC
        """,
        tuple(selected_models),
    )

    # --- KPI header ---
    with st.container(key="kpi_row"):
        cols = st.columns(4, gap="medium")
        with cols[0]:
            st.metric(
                "Précision moyenne",
                f"{stats['accuracy'].mean():.1%}",
                border=True,
            )
        with cols[1]:
            st.metric(
                "Modèles comparés",
                len(selected_models),
                border=True,
            )
        with cols[2]:
            st.metric(
                "Questions évaluées",
                int(stats["n"].sum()),
                border=True,
            )
        with cols[3]:
            st.metric(
                "Temps de réponse moyen",
                f"{stats['avg_response_time'].mean():.2f}s",
                border=True,
            )

    st.divider()

    # --- Bar chart avec barres d'erreur (IC 95% approx via erreur standard) ---
    ci95 = stats["se"] * 1.96
    fig = go.Figure(
        go.Bar(
            x=stats["model"],
            y=stats["accuracy"],
            error_y=dict(type="data", array=ci95, visible=True),
            marker_color="#6C5CE7",
            texttemplate="%{y:.1%}",
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Précision: %{y:.1%}<extra></extra>",
        )
    )
    fig.update_layout(
        height=420,
        margin=dict(l=20, r=20, t=40, b=20),
        yaxis=dict(tickformat=".0%", title="Précision"),
        xaxis=dict(title=None),
        showlegend=False,
    )
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    st.plotly_chart(fig, use_container_width=True, theme="streamlit")

    st.divider()

    # --- Tableau filtré avec column_config ---
    st.subheader("Détail par modèle")
    st.dataframe(
        stats,
        hide_index=True,
        column_config={
            "model": st.column_config.TextColumn("Modèle"),
            "accuracy": st.column_config.ProgressColumn(
                "Précision", format="%.1f%%", min_value=0, max_value=1
            ),
            "se": st.column_config.NumberColumn("Erreur standard", format="%.3f"),
            "n": st.column_config.NumberColumn("N questions"),
            "avg_response_time": st.column_config.NumberColumn(
                "Temps moyen (s)", format="%.2f s"
            ),
        },
        width="stretch",
    )
```

---

## Sources

**Streamlit (Context7 `/streamlit/docs` + WebFetch direct docs.streamlit.io)**
- https://docs.streamlit.io/develop/api-reference/navigation/st.navigation
- https://docs.streamlit.io/develop/api-reference/navigation/st.page
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/multipage-apps/page-and-navigation.md
- https://github.com/streamlit/docs/blob/main/content/develop/tutorials/multipage-apps/dynamic-navigation.md
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/multipage-apps/widgets.md
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/architecture/widget-behavior.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/configuration/set_page_config.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/configuration/config-toml.md
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/configuration/theming-colors-and-borders.md
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/configuration/theming-fonts.md
- https://github.com/streamlit/docs/blob/main/content/develop/tutorials/theming/static-fonts.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/data/dataframe.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/data/column_config/_index.md (+ progresscolumn.md, textcolumn.md, datetimecolumn.md, barchartcolumn.md, column.md)
- https://github.com/streamlit/docs/blob/main/content/develop/tutorials/elements/dataframes/row_selections.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/caching-and-state/cache-data.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/caching-and-state/cache-resource.md
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/architecture/caching.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/connections/_index.md
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/connections/connecting-to-data.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/charts/plotly_chart.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/layout/container.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/layout/columns.md
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/app-design/layouts-and-containers.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/widgets/segmented_control.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/widgets/pills.md
- https://docs.streamlit.io/develop/api-reference/text/st.badge (WebFetch)
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/text/markdown.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/media/logo.md
- https://github.com/streamlit/docs/blob/main/content/develop/api-reference/caching-and-state/query_params.md, session_state.md
- https://github.com/streamlit/docs/blob/main/content/develop/concepts/architecture/fragments.md
- https://github.com/streamlit/docs/blob/main/python/streamlit.json (signatures API exactes, sources multiples)
- https://github.com/streamlit/docs/blob/main/content/develop/quick-references/release-notes/2026.md et 2025.md
- https://docs.streamlit.io/develop/quick-reference/release-notes (WebFetch)
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies (WebFetch)

**Plotly (Context7 `/plotly/plotly.py` + GitHub)**
- https://github.com/plotly/plotly.py/blob/main/doc/python/templates.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/error-bars.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/ecdf-plots.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/subplots.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/indicator.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/bullet-charts.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/imshow.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/annotated-heatmap.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/violin.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/box-plots.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/discrete-color.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/styling-plotly-express.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/legend.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/figure-labels.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/setting-graph-size.md
- https://github.com/plotly/plotly.py/blob/main/doc/python/axes.md
- https://raw.githubusercontent.com/plotly/plotly.py/main/CHANGELOG.md (WebFetch)

**PyPI (requêtes directes `curl` sur l'API JSON, la plus fiable pour les numéros de version)**
- https://pypi.org/pypi/streamlit/json
- https://pypi.org/pypi/plotly/json
- https://pypi.org/project/streamlit/
- https://pypi.org/project/plotly/

**WebSearch (recoupement communautaire, confiance moyenne — signalé explicitement dans le texte à chaque usage)**
- « streamlit duckdb connection st.connection official DuckDB 2026 »
- « streamlit custom CSS st.markdown unsafe_allow_html best practice st.html 2026 »
- « Streamlit Community Cloud deploy uv pyproject.toml python-version pin 2026 »
- « streamlit cache_resource duckdb read_only=True connection shared across pages dbt rebuild file locked »
- « Plotly 7.0.0 release notes breaking changes 2026 »
