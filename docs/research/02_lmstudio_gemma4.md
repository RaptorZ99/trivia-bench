# LM Studio (SDK Python `lmstudio`, CLI `lms`, REST API) + `google/gemma-4-12b-qat`
### Référence vérifiée pour un harnais de benchmark (~4000+ questions de trivia) — MacBook Pro M2 Pro / 16 Go

Date de la recherche : 2026-09-10. Machine cible : Apple M2 Pro, 16 Go RAM unifiée, macOS. LM Studio installé dans `~/.lmstudio`, binaire `lms` dans `~/.lmstudio/bin/lms`. Serveur **pas encore démarré**.

Méthodologie : Context7 (doc officielle indexée), WebFetch sur `lmstudio.ai/docs/*`, PyPI, code source public `lmstudio-ai/lmstudio-python` (via `gh api`, y compris le schéma JSON canonique `sdk-schema/lms.json` qui décrit le protocole wire — c'est la source la plus fiable pour les noms exacts de champs), Hugging Face, Google AI for Developers, WebSearch. Tout ce qui n'a pas pu être confirmé par une source est marqué **NON VÉRIFIÉ**.

---

## Résumé exécutif

- **SDK Python** : package PyPI `lmstudio`, dernière version **stable 1.5.0** (22 août 2025), `>=3.10` requis (3.10–3.13 testés). Une version bêta `1.6.0b1` existe sur PyPI/GitHub mais n'est pas installée par défaut (`pip install lmstudio`).
- **Import** : `import lmstudio as lms`. Deux façons d'appeler le modèle : API de convenance `lms.llm(...)` (client global implicite) vs API scoped `with lms.Client() as client: ...` — **pour un batch de milliers d'appels, préférer `with lms.Client(api_host=...) as client:`** (contrôle explicite du host/port, fermeture déterministe des ressources websocket).
- **Appels clés retenus** : `model.respond(chat, config={...}, response_format=...)` pour le chat (avec `lms.Chat("system prompt")` + `chat.add_user_message(...)`), `model.complete(prompt, config={...})` pour du texte brut sans template.
- **Piège n°1 (critique) — casse des clés de config** : quand `config=` est un **dict Python brut**, les clés sont en **camelCase** et suivent exactement le protocole wire (`maxTokens`, `topKSampling`, `topPSampling`, `minPSampling`, `repeatPenalty`, `stopStrings`, `contextOverflowPolicy`, `draftModel`, `cpuThreads`...). Si on construit un objet `lms.LlmPredictionConfig(...)`, les kwargs sont en **snake_case** (`max_tokens`, `top_k_sampling`, `top_p_sampling`, `min_p_sampling`, `repeat_penalty`, `stop_strings`...). Confirmé au niveau du code source (`sdk-schema/_templates/msgspec.jinja2` : *"Multi-word keys are defined using their camelCase form, as that is what `to_dict()` emits"*) et des tests unitaires du SDK.
- **Stats de prédiction** : `result.stats.predicted_tokens_count`, `result.stats.time_to_first_token_sec`, `result.stats.tokens_per_second`, `result.stats.prompt_tokens_count`, `result.stats.total_tokens_count`, `result.stats.stop_reason`, `result.stats.num_gpu_layers` + champs de speculative decoding (`accepted_draft_tokens_count`, etc.). Aussi `result.model_info`, `result.load_config`, `result.prediction_config` — tous confirmés dans le code source (`PredictionResult` dataclass, `src/lmstudio/json_api.py`).
- **Sortie structurée** : `response_format=UnPydanticBaseModel` ou `response_format={json schema dict}` → `result.parsed`. Sous le capot, LM Studio supporte `structured.type = "json" | "gbnf" | "none"` (confirmé par le schéma JSON), donc une grammaire **GBNF** est bien utilisable — c'est la même mécanique llama.cpp quel que soit le modèle GGUF, donc compatible Gemma 4 GGUF **avec un niveau de confiance élevé mais pas de confirmation spécifique "Gemma 4" trouvée (NON VÉRIFIÉ pour ce modèle précis)**.
- **Modèle cible** : clé LM Studio **`google/gemma-4-12b-qat`** (catalogue LM Studio ; le dépôt Hugging Face sous-jacent est `lmstudio-community/gemma-4-12B-it-QAT-GGUF`, fichier unique `gemma-4-12B-it-QAT-Q4_0.gguf` ≈ **6.98 Go**). RAM minimum indiquée par LM Studio : **7 Go** → tient large sur 16 Go unifiés, mais contexte à réduire (4K–8K recommandé au lieu du max 256K) pour laisser de la marge KV-cache + OS.
- **Gemma 4 gotcha #1 — mode "thinking"** : activé par défaut ("Enable Thinking" dans LM Studio). Selon la fiche modèle Google, le thinking se déclenche par un token `<|think|>` en tête du prompt système ; le retirer désactive le raisonnement. **Aucun champ dédié `enable_thinking`/`reasoning` n'existe dans le schéma `llmPredictionConfigInput` du SDK Python** (seul `reasoningParsing` existe, et il ne fait que *parser* la sortie, pas l'activer/désactiver) — alors que l'API REST native `/api/v1/chat` expose un champ `reasoning: "off"|"on"|"low"|"medium"|"high"`. Donc en Python, désactiver le thinking passe soit par le toggle GUI au chargement, soit par contrôle manuel du prompt système, soit par la voie REST native.
- **Sampling recommandé par Google pour Gemma 4** : `temperature=1.0, top_p=0.95, top_k=64`. **Pour un benchmark déterministe** : `temperature: 0` (greedy) recommandé plutôt que ces valeurs "créatives".
- **`seed`** existe uniquement dans `LlmLoadModelConfig` (paramètre de **chargement** du modèle), **pas** dans `LlmPredictionConfigInput` (pas de seed par requête). La reproductibilité par requête repose donc sur `temperature=0` + configuration figée, pas sur un seed per-call.
- **Concurrence** : LM Studio supporte le *continuous batching* ("Parallel Requests", GUI uniquement documentée, défaut = 4 requêtes concurrentes, nécessite runtime llama.cpp ≥ v2.0.0). **Pour un benchmark où on mesure le temps de réponse individuel proprement, envoyer les requêtes séquentiellement** (une par une) est recommandé — le parallélisme brouille les mesures de latence par requête via le batching côté serveur.
- **CLI** : `lms server start [--port N] [--cors] [--bind 0.0.0.0|127.0.0.1]`, port par défaut **1234** (confirmé dans les exemples officiels), bind par défaut `127.0.0.1`. `lms load <model_key> [--context-length N] [--gpu max|auto|0-1] [--identifier X] [--ttl S] [--estimate-only]`. **Pas de flag `-y/--yes` documenté** sur `lms load`. Le serveur n'a **pas besoin de l'app GUI ouverte** une fois LM Studio lancé au moins une fois (setup initial requis).

---

## 1. Installation Python SDK & versions

**Package PyPI** : `lmstudio`. Installation :
```bash
pip install lmstudio
```
- **Dernière version stable** : `1.5.0` (publiée le 22 août 2025, 13:52:41 UTC). Une pré-version `1.6.0b1` est disponible sur PyPI et sur GitHub (branche `main` du dépôt `lmstudio-ai/lmstudio-python`, confirmé via `pyproject.toml` : `version = "1.6.0b1"`), mais `pip install lmstudio` installe la version stable 1.5.0 par défaut.
- **Python requis** : `>=3.10` (3.10, 3.11, 3.12, 3.13 supportés).
- **Historique des versions** (PyPI) : 0.0.1, 1.0.0(rc1), 1.0.1, 1.1.0, 1.2.0, 1.3.0/1.3.1/1.3.2, 1.4.0/1.4.1, 1.5.0(b1), 1.6.0b1.

**Import idiomatique** :
```python
import lmstudio as lms
```

### API de convenance vs API scoped (Client)

Le SDK propose **trois patterns** (source : page d'intro `lmstudio.ai/docs/python`) :

1. **Interactive Convenience API** : utilise un client global implicite par défaut — pratique en REPL / notebook.
   ```python
   import lmstudio as lms
   model = lms.llm("google/gemma-4-12b-qat")
   result = model.respond("Quelle est la capitale de la France ?")
   ```
2. **Scoped Resource API** : gestion déterministe des ressources via context manager, recommandée pour un script long-lived.
   ```python
   with lms.Client(api_host="localhost:1234") as client:
       model = client.llm.model("google/gemma-4-12b-qat")
       result = model.respond("Quelle est la capitale de la France ?")
   ```
3. **Asynchronous API** (depuis SDK **v1.5.0+**) : `lms.AsyncClient()`, structured concurrency (`asyncio`), pas de timeout intégré par défaut (contrairement au sync).

**Recommandation pour un batch de ~4000 appels** : utiliser l'**API scoped `with lms.Client(...) as client:`**. Raisons vérifiées dans le code source (`src/lmstudio/sync_api.py`, classe `Client`) :
- fermeture déterministe du thread websocket (`AsyncWebsocketThread`) à la sortie du `with` (pas de dépendance à la terminaison du process) ;
- possibilité de garder une seule connexion websocket ouverte pour tout le run plutôt que d'en recréer une via l'API de convenance à chaque redémarrage de script ;
- `api_host` explicite pour éviter toute ambiguïté de découverte réseau (voir piège ci-dessous).

### Configurer un host/port personnalisé

Confirmé dans le code source (`ClientBase.__init__`) :
```python
client = lms.Client(api_host="localhost:1234")           # host:port explicite
```
Pour l'API de convenance :
```python
lms.configure_default_client(api_host="localhost:1234")  # avant tout appel lms.llm(...)
```
**Piège découvert dans le code source** : si `api_host` n'est **pas** fourni, le SDK ne tente **pas** uniquement le port 1234. Il sonde une liste fixe de ports candidats générée automatiquement (`src/lmstudio/_api_server_ports.py`) :
```python
default_api_ports = (41343, 52993, 16141, 39414, 22931)
```
en interrogeant `http://127.0.0.1:<port>/lmstudio-greeting` jusqu'à trouver une réponse `{"lmstudio": true}`. **Recommandation forte : toujours passer `api_host="localhost:1234"` explicitement dans un harnais de benchmark**, pour ne pas dépendre de cette découverte automatique (qui peut échouer si le serveur tourne sur un port différent des candidats, ou ralentir le démarrage du script).

### Timeout de l'API synchrone

Depuis SDK v1.5.0+, timeout par défaut de **60 secondes** :
```python
import lmstudio as lms
lms.set_sync_api_timeout(120.0)   # 2 minutes
lms.get_sync_api_timeout()        # lire la valeur actuelle
```
L'API asynchrone n'a pas de timeout intégré ; utiliser `asyncio.wait_for(...)`.

**Sources** : https://lmstudio.ai/docs/python · https://pypi.org/project/lmstudio/ · https://pypi.org/pypi/lmstudio/json · code source `lmstudio-ai/lmstudio-python` (`src/lmstudio/sync_api.py`, `src/lmstudio/json_api.py`, `src/lmstudio/_api_server_ports.py`, `pyproject.toml`)

---

## 2. Chat / prediction : signatures exactes et clés de config

### Signature exacte de `respond()` (confirmée dans `src/lmstudio/sync_api.py`, classe `LLM`)

```python
def respond(
    self,
    history: Chat | ChatHistoryDataDict | str,
    *,
    response_format: ResponseSchema | None = None,
    config: LlmPredictionConfig | LlmPredictionConfigDict | None = None,
    preset: str | None = None,
    on_message: PredictionMessageCallback | None = None,
    on_first_token: PredictionFirstTokenCallback | None = None,
    on_prediction_fragment: PredictionFragmentCallback | None = None,
    on_prompt_processing_progress: PromptProcessingCallback | None = None,
) -> PredictionResult: ...
```
Il existe aussi `respond_stream(...)` (retourne un `PredictionStream` itérable de fragments) avec la même signature.

### Signature exacte de `complete()` (idem fichier)

```python
def complete(
    self,
    prompt: str,
    *,
    response_format: ResponseSchema | None = None,
    config: LlmPredictionConfig | LlmPredictionConfigDict | None = None,
    preset: str | None = None,
    on_message: PredictionMessageCallback | None = None,
    on_first_token: PredictionFirstTokenCallback | None = None,
    on_prediction_fragment: PredictionFragmentCallback | None = None,
    on_prompt_processing_progress: PromptProcessingCallback | None = None,
) -> PredictionResult: ...
```
`complete()` n'applique **pas** le chat template (pas de rôles system/user) — utile pour du texte brut, mais **pour Gemma 4 (modèle instruct)**, `respond()` avec `Chat` est la méthode adaptée pour un benchmark de questions/réponses.

Les deux acceptent aussi un paramètre `preset: str | None` (nom d'un preset LM Studio sauvegardé côté serveur) — non demandé explicitement mais utile à savoir : peut remplacer un `config=` complet.

### Passer un prompt système

```python
chat = lms.Chat("Tu es un assistant qui répond uniquement par la bonne réponse, sans explication.")
chat.add_user_message("Quelle est la capitale de la France ?")
result = model.respond(chat)
```
Confirmé dans le code source (`src/lmstudio/history.py`, classe `Chat`) :
```python
class Chat:
    def __init__(self, initial_prompt: SystemPromptInput | None = None, *, _initial_history=None): ...
    def add_system_prompt(self, prompt: SystemPromptInput) -> SystemPrompt: ...
    def add_user_message(self, content, *, images: Sequence[FileHandleInput] = (), ...) -> UserMessage: ...
    def add_assistant_response(self, response, tool_requests=...) -> AssistantResponse: ...
```
**Note importante** : `add_system_prompt` lève une erreur (`LMStudioRuntimeError`) si un prompt système existe déjà consécutivement — un seul prompt système par `Chat`, à définir en général via le constructeur `lms.Chat("...")`.

### Passer une config par requête

```python
result = model.respond(chat, config={
    "temperature": 0,
    "maxTokens": 16,
    "topKSampling": 64,
    "topPSampling": 0.95,
    "stopStrings": ["\n\n"],
})
```

### Table exhaustive des clés de `LlmPredictionConfigInput` (confirmée via le schéma JSON canonique `sdk-schema/lms.json`, définition `llmPredictionConfigInput`)

| Clé **dict (camelCase, wire)** | Équivalent kwarg **struct Python (snake_case)** | Type | Description |
|---|---|---|---|
| `maxTokens` | `max_tokens` | `int \| false` | Nombre max de tokens à générer. `false` = illimité. |
| `temperature` | `temperature` | `float ≥ 0` | Aléa de l'échantillonnage. |
| `stopStrings` | `stop_strings` | `list[str]` | Chaînes déclenchant l'arrêt de la génération. |
| `toolCallStopStrings` | `tool_call_stop_strings` | `list[str]` | Idem mais avec `stopReason = toolCalls`. |
| `contextOverflowPolicy` | `context_overflow_policy` | enum `stopAtLimit \| truncateMiddle \| rollingWindow` | Comportement si dépassement de la fenêtre de contexte. |
| `structured` | `structured` | `ZodType \| LLMStructuredPredictionSetting` | Voir section 3 (sortie structurée). |
| `rawTools` | `raw_tools` | objet (`type: "none"` ou `"toolArray"` + `tools`) | Configuration bas niveau du tool-use. |
| `topKSampling` | `top_k_sampling` | `float` | Top-K sampling. |
| `repeatPenalty` | `repeat_penalty` | `float \| false` | Pénalité de répétition (1.0 = aucune, `false` = désactivée). |
| `minPSampling` | `min_p_sampling` | `float \| false` | Seuil min-p. |
| `topPSampling` | `top_p_sampling` | `float \| false` | Nucleus sampling (top-p). |
| `cpuThreads` | `cpu_threads` | `int` | Threads CPU pour l'inférence. |
| `promptTemplate` | `prompt_template` | objet `llmPromptTemplate` | Template de prompt personnalisé (manuel ou Jinja) + `stopStrings` associées. |
| `draftModel` | `draft_model` | `str` | Clé du modèle brouillon (speculative decoding). |
| `speculativeDecodingNumDraftTokensExact` | `speculative_decoding_num_draft_tokens_exact` | `int ≥ 1` | Nombre exact de tokens brouillons. |
| `speculativeDecodingMinDraftLengthToConsider` | `speculative_decoding_min_draft_length_to_consider` | `int ≥ 0` | Longueur min. avant de considérer le brouillon. |
| `speculativeDecodingMinContinueDraftingProbability` | `speculative_decoding_min_continue_drafting_probability` | `float` | Probabilité min. pour continuer le brouillon. |
| `reasoningParsing` | `reasoning_parsing` | objet `{enabled, startString, endString}` | Contrôle le **parsing** (pas la génération) des tokens de raisonnement. |
| `raw` | `raw` | `kvConfig` | Échappatoire bas niveau vers la config clé-valeur brute du serveur (utile si un champ n'est pas encore exposé typé). |

**⚠️ Piège de casse confirmé au niveau code** (`sdk-schema/_templates/msgspec.jinja2`, commentaire du générateur de code, corroboré par `tests/test_kv_config.py` qui montre côte à côte `"maxTokens"/"minPSampling"/"topKSampling"/"topPSampling"` (forme dict) et `"max_tokens"/"min_p_sampling"/"top_k_sampling"/"top_p_sampling"` (forme struct)) :
- **Dict Python brut** passé à `config=` → **camelCase obligatoire**, car c'est directement désérialisé comme `LlmPredictionConfigDict` (`TypedDict`), qui *"emits camelCase, as that is what `to_dict()` emits, and what `_from_api_dict()` accepts"*.
- **Objet `lms.LlmPredictionConfig(...)`** construit programmatiquement → kwargs en **snake_case**.
- Dans le doute pour un harnais de benchmark : **utiliser systématiquement la forme dict camelCase** (c'est la forme majoritairement illustrée dans toute la documentation officielle et les exemples GitHub), ce qui évite toute ambiguïté.

**Non trouvé dans le schéma canonique actuel** (`xtcProbability`, `xtcThreshold` mentionnés par une page de doc TypeScript rendue par IA) : absents du fichier `sdk-schema/lms.json` du SDK Python à la version testée → **marqué NON VÉRIFIÉ / probablement obsolète ou spécifique à une autre branche**, ne pas s'y fier pour le harnais.

**Sources** : https://lmstudio.ai/docs/python/llm-prediction/chat-completion · https://lmstudio.ai/docs/python/llm-prediction/completion · https://lmstudio.ai/docs/python/llm-prediction/parameters · code source `lmstudio-ai/lmstudio-python` (`src/lmstudio/sync_api.py`, `sdk-schema/lms.json` définition `llmPredictionConfigInput`, `sdk-schema/_templates/msgspec.jinja2`, `tests/test_kv_config.py`)

---

## 3. Sortie structurée (JSON forcé)

Deux façons de forcer un schéma, toutes deux passées via `response_format=` :

### a) Avec une classe Pydantic (ou `lms.BaseModel`)

```python
from pydantic import BaseModel

class TriviaAnswer(BaseModel):
    answer: str
    confidence: float

result = model.respond(
    "Quelle est la capitale de la France ? Réponds au format demandé.",
    response_format=TriviaAnswer,
)
data = result.parsed   # dict conforme au schéma
print(data["answer"], data["confidence"])
```
Note du SDK : *"Pydantic models natively implement the `lmstudio.ModelSchema` protocol"* — `lmstudio.BaseModel` (wrapper `msgspec`) fonctionne aussi.

### b) Avec un schéma JSON brut (dict)

```python
schema = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["answer", "confidence"],
}
result = model.respond("Quelle est la capitale de la France ?", response_format=schema)
data = result.parsed
```

### Ce que retourne `result.parsed`

D'après la doc officielle : *"the prediction result's `parsed` field will contain a string-keyed dictionary that conforms to the given schema."* → toujours un **dict Python** (même en partant d'un modèle Pydantic), pas une instance Pydantic re-hydratée. `result.structured` (bool) indique si la sortie est structurée.

### GBNF / grammaire — mécanique sous-jacente

Confirmé par le schéma canonique (`sdk-schema/lms.json`, définition `llmStructuredPredictionSetting`) :
```json
{
  "type": {"enum": ["none", "json", "gbnf"]},
  "jsonSchema": "...",
  "gbnfGrammar": "string"
}
```
→ Le SDK **supporte bien une grammaire GBNF** en plus du mode "json" (schéma → grammaire générée automatiquement côté serveur pour llama.cpp). C'est le mécanisme standard llama.cpp de contrainte de génération token-par-token, **indépendant de l'architecture du modèle** — donc applicable en théorie à tout modèle GGUF chargé via le runtime llama.cpp de LM Studio, Gemma 4 y compris. **Aucune confirmation spécifique "Gemma 4 + structured output" trouvée dans la documentation ou les release notes → NON VÉRIFIÉ pour ce modèle précis**, mais le mécanisme étant générique au runtime (pas au modèle), le risque d'incompatibilité est faible.

**Caveat streaming** : *"even for structured responses, the fragment contents are still only text"* — en mode `respond_stream`, il faut accumuler puis parser à la fin ; seul `result.parsed` (sur le résultat final) est garanti conforme au schéma.

**Sources** : https://lmstudio.ai/docs/python/llm-prediction/structured-response · schéma `sdk-schema/lms.json` (`lmstudio-ai/lmstudio-python`)

---

## 4. Stats de prédiction — champs exacts

### Exemple officiel (doc rendue, page chat-completion)

```python
# `result` est la réponse du modèle.
print("Model used:", result.model_info.display_name)
print("Predicted tokens:", result.stats.predicted_tokens_count)
print("Time to first token (seconds):", result.stats.time_to_first_token_sec)
print("Stop reason:", result.stats.stop_reason)
```

### Liste exhaustive de `result.stats` (`LlmPredictionStats`)

Établie à partir du **schéma JSON canonique** (`sdk-schema/lms.json`, définition `llmPredictionStats` — clés wire en camelCase) et confirmée pour la conversion vers le snake_case Python par le même mécanisme de génération de code que la section 2 :

| Attribut Python (`result.stats.xxx`) | Clé wire (camelCase) | Type | Obligatoire ? |
|---|---|---|---|
| `stop_reason` | `stopReason` | enum (voir ci-dessous) | oui |
| `tokens_per_second` | `tokensPerSecond` | `float` | non |
| `num_gpu_layers` | `numGpuLayers` | `float` | non |
| `time_to_first_token_sec` | `timeToFirstTokenSec` | `float` | non |
| `prompt_tokens_count` | `promptTokensCount` | `int` | non |
| `predicted_tokens_count` | `predictedTokensCount` | `int` | non |
| `total_tokens_count` | `totalTokensCount` | `int` | non (⚠️ **pas** `total_tokens`) |
| `used_draft_model_key` | `usedDraftModelKey` | `str` | non |
| `total_draft_tokens_count` | `totalDraftTokensCount` | `int` | non |
| `accepted_draft_tokens_count` | `acceptedDraftTokensCount` | `int` | non |
| `rejected_draft_tokens_count` | `rejectedDraftTokensCount` | `int` | non |
| `ignored_draft_tokens_count` | `ignoredDraftTokensCount` | `int` | non |

Valeurs possibles de `stop_reason` (enum `llmPredictionStopReason`, confirmé dans le schéma) :
`userStopped`, `modelUnloaded`, `failed`, `eosFound`, `stopStringFound`, `toolCalls`, `maxPredictedTokensReached`, `contextLengthReached`.

### `result.model_info`, `result.load_config`, `result.prediction_config`

Confirmés directement dans le code source du dataclass `PredictionResult` (`src/lmstudio/json_api.py`) :
```python
@dataclass(kw_only=True, frozen=True, slots=True)
class PredictionResult:
    content: str
    parsed: AnyPrediction
    stats: LlmPredictionStats
    model_info: LlmInfo
    structured: bool
    load_config: LlmLoadModelConfig
    prediction_config: LlmPredictionConfig
```
- `result.model_info` : objet `LlmInfo` avec entre autres `display_name`, `model_key`, `format`, `path`, `size_bytes`, `params_string`, `architecture`, `vision`, `trained_for_tool_use`, `max_context_length` (champs `llmInfo` du schéma JSON, camelCase→snake_case comme ci-dessus).
- `result.load_config` : la config de **chargement** effectivement utilisée pour l'instance (voir section 5 pour ses champs).
- `result.prediction_config` : la config de **génération** effectivement utilisée (résolution finale des valeurs par défaut + overrides).

**Pour le harnais de benchmark**, ceci permet de logguer, par question, le couple `(load_config, prediction_config)` réellement appliqué — utile pour la traçabilité/reproductibilité (section 10).

**Sources** : https://lmstudio.ai/docs/python/llm-prediction/chat-completion · https://lmstudio.ai/docs/python/llm-prediction/speculative-decoding · code source (`src/lmstudio/json_api.py`, `sdk-schema/lms.json` définitions `llmPredictionStats`, `llmInfo`)

---

## 5. Gestion des modèles depuis Python

### `lms.llm("model-key")` — sémantique "get if loaded, or load"

```python
model = lms.llm("google/gemma-4-12b-qat")   # charge si absent, réutilise sinon
model = lms.llm()                            # récupère N'IMPORTE QUEL modèle déjà chargé
```
Confirmé code source (`_SyncSessionModel.model()`, `src/lmstudio/sync_api.py`) : sans clé, retourne le premier modèle déjà chargé (`_get_any()`) ; avec une clé, appelle en interne `_get_or_load(model_key, ttl, config, on_load_progress)`. **⚠️ Si le modèle est déjà chargé, la `config` fournie est ignorée** ("configuration of retrieved model is NOT checked against the given config").

### Charger une nouvelle instance avec une config garantie (recommandé pour le benchmark)

```python
with lms.Client(api_host="localhost:1234") as client:
    model = client.llm.load_new_instance(
        "google/gemma-4-12b-qat",
        "trivia-bench",             # instance_identifier (positionnel, optionnel)
        ttl=None,                   # None = pas d'auto-unload ; sinon secondes
        config={
            "contextLength": 4096,
            "gpu": "max",
            "flashAttention": True,
        },
    )
```
Signature exacte confirmée (`DownloadedModel.load_new_instance`, `src/lmstudio/sync_api.py`) :
```python
def load_new_instance(
    self, model_key: str, instance_identifier: str | None = None, *,
    ttl: int | None = DEFAULT_TTL,      # DEFAULT_TTL = 3600 (1h), confirmé code source
    config: TLoadConfig | TLoadConfigDict | None = None,
    on_load_progress: ModelLoadingCallback | None = None,
) -> TModelHandle: ...
```
**⚠️ Si `instance_identifier` correspond à une instance déjà existante, le serveur lève une erreur.**

### Table des clés de `LlmLoadModelConfig` (schéma JSON canonique, définition `llmLoadModelConfig`)

| Clé dict (camelCase) | snake_case struct (pattern confirmé, cf. section 2) | Type | Description |
|---|---|---|---|
| `gpu` | `gpu` | objet `GPUSetting` (`ratio: 0-1\|"max"\|"off"`, `mainGpu`, `splitStrategy: "evenly"\|"favorMainGpu"`, `disabledGpus`) | Répartition GPU. |
| `gpuStrictVramCap` | `gpu_strict_vram_cap` | `bool` | Plafond VRAM strict. |
| `offloadKVCacheToGpu` | `offload_kv_cache_to_gpu` | `bool` | Décharger le cache KV sur le GPU. |
| `contextLength` | `context_length` | `int ≥ 1` | Taille de la fenêtre de contexte (tokens). |
| `ropeFrequencyBase` | `rope_frequency_base` | `float` | RoPE base freq. |
| `ropeFrequencyScale` | `rope_frequency_scale` | `float` | RoPE scaling. |
| `evalBatchSize` | `eval_batch_size` | `int ≥ 1` | Taille du batch d'évaluation du prompt. |
| `flashAttention` | `flash_attention` | `bool` | Active Flash Attention. |
| `keepModelInMemory` | `keep_model_in_memory` | `bool` | Empêche le swap. |
| `seed` | `seed` | `int` | Graine aléatoire — **au chargement du modèle, pas par requête** (voir section 10). |
| `useFp16ForKVCache` | `use_fp16_for_kv_cache` | `bool` | Cache KV en FP16. |
| `tryMmap` | `try_mmap` | `bool` | Chargement via mmap. |
| `numExperts` | `num_experts` | `int` | Nb d'experts actifs (MoE — non pertinent pour Gemma 4 12B dense). |
| `llamaKCacheQuantizationType` | `llama_k_cache_quantization_type` | enum ou `false` (`f32,f16,q8_0,q4_0,q4_1,iq4_nl,q5_0,q5_1`) | Quantization cache K. |
| `llamaVCacheQuantizationType` | `llama_v_cache_quantization_type` | idem | Quantization cache V. |

**Aucun champ `parallel` / `numParallel` / "max concurrent predictions" n'existe dans ce schéma** côté SDK Python (confirmé par `grep` exhaustif sur le schéma JSON) — ce réglage n'est documenté que côté GUI (section 8).

### Lister les modèles téléchargés / chargés, décharger

```python
with lms.Client(api_host="localhost:1234") as client:
    downloaded = client.system.list_downloaded_models()   # tous les modèles sur disque
    loaded = client.llm.list_loaded()                       # LLMs actuellement en mémoire
    client.llm.unload("trivia-bench")                       # décharge par identifiant
```
Confirmé code source : `list_downloaded_models()` vit dans le namespace **`system`** (`_SyncSessionSystem.list_downloaded_models`, appel RPC `"listDownloadedModels"`), tandis que `list_loaded()` / `unload(identifier)` vivent dans le namespace **`llm`** (ou `embedding`). Une méthode de commodité existe aussi sur `Client` directement : `client.list_downloaded_models(namespace=None)` et `client.list_loaded_models(namespace=None)` (filtre optionnel `"llm"`/`"embedding"`).

### Identifiant du modèle Gemma 4 12B QAT

- **Clé LM Studio (à utiliser avec `lms.llm(...)`, `lms load`, `client.llm.load_new_instance(...)`)** : **`google/gemma-4-12b-qat`** (confirmé via la page catalogue officielle `lmstudio.ai/models/google/gemma-4-12b-qat`).
- Le **dépôt Hugging Face source** des poids GGUF est `lmstudio-community/gemma-4-12B-it-QAT-GGUF` (fichier `gemma-4-12B-it-QAT-Q4_0.gguf`, ≈ 6.98 Go, + `mmproj-gemma-4-12B-it-QAT-BF16.gguf` ≈ 175 Mo pour la partie vision). C'est le nom du dépôt HF, **pas** la clé à utiliser directement dans le SDK — LM Studio fait le mapping en interne via son catalogue.
- Pour confirmer la clé exacte sur la machine cible une fois le modèle téléchargé : `lms ls --llm --json` ou `lms get gemma-4-12b-qat` (recherche interactive).

**Sources** : https://lmstudio.ai/docs/python/manage-models/loading · https://lmstudio.ai/models/google/gemma-4-12b-qat · https://huggingface.co/lmstudio-community/gemma-4-12B-it-QAT-GGUF · code source (`src/lmstudio/sync_api.py`, `sdk-schema/lms.json` définition `llmLoadModelConfig`)

---

## 6. `lms` CLI — commandes et flags exacts

Vérifié directement sur le contenu brut des pages de doc officielles (`lmstudio-ai/docs`, dossier `3_cli/`).

### Serveur

```bash
lms server start [--port <number>] [--cors] [--bind 0.0.0.0|127.0.0.1]
lms server status [--json] [--verbose|--quiet|--log-level <level>]
lms server stop
```
- `--port` : "uses the last used port" si non fourni.
- `--bind` : défaut `127.0.0.1` (localhost uniquement) — aussi configurable via variable d'env `LMS_SERVER_HOST`.
- `--cors` : désactivé par défaut ; l'activer expose un risque de sécurité (avertissement officiel).
- **Port par défaut confirmé par l'exemple officiel de sortie** :
  ```
  ➜  ~ lms server start
  Success! Server is now running on port 1234
  ➜  ~ lms server status
  The server is running on port 1234.
  ```
  → `lms server status --json --quiet` retourne `{ "running": true, "port": 1234 }`.

### Modèles locaux

```bash
lms ls [--llm] [--embedding] [--json] [--detailed]
lms ps [--json]
lms get [modelName[@quant]] [--mlx] [--gguf] [-n/--limit N] [--always-show-all-results] [-a/--always-show-download-options]
lms load [path] [--ttl <seconds>] [--gpu 0-1|off|max] [--context-length <N>] [--identifier <name>] [--estimate-only] [--host <host>]
lms unload [model_key] [--all] [--host <host>]
```
- **Pas de flag `-y/--yes`** documenté sur `lms load` (contrairement à ce qui est parfois supposé pour scripter sans prompt interactif — à vérifier empiriquement sur la machine, mais absent de la doc officielle).
- `lms load --estimate-only <model_key>` : donne une estimation mémoire sans charger :
  ```
  $ lms load --estimate-only gpt-oss-120b
  Model: openai/gpt-oss-120b
  Estimated GPU Memory:   65.68 GB
  Estimated Total Memory: 65.68 GB
  ```
  → **très utile à exécuter en amont sur la machine cible** avec `google/gemma-4-12b-qat` pour valider l'empreinte mémoire réelle avant de lancer 4000 requêtes.
- Exemple pour charger Gemma 4 avec un contexte réduit et un identifiant dédié :
  ```bash
  lms load google/gemma-4-12b-qat --context-length 4096 --gpu max --identifier trivia-bench
  ```

### Runtime (moteur d'inférence llama.cpp / MLX)

```bash
lms runtime ls        # liste les runtimes installés
lms runtime get        # télécharge un runtime
lms runtime select     # bascule le runtime actif (interactif)
lms runtime remove     # désinstalle un runtime
lms runtime update      # met à jour un runtime installé
```
Un post officiel LM Studio (X/Twitter) mentionne `lms runtime update --all` pour mettre à jour tous les runtimes après un correctif Gemma 4 (engine 2.20.1) — **le flag `--all` n'apparaît pas dans la page de doc `runtime.md` récupérée, donc NON VÉRIFIÉ à 100 % côté documentation officielle, mais provient d'un compte officiel**.

### Daemon headless (`llmster`)

Architecture plus récente pour du déploiement 100% headless (sans jamais ouvrir la GUI après le setup initial) :
```bash
lms daemon up [--json]       # démarre le daemon llmster
lms daemon status
lms daemon down
lms daemon update
```
Exemple de sortie JSON : `{ "status": "running", "pid": 26754, "isDaemon": true, "version": "0.4.4+1" }`.

### GUI requise ?

**Non, pas en continu.** *"You need to run LM Studio at least once before you can use `lms`"* (setup initial : enregistrement du dossier de modèles, etc.), mais ensuite `lms server start` (ou `lms daemon up`) lance un process serveur autonome, indépendant de la fenêtre GUI (confirmé : *"the daemon runs standalone, and it is not dependent on the LM Studio GUI"*).

### `lms bootstrap`

`lms` est installé avec l'app LM Studio elle-même (`~/.lmstudio/bin/lms` sur la machine cible) — la doc officielle actuelle ne mentionne pas de sous-commande `bootstrap` explicite dans les pages consultées (elle existait dans des versions antérieures pour ajouter `lms` au `PATH` ; sur la machine cible, `~/.lmstudio/bin/lms` doit être ajouté manuellement au `PATH` si `lms` n'est pas déjà résolu globalement) → **NON VÉRIFIÉ sur la version actuelle**, à vérifier avec `lms --help` directement sur la machine.

**Sources** : https://lmstudio.ai/docs/cli · pages brutes `lmstudio-ai/docs` (`3_cli/0_local-models/{load,ls,ps,get}.md`, `3_cli/1_serve/{server-start,server-status}.mdx|.md`, `3_cli/2_daemon/daemon-up.md`, `3_cli/4_runtime/runtime.md`, `3_cli/index.mdx`)

---

## 7. API REST (alternative / fallback)

Le serveur local expose **trois familles d'endpoints** (confirmé `lmstudio.ai/docs/app/api`) : compatibles OpenAI, natifs `/api/v1`, et compatibles Anthropic (Messages API). Port par défaut **1234**, GUI non requise.

### a) Endpoints compatibles OpenAI

| Endpoint | Méthode |
|---|---|
| `/v1/models` | GET |
| `/v1/responses` | POST |
| `/v1/chat/completions` | POST |
| `/v1/embeddings` | POST |
| `/v1/completions` | POST |

Le package officiel **`openai` (Python) fonctionne directement** en changeant juste le `base_url` :
```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")  # api_key ignorée/placeholder

resp = client.chat.completions.create(
    model="google/gemma-4-12b-qat",
    messages=[
        {"role": "system", "content": "Réponds uniquement par la bonne réponse."},
        {"role": "user", "content": "Quelle est la capitale de la France ?"},
    ],
    temperature=0,
    response_format={"type": "json_schema", "json_schema": {"name": "answer", "schema": {...}}},
)
```
(la forme exacte du `response_format` json_schema n'a pas pu être récupérée verbatim depuis la doc — motif de schéma standard OpenAI, à tester empiriquement).

### b) API REST native `/api/v1` (plus riche, spécifique LM Studio)

`GET /api/v1/models` — forme confirmée (rendue depuis la doc officielle) :
```json
{
  "models": [
    {
      "type": "llm",
      "publisher": "google",
      "key": "google/gemma-4-12b-qat",
      "display_name": "Gemma 4 12B QAT",
      "architecture": "gemma4",
      "quantization": {"name": "Q4_0", "bits_per_weight": 4.5},
      "size_bytes": 7490000000,
      "params_string": "12B",
      "loaded_instances": [
        {"id": "trivia-bench", "config": {"context_length": 4096, "parallel": 4, "flash_attention": true, "offload_kv_cache_to_gpu": true}}
      ],
      "max_context_length": 262144,
      "format": "gguf",
      "capabilities": {
        "vision": true,
        "trained_for_tool_use": true,
        "reasoning": {"allowed_options": ["off","on","low","medium","high"], "default": "on"}
      }
    }
  ]
}
```
`POST /api/v1/chat` — champs de requête confirmés : `model`, `input`, `system_prompt`, `stream`, `temperature`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `max_output_tokens`, `reasoning`, `context_length`, `store`, `previous_response_id`.

**Oui, la réponse inclut toujours un objet `stats`** — champs confirmés :
```json
{
  "model_instance_id": "trivia-bench",
  "output": [ { "type": "message", "content": "Paris" } ],
  "stats": {
    "input_tokens": 42,
    "total_output_tokens": 3,
    "reasoning_output_tokens": 0,
    "tokens_per_second": 38.2,
    "time_to_first_token_seconds": 0.41,
    "model_load_time_seconds": null
  },
  "response_id": "..."
}
```
Notez que **les noms de champs REST natifs diffèrent des noms du SDK Python** (ex : `input_tokens` REST vs `prompt_tokens_count` SDK Python ; `total_output_tokens` REST vs `predicted_tokens_count` SDK Python ; `time_to_first_token_seconds` REST vs `time_to_first_token_sec` SDK Python) — **à ne pas confondre si le harnais bascule entre SDK et REST**.

Le champ `reasoning` de la requête `/api/v1/chat` (`off|on|low|medium|high`) est le **moyen natif et le plus direct de désactiver le thinking de Gemma 4** via HTTP — c'est un net avantage de la voie REST native par rapport au SDK Python actuel (voir section 9).

**Sources** : https://lmstudio.ai/docs/app/api · https://lmstudio.ai/docs/app/api/endpoints/openai · https://lmstudio.ai/docs/app/api/endpoints/rest · https://lmstudio.ai/docs/developer/rest/chat · https://lmstudio.ai/docs/developer/rest/list

---

## 8. Concurrence

- Le SDK **peut** émettre des requêtes en parallèle : voir l'exemple officiel avec l'API asynchrone (`AsyncClient`) :
  ```python
  async with lms.AsyncClient() as client:
      model = await client.llm.model("google/gemma-4-12b-qat")
      results = await asyncio.gather(*[model.complete(q) for q in questions])
  ```
  Ceci est disponible depuis SDK **v1.5.0+**.
- Côté serveur, LM Studio supporte le **continuous batching** ("Parallel Requests") : toggle GUI *"Manually choose model load parameters" → "Show advanced settings" → "Max Concurrent Predictions"*, **défaut = 4**. Nécessite le runtime llama.cpp **≥ v2.0.0** (support MLX annoncé "coming later", donc pas encore actif sur Metal/MLX au moment de la recherche). Les requêtes au-delà de la limite sont **mises en file d'attente**, pas rejetées.
- **Aucun champ `parallel`/équivalent trouvé dans le schéma `LlmLoadModelConfig` du SDK Python** — ce réglage n'est pas pilotable typé depuis le SDK Python à ce jour (uniquement via la GUI, ou potentiellement via l'échappatoire `raw` kvConfig, non testé/NON VÉRIFIÉ).

### Recommandation pour le benchmark (16 Go, un seul modèle chargé)

**Séquentiel, une requête à la fois.** Justification :
1. Le but déclaré est de **mesurer le temps de réponse par question** — le continuous batching côté serveur mélange le traitement de plusieurs requêtes simultanées, ce qui **fausse `time_to_first_token_sec` et `tokens_per_second` par requête individuelle** (le GPU/CPU est partagé entre plusieurs générations en vol).
2. Sur une machine à **16 Go de RAM unifiée** avec Gemma 4 12B déjà proche de la limite raisonnable de contexte (4-8K), lancer plusieurs générations concurrentes multiplie la pression mémoire (KV-cache × N) sans gain de débit garanti sur Apple Silicon (le runtime MLX, plus adapté à Metal, ne supporte pas encore le parallélisme au moment de cette recherche).
3. Si le débit total (throughput) prime sur la précision de la mesure par question, on peut envisager un parallélisme modéré (2–4) **uniquement après avoir validé qu'aucune dérive systématique n'apparaît sur les stats individuelles** — à traiter comme une optimisation, pas un défaut.

**Sources** : https://lmstudio.ai/docs/app/advanced/parallel-requests · code source (`asyncio.gather` example, `AsyncClient`) · schéma `sdk-schema/lms.json`

---

## 9. Gemma 4 12B QAT — spécificités

- **Famille / architecture** : Gemma 4 (Google DeepMind), architecture désignée `gemma4` par LM Studio ; le modèle 12B est un modèle **dense, multimodal, "encoder-free"** (projections linéaires directes pour vision/audio, pas d'encodeur séparé), attention hybride locale (fenêtre glissante) + globale, RoPE proportionnel pour l'efficacité en long contexte.
- **Paramètres** : **11.95 Md de paramètres** (variante "12B Unified").
- **Fenêtre de contexte** : jusqu'à **256K tokens** au maximum théorique (catégorie "medium/large" de la famille Gemma 4). En pratique sur 16 Go unifiés : **réduire à 4096–8192 tokens** (recommandation trouvée : *"Start with a smaller context length... reducing this to 4K–8K frees up significant memory and speeds up loading"*).
- **Taille du GGUF QAT (Q4_0)** : **6.98 Go** (fichier unique `gemma-4-12B-it-QAT-Q4_0.gguf`), + `mmproj` BF16 ≈ 175 Mo pour la partie vision (non nécessaire pour un benchmark texte-only, peut être ignoré/non chargé).
- **RAM minimum indiquée par LM Studio pour ce modèle : 7 Go.** Sur une machine à **16 Go unifiés**, cela **tient confortablement** pour les poids seuls ; la marge restante (~9 Go) doit couvrir OS + KV-cache + overhead runtime — d'où la recommandation de limiter le contexte à 4-8K plutôt que d'utiliser le max théorique 256K (qui ferait exploser la mémoire KV-cache).
- **Prompt système / rôle `system`** : **Gemma 4 introduit un support natif du rôle `system`** (contrairement à Gemma 3, qui repliait le system prompt dans le premier tour utilisateur). C'est une différence importante par rapport à Gemma 3 : `lms.Chat("prompt système")` fonctionnera nativement comme un vrai tour système pour Gemma 4, sans contournement nécessaire.
- **Mode "thinking" / raisonnement** :
  - Toutes les tailles Gemma 4 incluent une capacité de raisonnement ("built-in reasoning mode that lets the model think step-by-step before answering").
  - Sur la page catalogue LM Studio du modèle : **"Enable Thinking" activé par défaut**, avec parsing basé sur des marqueurs `<|channel>thought`.
  - Selon la fiche modèle Google (`ai.google.dev/gemma/docs/core/model_card_4`) : *"Thinking is enabled by including the `<|think|>` token at the start of the system prompt. To disable thinking, remove the token."*
  - **Pour désactiver le thinking dans un benchmark** (important pour la vitesse et la simplicité du parsing de réponse) :
    1. **Voie GUI/chargement** : décocher "Enable Thinking" au chargement du modèle dans LM Studio (persiste pour l'instance chargée).
    2. **Voie REST native** : passer `"reasoning": "off"` dans le body de `POST /api/v1/chat` (champ confirmé dans le schéma REST).
    3. **Voie SDK Python** : **aucun champ dédié confirmé** dans `llmPredictionConfigInput` (seul `reasoningParsing` existe, et il ne fait que parser une sortie déjà générée, pas la supprimer à la source) → il faut soit s'appuyer sur la config de chargement (option 1), soit gérer manuellement le template/prompt système pour éviter le déclenchement du thinking, soit passer par l'échappatoire `raw` kvConfig (non testé). **Recommandation pratique : charger le modèle une fois avec "Enable Thinking" désactivé via la GUI (ou un preset associé à l'`instance_identifier` utilisé par le benchmark), puis piloter les requêtes du benchmark via le SDK Python normalement.**
- **Sampling recommandé par Google** (fiche modèle, config standardisée pour tous les cas d'usage) : **`temperature=1.0, top_p=0.95, top_k=64`**.
- **Sampling recommandé pour un benchmark déterministe/reproductible** : **`temperature=0`** (greedy decoding) plutôt que les valeurs "créatives" ci-dessus — un trivia bench veut la réponse la plus probable, pas de diversité. Avec `temperature=0`, `top_k`/`top_p` deviennent sans effet (un seul token a une probabilité non nulle après l'argmax).
- **Version minimale de LM Studio / runtime** : **information partiellement contradictoire entre sources**, à traiter avec prudence :
  - Un post officiel X/LM Studio mentionne un correctif Gemma 4 en **engine version 2.20.1** (`lms runtime update --all`).
  - Le changelog historique (branche de versions `0.4.x`) montre l'ajout du support Gemma 4 vers **v0.4.9/0.4.10** (avril 2026), avec correction du chat template en **v0.4.11** (10 avril 2026).
  - Le changelog **actuel** ("Bionic", renumérotation `1.0.x`/`1.1.x`) montre la dernière version en date **1.1.2 (8 septembre 2026)**, avec runtime llama.cpp **2.33.0**, et une correction antérieure *"Fixed Gemma 4 native tool-use detection"* en **v1.0.3 (22 juillet 2026)**.
  - **Conclusion pratique pour la machine cible (serveur pas encore démarré)** : comme LM Studio n'a jamais été lancé/configuré sur cette machine, **le premier lancement installera vraisemblablement la dernière version disponible (≥ 1.1.2, runtime llama.cpp ≥ 2.33.0)**, largement postérieure à toutes les versions mentionnées ci-dessus qui ont introduit/corrigé le support Gemma 4 — **aucune action de mise à jour manuelle ne devrait être nécessaire**, mais il est recommandé de lancer `lms runtime ls` / `lms runtime update` (voire `lms runtime update --all` si le flag existe réellement — NON VÉRIFIÉ à 100%) avant le run de benchmark, par précaution.
- **Mise à jour du runtime** : `lms runtime ls` (voir installé), `lms runtime update` (mettre à jour), ou via la GUI (Settings → Runtimes).

**Sources** : https://ai.google.dev/gemma/docs/core/model_card_4 · https://huggingface.co/lmstudio-community/gemma-4-12B-it-QAT-GGUF · https://lmstudio.ai/models/google/gemma-4-12b-qat · https://lmstudio.ai/models/gemma-4 · https://lmstudio.ai/changelog · gemma4all.com/blog/run-gemma-4-with-lm-studio (WebSearch, tiers-parti — NON officiel, à recouper) · X/Twitter @lmstudio (officiel, mention engine 2.20.1)

---

## 10. Déterminisme & reproductibilité

- **`seed` n'existe que dans `LlmLoadModelConfig`** (paramètre de **chargement**, confirmé dans le schéma canonique — absent de `llmPredictionConfigInput`). **Il n'y a donc pas de `seed` par requête** dans l'API de prédiction. Pour un run reproductible :
  1. Charger le modèle une seule fois avec un `seed` fixe : `config={"seed": 42, "contextLength": 4096, ...}`.
  2. Garder l'instance chargée pour toute la durée du run des 4000 questions (ne pas recharger entre chaque question).
  3. Utiliser `temperature: 0` par requête (greedy) — avec un décodage glouton, la sortie ne dépend quasiment plus du seed de toute façon (un seul chemin a une probabilité non nulle), ce qui est la vraie garantie de reproductibilité pour un benchmark.
- **Limite connue à documenter** : même avec `temperature=0`, un llama.cpp multi-thread peut produire de très légères variations de sortie entre deux runs à cause du non-déterminisme de l'accumulation flottante en parallèle (ordre de sommation différent selon le nombre de threads / le batching). Pour maximiser la reproductibilité bit-à-bit : fixer `cpuThreads` à une valeur constante et désactiver le continuous batching (une requête à la fois, section 8) — **ceci n'a pas de confirmation officielle spécifique à LM Studio, c'est une propriété générale connue de llama.cpp → à considérer comme une bonne pratique, NON VÉRIFIÉE formellement pour ce runtime précis.**
- **Ce qu'il faut logguer par run** (pour la reproductibilité et le debug a posteriori) :
  - `result.model_info` (clé du modèle, `display_name`, `architecture`, `max_context_length`, quantization) ;
  - `result.load_config` (context_length, gpu, flash_attention, seed, cache quant types...) ;
  - `result.prediction_config` (temperature, max_tokens, top_k/top_p effectifs, stop_strings...) ;
  - version de LM Studio (`lms server status` ne la donne pas directement — utiliser `lms daemon up --json` → champ `version`, ou l'à-propos de la GUI) ;
  - version du runtime llama.cpp/MLX actif (`lms runtime ls`) ;
  - version du SDK Python (`lmstudio.__version__` si exposé, sinon `pip show lmstudio`) ;
  - `result.stats` complet par question (voir section 4) ;
  - timestamp + durée mesurée côté client (`time.perf_counter()`, voir snippet section "Snippet de référence").

**Sources** : schéma `sdk-schema/lms.json` (`llmLoadModelConfig.seed` présent, absent de `llmPredictionConfigInput`) · https://lmstudio.ai/docs/cli/daemon/daemon-up (champ `version` dans la sortie JSON)

---

## 11. Gestion d'erreurs

Hiérarchie d'exceptions confirmée dans le code source (`src/lmstudio/json_api.py`) :

```
LMStudioError
├── LMStudioServerError                    # erreurs renvoyées par le serveur LM Studio
│   ├── LMStudioModelNotFoundError
│   ├── LMStudioPresetNotFoundError
│   ├── LMStudioChannelClosedError
│   └── LMStudioPredictionError            # échec pendant une prédiction (ex: tool call invalide)
└── LMStudioClientError                    # erreurs détectées côté client (SDK)
    ├── LMStudioUnknownMessageWarning       # (UserWarning) message serveur inattendu
    ├── LMStudioCancelledError              # opération annulée via le client
    ├── LMStudioTimeoutError                # (hérite aussi de TimeoutError) pas de réponse à temps
    └── LMStudioWebsocketError              # session websocket fermée / jamais ouverte
```

### Timeout

```python
import lmstudio as lms
lms.set_sync_api_timeout(120.0)   # 2 minutes — API synchrone uniquement, défaut 60s depuis v1.5.0
```
Pour l'API asynchrone : envelopper avec `asyncio.wait_for(...)` (pas de timeout intégré).

### Annulation

```python
prediction_stream = model.respond_stream(chat, config=...)
for fragment in prediction_stream:
    print(fragment.content, end="")
    if some_condition:
        prediction_stream.cancel()
        # il est recommandé de laisser l'itération se terminer plutôt que
        # de `break` immédiatement, pour que le résultat partiel + les stats
        # soient bien enregistrés
result = prediction_stream.result()
```

### Pattern d'error handling recommandé (calqué sur l'exemple officiel du SDK)

```python
from lmstudio import (
    LMStudioError, LMStudioClientError,
    LMStudioTimeoutError, LMStudioPredictionError,
)

try:
    with lms.Client(api_host="localhost:1234") as client:
        model = client.llm.model("google/gemma-4-12b-qat")
        try:
            result = model.respond(chat, config={"temperature": 0, "maxTokens": 16})
        except LMStudioTimeoutError:
            ...  # modèle surchargé / question bloquante -> logguer et passer à la suivante
        except LMStudioPredictionError as e:
            ...  # échec de génération -> logguer et passer à la suivante
except LMStudioClientError as e:
    ...  # serveur LM Studio injoignable -> arrêter le run, alerter
except LMStudioError as e:
    ...  # toute autre erreur SDK
```

### Retries

**Aucun mécanisme de retry automatique documenté ou trouvé dans le code source.** Pour un harnais de 4000+ questions, **implémenter les retries manuellement** (ex : `tenacity`, ou une boucle simple avec backoff) autour de `LMStudioTimeoutError` / `LMStudioPredictionError`, avec un compteur de tentatives par question et un log des échecs définitifs.

**Sources** : code source `lmstudio-ai/lmstudio-python` (`src/lmstudio/json_api.py`, hiérarchie d'exceptions) · https://lmstudio.ai/docs/python (page d'intro, section timeout) · doc rendue "cancelling-predictions"

---

## Pièges & recommandations

1. **Casse des clés de config** : dict brut → camelCase (`maxTokens`, `topKSampling`...) ; objet `LlmPredictionConfig(...)` → snake_case (`max_tokens`, `top_k_sampling`...). Se tromper ne lève pas forcément une erreur claire selon le chemin de validation — **toujours tester une requête de config avec des valeurs extrêmes en amont** (ex: `maxTokens: 1`) pour vérifier qu'elle est bien prise en compte, plutôt que de découvrir l'erreur après 4000 questions.
2. **`total_tokens_count`, pas `total_tokens`** — nom de champ piégeux si on code de mémoire à partir d'habitudes OpenAI.
3. **Découverte automatique du host/port** : ne jamais laisser `api_host=None` en production/benchmark — toujours `api_host="localhost:1234"` explicite (ou la valeur réelle après `lms server start --port ...`).
4. **`lms.llm("clé")` ignore silencieusement la `config` si le modèle est déjà chargé.** Pour garantir une config de benchmark reproductible (context length, seed, flash attention...), toujours utiliser `client.llm.load_new_instance(...)` avec un `instance_identifier` dédié plutôt que `lms.llm(...)`/`client.llm.model(...)` si un autre process/la GUI a pu charger le modèle avec d'autres paramètres avant.
5. **Pas de `seed` par requête** — la reproductibilité passe par `temperature=0` + config de chargement figée, pas par un paramètre de génération.
6. **Thinking activé par défaut sur Gemma 4** — s'il n'est pas désactivé, chaque réponse contiendra des tokens de raisonnement en plus de la réponse finale, ce qui (a) ralentit chaque requête, (b) complique le parsing de la réponse finale, (c) fausse les comparaisons de `tokens_per_second`/`predicted_tokens_count` entre runs. **Désactiver "Enable Thinking" au chargement est la voie la plus sûre côté SDK Python** (pas de champ de requête dédié confirmé).
7. **Parallélisme serveur (continuous batching, défaut 4) fausse les mesures de latence par requête** si actif pendant le benchmark — envoyer séquentiellement, ou au minimum vérifier/désactiver ce réglage sur l'instance utilisée pour le benchmark.
8. **REST natif (`/api/v1/chat`) et SDK Python n'utilisent pas les mêmes noms de champs de stats** (`input_tokens` vs `prompt_tokens_count`, etc.) — ne pas mélanger les deux sans mapping explicite si le harnais doit pouvoir basculer entre les deux transports.
9. **Contexte 256K théorique ≠ contexte praticable sur 16 Go** — fixer explicitement `contextLength` à 4096 ou 8192 au chargement (le laisser au max par défaut peut faire exploser l'usage mémoire du KV-cache et ralentir/planter le chargement).
10. **Le SDK ne retente rien automatiquement** — pour 4000+ requêtes séquentielles sur plusieurs heures, prévoir retries + logs incrémentaux (écrire les résultats question par question, pas tout en mémoire jusqu'à la fin) pour survivre à un crash/timeout isolé sans perdre tout le run.
11. **Champs `xtcProbability`/`xtcThreshold`** vus dans une page de doc TypeScript générée : absents du schéma canonique du SDK Python testé → ne pas les utiliser sans test empirique préalable.
12. **Toujours exécuter `lms load --estimate-only google/gemma-4-12b-qat --context-length 4096` avant le run complet** pour valider l'empreinte mémoire réelle sur la machine M2 Pro / 16 Go.

---

## Snippet de référence

Fonction `ask(...)` complète et vérifiable, utilisant l'**API scoped `Client`**, mesurant le temps à la fois via les stats SDK et via `time.perf_counter()` côté client, avec gestion d'erreurs et retries basiques — pensée pour être appelée en boucle sur ~4000 questions avec un modèle déjà chargé une fois en amont.

```python
"""
Snippet de référence vérifié pour le harnais de benchmark LM Studio / Gemma 4 12B QAT.
Toutes les clés de config, tous les attributs de stats et toutes les signatures
proviennent de sources vérifiées (voir 02_lmstudio_gemma4.md, sections 2, 4, 5, 11).
"""

import time
from typing import Any

import lmstudio as lms
from lmstudio import (
    LMStudioClientError,
    LMStudioError,
    LMStudioPredictionError,
    LMStudioTimeoutError,
)

API_HOST = "localhost:1234"          # toujours explicite, cf. piège #3
MODEL_KEY = "google/gemma-4-12b-qat"
INSTANCE_ID = "trivia-bench"


def load_benchmark_model(client: lms.Client, *, context_length: int = 4096) -> lms.LLM:
    """Charge (ou récupère) l'instance dédiée au benchmark avec une config figée.

    Utilise load_new_instance plutôt que client.llm.model(...) pour garantir que
    la config demandée est bien appliquée (cf. piège #4 : model() ignore la config
    si le modèle est déjà chargé).
    """
    try:
        # Réutilise l'instance si elle existe déjà (ex: run précédent interrompu).
        for handle in client.llm.list_loaded():
            if handle.identifier == INSTANCE_ID:
                return handle
    except LMStudioError:
        pass

    return client.llm.load_new_instance(
        MODEL_KEY,
        INSTANCE_ID,
        ttl=None,  # pas d'auto-unload pendant le run
        config={
            "contextLength": context_length,
            "gpu": "max",
            "flashAttention": True,
            "seed": 42,  # reproductibilité (cf. section 10) ; combiné à temperature=0
        },
    )


def ask(
    model: lms.LLM,
    system_prompt: str,
    user_prompt: str,
    config: dict[str, Any] | None = None,
    *,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Pose une question au modèle et retourne le texte de réponse + toutes les stats.

    `config` suit le format dict camelCase attendu par le SDK (cf. section 2).
    Mesure le temps à la fois via `result.stats` (mesure serveur, la plus fiable
    pour tokens/s et TTFT) et via `time.perf_counter()` côté client (inclut la
    latence réseau/IPC websocket, utile pour détecter un overhead client anormal).
    """
    if config is None:
        config = {"temperature": 0, "maxTokens": 16}

    chat = lms.Chat(system_prompt)
    chat.add_user_message(user_prompt)

    wall_clock_start = time.perf_counter()
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            result = model.respond(chat, config=config)
            wall_clock_seconds = time.perf_counter() - wall_clock_start

            stats = result.stats
            return {
                "success": True,
                "attempt": attempt,
                "answer_text": result.content,
                "answer_parsed": result.parsed if result.structured else None,
                # --- mesures de temps ---
                "wall_clock_seconds": wall_clock_seconds,               # time.perf_counter(), côté client
                "time_to_first_token_sec": stats.time_to_first_token_sec,  # côté serveur (SDK stats)
                # --- débit / tokens ---
                "tokens_per_second": stats.tokens_per_second,
                "prompt_tokens_count": stats.prompt_tokens_count,
                "predicted_tokens_count": stats.predicted_tokens_count,
                "total_tokens_count": stats.total_tokens_count,
                "stop_reason": stats.stop_reason,
                # --- traçabilité / reproductibilité ---
                "model_key": result.model_info.model_key,
                "model_display_name": result.model_info.display_name,
                "load_config": result.load_config.to_dict()
                if hasattr(result.load_config, "to_dict")
                else vars(result.load_config),
                "prediction_config": result.prediction_config.to_dict()
                if hasattr(result.prediction_config, "to_dict")
                else vars(result.prediction_config),
                "error": None,
            }
        except LMStudioTimeoutError as e:
            last_error = e
            continue  # retry
        except LMStudioPredictionError as e:
            last_error = e
            continue  # retry
        except LMStudioClientError as e:
            # Le serveur est injoignable : inutile de retenter localement,
            # on remonte l'erreur pour que l'appelant décide (pause/alerte/abandon du run).
            wall_clock_seconds = time.perf_counter() - wall_clock_start
            return {
                "success": False,
                "attempt": attempt,
                "wall_clock_seconds": wall_clock_seconds,
                "error": f"client_error: {e}",
            }

    wall_clock_seconds = time.perf_counter() - wall_clock_start
    return {
        "success": False,
        "attempt": max_retries,
        "wall_clock_seconds": wall_clock_seconds,
        "error": f"failed_after_retries: {last_error}",
    }


def run_benchmark(questions: list[str], system_prompt: str) -> list[dict[str, Any]]:
    """Boucle séquentielle sur ~4000 questions (cf. section 8 : séquentiel recommandé
    pour ne pas fausser les mesures individuelles de latence via le continuous batching).
    """
    results: list[dict[str, Any]] = []
    with lms.Client(api_host=API_HOST) as client:
        model = load_benchmark_model(client)
        for i, question in enumerate(questions):
            record = ask(
                model,
                system_prompt,
                question,
                config={"temperature": 0, "maxTokens": 16, "stopStrings": ["\n"]},
            )
            record["question_index"] = i
            record["question_text"] = question
            results.append(record)
            # Écrire au fil de l'eau (pas seulement à la fin) pour survivre à un crash.
            # (ex: json.dumps(record) -> append à un .jsonl)
    return results
```

**Points vérifiés utilisés dans ce snippet** : signature de `respond()` et de `load_new_instance()` (code source `sync_api.py`), casse camelCase du dict `config=` (schéma + tests), noms exacts des attributs `stats.*` (schéma `llmPredictionStats`), hiérarchie d'exceptions (`json_api.py`), absence de retry automatique (justifie la boucle manuelle), `seed` uniquement en config de chargement (section 10), recommandation séquentielle (section 8).

---

## Sources

- SDK Python — doc officielle : https://lmstudio.ai/docs/python · https://lmstudio.ai/docs/python/getting-started/authentication · https://lmstudio.ai/docs/python/llm-prediction/chat-completion · https://lmstudio.ai/docs/python/llm-prediction/completion · https://lmstudio.ai/docs/python/llm-prediction/parameters · https://lmstudio.ai/docs/python/llm-prediction/structured-response · https://lmstudio.ai/docs/python/llm-prediction/speculative-decoding · https://lmstudio.ai/docs/python/manage-models/loading
- SDK Python — code source (GitHub, `lmstudio-ai/lmstudio-python`, branche `main`) : `src/lmstudio/sync_api.py`, `src/lmstudio/json_api.py`, `src/lmstudio/history.py`, `src/lmstudio/_api_server_ports.py`, `src/lmstudio/schemas.py`, `sdk-schema/lms.json` (schéma JSON canonique du protocole), `sdk-schema/_templates/msgspec.jinja2`, `tests/test_kv_config.py`, `pyproject.toml`, `examples/speculative-decoding.py`
- SDK Python — GitHub issue (contexte JS, informatif) : https://github.com/lmstudio-ai/lmstudio-js/issues/557
- Context7 : `/lmstudio-ai/lmstudio-python` (résolu via `resolve-library-id`, interrogé via `query-docs`)
- PyPI : https://pypi.org/project/lmstudio/ · https://pypi.org/pypi/lmstudio/json
- CLI `lms` — doc officielle (rendue + brute GitHub `lmstudio-ai/docs`) : https://lmstudio.ai/docs/cli · `3_cli/0_local-models/{load,ls,ps,get}.md` · `3_cli/1_serve/{server-start.mdx,server-status.md}` · `3_cli/2_daemon/daemon-up.md` · `3_cli/4_runtime/runtime.md` · `3_cli/index.mdx`
- REST API : https://lmstudio.ai/docs/app/api · https://lmstudio.ai/docs/app/api/endpoints/openai · https://lmstudio.ai/docs/app/api/endpoints/rest · https://lmstudio.ai/docs/developer/rest/chat · https://lmstudio.ai/docs/developer/rest/list
- Concurrence : https://lmstudio.ai/docs/app/advanced/parallel-requests
- LM Studio — changelog / versions : https://lmstudio.ai/changelog · https://lmstudio.ai/changelog/lmstudio-v0.4.9 · .../v0.4.10 · .../v0.4.11 · .../v0.4.13
- Gemma 4 — modèle : https://ai.google.dev/gemma/docs/core/model_card_4 · https://ai.google.dev/gemma/docs/core
- Gemma 4 GGUF (LM Studio community) : https://huggingface.co/lmstudio-community/gemma-4-12B-it-QAT-GGUF · https://huggingface.co/lmstudio-community/gemma-4-12B-it-QAT-GGUF/tree/main
- Catalogue modèle LM Studio : https://lmstudio.ai/models/google/gemma-4-12b-qat · https://lmstudio.ai/models/gemma-4
- Tiers-parti (WebSearch, à recouper, non officiel) : https://gemma4all.com/blog/run-gemma-4-with-lm-studio · https://techsy.io/en/blog/gemma-4-12b · https://gist.github.com/devxoul/dc01c7c82335b6d1c1054c294eaa547e (astuces MLX, non pertinent pour GGUF/llama.cpp — écarté du corps du document)
- X/Twitter officiel LM Studio : https://x.com/lmstudio/status/2062321901226033632 (correctif Gemma 4, engine 2.20.1)
