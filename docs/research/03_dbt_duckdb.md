# dbt-core + dbt-duckdb + DuckDB (Python) — Référence vérifiée pour la couche Gold

Date de la recherche : 2026-09-10.

**Méthodologie** : au-delà de la documentation (README GitHub de dbt-duckdb, docs.getdbt.com, duckdb.org, PyPI, Context7), la plupart des affirmations critiques de ce document ont été **vérifiées empiriquement** : installation réelle avec `uv` (Python 3.12), lecture du code source installé de `dbt-adapters/duckdb` (paquet `dbt-duckdb==1.11.0`) et de `dbt-core==1.12.4`, puis exécution réelle d'un mini-projet dbt reproduisant l'architecture cible (Parquet silver → `dbt build` → `.duckdb` gold), y compris un test de verrouillage concurrentiel avec deux process Python réels. Les faits ainsi vérifiés sont marqués **[testé]**. Ce qui n'a pas pu être vérifié directement est marqué **NON VÉRIFIÉ**.

---

## Résumé exécutif

1. **Versions au 2026-09-10** (PyPI) : `dbt-core` **1.12.4**, `dbt-duckdb` **1.11.0**, paquet Python `duckdb` **1.5.5**. `uv add dbt-core dbt-duckdb` sur Python 3.12 résout et installe ces trois versions sans conflit de dépendances (`protobuf==6.33.6`, `dbt-adapters==1.24.5`) — **[testé]**.
2. **Piège d'installation réel rencontré** : la dépendance transitive `dbt-core-experimental-parser` télécharge un wheel précompilé depuis une *release* GitHub pendant son étape de build (pas un vrai wheel PyPI). Dans un environnement réseau restreint / bundle CA custom, `uv add`/`pip install` échoue avec `SSL: CERTIFICATE_VERIFY_FAILED` — **[testé]**, résolu en pointant `SSL_CERT_FILE` vers un CA bundle valide.
3. `profiles.yml` peut rester **dans le repo** : `dbt build --project-dir dbt --profiles-dir dbt`. dbt cherche `profiles.yml` d'abord dans le **répertoire courant (CWD)**, puis dans `~/.dbt/` — confirmé dans le code source (`dbt/cli/params.py`).
4. **Piège majeur vérifié empiriquement** : les chemins relatifs (`path:` du profil DuckDB, et les chemins passés à `read_parquet()` via `external_location`) sont résolus **par rapport au CWD du process `dbt`**, pas par rapport à `profiles.yml` ni à `dbt_project.yml`. Toujours lancer `dbt` depuis la racine du repo avec des chemins relatifs à cette racine, ou utiliser des chemins absolus / variables d'environnement.
5. Lecture des Parquet en source dbt : `meta.external_location: "read_parquet('.../{name}.parquet')"` dans `sources.yml`. Le templating utilise `str.format_map()` de Python (style `{name}`, `{identifier}`, `{schema}`, `{database}`, ou toute clé `meta`/`config` custom) — confirmé en lisant `relation.py`/`utils.py` du paquet installé, et testé de bout en bout.
6. Matérialisations : `view` pour le staging, `table` pour les marts gold ; tout est persisté dans le fichier `.duckdb` pointé par `path:`. Le schéma par défaut est `main`. Pour obtenir un schéma propre `gold` (sans préfixe `<target>_`), il faut surcharger `generate_schema_name` avec la macro built-in `generate_schema_name_for_env` **ET** utiliser un `target` nommé `prod` — **[testé]** : en `target: dev` le préfixe custom est ignoré et tout retombe dans `main`, en `target: prod` on obtient bien des schémas `staging`/`gold` propres.
7. **Règle de concurrence DuckDB vérifiée avec 2 process réels** : un seul writer **OU** N readers, jamais les deux en même temps sur le même fichier. Une connexion `read_only=True` ouverte pendant qu'un `dbt build` tourne échoue avec `IO Error: Could not set lock on file ...: Conflicting lock is held in <process> (PID ...)`. Et inversement, **un `dbt build` échoue** si un process Streamlit garde une connexion (même `read_only=True`) ouverte en cache sur le même fichier — implication directe pour l'architecture cible.
8. Le module Parquet est **intégré nativement** à DuckDB (autoload confirmé par `duckdb_extensions()`), aucune extension à installer pour lire des fichiers Parquet locaux.
9. `dbt build` exécute seeds → models → tests (+ snapshots) dans l'ordre du DAG, avec skip en cascade si un test échoue — **[testé]** : `PASS=6 ... Completed successfully` sur le mini-projet de référence.
10. L'API programmatique `dbtRunner` (`from dbt.cli.main import dbtRunner`) fonctionne et a été testée avec `dbt-core==1.12.4` / `dbt-duckdb==1.11.0` — `dbt.invoke(["build", "--project-dir", "dbt", "--profiles-dir", "dbt"])` renvoie `res.success == True`.
11. `data_tests:` remplace `tests:` (déprécié mais toujours accepté comme alias, on ne peut pas mélanger les deux sur la même ressource) depuis dbt-core ≥1.8. Testé avec `unique`/`not_null` sur un modèle mart.
12. `dbt docs generate --static` produit un unique fichier `static_index.html` autonome (~2,4 Mo dans le test) — bon livrable additionnel à distribuer sans serveur.

---

## 1. Installation & versions

### Versions latest (PyPI, 2026-09-10)

| Paquet | Version | `requires-python` | Contraintes clés |
|---|---|---|---|
| `dbt-core` | **1.12.4** | `>=3.10` | `dbt-adapters<2,>=1.24.5`, `dbt-common<2,>=1.37.5`, `dbt-core-experimental-parser<3,>=2.0.0b1`, `dbt-extractor<=0.6,>=0.5.0`, `dbt-protos<2,>=1.0.514`, `jinja2<4,>=3.1.3`, `click<9,>=8.3.0`, `protobuf<8,>=6.0` |
| `dbt-duckdb` | **1.11.0** | `>=3.10` | `dbt-core>=1.8.0`, `dbt-adapters<2,>=1`, `dbt-common<2,>=1`, `duckdb>=1.0.0` ; extras `glue` (boto3) et `md` (⚠️ pin exact `duckdb==1.5.5` pour MotherDuck) |
| `duckdb` (paquet Python) | **1.5.5** | `>=3.10.0` | — |

Source : `curl https://pypi.org/pypi/<paquet>/json` (champs `info.version`, `info.requires_python`, `info.requires_dist`), interrogé le 2026-09-10.

`dbt-duckdb` ne pin **pas** de version haute pour `duckdb` (juste `>=1.0.0`) : un install standard prend donc la dernière version DuckDB disponible sur PyPI (1.5.5 au moment du test). Seul l'extra `md` (MotherDuck) fige `duckdb==1.5.5` exactement, pour compatibilité de protocole.

Notes de version dbt-duckdb (changelog GitHub, `api.github.com/repos/duckdb/dbt-duckdb/releases`) :
- **1.11.0** (2026-08-07) : changement de comportement sur `partitioned_by`/`partition_by` (les noms de colonnes ne sont plus auto-quotés).
- **1.10.1** (2026-02-17) : **Python 3.8 et 3.9 ne sont plus supportés** (confirme le `requires-python >=3.10`).
- **1.10.0** (2025-11-05) : ajout support Python 3.13, instructions DuckLake.

### `uv add dbt-core dbt-duckdb` : ça marche ?

**Oui, testé de bout en bout** — `uv init --python 3.12` puis `uv add dbt-core dbt-duckdb` dans un projet vide :

