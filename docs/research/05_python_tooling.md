# Stack Python pour le pipeline `trivia-bench` — Référence vérifiée (2026-09-10)

Cible : macOS Apple Silicon, `uv` (build 0.10.x installé, dernière branche stable publiée `0.12.x` — voir Pièges), Python 3.12, projet `uv` unique avec layout `src/`.

---

## Résumé exécutif

- **Gestionnaire de projet** : `uv` (Rust, Astral). `uv init --package` crée un projet `src/`-layout avec build-system par défaut **`uv_build`** depuis uv ≥0.7.19 (remplace `hatchling`) — si on veut `hatchling` explicitement (comme demandé), utiliser `uv init --package --build-backend hatchling` ou l'écrire à la main dans `pyproject.toml`.
- **Dépendances dev** : `[dependency-groups] dev = [...]` (PEP 735, standard uv actuel) plutôt que l'ancien `[tool.uv.dev-dependencies]`. Le groupe `dev` est installé **par défaut** par `uv sync`/`uv run` (comportement spécial documenté) ; les autres groupes doivent être ajoutés à `[tool.uv] default-groups` ou appelés explicitement avec `--group`.
- **Une seule commande d'installation équipe** : `uv sync` (crée le `.venv`, installe le projet en **editable** par défaut + groupe `dev`). En CI : `uv sync --locked` (ou `--frozen` pour ne pas du tout vérifier la fraîcheur du lock).
- **Polars écrit du Parquet nativement en Rust, sans PyArrow** (`use_pyarrow=True` est optionnel, non requis). PyArrow reste nécessaire dans ce projet car **Streamlit en dépend en dur** (`pyarrow>=7.0,<26,!=25.0.0` dans les dépendances de `streamlit==1.63.0`) — donc pas besoin d'ajouter PyArrow "pour Polars", mais il sera présent via Streamlit de toute façon.
- **DuckDB interroge directement un DataFrame Polars** via `duckdb.sql("SELECT * FROM df")` (résolution du nom de variable Python), sans Pandas. `.pl()` retourne un DataFrame Polars, `.df()` un DataFrame Pandas.
- **Hive partitioning fonctionne des deux côtés** : `pl.scan_parquet("dir/**/*.parquet", hive_partitioning=True)` et `duckdb.sql("... read_parquet('dir/**/*.parquet', hive_partitioning = true)")`. Recommandé pour accumuler les runs de benchmark plutôt que réécrire tout le fichier.
- **httpx + tenacity** : `httpx.Client(transport=httpx.HTTPTransport(retries=N))` gère les erreurs de connexion bas niveau ; `tenacity` gère la logique de retry métier (status HTTP, rate-limit custom) — les deux sont complémentaires, pas redondants.
- **Pydantic v2** : `TypeAdapter(list[Question]).validate_python(data)` est l'idiome recommandé pour valider une liste JSON brute ; `model_validator(mode="after")` pour les contraintes inter-champs (ex. `correct_answer not in incorrect_answers`).
- **mypy est passé en version majeure 2.x en 2026** (2.0 en mai 2026) — piège si de la doc/mémoire mentionne encore "mypy 1.x".
- **rapidfuzz nécessite Python ≥3.11** (compatible 3.12) — `process.extractOne(query, choices, scorer=fuzz.WRatio, processor=utils.default_process)` est l'idiome recommandé, avec normalisation préalable (`utils.default_process` = lowercase + strip ponctuation + collapse espaces).
- **Logging recommandé : Loguru** plutôt que stdlib+RichHandler pour ce projet (CLI + scraping + benchmark asynchrone/séquentiel) : API `logger.add(sink, rotation=..., level=..., serialize=...)` en une ligne, zéro configuration de handlers/formatters, et compatible avec Rich pour les progress bars (deux libs orthogonales, pas de conflit).
- **Ruff remplace flake8+isort+pyupgrade+black** : un seul outil, `ruff check` (lint) + `ruff format` (formatage façon Black). Rule-set recommandé : `E,F,I,B,UP,N,SIM,RUF`.
- **`uv add` gère `dbt-core`, `dbt-duckdb` et `streamlit` sans souci connu** début 2026 (les anciens bugs de résolution `uv pip install --upgrade` liés aux bornes de version de `dbt-core` sont spécifiques à `pip install`, pas à `uv add`/`uv lock` en mode projet). DuckDB fournit des wheels `macosx_11_0_arm64` natifs — aucun souci Apple Silicon.

---

## Tableau des versions

*(Snapshot vérifié via PyPI JSON API le 2026-09-10 — épingler ces versions ou plus récentes dans `uv.lock` ; certaines communiquent une borne Python assez haute donc bien vérifier que `requires-python = ">=3.12"` du projet reste dans leurs bornes)*