```
Installed 59 packages
 + dbt-core==1.12.4
 + dbt-duckdb==1.11.0
 + duckdb==1.5.5
 + dbt-adapters==1.24.5
 + dbt-common==1.39.0
 + protobuf==6.33.6
 + dbt-core-experimental-parser==2.0.0rc2
 + dbt-protos==1.0.565
 + jinja2==3.1.6
 + click==8.5.0
 + pydantic==2.13.5
 + mashumaro==3.17
 + sqlglot==30.18.0
 + rapidfuzz==3.14.6
 ... (59 au total)
```

Aucun conflit de `protobuf` entre `dbt-core` (`<8,>=6`) et `dbt-duckdb` (pas de pin direct) : résolu à `protobuf==6.33.6`.

### ⚠️ Piège d'installation réel (rencontré et reproduit)

À la première tentative, `uv add dbt-core dbt-duckdb` a échoué :

```
× Failed to build `dbt-core-experimental-parser==2.0.0rc2`
╰─▶ Call to `_dbt_sa_build.build_wheel` failed (exit status: 1)
    RuntimeError: failed to download
    https://github.com/dbt-labs/dbt-core/releases/download/v2.0.0-rc.2/dbt_core_experimental_parser-2.0.0rc2-py3-none-macosx_11_0_arm64.whl:
    <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
    unable to get local issuer certificate (_ssl.c:1000)>
```

**Cause** : `dbt-core-experimental-parser` (dépendance de `dbt-core` depuis la 1.10+, un parseur SQL expérimental) n'est pas distribué comme wheel PyPI classique pour toutes les plateformes : sa procédure de *build* télécharge dynamiquement un wheel précompilé spécifique à l'OS/l'archi depuis une URL de *release* GitHub. Si le Python géré par `uv` n'a pas de CA bundle correctement configuré (proxy d'entreprise, environnement sandboxé), ce téléchargement échoue en SSL.

**Correctif vérifié** : pointer `SSL_CERT_FILE` vers un CA bundle valide avant `uv add`, p. ex. sur macOS :
```bash
export SSL_CERT_FILE=/etc/ssl/cert.pem   # bundle système macOS
uv add dbt-core dbt-duckdb
```
Après correction, l'installation aboutit et affiche `Installed 59 packages` avec la liste ci-dessus.

**À retenir pour ce projet** : sur un poste d'entreprise avec proxy/MITM SSL (fréquent), attendez-vous à devoir configurer `SSL_CERT_FILE` (ou `UV_NATIVE_TLS=1`, NON VÉRIFIÉ ici) avant le premier `uv add`/`uv sync` incluant `dbt-core`.

### dbt Fusion (moteur Rust) — pertinence

La documentation dbt mentionne « dbt Fusion » comme nouveau moteur v2 écrit en Rust, avec recherche de `profiles.yml` légèrement différente (pas de fallback CWD documenté) et chargement d'extensions DuckDB nécessitant le driver `dbc` (l'extrait récupéré indique que "the bundled Fusion driver does not support extensions"). **NON VÉRIFIÉ** : compatibilité exacte de Fusion avec l'adaptateur `dbt-duckdb` — la doc consultée ne le confirme ni ne l'infirme explicitement. **Recommandation** : rester sur `dbt-core` (le moteur Python classique, celui testé ici) pour ce projet, c'est celui documenté et supporté par `dbt-duckdb`.

Sources : https://pypi.org/project/dbt-core/ · https://pypi.org/project/dbt-duckdb/ · https://pypi.org/project/duckdb/ · https://github.com/duckdb/dbt-duckdb (README, section Installation/Compatibility) · https://api.github.com/repos/duckdb/dbt-duckdb/releases · https://docs.getdbt.com/docs/fusion/about-fusion

---

## 2. `profiles.yml` pour duckdb

### Liste exhaustive des clés

Extraite **directement du code source installé** (`dbt/adapters/duckdb/credentials.py`, classe `DuckDBCredentials`, paquet `dbt-duckdb==1.11.0`) — la source la plus fiable possible :

| Clé | Type / défaut | Signification |
|---|---|---|
| `type` | `duckdb` (obligatoire) | Sélectionne l'adaptateur. |
| `path` | `str = ":memory:"` | Chemin du fichier `.duckdb` (ou `md:...` pour MotherDuck, ou `ducklake:...`). Si absent → base en mémoire. **Résolu par rapport au CWD du process `dbt`** (voir piège §4/§Pièges). |
| `database` | `str = "main"` | Nom du catalogue DuckDB. Si non précisé, dbt-duckdb l'infère automatiquement du *basename* de `path` sans extension (`benchmark.duckdb` → catalogue `benchmark`) — logique confirmée dans `credentials.py` (`os.path.basename` / `os.path.splitext`). |
| `schema` | `str = "main"` | Schéma cible par défaut. |
| `threads` | dbt générique | Nombre de threads pour la construction parallèle des modèles. |
| `config_options` | `dict` | Options de connexion DuckDB additionnelles (ex. autoriser des extensions non signées). |
| `extensions` | `list[str \| {name, repo}]` | Extensions DuckDB à `INSTALL`/`LOAD` à la connexion, ex. `httpfs`, `parquet`, ou `{name: h3, repo: community}`. |
| `settings` | `dict` | Config DuckDB façon `PRAGMA`/`SET`, ex. `s3_region: us-east-1`. |
| `secrets` | `list[dict]` | Entrées du DuckDB Secrets Manager (S3, GCS, Azure, HF...) : `type`, `key_id`, `secret`, `region`, `provider: credential_chain`, `scope`. |
| `external_root` | `str = "."` | Racine utilisée pour les chemins de sortie de la matérialisation `external` quand `location` n'est pas absolu. Défaut = CWD. |
| `use_credential_provider` | `Optional[str]` | Utilise la chaîne de credentials par défaut (AWS/GCloud) au lieu de variables statiques. |
| `attach` | `list[Attachment]` | Attache d'autres bases (duckdb, sqlite, postgres, MotherDuck) : `path`, `type`, `alias`, `read_only`, `is_ducklake`. |
| `filesystems` | `list[dict]` | Filesystems `fsspec` à enregistrer (clé `fs` + kwargs), ex. accès S3 via fsspec plutôt que `httpfs`. |
| `remote` | `Remote` | Config pour environnements Python distants (avancé, non utile ici). |
| `plugins` | `list[PluginConfig]` | Plugins `dbt-duckdb` (`module`, `alias`, `config`) — ex. lecture Excel/Google Sheets/SQLAlchemy. |
| `module_paths` | `list[str]` | Chemins additionnels de modules Python (plugins/macros Python custom). |
| `disable_transactions` | `bool = False` | Désactive le wrapping `BEGIN`/`COMMIT` — utile pour réduire la taille du fichier résultant. |
| `keep_open` | `bool = True` | Garde la connexion DuckDB ouverte entre les invocations dbt (pertinent avec `dbtRunner` réutilisé dans un même process). |
| `retries` | `Retries{connect_attempts, query_attempts, retryable_exceptions}` | Retente en cas d'échec transitoire ; `connect_attempts` est documenté comme **utile pour attendre qu'un autre process libère son verrou sur le fichier** — directement pertinent pour la cohabitation avec Streamlit (voir §8). |
| `is_ducklake` | `Optional[bool]` | Indique explicitement une base DuckLake. |

### Exemples minimal et complet

```yaml
# Minimal (mémoire)
benchmark:
  target: dev
  outputs:
    dev:
      type: duckdb
```

```yaml
# Complet, avec extensions/settings/retries (testé, adapté)
benchmark:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{{ env_var('DBT_DUCKDB_PATH', 'data/gold/benchmark.duckdb') }}"
      schema: main
      threads: 4
      extensions:
        - parquet
      settings:
        s3_region: "{{ env_var('S3_REGION', '') }}"
      retries:
        connect_attempts: 5
        query_attempts: 3
    prod:
      type: duckdb
      path: "{{ env_var('DBT_DUCKDB_PATH', 'data/gold/benchmark.duckdb') }}"
      threads: 4
      extensions:
        - parquet
```

### Où dbt cherche `profiles.yml` et comment le garder dans le repo

Confirmé **dans le code source** de dbt-core 1.12.4 (`dbt/cli/params.py`) — le texte d'aide officiel du flag est explicite :

```
--profiles-dir  (env var DBT_PROFILES_DIR)
"Which directory to look in for the profiles.yml file.
 If not set, dbt will look in the current working directory first, then HOME/.dbt/"
```

Donc :
1. `--profiles-dir <dir>` ou variable d'env `DBT_PROFILES_DIR` (priorité la plus haute).
2. **Répertoire courant (CWD)** — donc si vous lancez `dbt` depuis le dossier qui contient `profiles.yml`, il est trouvé automatiquement, **sans flag**.
3. `~/.dbt/profiles.yml` (fallback historique).

Il n'y a **pas** d'auto-détection basée sur l'emplacement de `dbt_project.yml` en tant que tel — c'est bien le CWD du process qui compte. Pour garder `profiles.yml` dans le repo de façon fiable quel que soit le CWD d'appel, le plus robuste est de toujours passer explicitement `--profiles-dir dbt` (ou équivalent), ce qui a été **testé et fonctionne** :

```bash
uv run dbt build --project-dir dbt --profiles-dir dbt
```

### Variables d'environnement dans `profiles.yml`

`env_var('X')` (obligatoire) ou `env_var('X', 'valeur_par_défaut')` (avec défaut) — syntaxe Jinja standard, testée dans le profil ci-dessus pour `DBT_DUCKDB_PATH`.

Sources : `dbt/cli/params.py` (paquet `dbt-core==1.12.4` installé) · https://github.com/duckdb/dbt-duckdb (README, _autodocs/10-configuration-reference.md via Context7) · https://docs.getdbt.com/reference/warehouse-setups/duckdb-setup

---

## 3. Sources Parquet dans dbt (`external_location`)

### Mécanisme exact (lu dans le code source `dbt/adapters/duckdb/relation.py` et `utils.py`)