| Package | Dernière version (PyPI) | Python requis | Rôle dans le projet |
|---|---|---|---|
| `uv` | 0.12.10 (branche stable la plus récente ; poste cible a 0.10.x) | n/a (binaire) | gestionnaire de projet / lock / venv |
| `polars` | 1.44.2 | ≥3.10 | DataFrame bronze→silver, écriture Parquet |
| `pyarrow` | 25.0.1 | ≥3.10 | requis transitivement par Streamlit (`st.dataframe`) |
| `httpx` | 0.28.1 stable (1.0 en pré-version `1.0.dev6`, pas encore stable) | ≥3.8 | client HTTP pour `trivia scrape` |
| `tenacity` | 9.1.4 | ≥3.10 | retries/backoff sur les appels HTTP/LLM |
| `pydantic` | 2.13.5 | ≥3.9 | modèles `Question`, validation |
| `pydantic-settings` | 2.15.0 | ≥3.10 | `Settings(BaseSettings)` + `.env` |
| `typer` | 0.27.2 | ≥3.10 | CLI (`trivia scrape/clean/benchmark/build`) |
| `rich` | 15.0.0 | ≥3.9 | progress bars, tables, rendu console |
| `loguru` | 0.7.3 | ≥3.5,<4.0 | logging applicatif |
| `ruff` | 0.16.6 | ≥3.7 (l'outil, pas le code linté) | lint + format |
| `pytest` | 9.1.1 | ≥3.10 | tests |
| `pytest-httpx` | 0.36.2 | ≥3.10 | mock des appels `httpx` en test |
| `respx` (alternative à pytest-httpx) | 0.23.1 | ≥3.8 | idem, API basée sur `unittest.mock`-style routing |
| `python-dotenv` | 1.2.3 | ≥3.10 | chargement `.env` (redondant avec pydantic-settings, utile en script/notebook) |
| `pre-commit` | 4.6.2 | ≥3.10 (l'outil) | hooks git |
| `pre-commit-hooks` (repo standard) | v6.0.0 | ≥3.9 (l'outil) | hooks génériques (trailing-whitespace, etc.) |
| `ruff-pre-commit` (repo) | v0.16.6 (suit la version de Ruff) | n/a | intégration Ruff/pre-commit |
| `mypy` | **2.3.1** (mypy est passé en v2.x en mai 2026) | ≥3.10 | typage statique optionnel |
| `tqdm` | 4.70.0 | ≥3.8 | barres de progression alternative (non retenu, on utilise `rich`) |
| `rapidfuzz` | 3.14.6 | ≥3.11 | fuzzy matching des réponses |
| `Unidecode` | 1.4.0 | ≥3.7 | transformation Unicode→ASCII (alternative à `unicodedata`) |
| `duckdb` | 1.5.5 (branche LTS 1.4.x maintenue jusqu'à mi/fin-sept 2026) | ≥3.10 | requêtes SQL sur Parquet/DataFrames, backend dbt |
| `dbt-core` | 1.12.4 | ≥3.10 | transformations SQL (couche gold) |
| `dbt-duckdb` | 1.11.0 | ≥3.10 | adapter dbt→DuckDB |
| `streamlit` | 1.63.0 | ≥3.10 | app de visualisation |

Toutes ces bornes basses sont ≤3.12 et aucune borne haute connue n'exclut 3.12 : **compatibilité Python 3.12 confirmée pour l'ensemble de la stack**.

---

## 1. Projet `uv` : scaffolding exact

### Commandes de création

```console
$ uv python pin 3.12          # écrit .python-version = "3.12" (à faire avant init, ou après)
$ uv init --package trivia-bench --python 3.12
$ cd trivia-bench
```

`uv init` (sans option) crée un template *application* ; `--package` force la présence d'un build-system et d'un layout `src/<nom>/` avec entry points possibles ; `--lib` est réservé aux bibliothèques distribuables. Depuis uv ≥0.7.19 (stabilisation de `uv_build`), **le build-backend par défaut de `uv init --package` est `uv_build`, pas `hatchling`** — c'est un changement de comportement récent à connaître. Pour obtenir `hatchling` comme demandé dans le brief :

```console
$ uv init --package trivia-bench --python 3.12 --build-backend hatchling
```

Fichiers générés par `uv init` : `.git/`, `.gitignore`, `.python-version`, `pyproject.toml`, `README.md`, `src/trivia_bench/__init__.py`. Après premier `uv add`/`uv sync`/`uv run` : `.venv/` et `uv.lock` apparaissent.

### Dépendances

```console
$ uv add httpx tenacity polars pyarrow pydantic pydantic-settings typer rich loguru rapidfuzz python-dotenv duckdb dbt-core dbt-duckdb streamlit
$ uv add --dev pytest pytest-httpx ruff pre-commit mypy
```

- `uv add <pkg>` → ajoute à `[project.dependencies]`.
- `uv add --dev <pkg>` → équivalent à `uv add --group dev <pkg>`, ajoute à `[dependency-groups] dev = [...]`.
- `uv add --group <nom> <pkg>` → groupe personnalisé (ex. `lint`, `test`) — n'est **pas** installé par défaut sauf ajout à `[tool.uv] default-groups`.

### Installation en une commande (poste d'un collègue)

```console
$ uv sync
```

`uv sync` verrouille (si besoin), crée `.venv/`, installe le projet racine en **mode editable par défaut** (pas besoin de `pip install -e .`), et installe le groupe `dev` par défaut. En CI/prod, figer strictement :

```console
$ uv sync --locked   # échoue si uv.lock n'est pas à jour (au lieu de le régénérer)
$ uv sync --frozen    # installe tel quel sans même vérifier la fraîcheur du lock
```

### Exécution

```console
$ uv run trivia scrape --limit 50
$ uv run pytest
$ uv run python -m trivia_bench
```

`uv run` synchronise automatiquement l'environnement avant d'exécuter (sauf `--frozen`/`--no-sync`).

### Mise à jour du lock

```console
$ uv lock --upgrade              # upgrade toutes les deps compatibles avec les contraintes
$ uv lock --upgrade-package polars   # upgrade ciblé
```

### `.python-version` et `uv python pin`

`uv python pin 3.12` écrit un fichier `.python-version` contenant `3.12` à la racine — uv l'utilise pour créer le `.venv` et pour la résolution, sans avoir besoin de le répéter en CLI à chaque commande.

### `uvx` / `uv tool run` pour des outils ponctuels

```console
$ uvx ruff check .
$ uv tool run ruff format .
$ uvx pre-commit run --all-files
```

`uvx <outil>` est un raccourci strict de `uv tool run <outil>` : exécute l'outil dans un environnement éphémère/isolé sans polluer le `.venv` du projet ni nécessiter `uv add --dev`. Utile pour `pre-commit` en CI si on ne veut pas l'ajouter aux deps du projet — mais ici on le met quand même en `dev` group pour que `uv run pre-commit install` fonctionne localement.

### `[build-system]` et `[project.scripts]`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
trivia = "trivia_bench.cli:app"
```

### `dbt-core`, `streamlit`, `duckdb` sous `uv` : pièges connus

- **DuckDB** : wheels `macosx_11_0_arm64` disponibles nativement sur PyPI pour toutes les versions récentes → aucun souci de compilation sur Apple Silicon, `uv add duckdb` installe un wheel précompilé.
- **dbt-core / adapters** : un bug documenté concerne `uv pip install --upgrade dbt-core` (mode *pip interface*) qui peut ignorer une contrainte de compatibilité imposée par un adapter (ex. `dbt-databricks` exigeant `dbt-core<1.11.7`). Ce piège concerne l'usage `uv pip install`, **pas** le mode projet (`uv add` + `uv.lock`), qui résout toutes les contraintes de `pyproject.toml`/`dependency-groups` ensemble et échoue explicitement en cas de conflit réel. Recommandation : rester en mode projet (`uv add`/`uv sync`/`uv lock`), éviter `uv pip install` pour les dépendances applicatives.
- **Streamlit** : aucun souci de résolution signalé avec `uv` ; Streamlit ≥ une version récente 2026 supporte même `uv run streamlit run app.py` / un point d'entrée `App.run()` documenté dans les notes de version 2026 de Streamlit.

---

## 2. Polars — idiomes couche silver

### Lecture CSV (bronze)

```python
import polars as pl

df = pl.read_csv(
    "data/bronze/questions.csv",
    infer_schema_length=10_000,   # ou None pour scanner tout le fichier
    schema_overrides={
        "category": pl.String,
        "difficulty": pl.String,
        "type": pl.String,
    },
)
```

`schema_overrides` doit couvrir exactement les colonnes visées (pas besoin de couvrir toutes les colonnes du fichier, contrairement à l'ancien comportement encore observable dans certains guides de migration). `pl.String` est le nom canonique depuis Polars ≥0.19/1.x ; `pl.Utf8` reste un **alias** conservé pour compatibilité — préférer `pl.String` dans du code neuf.

### Transformations `with_columns`

```python
import html

df = df.with_columns(
    pl.col("question").str.strip_chars().alias("question"),
    pl.col("category").str.to_lowercase(),
    # vectorisé quand possible (rapide, pas de callback Python) :
    pl.col("question").str.replace_all("&amp;", "&"),
    # sinon, UDF explicite avec return_dtype obligatoire pour la perf/le typage :
    pl.col("question").map_elements(html.unescape, return_dtype=pl.String),
)
```

- `.str.strip_chars()` est le nom actuel (renommage de l'ancien `.str.strip()`, qui prêtait à confusion avec le trim par défaut vs par jeu de caractères).
- `Expr.map_elements(function, return_dtype=...)` exécute la fonction Python **ligne par ligne** (donc lent sur de gros volumes) — à réserver aux cas non vectorisables comme `html.unescape` (pas d'équivalent Rust natif dans Polars). Pour tout ce qui est remplacement de motifs fixes/regex, préférer `.str.replace_all()` (vectorisé, en Rust).
- `group_by` (avec underscore) est le nom actuel — l'ancien `groupby` est déprécié/retiré dans les versions 1.x.

### `pl.Enum` pour `category` / `difficulty` / `type`

```python
Difficulty = pl.Enum(["easy", "medium", "hard"])
QuestionType = pl.Enum(["multiple", "boolean"])

df = df.with_columns(
    pl.col("difficulty").cast(Difficulty),
    pl.col("type").cast(QuestionType),
)
```

Recommandation officielle : préférer `pl.Enum` (catégories fixées à l'avance, ordonnables, encodage stable entre colonnes/datasets) à `pl.Categorical` (catégories inférées dynamiquement, plus coûteux — ré-encodage ou lookup de cache). Ici `difficulty`/`type` ont un jeu de valeurs fermé et connu à l'avance → `pl.Enum` est le bon choix. `category` (52 catégories OpenTDB, potentiellement instable dans le temps) peut rester `pl.Categorical` ou `pl.String` selon si on veut figer la liste.

### Colonnes liste (`incorrect_answers`)

```python
df = df.with_columns(
    pl.col("incorrect_answers").cast(pl.List(pl.String))
)
```

Une colonne `pl.List(pl.String)` se sérialise nativement en Parquet comme un groupe répété (type `LIST` Arrow/Parquet standard) — lisible tel quel par PyArrow, DuckDB, et Polars, sans transformation supplémentaire.

### Déduplication, écriture, lecture

```python
df = df.unique(subset=["question", "category"])  # ou n_unique(subset=...) pour compter

df.write_parquet("data/silver/questions.parquet", compression="zstd")

df2 = pl.read_parquet("data/silver/questions.parquet")          # eager
lf  = pl.scan_parquet("data/silver/questions.parquet")          # lazy, requêtes optimisées
```

`write_parquet` utilise **l'écrivain Rust natif de Polars par défaut** (pas besoin de PyArrow installé) ; `use_pyarrow=True` est une option pour forcer l'implémentation C++ PyArrow si besoin d'une fonctionnalité Parquet spécifique — inutile ici.

### `pl.concat`, export Arrow, interop DuckDB

```python
combined = pl.concat([df_run1, df_run2])

arrow_table = df.to_arrow()          # nécessite pyarrow installé (présent via Streamlit)

import duckdb
result = duckdb.sql("SELECT * FROM df WHERE difficulty = 'hard'").pl()  # résout la variable Python "df"
```

`duckdb.sql("SELECT ... FROM df")` **fonctionne directement sur un DataFrame Polars sans Pandas installé** — DuckDB détecte et référence la variable Python nommée `df` dans la requête SQL par introspection de frame ; `.pl()` retourne le résultat en DataFrame Polars, `.df()` en Pandas (à éviter ici, pas de dépendance Pandas dans ce projet).

### Lazy vs eager, `sink_parquet`

- `pl.read_csv`/`pl.read_parquet` → eager (tout en mémoire immédiatement).
- `pl.scan_csv`/`pl.scan_parquet` → lazy (`LazyFrame`), permet l'optimisation de requête (projection/predicate pushdown) avant `.collect()`.
- `LazyFrame.sink_parquet(path)` → exécute en mode streaming et écrit directement sur disque, utile pour des volumes qui ne tiennent pas en RAM (non critique ici vu les volumes ~milliers de lignes, mais bon réflexe pour `answers.parquet` qui grossit au fil des runs).

**Source** : Context7 `/pola-rs/polars` (docs officielles pola-rs/polars sur GitHub), `docs.pola.rs/user-guide/expressions/categorical-data-and-enums/`.

---

## 3. Détails Parquet

- **Polars écrit du Parquet sans PyArrow** — confirmé (écrivain Rust natif par défaut ; `use_pyarrow=True` optionnel). Source : documentation `DataFrame.write_parquet` + discussion GitHub pola-rs/polars #14542 (support du writer Rust natif).
- **PyArrow reste nécessaire dans ce repo** car **Streamlit en dépend physiquement** : `streamlit==1.63.0` déclare `pyarrow!=25.0.0,<26,>=7.0` dans ses dépendances (confirmé via PyPI JSON). C'est de toute façon `st.dataframe`/`st.table` qui utilisent PyArrow en interne pour le rendu — donc `pyarrow` sera installé transitivement même sans l'ajouter explicitement, mais l'ajouter en direct (`uv add pyarrow`) est plus explicite/robuste. **Piège** : la version 25.0.0 exacte de PyArrow est exclue par Streamlit — au 2026-09-10 la dernière PyPI est 25.0.1, donc pas de conflit, mais à surveiller lors d'un futur `uv lock --upgrade`.
- **Compression** : `zstd` recommandé (meilleur ratio compression/vitesse que `snappy` pour ce type de données textuelles répétitives — catégories, difficulté). `write_parquet(path, compression="zstd")`.
- **`statistics=True`** : activé par défaut dans les writers Parquet modernes (Polars comme PyArrow) — utile pour le predicate pushdown côté DuckDB/Polars lazy scan, mais **sans impact mesurable** sur un volume de quelques milliers de lignes comme celui du projet.
- **Row-group sizing** : non pertinent pour ~5k lignes (un seul row-group largement suffisant, bien en dessous des seuils de découpe par défaut de tous les writers) — ne pas configurer, laisser les valeurs par défaut.
- **Schéma d'évolution / append de runs de benchmark** : **une partition par run est recommandée plutôt qu'une réécriture complète du fichier**, pour deux raisons : (1) écrire un run = un seul fichier immuable, jamais de réécriture concurrente/risque de corruption ; (2) lecture sélective via Hive partitioning.

```
data/gold/answers/
  run_id=2026-09-01T10-00-00/
    part-0.parquet
  run_id=2026-09-05T14-30-00/
    part-0.parquet
```

Lecture unifiée, vérifiée des deux côtés :

```python
# Polars
lf = pl.scan_parquet("data/gold/answers/**/*.parquet", hive_partitioning=True)
```

```sql
-- DuckDB
SELECT * FROM read_parquet('data/gold/answers/**/*.parquet', hive_partitioning = true);
```

Dans les deux moteurs, le glob `**/*.parquet` est requis pour la découverte des fichiers, et `hive_partitioning=True/true` active l'extraction des colonnes de partition (`run_id=...`) depuis les noms de dossiers — DuckDB active même cette détection automatiquement par défaut si la structure `clé=valeur` est reconnue, mais le flag explicite reste recommandé pour la reproductibilité.

**Sources** : `docs.pola.rs/user-guide/io/hive/`, `duckdb.org/docs/current/data/partitioning/hive_partitioning`, GitHub `duckdb/duckdb` discussion #14164.

---

## 4. httpx + tenacity : client HTTP robuste

```python
import time
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

logger = logging.getLogger(__name__)


class RateLimited(Exception):
    """Levée quand l'API renvoie un statut indiquant un rate-limit applicatif (ex. OpenTDB code 5)."""


def make_client() -> httpx.Client:
    return httpx.Client(
        base_url="https://opentdb.com",
        timeout=httpx.Timeout(10.0, read=30.0),
        headers={"User-Agent": "trivia-bench/0.1 (+contact@example.com)"},
        transport=httpx.HTTPTransport(retries=3),  # retries bas niveau: erreurs de connexion/DNS
    )


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=30),  # backoff exponentiel + jitter
    retry=retry_if_exception_type((httpx.HTTPError, RateLimited)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def fetch_questions(client: httpx.Client, amount: int = 50) -> dict:
    response = client.get("/api.php", params={"amount": amount, "type": "multiple"})
    response.raise_for_status()
    payload = response.json()
    if payload.get("response_code") == 5:
        raise RateLimited("OpenTDB rate limit (response_code=5)")
    return payload


def scrape_all(total: int, batch_size: int = 50) -> list[dict]:
    results = []
    with make_client() as client:
        for _ in range(0, total, batch_size):
            t0 = time.monotonic()
            payload = fetch_questions(client, amount=batch_size)
            results.extend(payload["results"])
            elapsed = time.monotonic() - t0
            # OpenTDB tolère ~1 requête / 5s par IP : on complète le delta si l'appel a été rapide
            time.sleep(max(0.0, 5.1 - elapsed))
    return results
```

Points vérifiés :
- `httpx.HTTPTransport(retries=N)` gère uniquement les erreurs **de connexion** (`ConnectError`, `ConnectTimeout`) au niveau transport — il ne relit pas sur un code HTTP 4xx/5xx ni sur une erreur applicative. D'où la complémentarité avec `tenacity` : `tenacity` couvre `httpx.HTTPError` (levée après `raise_for_status()`) **et** l'exception métier `RateLimited`.
- `httpx.Timeout(10.0, read=30.0)` : timeout par défaut 10s pour connect/write/pool, 30s spécifiquement pour la lecture (utile si l'API est lente à streamer une grosse réponse).
- `wait_exponential_jitter` : le paramètre `initial` est **déprécié au profit de `multiplier`** dans les versions récentes de tenacity (avertissement `DeprecationWarning` mais fonctionne encore) — préférer `wait_exponential_jitter(multiplier=1, max=30)` dans du code neuf.
- `time.monotonic()` recommandé pour mesurer des durées (insensible aux ajustements d'horloge système), par opposition à `time.time()`. `time.perf_counter()` est équivalent pour ce cas d'usage (résolution plus fine, même garantie de monotonicité sur la durée du process).

**Sources** : Context7 `/encode/httpx` (docs.astral… non, `github.com/encode/httpx`), `/jd/tenacity`.

---

## 5. Pydantic v2 — modèles et settings

```python
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator, TypeAdapter


class Question(BaseModel):
    category: str = Field(min_length=1)
    type: Literal["multiple", "boolean"]
    difficulty: Literal["easy", "medium", "hard"]
    question: str = Field(min_length=1)
    correct_answer: str = Field(min_length=1)
    incorrect_answers: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def check_correct_not_in_incorrect(self) -> Self:
        if self.correct_answer in self.incorrect_answers:
            raise ValueError("correct_answer ne doit pas apparaître dans incorrect_answers")
        return self


# Validation d'une liste brute issue de l'API
questions = TypeAdapter(list[Question]).validate_python(raw_json["results"])

# Ingestion Polars
import polars as pl

df = pl.DataFrame([q.model_dump() for q in questions])
# équivalent, plus direct pour une liste de dicts :
df = pl.from_dicts([q.model_dump() for q in questions])
```

`model_validator(mode="after")` reçoit `self` déjà validé champ par champ et retourne `Self` (ou lève `ValueError`, converti automatiquement en `ValidationError` par Pydantic). `TypeAdapter(list[Question]).validate_python(data)` est l'idiome recommandé pour valider une collection sans créer de modèle wrapper dédié.

`Field(min_length=1)` fonctionne aussi bien sur `str` (longueur de chaîne) que sur `list` (nombre d'éléments) — même contrainte, deux sémantiques selon le type annoté.

### `ConfigDict(frozen=True)` (pour un modèle immuable, ex. config de run)

```python
from pydantic import BaseModel, ConfigDict

class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_key: str
    limit: int
```

### `pydantic-settings` avec `.env`

```python
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TRIVIA_",
        extra="ignore",
    )

    lmstudio_host: str = Field(default="http://localhost:1234")
    data_dir: Path = Field(default=Path("data"))
    model_key: str = Field(default="local-model")


settings = Settings()  # lit TRIVIA_LMSTUDIO_HOST, TRIVIA_DATA_DIR, TRIVIA_MODEL_KEY depuis .env/env
```

Avec `env_prefix="TRIVIA_"`, une variable `.env` doit s'appeler `TRIVIA_LMSTUDIO_HOST` (le préfixe est retiré automatiquement pour matcher `lmstudio_host`). `env_file` accepte aussi une liste (`[".env", ".env.local"]`), les fichiers suivants surchargeant les précédents.

**Sources** : Context7 `/pydantic/pydantic`, `/pydantic/pydantic-settings` (docs officielles GitHub pydantic/pydantic-settings).

---

## 6. Typer — squelette CLI

```python
from typing import Annotated
import typer
from rich.progress import Progress

app = typer.Typer(
    help="trivia-bench: scraper, clean, benchmark, build.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command()
def scrape(
    limit: Annotated[int, typer.Option("--limit", help="Nombre de questions à récupérer.")] = 50,
) -> None:
    """Récupère les questions depuis OpenTDB et écrit la couche bronze."""
    with Progress() as progress:
        task = progress.add_task("Scraping...", total=limit)
        # ... appel scrape_all, progress.advance(task, n) à chaque batch
    typer.echo(f"{limit} questions récupérées.")


@app.command()
def clean() -> None:
    """Nettoie/normalise la couche bronze vers la couche silver (Polars)."""
    ...


@app.command()
def benchmark(
    model: Annotated[str, typer.Option(help="Clé du modèle LLM à évaluer.")],
) -> None:
    """Lance un run de benchmark LLM et écrit un nouveau partition answers/run_id=.../."""
    try:
        ...
    except Exception as exc:
        typer.echo(f"Échec du benchmark: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def build() -> None:
    """Déclenche `dbt build` sur le projet dbt-duckdb."""
    ...


if __name__ == "__main__":
    app()
```

`no_args_is_help=True` affiche l'aide quand la CLI est invoquée sans sous-commande (plutôt que planter/rien faire). `rich_markup_mode="rich"` (valeur par défaut) active le balisage Rich (`[bold]...[/bold]`) dans les docstrings de commandes pour un rendu `--help` enrichi. `typer.Exit(code=1)` termine proprement le process avec un code de sortie non nul — pattern standard pour signaler un échec à un script appelant.

Pour des sous-CLI groupées (ex. `trivia dbt run`, `trivia dbt test`) : `app.add_typer(dbt_app, name="dbt")` — **le nom du sous-groupe doit être passé explicitement** depuis Typer 0.14 (l'inférence automatique du nom depuis le callback a été supprimée).

**Sources** : Context7 `/fastapi/typer`, `typer.tiangolo.com/tutorial/commands/help/`.

---

## 7. Logging — Loguru recommandé

**Recommandation : Loguru plutôt que stdlib `logging` + `RichHandler`.**

Justification : le projet est un ensemble de commandes CLI courtes (scrape/clean/benchmark/build), pas un service long-running avec hiérarchie de loggers complexe — Loguru élimine le boilerplate `getLogger(__name__)` + configuration de handlers/formatters de la stdlib, offre `rotation=`/`serialize=` (JSON) en un paramètre pour journaliser les runs de benchmark, et une API d'exception (`logger.exception`) plus lisible. `rich.progress.Progress` reste utilisé en parallèle pour les barres de progression (rôle différent, pas de conflit — Loguru gère les logs texte, Rich gère l'UI interactive du terminal).

```python
import sys
from loguru import logger

logger.remove()  # retire le handler stderr par défaut avant de reconfigurer
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(
    "logs/trivia_{time}.log",
    level="DEBUG",
    rotation="10 MB",
    retention="14 days",
    serialize=True,  # JSON structuré, exploitable pour les runs de benchmark
)

logger.info("Scraping started, limit={}", 50)
try:
    ...
except Exception:
    logger.exception("Scraping failed")
```

**Sources** : Context7 `/delgan/loguru` (docs officielles GitHub delgan/loguru).

---

## 8. Ruff + pytest + pre-commit

### `[tool.ruff]` / `[tool.ruff.lint]` / `[tool.ruff.format]`

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "SIM", "RUF"]

[tool.ruff.lint.isort]
known-first-party = ["trivia_bench"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
docstring-code-format = true
```

Règles sélectionnées : `E`/`F` (pycodestyle/pyflakes, base), `I` (isort — tri des imports), `B` (bugbear — pièges Python courants), `UP` (pyupgrade — idiomes modernes selon `target-version`), `N` (pep8-naming), `SIM` (simplifications de code), `RUF` (règles spécifiques Ruff). `target-version = "py312"` aligne les suggestions `UP` sur la syntaxe disponible en 3.12.

### `[tool.pytest.ini_options]`

```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-ra -q"
testpaths = ["tests"]
```

### `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.6
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-toml
      - id: check-yaml
      - id: check-added-large-files
```

Note sur les IDs de hooks Ruff : `id: ruff-check` (le nom du hook de lint a été renommé — l'ancien `id: ruff` est un alias historique encore accepté mais déprécié dans la doc actuelle). `rev:` doit être un tag exact du dépôt `ruff-pre-commit` (ici `v0.16.6`, synchronisé avec la version de Ruff installée localement/en CI — **à vérifier/mettre à jour à chaque `uv lock --upgrade-package ruff`**, sinon la version lint locale et la version pre-commit divergent).

### mypy (optionnel)

```toml
[tool.mypy]
strict = true
python_version = "3.12"
packages = ["trivia_bench"]

[[tool.mypy.overrides]]
module = ["duckdb.*"]
ignore_missing_imports = true
```

Statut des stubs : **Polars est nativement typé** (fichiers `.pyi`/`py.typed` distribués avec le package). **DuckDB** et **Streamlit** n'ont pas de statut de stubs officiellement confirmé dans cette recherche (NON VÉRIFIÉ pour la complétude — recommandation prudente : `ignore_missing_imports = true` ciblé sur ces modules plutôt qu'un `ignore_missing_imports` global, pour ne pas masquer de vraies erreurs de typage ailleurs). `mypy` est passé en version majeure **2.x** en 2026 (2.0.0 publié en mai 2026) — **NON VÉRIFIÉ dans le détail des breaking changes 2.x** ; à consulter dans `mypy.readthedocs.io/en/stable/changelog.html` avant d'activer `strict = true` sur un gros codebase existant.

**Sources** : Context7 `/astral-sh/ruff`, `/pytest-dev/pytest`, `/pre-commit/pre-commit.com`, WebSearch (releases `astral-sh/ruff-pre-commit`, `pre-commit/pre-commit-hooks`, `mypy-lang.blogspot.com`).

---

## 9. Normalisation des réponses

```python
import html
import re
import unicodedata

from rapidfuzz import fuzz, process, utils

_ARTICLES = {"the", "a", "an"}
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def strip_accents(s: str) -> str:
    # NFKD décompose lettre+diacritique, on retire ensuite les marques combinantes (Mn)
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_answer(raw: str) -> str:
    s = html.unescape(raw)             # &#039; -> ' (nécessaire pour les payloads OpenTDB)
    s = strip_accents(s)
    s = s.casefold()                   # plus agressif que .lower(), pensé pour les comparaisons
    s = _PUNCT_RE.sub(" ", s)          # ponctuation -> espace
    tokens = [t for t in s.split() if t not in _ARTICLES]
    return " ".join(tokens)


def match_answer(candidate: str, correct: str, threshold: float = 90.0) -> bool:
    score = fuzz.ratio(normalize_answer(candidate), normalize_answer(correct))
    return score >= threshold


def best_match(candidate: str, choices: list[str], threshold: float = 90.0) -> str | None:
    result = process.extractOne(
        candidate,
        choices,
        scorer=fuzz.WRatio,
        processor=utils.default_process,   # lowercase + strip ponctuation + collapse espaces
        score_cutoff=threshold,
    )
    return result[0] if result else None
```

- **OpenTDB renvoie des entités HTML** (`&#039;`, `&quot;`, `&amp;`...) dans les questions/réponses — `html.unescape` est l'étape systématique documentée par tous les wrappers OpenTDB en Python avant tout affichage/comparaison.
- **`unicodedata.normalize("NFKD", s)` + filtre `unicodedata.combining()`** : léger, sans dépendance, **mais limité** — certains caractères composés hors-Latin (ex. `ł` polonais) ne se décomposent pas proprement en base+diacritique via NFKD et finissent supprimés plutôt que translittérés. **`Unidecode`** est plus agressif (translittère tout Unicode vers de l'ASCII approximatif, y compris CJK/cyrillique/etc.) mais ajoute une dépendance. Pour ce projet (questions trivia majoritairement en anglais/latin), `unicodedata` + `casefold()` est suffisant et évite une dépendance ; `Unidecode` (1.4.0, ≥3.7) reste l'option de repli si des réponses contiennent des scripts non-latins.
- **Seuils rapidfuzz** : pas de seuil officiel unique publié par la doc, mais la pratique communautaire documentée converge sur **≥90 pour un "quasi-exact"** (fautes de frappe mineures, variations de casse/ponctuation déjà neutralisées par la normalisation en amont) et **70–85 pour un rapprochement plus permissif** (nécessite une revue humaine). `fuzz.WRatio` est le scorer par défaut de `process.extractOne`, recommandé "si on ne sait pas lequel choisir" ; `fuzz.token_set_ratio` est préférable pour du texte non ordonné/répétitif (ex. réponses reformulées avec les mots dans un autre ordre).

**Sources** : Context7 `/rapidfuzz/rapidfuzz`, WebSearch (html.unescape/OpenTDB, comparatif unidecode vs unicodedata — Stack Overflow / sqlpey.com, à recouper).

---

## 10. Packaging `src/` layout

```
trivia-bench/
├── pyproject.toml
├── uv.lock
├── .python-version
├── src/
│   └── trivia_bench/
│       ├── __init__.py
│       ├── __main__.py
│       ├── py.typed
│       ├── cli.py
│       ├── config.py
│       ├── http.py
│       └── normalize.py
└── tests/
    └── test_normalize.py
```

- `py.typed` (fichier vide) : marqueur PEP 561 signalant que le package distribue ses propres annotations de type — pertinent si `trivia_bench` est un jour installé comme dépendance ailleurs ; sans impact sur `mypy` en interne au repo mais bonne pratique dès la création.
- `__main__.py` :

```python
from trivia_bench.cli import app

if __name__ == "__main__":
    app()
```
permet `python -m trivia_bench` / `uv run python -m trivia_bench` en plus de l'entry point `trivia` déclaré dans `[project.scripts]`.

- **Installation éditable par défaut** : confirmé — `uv sync` installe automatiquement le package racine du projet en mode editable (comportement décrit comme permettant "que les changements de code soient reflétés sans re-sync"), donc `uv run pytest` voit directement `src/trivia_bench/` sans étape `pip install -e .` manuelle. Pour désactiver (rare, ex. test d'un vrai wheel packagé) : `uv sync --no-editable`.

---

## Pièges & recommandations

1. **`uv init --package` ne produit plus `hatchling` par défaut** depuis uv ≥0.7.19 (bascule vers `uv_build`) — si le brief impose `hatchling`, le spécifier explicitement (`--build-backend hatchling` ou édition manuelle du `[build-system]`).
2. **Le poste cible a `uv 0.10.x`, la branche stable la plus récente documentée ici est `0.12.x`** (au 2026-09-10) — les fonctionnalités utilisées dans ce document (`dependency-groups`, `--group`, `uv_build`, `uv python pin`) sont toutes stabilisées bien avant `0.10`, donc aucun blocage attendu, mais recommander `uv self update` avant de démarrer le scaffolding pour bénéficier des derniers correctifs de résolution.
3. **`map_elements` en Polars est un point chaud de perf** : à réserver à `html.unescape` (pas d'équivalent vectorisé natif) ; tout le reste (strip, lowercase, replace de motifs fixes) doit passer par les méthodes `.str.*` vectorisées.
4. **`pl.Utf8` est un alias, pas le nom canonique** — accepté partout mais `pl.String` est la forme actuelle recommandée dans la doc et les exemples récents.
5. **PyArrow `==25.0.0` est explicitement exclu par Streamlit 1.63.0** (`pyarrow!=25.0.0,<26,>=7.0`) — un `uv lock` figeant accidentellement cette version exacte casserait l'installation ; peu probable vu que `25.0.1` est disponible, mais à garder en tête lors d'un futur troubleshooting de résolution.
6. **`httpx` 1.0 est en pré-version (`1.0.dev6`) au 2026-09-10, pas stable** — épingler `httpx>=0.28.1,<1` pour ne pas récupérer accidentellement une pré-version lors d'un `uv add httpx` sans contrainte, tant que 1.0 stable n'est pas sorti.
7. **`wait_exponential_jitter(initial=...)` est déprécié** dans tenacity récent — utiliser `multiplier=` pour éviter un `DeprecationWarning` dans les logs de CI.
8. **`app.add_typer(sub_app, name="...")` exige le nom explicite** depuis Typer 0.14 — l'ancienne inférence automatique du nom depuis le callback a été supprimée (breaking change à connaître si on copie un vieux tutoriel).
9. **`mypy` est passé en version majeure 2.x mi-2026** — toute doc/mémoire antérieure parlant de "mypy 1.x" comme version courante est obsolète ; revérifier le changelog `2.0` avant d'activer `strict = true` sur un code existant (possibles nouvelles erreurs strictes).
10. **Groupes `[dependency-groups]` autres que `dev` ne sont pas installés par défaut** par `uv sync` — si l'équipe ajoute un groupe `lint` ou `docs` séparé, soit l'ajouter à `[tool.uv] default-groups = ["dev", "lint"]`, soit toujours appeler `uv sync --group lint` explicitement (sinon CI verte en local, rouge en CI par groupe manquant).
11. **`unicodedata`-only pour le strip d'accents a des angles morts non-latins** (ex. `ł`, `ø` ne se décomposent pas via NFKD) — accepté ici vu le corpus (trivia en anglais), mais si des questions dans d'autres langues apparaissent, prévoir un fallback `Unidecode`.
12. **Répartir `answers.parquet` en un fichier par run (`run_id=.../part.parquet`) plutôt que réécrire un fichier unique** — évite toute race condition/corruption lors de benchmarks lancés en parallèle ou interrompus, et s'appuie sur le Hive partitioning supporté nativement par Polars et DuckDB pour une lecture unifiée transparente.

---

## Squelette de référence

### `pyproject.toml`

```toml
[project]
name = "trivia-bench"
version = "0.1.0"
description = "Pipeline scraper -> parquet -> enrichissement LLM -> dbt -> Streamlit pour un benchmark de trivia."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.28.1,<1",
    "tenacity>=9.1.4",
    "polars>=1.44.2",
    "pyarrow>=25.0.1",
    "pydantic>=2.13.5",
    "pydantic-settings>=2.15.0",
    "typer>=0.27.2",
    "rich>=15.0.0",
    "loguru>=0.7.3",
    "rapidfuzz>=3.14.6",
    "python-dotenv>=1.2.3",
    "duckdb>=1.5.5",
    "dbt-core>=1.12.4",
    "dbt-duckdb>=1.11.0",
    "streamlit>=1.63.0",
]

[project.scripts]
trivia = "trivia_bench.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "pytest-httpx>=0.36.2",
    "ruff>=0.16.6",
    "pre-commit>=4.6.2",
    "mypy>=2.3.1",
]

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "SIM", "RUF"]

[tool.ruff.lint.isort]
known-first-party = ["trivia_bench"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
docstring-code-format = true

[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-ra -q"
testpaths = ["tests"]

[tool.mypy]
strict = true
python_version = "3.12"
packages = ["trivia_bench"]

[[tool.mypy.overrides]]
module = ["duckdb.*"]
ignore_missing_imports = true
```

### `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.6
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-toml
      - id: check-yaml
      - id: check-added-large-files
```

### `.env.example`

```dotenv
# Copier en .env et renseigner localement. Préfixe TRIVIA_ requis (pydantic-settings env_prefix).
TRIVIA_LMSTUDIO_HOST=http://localhost:1234
TRIVIA_DATA_DIR=data
TRIVIA_MODEL_KEY=local-model
```

### `src/trivia_bench/config.py`

```python
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TRIVIA_",
        extra="ignore",
    )

    lmstudio_host: str = Field(default="http://localhost:1234")
    data_dir: Path = Field(default=Path("data"))
    model_key: str = Field(default="local-model")


settings = Settings()
```

### `src/trivia_bench/cli.py`

```python
from typing import Annotated

import typer
from rich.progress import Progress

app = typer.Typer(
    help="trivia-bench: scraper, clean, benchmark, build.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command()
def scrape(
    limit: Annotated[int, typer.Option("--limit", help="Nombre de questions à récupérer.")] = 50,
) -> None:
    """Récupère les questions depuis OpenTDB et écrit la couche bronze."""
    with Progress() as progress:
        progress.add_task("Scraping...", total=limit)
        # TODO: brancher trivia_bench.http.scrape_all
    typer.echo(f"{limit} questions récupérées.")


@app.command()
def clean() -> None:
    """Nettoie/normalise bronze -> silver (Polars)."""
    typer.echo("Clean: TODO")


@app.command()
def benchmark(
    model: Annotated[str, typer.Option(help="Clé du modèle LLM à évaluer.")],
) -> None:
    """Lance un run de benchmark LLM, écrit answers/run_id=.../part.parquet."""
    try:
        typer.echo(f"Benchmark avec {model}: TODO")
    except Exception as exc:
        typer.echo(f"Échec du benchmark: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def build() -> None:
    """Déclenche dbt build sur le projet dbt-duckdb."""
    typer.echo("Build: TODO")


if __name__ == "__main__":
    app()
```

### `src/trivia_bench/http.py`

```python
import logging
import time

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


class RateLimited(Exception):
    """Levée quand l'API renvoie un rate-limit applicatif (ex. OpenTDB response_code=5)."""


def make_client() -> httpx.Client:
    return httpx.Client(
        base_url="https://opentdb.com",
        timeout=httpx.Timeout(10.0, read=30.0),
        headers={"User-Agent": "trivia-bench/0.1"},
        transport=httpx.HTTPTransport(retries=3),
    )


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(multiplier=1, max=30),
    retry=retry_if_exception_type((httpx.HTTPError, RateLimited)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def fetch_questions(client: httpx.Client, amount: int = 50) -> dict:
    response = client.get("/api.php", params={"amount": amount, "type": "multiple"})
    response.raise_for_status()
    payload = response.json()
    if payload.get("response_code") == 5:
        raise RateLimited("OpenTDB rate limit (response_code=5)")
    return payload


def scrape_all(total: int, batch_size: int = 50) -> list[dict]:
    results: list[dict] = []
    with make_client() as client:
        for _ in range(0, total, batch_size):
            t0 = time.monotonic()
            payload = fetch_questions(client, amount=batch_size)
            results.extend(payload["results"])
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, 5.1 - elapsed))
    return results
```

### `src/trivia_bench/normalize.py`

```python
import html
import re
import unicodedata

from rapidfuzz import fuzz, process, utils

_ARTICLES = {"the", "a", "an"}
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_answer(raw: str) -> str:
    s = html.unescape(raw)
    s = strip_accents(s)
    s = s.casefold()
    s = _PUNCT_RE.sub(" ", s)
    tokens = [t for t in s.split() if t not in _ARTICLES]
    return " ".join(tokens)


def match_answer(candidate: str, correct: str, threshold: float = 90.0) -> bool:
    score = fuzz.ratio(normalize_answer(candidate), normalize_answer(correct))
    return score >= threshold


def best_match(candidate: str, choices: list[str], threshold: float = 90.0) -> str | None:
    result = process.extractOne(
        candidate,
        choices,
        scorer=fuzz.WRatio,
        processor=utils.default_process,
        score_cutoff=threshold,
    )
    return result[0] if result else None
```

### `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/

# uv / venv
.venv/
.python-version.bak

# Environnement
.env
.env.*
!.env.example

# dbt
target/
dbt_packages/
logs/
.dbt/

# Streamlit
.streamlit/secrets.toml

# DuckDB
*.duckdb
*.duckdb.wal

# Données du pipeline (garder la structure, pas les fichiers volumineux)
data/bronze/
data/silver/
data/gold/
!data/.gitkeep

# Tests / couverture / typage
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
```

---

## Sources

- uv (Astral) — docs officielles : `https://docs.astral.sh/uv/concepts/projects/layout/`, `https://docs.astral.sh/uv/concepts/projects/dependencies/`, `https://docs.astral.sh/uv/concepts/projects/sync/`, `https://docs.astral.sh/uv/guides/projects/`, `https://docs.astral.sh/uv/concepts/projects/config/` ; Context7 `/astral-sh/uv` (GitHub astral-sh/uv, docs + changelogs 0.7.x/0.8.x).
- Polars — Context7 `/pola-rs/polars` (GitHub pola-rs/polars, reference API + user-guide) ; `https://docs.pola.rs/user-guide/expressions/categorical-data-and-enums/` ; WebSearch (issue GitHub #14542 sur l'écrivain Parquet Rust natif).
- httpx — Context7 `/encode/httpx` (GitHub encode/httpx, docs/advanced/transports.md, timeouts.md, clients.md).
- tenacity — Context7 `/jd/tenacity` (GitHub jd/tenacity, `_autodocs` + `doc/source/index.rst`).
- pydantic / pydantic-settings — Context7 `/pydantic/pydantic`, `/pydantic/pydantic-settings` (GitHub pydantic/pydantic, pydantic/pydantic-settings).
- typer — Context7 `/fastapi/typer` (GitHub fastapi/typer) ; `https://typer.tiangolo.com/tutorial/commands/help/`.
- rich — Context7 `/textualize/rich` (GitHub textualize/rich, docs/source/logging.md, progress.md).
- loguru — Context7 `/delgan/loguru` (GitHub delgan/loguru, docs/api/logger.md, docs/overview.md).
- ruff — Context7 `/astral-sh/ruff` (GitHub astral-sh/ruff, docs/faq.md, docs/formatter.md, docs/tutorial.md).
- pytest / pytest-httpx — Context7 `/pytest-dev/pytest`, `/colin-b/pytest_httpx`.
- pre-commit — Context7 `/pre-commit/pre-commit.com` ; WebSearch releases `astral-sh/ruff-pre-commit`, `pre-commit/pre-commit-hooks`.
- python-dotenv — Context7 `/theskumar/python-dotenv`.
- rapidfuzz — Context7 `/rapidfuzz/rapidfuzz` (GitHub rapidfuzz/rapidfuzz, docs/Usage/process.rst, fuzz.rst) ; PyPI `https://pypi.org/pypi/rapidfuzz/json`.
- DuckDB × Polars interop — WebSearch (Medium "Polars & DuckDB", Towards Data Science "Using DuckDB with Polars").
- Hive partitioning — `https://docs.pola.rs/user-guide/io/hive/` ; `https://duckdb.org/docs/current/data/partitioning/hive_partitioning` ; GitHub discussion `duckdb/duckdb#14164`.
- OpenTDB / html.unescape — WebSearch (freecodecamp.org, github.com/MaT1g3R/Python-Trivia-API).
- unidecode vs unicodedata — WebSearch (comparatifs Stack Overflow / sqlpey.com — recoupement multi-sources, non issu d'une doc officielle unique).
- mypy 2.x — WebSearch (`mypy-lang.blogspot.com/2026/05/mypy-20-relased.html`, PyPI `mypy`).
- Versions PyPI (snapshot 2026-09-10) — `https://pypi.org/pypi/<package>/json` pour : polars, pyarrow, httpx, tenacity, pydantic, pydantic-settings, typer, rich, loguru, ruff, pytest, pytest-httpx, respx, python-dotenv, pre-commit, mypy, tqdm, rapidfuzz, duckdb, streamlit, dbt-core, dbt-duckdb, Unidecode.
- uv × dbt-core / Streamlit — WebSearch (GitHub issue `astral-sh/uv#18551`, `docs.streamlit.io/develop/quick-reference/release-notes/2026`).

**Mentions NON VÉRIFIÉ** (à confirmer avant usage en production) : statut exact des stubs de types pour `duckdb` et `streamlit` (py.typed / paquets `-stubs` tiers) ; détail complet des breaking changes mypy 1.x→2.x ; comportement exact de `uv 0.10.x` spécifiquement (les vérifications ci-dessus portent sur la doc actuelle, potentiellement en avance sur cette version précise — recommander `uv self update` avant de suivre ce document à la lettre).