Quand une source a une clé `external_location` (dans `meta:` **ou** `config:` — les deux fonctionnent, `config:` a priorité s'il y a doublon car `meta.update(config_properties)`), dbt-duckdb :
1. Prend le gabarit `external_location` (une chaîne).
2. Le formate avec un des 3 « formatters » (clé `formatter`, défaut `newstyle`) :
   - `newstyle` (défaut) : Python `str.format_map(...)` → syntaxe `{name}`.
   - `oldstyle` : `%`-formatting → syntaxe `%(name)s`.
   - `template` : `string.Template.substitute(...)` → syntaxe `$name`.
3. Les clés disponibles pour le templating sont : `name`, `identifier`, `schema`, `database`, `tags`, **plus toute clé custom définie dans `meta:`/`config:`** (confirmé dans `SourceConfig.as_dict()`).
4. Si la valeur formatée contient une parenthèse (`(` — c.-à-d. c'est un appel de fonction comme `read_parquet(...)`) ou commence déjà par un guillemet simple, dbt-duckdb ne rajoute **pas** de guillemets. Sinon (chemin brut), il l'entoure automatiquement de guillemets simples pour produire `FROM 'chemin'`.

### `sources.yml` complet et vérifié (testé avec succès)

```yaml
version: 2

sources:
  - name: silver
    meta:
      external_location: "read_parquet('{{ env_var('SILVER_DIR', 'data/silver') }}/{name}.parquet')"
    tables:
      - name: questions
      - name: answers
```

Modèle de staging correspondant (testé) :

```sql
-- models/staging/stg_questions.sql
select
    question_id,
    question_text,
    category,
    difficulty,
    correct_answer
from {{ source('silver', 'questions') }}
```

Compilé, cela donne (SQL réellement exécuté par DuckDB, capturé dans `target/compiled/`) :

```sql
select
    question_id, question_text, category, difficulty, correct_answer
from read_parquet('data/silver/questions.parquet')
```

⚠️ Le champ `{name}` vient bien de `source_config["name"]`, càd le nom de la **table** dans `tables:` (`questions`, `answers`), pas le nom de la source (`silver`). Testé et confirmé : `answers.parquet` et `questions.parquet` sont résolus correctement chacun avec son propre `{name}`.

### Glob patterns et overrides par table

```yaml
sources:
  - name: silver
    meta:
      external_location: "read_parquet('data/silver/{name}.parquet')"
    tables:
      - name: questions
      - name: answers
        config:
          # override : plusieurs fichiers partitionnés, ou glob
          external_location: "read_parquet('data/silver/answers_*.parquet')"
```

Glob DuckDB natif (indépendant de dbt) :
```sql
select * from read_parquet('data/silver/*.parquet');
select * from read_parquet(['data/silver/questions.parquet', 'data/silver/answers.parquet']);
```

### Alternative : `read_parquet()` directement dans un modèle

Plus simple si vous n'avez pas besoin de la couche `source()` (tests de fraîcheur, lineage) :
```sql
-- models/staging/stg_questions.sql
select * from read_parquet('data/silver/questions.parquet')
```
Compromis : vous perdez le lineage `source()`→`ref()` dans `dbt docs`/DAG, et les tests génériques ne peuvent plus cibler « la source » explicitement (ils resteraient utilisables sur le modèle staging lui-même). Pour ce projet, `external_location` + `source()` est préférable (meilleure doc/lineage, testé, coût nul).

Sources : lecture directe de `dbt/adapters/duckdb/relation.py` et `utils.py` (paquet installé) · https://github.com/duckdb/dbt-duckdb (`_autodocs/05-relation.md`, `_autodocs/10-configuration-reference.md` via Context7) · test empirique.

---

## 4. Matérialisations

### `view` vs `table` vs `incremental` vs `external`

| Matérialisation | Usage recommandé ici | Comportement |
|---|---|---|
| `view` | **staging** | Crée une `CREATE VIEW` — pas de copie physique, recalculée à chaque requête. Recommandé pour staging car les Parquet source sont déjà rapides à scanner et on évite de dupliquer la donnée silver. |
| `table` | **marts / gold** | `CREATE TABLE AS SELECT` — données persistées physiquement dans le fichier `.duckdb`. Recommandé pour les tables gold consommées par Streamlit (lecture rapide, pas de recalcul). |
| `incremental` | non nécessaire ici (petit volume, full-refresh à chaque run) | Stratégies dispo côté duckdb : `append`, `delete+insert` (nécessite `unique_key`), `merge` (DuckDB ≥1.4.0, options `merge_update_condition`, etc.), `microbatch` (dbt-core ≥1.9, nécessite `event_time`/`begin`/`batch_size`). |
| `external` | pour ré-exporter du gold en Parquet/CSV (ex. partage avec un autre outil) | Écrit un fichier au lieu d'une table. Voir ci-dessous. |

### Matérialisation `external` (spécifique dbt-duckdb)

```sql
-- models/marts/export_accuracy.sql
{{ config(
    materialized='external',
    location='data/exports/accuracy.parquet',
    format='parquet'
) }}
select * from {{ ref('mart_accuracy_by_model') }}
```

Clés de config : `location` (chemin de sortie ; si non absolu, relatif à `external_root` du profil, défaut `.`), `format` (`parquet` par défaut, aussi `csv`/`json`), `delimiter` (CSV), `options` (paramètres additionnels passés à la clause `COPY ... (...)`), `glue_register` (registre AWS Glue).

Flux interne (confirmé via la doc du dépôt) : le modèle est d'abord matérialisé en table temporaire, puis dbt-duckdb exécute `COPY (SELECT ...) TO 'chemin' (FORMAT ...)`.

### Persistance et schéma dans le fichier `.duckdb`

**Testé de bout en bout** : après `dbt build` avec `path: data/gold/benchmark.duckdb`, interrogation du fichier en lecture seule :

```
('main', 'mart_accuracy_by_model', 'BASE TABLE')
('main', 'stg_answers', 'VIEW')
('main', 'stg_questions', 'VIEW')
```

Par défaut, **tout tombe dans le schéma `main`**, quel que soit le `+schema:` custom configuré dans `dbt_project.yml`, **tant que le `target` actif n'est pas nommé `prod`** (comportement du macro built-in `generate_schema_name_for_env`, voir ci-dessous).

### Obtenir un schéma `gold` propre (sans préfixe `<target_schema>_<custom>`)

Le macro par défaut de dbt (`generate_schema_name`) concatène `<target_schema>_<custom_schema>` :
```jinja
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
```

Pour obtenir des schémas propres (`staging`, `gold`) sans préfixe, surcharger avec la macro built-in `generate_schema_name_for_env` :

```jinja
-- macros/generate_schema_name.sql
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ generate_schema_name_for_env(custom_schema_name, node) }}
{%- endmacro %}
```

**Comportement testé empiriquement** de `generate_schema_name_for_env` :

| `target.name` | `+schema: gold` configuré | Schéma obtenu |
|---|---|---|
| `dev` (défaut testé) | `gold` | **`main`** (le custom schema est ignoré hors prod, tout va dans le schema par défaut du target — comportement volontaire anti-collision multi-dev) |
| `prod` (testé) | `gold` | **`gold`** (propre, sans préfixe) |

⚠️ Pour ce projet local mono-développeur, l'implication pratique est : **nommer le target de build `prod`** dans `profiles.yml` (même si c'est un usage local), sinon vos tables gold resteront dans `main` malgré la config `+schema: gold`. Alternative plus simple pour un usage strictement local/solo : écrire un macro `generate_schema_name` qui retourne **toujours** `custom_schema_name` tel quel (sans jamais retomber sur `default_schema`), ce qui donne des schémas `staging`/`gold` propres quel que soit le target — au prix de perdre la protection anti-collision (non nécessaire ici, un seul développeur/un seul fichier `.duckdb` local).

Sources : https://docs.getdbt.com/docs/build/custom-schemas · test empirique (`information_schema.tables` avant/après changement de target) · https://docs.getdbt.com/reference/resource-configs/duckdb-configs (incremental strategies)

---

## 5. Scaffolding du projet dbt

### `dbt_project.yml` minimal valide — testé

**Vérifié empiriquement avec `dbt parse`** : un fichier contenant *seulement* `name:` et `profile:` est accepté sans erreur par dbt-core 1.12.4 (aucune clé `version:` ni `config-version:` requise) :

```yaml
name: 'minimal'
profile: 'benchmark'
```
→ `dbt parse` réussit (`Unable to do partial parsing... Starting full parse.` puis pas d'erreur).

Cela dit, en pratique on garde `version:` et les chemins pour la lisibilité. Contenu recommandé pour ce projet (celui effectivement testé) :

```yaml
name: 'benchmark'
version: '1.0.0'

profile: 'benchmark'

model-paths: ["models"]
macro-paths: ["macros"]
test-paths: ["tests"]
seed-paths: ["seeds"]

target-path: "target"
clean-targets:
  - "target"
  - "dbt_packages"

models:
  benchmark:
    staging:
      +materialized: view
      +schema: staging
    marts:
      +materialized: table
      +schema: gold
```

### Chemins par défaut — confirmés **dans le code source** de dbt-core (`dbt/config/project.py`)

| Clé | Défaut réel (source-code) |
|---|---|
| `model-paths` | `["models"]` |
| `macro-paths` | `["macros"]` |
| `seed-paths` | `["seeds"]` (⚠️ pas `"data/"` — cet ancien défaut correspond à la clé dépréciée `data-paths`, gardée seulement en compat ascendante) |
| `test-paths` | `["tests"]` |
| `analysis-paths` | `["analyses"]` |
| `snapshot-paths` | `["snapshots"]` |
| `function-paths` | `["functions"]` (nouveau, UDFs SQL, dbt-core ≥1.11) |
| `target-path` | `"target"` |
| `clean-targets` | `[target-path]` uniquement par défaut (`dbt_packages` **n'est pas** inclus par défaut, il faut l'ajouter explicitement si désiré) |
| `packages-install-path` | `"dbt_packages"` (renommé depuis l'ancien `dbt_modules`) |

### Arborescence recommandée

```
dbt/
  dbt_project.yml
  profiles.yml                 # gardé dans le repo, --profiles-dir dbt
  models/
    staging/
      sources.yml
      stg_questions.sql
      stg_answers.sql
    marts/
      marts.yml
      mart_accuracy_by_model.sql
  macros/
    generate_schema_name.sql
    wilson_interval.sql
  tests/
    (tests singuliers .sql, optionnel)
  seeds/                       # optionnel, pour des CSV de référence statiques
  target/                      # généré, à ignorer
  dbt_packages/                # généré par `dbt deps`, à ignorer
```

### `dbt init` vs écrire à la main

`dbt init` génère un squelette interactif (demande le type d'adaptateur, écrit `profiles.yml` dans `~/.dbt/` par défaut). Pour ce projet, comme on veut `profiles.yml` **dans le repo** dès le départ, il est plus simple et plus prévisible d'écrire les fichiers à la main (comme ci-dessus) — c'est l'approche testée dans ce document.

### `.gitignore`

Recommandé (le `dbt_modules/` historique dans les templates officiels type `jaffle-shop-classic` est **obsolète** ; le nom actuel du dossier généré par `dbt deps` est `dbt_packages/`, confirmé par `packages-install-path` par défaut dans le code source) :

```gitignore
target/
dbt_packages/
logs/
*.duckdb
*.duckdb.wal
.env
```

(`*.duckdb`/`*.duckdb.wal` à ajouter car la base gold est un artefact généré par `dbt build`, pas du code source — sauf si vous voulez explicitement versionner le binaire, ce qui est déconseillé.)

Sources : `dbt/config/project.py` (paquet `dbt-core==1.12.4` installé, lecture directe) · https://github.com/dbt-labs/jaffle-shop-classic/blob/main/.gitignore (référence historique) · test empirique `dbt parse`.

---

## 6. Tests de données

### Syntaxe actuelle : `data_tests:` (pas `tests:`)

**Testé avec succès** — `models/marts/marts.yml` :

```yaml
version: 2

models:
  - name: mart_accuracy_by_model
    description: "Accuracy and response time stats per model"
    columns:
      - name: model
        data_tests:
          - unique
          - not_null
      - name: accuracy
        data_tests:
          - not_null
```

Résultat réel de `dbt build` :
```
4 of 6 PASS not_null_mart_accuracy_by_model_accuracy
5 of 6 PASS not_null_mart_accuracy_by_model_model
6 of 6 PASS unique_mart_accuracy_by_model_model
Done. PASS=6 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=6
```

Règles : `data_tests:` remplace `tests:` (renommage dbt-core ≥1.8) ; `tests:` reste accepté comme **alias déprécié**, mais **on ne peut pas utiliser les deux clés sur la même ressource** (erreur de validation). Depuis dbt-core 1.10.5 / v2 (Fusion), les arguments des tests génériques (`values:`, `to:`, `field:`...) doivent être imbriqués sous une clé `arguments:` :
```yaml
- name: status
  data_tests:
    - accepted_values:
        arguments:
          values: ['placed', 'shipped', 'completed']
```
NON VÉRIFIÉ empiriquement (non testé dans ce projet — nos tests utilisés, `unique`/`not_null`, n'ont pas d'arguments), mais confirmé par la doc dbt officielle.

### Les 4 tests génériques built-in

`unique`, `not_null`, `accepted_values`, `relationships` (clé foreign-key, `to: ref('...')`, `field: ...`).

### Tests singuliers (`tests/*.sql`)

```sql
-- tests/assert_accuracy_between_0_and_1.sql
select model, accuracy
from {{ ref('mart_accuracy_by_model') }}
where accuracy < 0 or accuracy > 1
```
Un fichier = un test, pas de point-virgule final, exécuté automatiquement par `dbt build`/`dbt test` sans déclaration YAML supplémentaire (nom du test = nom du fichier).

### Ordre d'exécution de `dbt build`

Ordre DAG : seeds → models → tests (+ snapshots), avec **skip en cascade** si un test bloquant échoue en amont (sévérité par défaut `error`; passer à `warn` pour ne pas bloquer les aval). Confirmé par le run réel ci-dessus (modèles d'abord, puis les 3 tests).

### `dbt_utils` : ça vaut le coup ?

Oui pour ce projet dès qu'on veut des tests plus riches (`accepted_range`, `not_constant`, `expression_is_true`, macros SQL type `pivot`, `date_spine`...). Version compatible avec dbt-core 1.12.4 : **`dbt-labs/dbt_utils` 1.4.1** (dernière release, `require-dbt-version: [">=1.3.0", "<3.0.0"]` — couvre bien dbt-core 1.12.4). NON testé en installation réelle dans ce projet (pas nécessaire pour la démo de base), mais compatibilité confirmée par lecture du `dbt_project.yml` du paquet sur GitHub.

```yaml
# packages.yml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.4.0", "<2.0.0"]
```
```bash
dbt deps --project-dir dbt   # installe dans dbt/dbt_packages/
```

Sources : https://docs.getdbt.com/docs/build/data-tests · https://github.com/dbt-labs/dbt-utils/releases · https://github.com/dbt-labs/dbt-utils/blob/main/dbt_project.yml · test empirique `dbt build`.

---

## 7. Lancer dbt depuis Python / `uv`

### CLI classique

```bash
uv run dbt build --project-dir dbt --profiles-dir dbt --target prod
```
Testé et fonctionnel — `Done. PASS=6 WARN=0 ERROR=0 SKIP=0`.

### API programmatique `dbtRunner`

**Testé avec succès** en conditions réelles avec `dbt-core==1.12.4` :

```python
from dbt.cli.main import dbtRunner, dbtRunnerResult

dbt = dbtRunner()
res: dbtRunnerResult = dbt.invoke([
    "build",
    "--project-dir", "dbt",
    "--profiles-dir", "dbt",
    "--target", "prod",
])
print(res.success)        # True
print(type(res.result))   # <class 'dbt.artifacts.schemas.run.v5.run.RunExecutionResult'>
```

Sortie réelle observée :
```
Registered adapter: duckdb=1.11.0
Found 3 models, 3 data tests, 2 sources, 502 macros
...
Completed successfully
success: True
```

Deux syntaxes d'appel équivalentes (doc officielle, non re-testées séparément mais cohérentes avec le comportement observé) :
```python
dbt.invoke(["run", "--select", "tag:my_tag"])
dbt.invoke(["run"], select="tag:my_tag")
```

Stabilité : l'API `dbtRunner` est documentée comme stable dans dbt-core ≥1.5, toujours d'actualité en 1.12.4. Astuce avancée (non testée ici) : réutiliser un `Manifest` déjà parsé entre plusieurs invocations pour éviter de re-parser à chaque appel (`dbtRunner(manifest=manifest)`).

Sources : https://docs.getdbt.com/reference/programmatic-invocations · test empirique direct.

---

## 8. Concurrence & verrouillage de fichier DuckDB — **section critique pour ce projet**

### Règle générale (doc DuckDB)

> Read-write mode : un seul process peut lire **et** écrire.
> Read-only mode : plusieurs process peuvent lire, mais **aucun** ne peut écrire.

Autrement dit : **un seul writer OU N readers**, jamais les deux à la fois sur le même fichier `.duckdb`.

### Vérification empirique avec 2 process réels (Python `subprocess`, pas juste de la doc)

**Test A — writer ouvert, un reader tente de se connecter pendant ce temps :**
```python
# process 1 (writer) : garde une connexion read_only=False ouverte 6s
con = duckdb.connect("benchmark.duckdb", read_only=False)
```
```python
# process 2 (reader), tente pendant que le writer est ouvert
con = duckdb.connect("benchmark.duckdb", read_only=True)
```
**Résultat réel obtenu (process 2) :**
```
IOException: IO Error: Could not set lock on file "<path>/benchmark.duckdb":
Conflicting lock is held in /.../Python (PID 85646) by user Workingplace.
See also https://duckdb.org/docs/stable/connect/concurrency
```
→ **Le reader échoue immédiatement**, avec ce message exact. Une seconde tentative en écriture échoue de façon identique.

**Test B — reader ouvert, un writer tente de se connecter pendant ce temps :**
```python
# process 1 (reader) : garde une connexion read_only=True ouverte 6s
con = duckdb.connect("benchmark.duckdb", read_only=True)
```
```python
# process 2, pendant que le reader est ouvert
conB = duckdb.connect("benchmark.duckdb", read_only=True)   # -> SUCCÈS, coexiste
conC = duckdb.connect("benchmark.duckdb", read_only=False)  # -> ÉCHEC
```
**Résultats réels obtenus :**
```
READER2 (read_only=True): SUCCESS while reader1 open -> [(2,)]
WRITER (read_only=False): FAILED as expected while reader1 open ->
IOException: IO Error: Could not set lock on file "<path>":
Conflicting lock is held in /.../Python (PID 85858) by user Workingplace.
However, you would be able to open this database in read-only mode,
e.g. by using the -readonly parameter in the CLI.
See also https://duckdb.org/docs/stable/connect/concurrency
```
→ Plusieurs readers coexistent bien ; un writer est bloqué avec un message légèrement différent (DuckDB suggère explicitement d'ouvrir en lecture seule).

**Point crucial confirmé** : le verrou est posé **à l'ouverture de la connexion** et tenu **pendant toute la durée de vie de la connexion** (pas seulement pendant l'exécution d'une requête) — vérifié car le process qui « tient » la connexion ne fait qu'un `time.sleep(6)` sans requête active, et bloque quand même les autres process pendant ces 6 secondes.

### Implication directe pour l'architecture cible (dbt build écrit / Streamlit lit)

1. Pendant `dbt build` (qui ouvre le fichier en `read_only=False` pour toute sa durée), **toute tentative Streamlit d'ouvrir une connexion (même read-only) échouera** avec `IO Error: Could not set lock on file`.
2. **Piège symétrique et non-intuitif** : si Streamlit met en cache une connexion `read_only=True` de longue durée (pattern `st.cache_resource` classique, gardée ouverte tout le cycle de vie de l'app), alors **`dbt build` échouera à son tour** tant que cette connexion Streamlit reste ouverte, puisqu'un writer ne peut pas s'ouvrir tant qu'un reader tient le fichier. C'est le scénario le plus probable de blocage dans ce projet si l'app tourne en continu pendant qu'on relance les builds dbt.

### Recommandations pratiques (raisonnement d'ingénierie, au-delà de la doc)

- **Option A — connexions courtes côté Streamlit (recommandé, le plus simple)** : ouvrir une connexion `read_only=True` **à la demande**, exécuter la requête, fermer immédiatement (`with duckdb.connect(path, read_only=True) as con: ...`), plutôt que de la garder en cache avec `st.cache_resource` sur toute la durée de vie du process. Coût d'ouverture négligeable pour un fichier local. Ajouter un `try/except duckdb.IOException` avec **retry + backoff court** (grâce à `retries.connect_attempts` côté profil dbt, l'inverse — dbt qui retente d'écrire — est aussi possible) pour absorber une fenêtre de conflit de quelques centaines de ms à quelques secondes pendant un `dbt build`.
- **Option B — build-puis-swap atomique (zéro downtime, plus robuste en prod)** : faire pointer `path:` de dbt vers un fichier temporaire (`benchmark_build.duckdb`), puis après succès du `dbt build`, faire un `os.replace()` atomique vers `benchmark.duckdb`. Les lecteurs Streamlit qui ont déjà un descripteur de fichier ouvert sur l'ancien fichier continuent de lire l'ancienne version sans erreur (comportement standard POSIX du rename), et les nouvelles connexions ouvertes après le swap lisent la nouvelle version. Élimine complètement le conflit de verrou entre build et lecture. NON testé dans ce projet (hors scope de la recherche dbt/duckdb pure) mais c'est un pattern standard reconnu pour ce genre de contrainte writer/reader exclusif.
- Si `st.cache_resource` est quand même utilisé pour la perf, prévoir un moyen de l'invalider/fermer explicitement (`.clear()`) avant de lancer un `dbt build`, ou orchestrer les builds uniquement quand l'app Streamlit n'a pas de connexion active.

Sources : https://duckdb.org/docs/stable/connect/concurrency (règle générale) · tests empiriques directs (messages d'erreur exacts capturés en conditions réelles, 2 process Python séparés) · `retries.connect_attempts` documenté dans le README dbt-duckdb.

---

## 9. API Python DuckDB — essentiels pour le writer silver et le reader Streamlit

Tout ce qui suit a été **testé** dans l'environnement du projet (`duckdb==1.5.5`).

### Connexion

```python
import duckdb

con = duckdb.connect()                                   # en mémoire (éphémère)
con = duckdb.connect("data/gold/benchmark.duckdb")        # fichier, read-write
con = duckdb.connect("data/gold/benchmark.duckdb", read_only=True)  # lecture seule (Streamlit)
with duckdb.connect("data/gold/benchmark.duckdb") as con:  # context manager, ferme auto
    ...
```
`duckdb.sql(...)`/`duckdb.connect(':default:')` partagent une connexion globale **non thread-safe** — utiliser une connexion explicite par thread/session Streamlit.

### Exécution & conversion de résultats

```python
con.execute("select 42").df()      # pandas DataFrame
con.execute("select 42").pl()      # Polars DataFrame  (nécessite `polars` installé)
con.execute("select 42").arrow()   # PyArrow Table
con.sql("select 42").fetchall()    # liste de tuples Python — fonctionne sans pandas/numpy installés (testé)
```
⚠️ Testé : `.df()` lève `ModuleNotFoundError: No module named 'numpy'` si `pandas`/`numpy` ne sont pas installés dans l'environnement — s'assurer que `pandas` (ou `polars`) est bien une dépendance explicite du projet Streamlit si vous utilisez `.df()`.

### Lecture Parquet — aucune extension à installer

**Testé** : sur une connexion en mémoire toute fraîche, sans aucun `INSTALL`/`LOAD` explicite :
```python
con.sql("select count(*) from read_parquet('data/silver/questions.parquet')").fetchall()  # -> [(4,)]
con.sql("select extension_name, loaded, installed from duckdb_extensions() where extension_name='parquet'").fetchall()
# -> [('parquet', True, True)]
```
→ **Le support Parquet est intégré et auto-chargé nativement dans DuckDB** ; `extensions: [parquet]` dans `profiles.yml` est donc superflu pour du Parquet local (inoffensif à garder, mais pas nécessaire). Confirme la question 9 de l'énoncé.

Autres formes équivalentes :
```python
con.read_parquet("data/silver/questions.parquet")      # objet relation DuckDB
duckdb.sql("select * from 'data/silver/questions.parquet'")  # inférence directe par extension de fichier
```

### Écriture Parquet

```python
con.execute("COPY questions TO 'data/silver/questions.parquet' (FORMAT PARQUET)")
# ou, sur une relation :
con.sql("select * from questions").write_parquet("data/silver/questions.parquet")
```
Testé pour générer les fixtures silver de ce document.

### Enregistrer un DataFrame Pandas/Polars comme vue

```python
import pandas as pd
df = pd.DataFrame({"a": [1, 2, 3]})
con.register("my_view", df)                       # crée une VIEW temporaire, lecture seule
con.execute("create table t as select * from my_view")  # pour la rendre mutable/persistante
```
Note (issue du code source du client Python) : `register()` crée une `ViewRelation` **read-only** — pas d'`INSERT`/`UPDATE`/`DELETE` direct dessus ; matérialiser via `CREATE TABLE AS SELECT` si besoin de DML.

### Requêtes paramétrées

```python
con.execute("select * from t where symbol = ?", ["RHAT"]).fetchone()
con.execute("select cast(? as integer), cast(? as integer)", ["42", "84"]).fetchall()
con.executemany("insert into stocks values (?,?,?,?,?)", rows)
```
DuckDB DB-API supporte `?` (positionnel) ; `$1`/`$2` (style PostgreSQL nommé/positionnel) est également supporté par DuckDB en SQL pur — NON re-testé isolément ici mais standard et documenté.

Sources : https://duckdb.org/docs/current/clients/python/overview.html · Context7 `/duckdb/duckdb-python` (tests unitaires du client officiel) · tests empiriques directs dans ce projet.

---

## 10. SQL DuckDB utile pour la couche gold

Toutes les fonctions ci-dessous existent bien dans DuckDB (confirmé via la doc officielle `duckdb-web`, noms exacts) ; `count_if`, `median`, `stddev_samp` ont en plus été **testées dans le mart de référence** de ce projet.

| Besoin | Fonction / syntaxe DuckDB |
|---|---|
| Percentile interpolé | `quantile_cont(col, 0.5)` ou `quantile_cont(col, [0.25, 0.5, 0.75])` |
| Médiane | `median(col)` — **testé** (`median(response_time)` dans le mart de référence) |
| Écart-type d'échantillon | `stddev_samp(col)` |
| Comptage conditionnel simple | `count_if(condition)` — **testé** (`count_if(is_correct)` dans le mart de référence, calcule le nombre de bonnes réponses) |
| Agrégat conditionnel générique | `agg(col) FILTER (WHERE condition)`, ex. `sum(i) FILTER (i <= 5)` |
| Pivot lignes→colonnes | Instruction dédiée `PIVOT ... ON ... USING agg(...) GROUP BY ...`, ex. `PIVOT cities ON year USING sum(population) GROUP BY country;` — ou via `FILTER` pour un pivot manuel |
| Fonctions fenêtre | Standard SQL, ex. `rank() OVER (partition by model order by accuracy desc)`, et les agrégats (`quantile_cont`, `min`, `max`...) fonctionnent aussi en `OVER (...)` |
| Troncature de date | `date_trunc('day', ts)`, `date_trunc('month', ts)`, etc. — spécificateurs standard (`year`, `quarter`, `month`, `week`, `day`, `hour`...) |
| Similarité de chaînes | `jaro_winkler_similarity(s1, s2)` (0 à 1, insensible pas à la casse... en fait sensible à la casse, confirmé par la doc), `jaro_similarity(s1, s2)` |
| Distance d'édition | `levenshtein(s1, s2)`, `damerau_levenshtein(s1, s2)` (inclut les transpositions de caractères adjacents) |

Exemple de matching flou réponse LLM vs réponse correcte pour ce projet :
```sql
select
    a.model,
    a.raw_answer,
    q.correct_answer,
    jaro_winkler_similarity(lower(trim(a.raw_answer)), lower(trim(q.correct_answer))) as similarity,
    levenshtein(lower(trim(a.raw_answer)), lower(trim(q.correct_answer))) as edit_distance
from {{ ref('stg_answers') }} a
join {{ ref('stg_questions') }} q using (question_id)
```

### Intervalle de confiance de Wilson (arithmétique pure, sans dépendance)

Formule statistique standard (« Wilson score interval », indépendante de dbt/DuckDB — cf. littérature statistique classique), **implémentée en macro dbt et testée avec succès** dans ce projet (résultats numériques cohérents obtenus : pour 4/4 succès, IC ≈ [0.51, 1.0] ; pour 2/4, IC ≈ [0.15, 0.85]) :

```jinja
{% macro wilson_interval(successes, trials, z=1.96) %}
    (
        select
            ({{ successes }}::double / nullif({{ trials }}, 0)
                + {{ z }}*{{ z }} / (2*nullif({{ trials }}, 0))
                - {{ z }} * sqrt(
                    ({{ successes }}::double / nullif({{ trials }}, 0))
                    * (1 - {{ successes }}::double / nullif({{ trials }}, 0)) / nullif({{ trials }}, 0)
                    + {{ z }}*{{ z }} / (4*nullif({{ trials }}, 0)*nullif({{ trials }}, 0))
                )
            ) / (1 + {{ z }}*{{ z }} / nullif({{ trials }}, 0)) as wilson_lower,
            ({{ successes }}::double / nullif({{ trials }}, 0)
                + {{ z }}*{{ z }} / (2*nullif({{ trials }}, 0))
                + {{ z }} * sqrt(
                    ({{ successes }}::double / nullif({{ trials }}, 0))
                    * (1 - {{ successes }}::double / nullif({{ trials }}, 0)) / nullif({{ trials }}, 0)
                    + {{ z }}*{{ z }} / (4*nullif({{ trials }}, 0)*nullif({{ trials }}, 0))
                )
            ) / (1 + {{ z }}*{{ z }} / nullif({{ trials }}, 0)) as wilson_upper
    )
{% endmacro %}
```

Usage (testé) — nécessite un `LATERAL` join car le macro référence des colonnes de la requête englobante :
```sql
select model, n_correct, n_answers, wilson_lower, wilson_upper
from agg
cross join lateral {{ wilson_interval('n_correct', 'n_answers') }} as w
```

Sources : https://duckdb.org/docs/current/sql/functions/aggregates.md, .../text.md, .../datepart.md, .../filter.md, .../statements/pivot.md (via Context7 `/duckdb/duckdb-web`) · test empirique complet du mart de référence.

---

## 11. Macros dbt & documentation (`dbt docs generate`)

### Écrire un macro réutilisable

Voir `wilson_interval` ci-dessus — pattern standard : `{% macro nom(args) %} ... SQL avec {{ args }} ... {% endmacro %}`, placé dans `macros/*.sql`, appelé depuis n'importe quel modèle via `{{ nom_macro(...) }}`.

### Documenter les modèles (`description:`)

```yaml
models:
  - name: mart_accuracy_by_model
    description: "Accuracy and response time stats per model"
    columns:
      - name: model
        description: "Identifiant du modèle LLM évalué"
```
Testé — ces descriptions apparaissent dans le catalogue généré par `dbt docs generate`.

### `dbt docs generate` — testé avec succès

```bash
uv run dbt docs generate --project-dir dbt --profiles-dir dbt --target prod
```
Sortie réelle :
```
Building catalog
Catalog written to .../dbt/target/catalog.json
```
Fichiers générés : `manifest.json`, `catalog.json`, `run_results.json`, `graph_summary.json`, `semantic_manifest.json`.

### `--static` — livrable additionnel autonome, testé

```bash
uv run dbt docs generate --project-dir dbt --profiles-dir dbt --target prod --static
```
Génère en plus **`target/static_index.html`** — un fichier HTML unique et autonome (2,4 Mo dans notre test) embarquant manifest/catalog, consultable sans serveur (double-clic ou `file://`). Bon complément livrable pour la documentation du projet, à publier à côté du dashboard Streamlit.

Sources : test empirique direct (`dbt docs generate`, `dbt docs generate --static`) · https://docs.getdbt.com (référence generale sur `description:`).

---

## Pièges & recommandations

1. **Chemins relatifs = piège n°1 vérifié.** `path:` dans `profiles.yml` ET les chemins dans `external_location`/`read_parquet()` sont résolus **par rapport au CWD du process `dbt`**, pas par rapport à `profiles.yml`, ni à `--project-dir`. Testé : lancer `dbt build` avec `cd repo_root && dbt build --project-dir dbt --profiles-dir dbt` et des chemins relatifs à `repo_root` (`data/silver/...`, `data/gold/...`) — **toujours lancer les commandes dbt depuis la racine du repo**, ou passer des chemins absolus / calculés dynamiquement via `env_var`.
2. **`dbt-core-experimental-parser` peut casser l'install en environnement réseau restreint** (proxy d'entreprise, CA custom) car il télécharge un wheel depuis une release GitHub pendant son build. Fix : `export SSL_CERT_FILE=/etc/ssl/cert.pem` (macOS) avant `uv add`/`uv sync`.
3. **Schéma `main` par défaut, piège de config silencieux.** Sans surcharge de `generate_schema_name` + `target: prod`, vos modèles avec `+schema: gold` finissent quand même tous dans `main` — aucune erreur, juste un mauvais schéma. Toujours vérifier après le premier build avec `select table_schema, table_name from information_schema.tables`.
4. **Conflit d'accès concurrent writer/reader, confirmé dans les deux sens.** `dbt build` bloque Streamlit ET une connexion Streamlit mise en cache longtemps bloque `dbt build`. Ne pas garder une connexion DuckDB ouverte indéfiniment côté Streamlit (`st.cache_resource` sur la connexion elle-même est un piège classique dans ce contexte précis) ; préférer des connexions courtes avec retry, ou le pattern build-puis-`os.replace()` atomique.
5. **`.df()` nécessite pandas/numpy installés** — erreur explicite sinon (`ModuleNotFoundError: No module named 'numpy'`). Vérifier que ces libs sont bien dans les dépendances Streamlit si `.df()` est utilisé.
6. **`data_tests:` vs `tests:`** — ne jamais mélanger les deux clés sur la même ressource (erreur de validation dbt). Utiliser systématiquement `data_tests:` (nom actuel).
7. **`.gitignore` : penser à `*.duckdb`** en plus de `target/`/`dbt_packages/`/`logs/` — le fichier gold généré n'a pas sa place dans git (gros, binaire, régénérable par `dbt build`).
8. **`clean-targets` par défaut n'inclut PAS `dbt_packages`** — si vous voulez que `dbt clean` supprime aussi les packages téléchargés, l'ajouter explicitement dans `dbt_project.yml`.
9. **`generate_schema_name_for_env` a un comportement dev/prod volontairement différent** — bien lire la table du §4 avant de s'étonner que le schéma custom « ne marche pas » en local.
10. **dbt Fusion et compatibilité duckdb : NON VÉRIFIÉ.** Rester explicitement sur dbt-core (testé et documenté pour dbt-duckdb) plutôt que d'installer une version « Fusion » sans confirmation de compatibilité.

---

## Squelette de référence (testé de bout en bout, `dbt build` → `PASS=6`)

### `dbt/dbt_project.yml`
```yaml
name: 'benchmark'
version: '1.0.0'

profile: 'benchmark'

model-paths: ["models"]
macro-paths: ["macros"]
test-paths: ["tests"]
seed-paths: ["seeds"]

target-path: "target"
clean-targets:
  - "target"
  - "dbt_packages"

models:
  benchmark:
    staging:
      +materialized: view
      +schema: staging
    marts:
      +materialized: table
      +schema: gold
```

### `dbt/profiles.yml`
```yaml
benchmark:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{{ env_var('DBT_DUCKDB_PATH', 'data/gold/benchmark.duckdb') }}"
      threads: 4
      extensions:
        - parquet
    prod:
      type: duckdb
      path: "{{ env_var('DBT_DUCKDB_PATH', 'data/gold/benchmark.duckdb') }}"
      threads: 4
      extensions:
        - parquet
```
Lancement (depuis la racine du repo, où se trouvent `data/` et `dbt/`) :
```bash
uv run dbt build --project-dir dbt --profiles-dir dbt --target prod
```

### `dbt/models/staging/sources.yml`
```yaml
version: 2

sources:
  - name: silver
    meta:
      external_location: "read_parquet('{{ env_var('SILVER_DIR', 'data/silver') }}/{name}.parquet')"
    tables:
      - name: questions
      - name: answers
```

### `dbt/models/staging/stg_questions.sql` (modèle staging, `view`)
```sql
select
    question_id,
    question_text,
    category,
    difficulty,
    correct_answer
from {{ source('silver', 'questions') }}
```

### `dbt/models/staging/stg_answers.sql`
```sql
select
    answer_id,
    question_id,
    model,
    prompt_variant,
    raw_answer,
    is_correct,
    response_time,
    tokens
from {{ source('silver', 'answers') }}
```

### `dbt/models/marts/mart_accuracy_by_model.sql` (mart, `table`)
```sql
with answers as (
    select * from {{ ref('stg_answers') }}
),

agg as (
    select
        model,
        count(*) as n_answers,
        count_if(is_correct) as n_correct,
        avg(response_time) as avg_response_time_s,
        median(response_time) as median_response_time_s
    from answers
    group by model
)

select
    model,
    n_answers,
    n_correct,
    n_correct::double / n_answers as accuracy,
    avg_response_time_s,
    median_response_time_s,
    wilson_lower,
    wilson_upper
from agg
cross join lateral {{ wilson_interval('n_correct', 'n_answers') }} as w
```

### `dbt/models/marts/marts.yml` (test sur le mart)
```yaml
version: 2

models:
  - name: mart_accuracy_by_model
    description: "Accuracy and response time stats per model"
    columns:
      - name: model
        data_tests:
          - unique
          - not_null
      - name: accuracy
        data_tests:
          - not_null
```

### `dbt/macros/wilson_interval.sql`
```jinja
{% macro wilson_interval(successes, trials, z=1.96) %}
    (
        select
            ({{ successes }}::double / nullif({{ trials }}, 0)
                + {{ z }}*{{ z }} / (2*nullif({{ trials }}, 0))
                - {{ z }} * sqrt(
                    ({{ successes }}::double / nullif({{ trials }}, 0))
                    * (1 - {{ successes }}::double / nullif({{ trials }}, 0)) / nullif({{ trials }}, 0)
                    + {{ z }}*{{ z }} / (4*nullif({{ trials }}, 0)*nullif({{ trials }}, 0))
                )
            ) / (1 + {{ z }}*{{ z }} / nullif({{ trials }}, 0)) as wilson_lower,
            ({{ successes }}::double / nullif({{ trials }}, 0)
                + {{ z }}*{{ z }} / (2*nullif({{ trials }}, 0))
                + {{ z }} * sqrt(
                    ({{ successes }}::double / nullif({{ trials }}, 0))
                    * (1 - {{ successes }}::double / nullif({{ trials }}, 0)) / nullif({{ trials }}, 0)
                    + {{ z }}*{{ z }} / (4*nullif({{ trials }}, 0)*nullif({{ trials }}, 0))
                )
            ) / (1 + {{ z }}*{{ z }} / nullif({{ trials }}, 0)) as wilson_upper
    )
{% endmacro %}
```

### `dbt/macros/generate_schema_name.sql` (schéma gold propre)
```jinja
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ generate_schema_name_for_env(custom_schema_name, node) }}
{%- endmacro %}
```

### Résultat réel obtenu
```
Found 3 models, 3 data tests, 2 sources, 502 macros
1 of 6 OK created sql view model staging.stg_answers
2 of 6 OK created sql view model staging.stg_questions
3 of 6 OK created sql table model gold.mart_accuracy_by_model
4 of 6 PASS not_null_mart_accuracy_by_model_accuracy
5 of 6 PASS not_null_mart_accuracy_by_model_model
6 of 6 PASS unique_mart_accuracy_by_model_model
Completed successfully
Done. PASS=6 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=6
```
Contenu de `gold.mart_accuracy_by_model` (lu en `read_only=True` après le build) :
```
model    n_answers  n_correct  accuracy  avg_response_time_s  median_response_time_s  wilson_lower  wilson_upper
gpt-4o   4          4          1.0       0.42                 0.38                    0.510         1.0
llama3   4          2          0.5       0.465                0.44                    0.150         0.850
```

### Exemple de writer silver (Python/DuckDB)
```python
import duckdb

con = duckdb.connect()
con.execute("CREATE TABLE questions AS SELECT * FROM ...")
con.execute("COPY questions TO 'data/silver/questions.parquet' (FORMAT PARQUET)")
con.close()
```

### Exemple de reader Streamlit (connexion courte, recommandé §Pièges)
```python
import duckdb
import streamlit as st

@st.cache_data(ttl=30)  # cache la DONNÉE, pas la connexion -> pas de verrou tenu
def load_accuracy() -> "pandas.DataFrame":
    with duckdb.connect("data/gold/benchmark.duckdb", read_only=True) as con:
        return con.execute("select * from gold.mart_accuracy_by_model").df()

df = load_accuracy()
st.dataframe(df)
```

---

## Sources

- PyPI JSON API : https://pypi.org/pypi/dbt-core/json, https://pypi.org/pypi/dbt-duckdb/json, https://pypi.org/pypi/duckdb/json (interrogées le 2026-09-10)
- GitHub dbt-duckdb (README + `_autodocs/*`) : https://github.com/duckdb/dbt-duckdb
- GitHub dbt-duckdb releases API : https://api.github.com/repos/duckdb/dbt-duckdb/releases
- Code source installé localement (lu directement) : `dbt/adapters/duckdb/credentials.py`, `relation.py`, `utils.py` (paquet `dbt-duckdb==1.11.0`) ; `dbt/cli/params.py`, `dbt/config/project.py` (paquet `dbt-core==1.12.4`)
- docs.getdbt.com : `/reference/warehouse-setups/duckdb-setup`, `/docs/build/sources`, `/reference/resource-configs/duckdb-configs`, `/docs/build/data-tests`, `/reference/commands/build`, `/reference/dbt_project.yml`, `/reference/programmatic-invocations`, `/docs/build/custom-schemas`, `/docs/core/connect-data-platform/profiles.yml`, `/docs/fusion/about-fusion`
- duckdb.org : `/docs/current/clients/python/overview.html`, `/docs/current/connect/concurrency.html`, `/docs/current/data/parquet/overview.html`, `/docs/current/sql/functions/aggregates.md`, `.../text.md`, `.../datepart.md`, `.../filter.md`, `/docs/current/sql/statements/pivot.md`
- dbt-utils : https://github.com/dbt-labs/dbt-utils/releases, https://github.com/dbt-labs/dbt-utils/blob/main/dbt_project.yml
- Context7 : `/duckdb/dbt-duckdb`, `/duckdb/duckdb-python`, `/duckdb/duckdb-web`, `/dbt-labs/docs.getdbt.com`
- Tests empiriques directs réalisés pendant cette recherche : installation `uv` réelle, `dbt build`/`dbt docs generate`/`dbtRunner` réels sur un mini-projet reproduisant l'architecture cible, test de verrouillage concurrentiel avec 2 process Python séparés.
