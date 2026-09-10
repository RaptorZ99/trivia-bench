# Méthodologie de benchmark — LLM local sur questions de trivia (OpenTDB)

Date de la recherche : **2026-09-10**
Modèle cible : **Gemma 4 12B QAT** via **LM Studio**, température **0** (greedy decoding)
Jeu de questions : OpenTDB, QCM (4 options) + vrai/faux — voir `01_opentdb.md` pour les détails API (pool "verified" = 5 298 questions au 2026-09-10, pas d'ID natif, entités HTML par défaut)
Stack projet déjà arrêtée : `uv`, `polars`, `duckdb`, `dbt-core` + `dbt-duckdb`, `pydantic` v2, `rapidfuzz`, `typer`, `httpx`+`tenacity` — voir `05_python_tooling.md`

Ce document est écrit pour qu'un ingénieur puisse concevoir les variantes de prompt, la logique de notation des réponses et l'analyse statistique du rapport de benchmark **sans avoir à refaire la recherche**. Chaque affirmation factuelle est sourcée ; ce qui n'a pas pu être vérifié depuis une source primaire est marqué **NON VÉRIFIÉ**.

---

## Résumé exécutif

1. **5 variantes de prompt** à benchmarker : V1 (naïf, texte libre, sans options), V2 (QCM, lettre seule), V3 (style *simple-evals* : system + contrainte explicite + cue `Answer:`), V4 (few-shot fixe à 2 exemples), V5 (JSON structuré via decoding contraint) — chacune déclinée en variante booléenne (True/False) pour les questions `type=boolean`.
2. **Shuffle déterministe** des options par question : seed = `sha256(question_id)` (jamais le `hash()` builtin Python, randomisé par process depuis PEP 456) — même ordre pour toutes les variantes/modèles, `options_order` et `correct_letter` stockés en couche silver. Le biais de position en QCM est documenté (Zheng et al. 2023/2024, ICLR Spotlight, arxiv.org/abs/2309.03882).
3. **Grading déterministe** en arbre de décision : extraction lettre/JSON → exact → fuzzy (rapidfuzz ≥ 90) → contains (avec garde anti-négation) → wrong → unparseable. `grade` (enum) est **séparé** de `ai_correct` (bool **nullable**) pour distinguer échec de format (instruction-following) et échec de connaissance.
4. `ai_correct = NULL` quand `grade = unparseable` — exclu de l'accuracy stricte, mais compté dans le *unparseable rate*, métrique de robustesse de format à part entière.
5. Température 0 ne suffit pas : il faut aussi neutraliser `top_k`, `top_p`, `min_p`, `typical_p`, et surtout **`repeat_penalty`** (défaut llama.cpp = 1.1, **pas neutre**), et fixer un `seed`. La reproductibilité bit-exacte n'est **pas garantie** même ainsi sur GPU (issues llama.cpp #10197, #7052, #4458).
6. JSON structuré (V5) : la littérature est partagée. Tam et al. 2024 (*"Let Me Speak Freely?"*, EMNLP Industry) documente une dégradation du raisonnement sous contrainte de format stricte ; la réfutation de dottxt (créateurs d'`outlines`) montre que l'effet vient surtout de l'**ordre des champs du schéma** (réponse forcée avant raisonnement) plutôt que de la contrainte elle-même → mettre `reasoning` avant `answer` si on veut préserver un éventuel CoT.
7. Statistiques à rapporter systématiquement : **intervalle de Wilson** (pas l'approximation normale) pour toute proportion ; **test de McNemar** (apparié) pour comparer deux variantes sur les mêmes questions ; **bootstrap apparié** pour l'IC de la différence ; accuracy **au-dessus du hasard** (25 % QCM 4 options, 50 % booléen) plutôt que l'accuracy brute.
8. Règle de pouce taille d'échantillon : `n ≈ p(1-p)·(z/E)²` → pour ±10 points de marge à 95 %, n≈97 par catégorie ; en dessous, calculer quand même l'IC de Wilson (valide à petit n) mais **flaguer la catégorie comme non conclusive**.
9. Temps de réponse : exclure le 1er appel (warm-up), exécution **strictement séquentielle**, rapporter médiane/p90/p95 (pas seulement la moyenne), et normaliser par token généré (`response_time / tokens_predicted`) car les variantes n'ont pas la même longueur de prompt (V4 few-shot ≫ V2) ni la même longueur de sortie.
10. OpenTDB : pas d'ID natif → `question_id` déterministe (sha256, déjà spécifié dans `01_opentdb.md` §8) ; `correct_answer` des questions booléennes est littéralement `"True"`/`"False"` ; entités HTML par défaut à décoder (`html.unescape`) **avant** toute normalisation — déjà implémenté dans `normalize.py` du projet.
11. Menaces à la validité à documenter dans le README : contamination probable du dataset (OpenTDB public depuis ~2014), quantization QAT Q4 vs pleine précision, effets thermiques/single-machine sur le timing, déséquilibre des catégories (pool total = 5 298 questions, réparti inégalement), petites catégories à IC large.
12. **Ne pas faire le fuzzy-matching en SQL/dbt** : `grade`/`ai_correct` doivent être calculés une fois en Python à l'ingestion (rapidfuzz n'a pas d'équivalent SQL portable simple) ; dbt/SQL ne fait que l'agrégation en couche gold sur des colonnes déjà gradées.

---

## 1. Conception des prompts pour OpenTDB QCM

### 1.1 Cadrage : pourquoi une notation *générative* et pas log-likelihood

EleutherAI **lm-evaluation-harness** définit deux familles de tâches très différentes (`docs/new_task_guide.md`, https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/new_task_guide.md) :

- **`output_type: multiple_choice`** : le harness ne fait *pas* générer de texte au modèle. Il calcule la **log-vraisemblance** de chaque choix (`doc_to_choice`) concaténé au prompt (`doc_to_text(doc) + target_delimiter + choice`, `target_delimiter` par défaut `" "`), et retient le choix de plus haute logprob. Il n'y a donc **aucune étape de parsing** et aucun mode d'échec « unparseable » — exemple YAML (SciQ) :
  ```yaml
  doc_to_text: "{{support.lstrip()}}\nQuestion: {{question}}\nAnswer:"
  doc_to_target: 3
  doc_to_choice: "{{[distractor1, distractor2, distractor3, correct_answer]}}"
  ```
- Les tâches **génératives** (ex. gsm8k) font au contraire échantillonner du texte libre, noté par extraction/regex — c'est le modèle le plus proche de notre cas.

Pour ce benchmark, **on utilise l'approche générative** : LM Studio expose une API de complétion de type chat, pas un accès direct et pratique aux logprobs de continuations arbitraires pour du texte libre multi-tokens, et le besoin métier explicite (`ai_answer` brut, `response_time`) impose de toute façon une vraie génération. C'est aussi le choix par défaut d'OpenAI **simple-evals** et d'**Inspect AI** pour des modèles accédés via API chat (voir ci-dessous) — on s'aligne donc sur la convention la plus reconnue plutôt que sur lm-eval-harness, qui suppose un accès direct aux logits du modèle.

### 1.2 Références externes qui informent le design

**OpenAI simple-evals** (https://github.com/openai/simple-evals, fetch direct de `common.py`/`mmlu_eval.py`) — template MMLU exact, verbatim :

```python
QUERY_TEMPLATE_MULTICHOICE = """
Answer the following multiple choice question. The last line of your response should be of the following format: 'Answer: $LETTER' (without quotes) where LETTER is one of ABCD. Think step by step before answering.

{Question}

A) {A}
B) {B}
C) {C}
D) {D}
""".strip()
```

Regex d'extraction exacte :

```python
ANSWER_PATTERN_MULTICHOICE = r"(?i)Answer[ \t]*:[ \t]*\$?([A-D])\$?"
```

En pratique, `mmlu_eval.py` n'utilise pas directement cette regex simple mais une famille multilingue (`MULTILINGUAL_ANSWER_REGEXES`, ~40 variantes locales de « Answer: ») essayées dans l'ordre via `re.search`, après un `normalize_response()` qui strippe le markdown/LaTeX (`**`, `$`, `\boxed{`, `\text{`…). Le score est un **exact match strict** (`1.0` si la lettre extraite == la bonne lettre, sinon `0.0`) — pas de fuzzy fallback côté simple-evals.

**Inspect AI** (UK AISI, https://inspect.aisi.org.uk/reference/inspect_ai.solver.html, https://inspect.aisi.org.uk/reference/inspect_ai.scorer.html) :

- Le solver `multiple_choice()` a un paramètre `shuffle: bool | Random` — accepte `True`/`False` **ou une instance `random.Random` seedée**, ce qui est exactement le mécanisme qu'on réplique manuellement ci-dessous (§2). Il existe aussi un shuffle au niveau dataset (`shuffle_choices(seed=...)` / `json_dataset(..., shuffle_choices=42)`) — les deux mécanismes existent, ne pas les confondre.
- Le scorer `choice()` attend une réponse préfixée `"ANSWER:"` (« *Some solvers including multiple_choice solicit answers from the model prefaced with 'ANSWER:'. This scorer extracts answers of this form for comparison with the target* »), dé-shuffle automatiquement avant de comparer, et supporte les réponses multi-correctes via une liste de lettres séparées par des virgules.
- Source GitHub du scorer (pour aller lire la regex exacte si besoin) : https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/scorer/_choice.py (regex précise non extraite dans cette passe de recherche — **NON VÉRIFIÉ** au niveau du texte exact de la regex, seul le comportement documenté est confirmé).

**Convergence des deux frameworks** : le cue `"Answer:"` en toute fin de prompt, suivi d'une lettre unique, est la convention dominante des deux frameworks d'évaluation les plus reconnus du marché — c'est un argument d'autorité de facto (pas une étude contrôlée isolée sur le placement de l'instruction ; voir §1.4).

### 1.3 Gemma — spécificités de prompting (contradiction documentaire à noter)

Recherche sur le prompting Gemma : la fiche modèle officielle **Gemma 4** (https://ai.google.dev/gemma/docs/core/model_card_4, checkpoints QAT 12B confirmés sur LM Studio https://lmstudio.ai/models/google/gemma-4-12b-qat et Hugging Face https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf) annonce un **support natif du rôle `system`**, avec des paramètres d'échantillonnage recommandés `temperature=1.0, top_p=0.95, top_k=64` pour un usage génératif normal (**à neutraliser** pour le benchmark, voir §4).

À l'inverse, la page générique « Gemma formatting » (https://ai.google.dev/gemma/docs/core/prompt-structure) affirme que *« the system role or a system turn is not supported »* et recommande d'injecter les instructions système dans le premier tour `user`, avec le format `<start_of_turn>user ... <end_of_turn><start_of_turn>model`.

**Ces deux sources officielles Google se contredisent** — probablement une page générique pas mise à jour. Recommandation pratique : tester les deux formats et vérifier empiriquement quel template de chat LM Studio applique réellement (LM Studio applique le chat template **embarqué dans le GGUF**, donc c'est lui qui fait foi, pas la doc web). Les templates ci-dessous présentent un champ `system` séparé ; si le template embarqué ne le supporte pas, replier son contenu en tête du premier tour `user`.

### 1.4 Placement de l'instruction de format — preuve faible, à documenter comme heuristique

Aucune étude contrôlée solide n'a été trouvée testant spécifiquement l'effet du **placement** (début vs fin de prompt) de la consigne « réponds uniquement par la lettre » sur un petit modèle local. L'effet « lost in the middle » (info mal exploitée au milieu d'un long contexte) est discuté ailleurs (ex. https://tianpan.co/blog/2026/04/14/the-instruction-position-problem, papier PRIME https://arxiv.org/html/2606.22470) mais ce sont des sources secondaires, **NON VÉRIFIÉ** comme preuve directe pour ce cas précis. De même, l'amélioration de la conformité de format par le few-shot est une **pratique courante mais non formellement sourcée** dans cette recherche. → à documenter explicitement dans le rapport comme choix de design motivé par la convention des frameworks d'éval reconnus (§1.2), pas comme fait scientifiquement établi.

### 1.5 Les 5 variantes — templates exacts

Placeholders : `{question}`, `{A}`/`{B}`/`{C}`/`{D}` = options déjà mélangées (§2), dans l'ordre `options_order`.

---

**V1 — Naïf, texte libre (baseline de connaissance brute)**

- Système : aucun
- Template utilisateur (identique QCM/booléen, pas d'options affichées) :
  ```
  {question}
  ```
- Sortie attendue : texte libre, idéalement court.
- Parsing : pipeline texte libre (§3.2).
- Ce que ça teste : la connaissance factuelle brute, **sans** la béquille de voir les options (pas d'élimination possible, pas de reconnaissance passive) — sert de référence pour mesurer l'écart « rappel actif » vs « reconnaissance » quand on compare à V2+.

---

**V2 — QCM contraint, lettre seule**

- Système : aucun
- Template (`type=multiple`) :
  ```
  Question: {question}

  A) {A}
  B) {B}
  C) {C}
  D) {D}

  Answer with the letter only (A, B, C, or D). Do not explain.
  ```
- Template (`type=boolean` — on répond par le mot, pas une lettre, pour coller directement au format des labels OpenTDB `"True"`/`"False"` et éviter une couche d'indirection lettre→booléen inutile pour 2 options) :
  ```
  Statement: {question}

  Is this statement True or False?

  Answer with one word only: True or False.
  ```
- Sortie attendue : une lettre (QCM) / un mot True|False (booléen).
- Parsing : arbre de décision §3.
- Ce que ça teste : instruction-following (conformité de format) + connaissance en mode reconnaissance (les options servent de filtre de plausibilité) — risque de biais de position (§2), mitigé par le shuffle déterministe.

---

**V3 — Style *simple-evals* (system + contrainte explicite + cue `Answer:`)**

- Système :
  ```
  You are a rigorous trivia quiz solver. Answer strictly according to the requested format and never add explanations unless explicitly asked.
  ```
- Template (`type=multiple`, adapté de `QUERY_TEMPLATE_MULTICHOICE` §1.2 — **écart assumé** : la clause *"Think step by step before answering"* de l'original est retirée par défaut car le trivia ne demande pas de raisonnement multi-étapes et elle double le temps de génération ; garder une variante V3-CoT en option/ablation si le temps le permet) :
  ```
  Answer the following multiple choice question. The last line of your response should be of the following format: 'Answer: $LETTER' (without quotes) where LETTER is one of ABCD.

  {question}

  A) {A}
  B) {B}
  C) {C}
  D) {D}
  ```
- Template (`type=boolean`) :
  ```
  Answer the following True/False question. The last line of your response should be of the following format: 'Answer: $WORD' (without quotes) where WORD is True or False.

  {question}
  ```
- Sortie attendue : bloc de texte se terminant par `Answer: X`.
- Parsing : regex primaire = `ANSWER_PATTERN_MULTICHOICE` exacte (§1.2), fallback sur le parser lettre ancré de V2, puis fallback texte d'option (§3).
- Ce que ça teste : l'effet d'un contrat de sortie explicite et validé par un framework d'éval de référence (system prompt + cue de fin), par rapport à la simple instruction nue de V2 — isole l'effet « cadrage d'autorité + contrat de sortie explicite ».

---

**V4 — Few-shot (2 exemples fixes)**

- Système : aucun (volontairement, pour isoler l'effet du few-shot de celui du system prompt de V3)
- Template (`type=multiple`) :
  ```
  Answer each multiple choice question with only the letter of the correct answer.

  Question: {fewshot_question_1}
  A) {fewshot_A_1}
  B) {fewshot_B_1}
  C) {fewshot_C_1}
  D) {fewshot_D_1}
  Answer: {fewshot_letter_1}

  Question: {fewshot_question_2}
  A) {fewshot_A_2}
  B) {fewshot_B_2}
  C) {fewshot_C_2}
  D) {fewshot_D_2}
  Answer: {fewshot_letter_2}

  Question: {question}
  A) {A}
  B) {B}
  C) {C}
  D) {D}
  Answer:
  ```
- Template (`type=boolean`) : même structure, exemples avec réponses `True`/`False`.
- Sortie attendue : une lettre (ou True/False), généralement sans autre texte (le pattern des exemples le suggère fortement).
- Parsing : identique à V3 (regex `Answer:` puis fallback lettre ancrée).
- Contrainte de conception : les 2 exemples few-shot doivent être **fixes** pour tout le run (mêmes questions pour toutes les questions cibles), tirés de questions OpenTDB **exclues du jeu d'évaluation**, si possible de catégories différentes de la question cible (éviter la fuite d'indice par catégorie), et déjà shufflées de façon déterministe elles aussi.
- Ce que ça teste : est-ce que **démontrer** le format par l'exemple améliore la conformité/parsabilité au-delà d'une instruction explicite seule (V2) ou cadrée par autorité (V3) — isole le mécanisme « apprentissage en contexte du pattern » de celui de « clarté de l'instruction ».

---

**V5 — JSON structuré (decoding contraint par schéma)**

- Système :
  ```
  You answer trivia questions. Respond only with a single JSON object matching the given schema. Do not include any text outside the JSON object.
  ```
- Template utilisateur (`type=multiple`) :
  ```
  Question: {question}

  A) {A}
  B) {B}
  C) {C}
  D) {D}
  ```
- Schéma JSON transmis via le paramètre de sortie structurée de LM Studio (`response_format`, vraisemblablement du grammar-constrained decoding via GBNF côté llama.cpp — **à vérifier empiriquement sur l'installation cible** ; un bug LM Studio documenté montre que les presets peuvent **silencieusement ignorer** les paramètres d'échantillonnage envoyés dans la requête, https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1389, donc valider par un test dédié que le schéma est bien appliqué) :
  ```json
  {
    "type": "json_schema",
    "json_schema": {
      "name": "trivia_answer",
      "schema": {
        "type": "object",
        "properties": {
          "answer": { "type": "string", "enum": ["A", "B", "C", "D"] }
        },
        "required": ["answer"],
        "additionalProperties": false
      }
    }
  }
  ```
- Template + schéma (`type=boolean`) : `enum: ["True", "False"]`.
- Sortie attendue : `{"answer": "C"}`
- Parsing : `json.loads()`, extraction de `.answer`, uppercase (QCM) ou casefold (booléen), validation dans l'ensemble autorisé. Un échec de parsing JSON malgré le decoding contraint devrait être **quasi nul** — un taux non nul est lui-même un signal diagnostique que la contrainte n'est pas réellement active.
- Ce que ça teste : format garanti parsable (taux d'unparseable attendu ≈ 0) contre un coût potentiel en précision — voir la tension Tam et al. 2024 / dottxt (§3.1). **Ablation recommandée** : une variante V5b avec `{"reasoning": "...", "answer": "A"}` (raisonnement **avant** réponse dans le schéma), car la réfutation dottxt attribue spécifiquement la dégradation mesurée par Tam et al. à l'ordre des champs forçant la réponse avant tout raisonnement.

---

## 2. Protocole de shuffle des options

### 2.1 Biais de position — preuves

**Zheng et al., *"Large Language Models Are Not Robust Multiple Choice Selectors"***, ICLR 2024 Spotlight — https://arxiv.org/abs/2309.03882 (code https://github.com/chujiezheng/LLM-MCQ-Bias). Documente un **« selection bias »** : sur 20 LLMs et 3 benchmarks, les modèles favorisent certains tokens d'ID d'option (« A », « B »…) indépendamment du contenu placé à cette position — un **biais de token** sur la prior des IDs de choix, pas sur le contenu lui-même. Mitigation proposée : **PriDe** (*Prior estimation and Debiasing*), méthode *label-free* qui estime la prior de token d'ID du modèle par permutation du contenu sur un petit sous-échantillon, puis débiaise les prédictions sur le reste — moins coûteuse qu'un moyennage complet sur toutes les permutations. **NON VÉRIFIÉ** : les chiffres précis de dégradation (le PDF n'a pas pu être extrait en texte exploitable dans cette passe de recherche) — seule la nature qualitative du phénomène et la méthode de mitigation sont confirmées depuis l'abstract/README.

**Robinson, Rytting, Wingate, *"Leveraging Large Language Models for Multiple Choice Question Answering"***, arXiv 2022 — https://arxiv.org/abs/2210.12353. Introduit le concept de **MCSB** (*Multiple Choice Symbol Binding*) : la capacité d'un modèle à associer correctement le contenu d'une option à sa lettre quand les options sont présentées conjointement (« natural prompting » — c'est l'approche adoptée ici en V2-V5) plutôt qu'en scoring cloze/log-vraisemblance séparé (l'approche lm-eval-harness classique, §1.1). Les modèles à fort MCSB tirent un bénéfice net du prompting naturel. **NON VÉRIFIÉ** : ce papier ne semble pas traiter explicitement de permutation cyclique quantifiée des options dans son abstract — ne pas lui attribuer cette affirmation spécifique.

**Contre-point trouvé en recherche complémentaire** : *"Look at the Text: Instruction-Tuned Language Models are More Robust Multiple Choice Selectors than You Think"* (2024, https://arxiv.org/html/2404.08382v1) nuance Zheng et al. en arguant que les modèles instruction-tuned sont moins biaisés que rapporté — à citer pour un traitement équilibré du sujet dans le README (§8).

### 2.2 Mitigation adoptée : shuffle déterministe par `question_id`

**Piège critique** : le `hash()` builtin Python sur des chaînes est **randomisé par processus** depuis Python 3.3 (PEP 456), sauf si `PYTHONHASHSEED` est fixé explicitement — voir https://docs.python.org/3/using/cmdline.html#envvar-PYTHONHASHSEED. Utiliser `hash(question_id)` comme seed produirait un ordre d'options **différent à chaque exécution du process**, cassant la comparabilité entre runs/variantes. Il faut un hash stable et indépendant du process : `hashlib.sha256`.

```python
import hashlib
import random


def deterministic_seed(question_id: str) -> int:
    """Stable across processes/runs — unlike Python's builtin hash(),
    which is per-process randomized since Python 3.3 (PEP 456) unless
    PYTHONHASHSEED is fixed. See:
    https://docs.python.org/3/using/cmdline.html#envvar-PYTHONHASHSEED
    """
    digest = hashlib.sha256(question_id.encode("utf-8")).hexdigest()
    return int(digest, 16) % (2**32)


def shuffle_options(
    question_id: str, correct_answer: str, incorrect_answers: list[str]
) -> tuple[list[str], str]:
    options = [*incorrect_answers, correct_answer]
    rng = random.Random(deterministic_seed(question_id))
    rng.shuffle(options)
    correct_letter = "ABCD"[options.index(correct_answer)]
    return options, correct_letter
```

- `options_order` (liste ordonnée, ou juste l'ordre + `correct_letter`) est calculé **une seule fois par `question_id`** et stocké en couche silver — **tous** les modèles et **toutes** les variantes de prompt voient le même agencement A/B/C/D pour une question donnée. Cela garantit une comparaison à input strictement identique.
- Conséquence positive : le `correct_letter` enregistré permet une analyse a posteriori du biais de position en agrégeant l'accuracy par valeur de `correct_letter` (table gold dédiée possible, voir §7).
- **Protocole étendu optionnel** (hors périmètre du run principal à ~4 000+ questions, coût ×4 en appels) : pour une étude de biais de position dédiée, évaluer un sous-échantillon sur les 4 rotations/permutations des options à la Zheng et al., avec estimation de prior façon PriDe.

---

## 3. Extraction et notation des réponses

### 3.1 Structured output vs accuracy — l'état du débat

**Tam et al., *"Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models"***, EMNLP 2024 Industry Track — https://arxiv.org/abs/2408.02442, https://aclanthology.org/2024.emnlp-industry.91/. Constat qualitatif : une dégradation significative des capacités de raisonnement sous contraintes de format strictes (JSON, XML), d'autant plus forte que la contrainte est stricte. **NON VÉRIFIÉ** : chiffres précis (non extraits du PDF dans cette passe).

**Réfutation/nuance — dottxt** (créateurs de la lib `outlines`), *"Say What You Mean: A Response to 'Let Me Speak Freely'"* — https://blog.dottxt.ai/say-what-you-mean.html (résumé tiers : https://dylancastillo.co/posts/say-what-you-mean-sometimes.html). Points de critique : (a) la condition « structurée » de Tam et al. était en réalité du *JSON-mode prompting* sans véritable moteur de contrainte grammaticale ; (b) les prompts n'étaient pas appariés entre conditions ; (c) un parseur de sortie était lui-même un LLM juge (biais) ; (d) **surtout** — le schéma forçait le champ `"answer"` **avant** un éventuel champ de raisonnement, empêchant le modèle de raisonner avant de répondre (chaîne de pensée cassée par construction du schéma). Sur des répliques « apples-to-apples » respectant l'ordre raisonnement→réponse, dottxt rapporte une génération structurée qui égale ou dépasse légèrement la génération libre.

**Implication pratique pour ce projet** : la leçon actionnable n'est pas « JSON = toujours pire » mais **« l'ordre des champs du schéma compte »** — d'où la recommandation V5b (§1.5) de placer `reasoning` avant `answer` si un CoT est souhaité. Pour du trivia pur (pas de raisonnement multi-étapes nécessaire), le risque de dégradation via V5 tel que défini (juste `answer`) est probablement faible, mais **à valider empiriquement sur ce run** en comparant V5 à V2/V3 sur les mêmes questions (via McNemar, §5).

### 3.2 Normalisation texte libre — SQuAD canonique + extension projet

Source canonique (https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/evaluate-v2.0.py), citée verbatim :

```python
def normalize_answer(s):
  """Lower text and remove punctuation, articles and extra whitespace."""
  def remove_articles(text):
    regex = re.compile(r'\b(a|an|the)\b', re.UNICODE)
    return re.sub(regex, ' ', text)
  def white_space_fix(text):
    return ' '.join(text.split())
  def remove_punc(text):
    exclude = set(string.punctuation)
    return ''.join(ch for ch in text if ch not in exclude)
  def lower(text):
    return text.lower()
  return white_space_fix(remove_articles(remove_punc(lower(s))))

def compute_exact(a_gold, a_pred):
  return int(normalize_answer(a_gold) == normalize_answer(a_pred))

def compute_f1(a_gold, a_pred):
  gold_toks = get_tokens(a_gold)          # get_tokens(s) = normalize_answer(s).split() — standard du script
  pred_toks = get_tokens(a_pred)
  common = collections.Counter(gold_toks) & collections.Counter(pred_toks)
  num_same = sum(common.values())
  if len(gold_toks) == 0 or len(pred_toks) == 0:
    return int(gold_toks == pred_toks)
  if num_same == 0:
    return 0
  precision = 1.0 * num_same / len(pred_toks)
  recall = 1.0 * num_same / len(gold_toks)
  f1 = (2 * precision * recall) / (precision + recall)
  return f1
```

**Ce projet a déjà une version étendue** (`src/trivia_bench/normalize.py`, voir `05_python_tooling.md` §9), qui ajoute deux étapes indispensables pour OpenTDB que le script SQuAD brut ne fait pas :
- `html.unescape()` — les payloads OpenTDB par défaut contiennent des entités HTML (`&#039;`, `&quot;`, `&amp;`…), documentées dans `01_opentdb.md`.
- `strip_accents()` (NFKD + suppression des marques combinantes) + `casefold()` (plus agressif que `.lower()`).

→ **Recommandation : réutiliser `normalize.py` existant comme implémentation de référence pour la notation**, pas une réimplémentation SQuAD brute — il sur-ensemble le comportement canonique et gère déjà les artefacts OpenTDB.

### 3.3 Seuil de fuzzy matching (rapidfuzz)

**Pas de seuil universel validé académiquement** — c'est une convention d'ingénierie, pas un résultat formel (confirmé indépendamment par la recherche web, https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html, ET par la convention déjà adoptée dans ce projet, `05_python_tooling.md` §9). La fourchette communément citée est **80–90**, avec **90+** recommandé quand la précision prime. Ce projet a déjà retenu **≥ 90** comme seuil « quasi-exact » et 70–85 comme zone de rapprochement permissif nécessitant revue humaine — **convergence de deux sources indépendantes**, retenu ici comme seuil par défaut.

Distinction des scorers (https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html) :
- `fuzz.ratio` : similarité caractère-par-caractère, sensible à l'ordre des mots.
- `fuzz.token_sort_ratio` : trie les mots avant de comparer — robuste aux réordonnancements.
- `fuzz.token_set_ratio` : compare des ensembles de mots — tolérant aux ajouts/suppressions, utile si le modèle reformule.
- `fuzz.WRatio` : scorer combiné par défaut, recommandé « si on ne sait pas lequel choisir » (c'est le choix déjà fait dans `normalize.py` du projet via `process.extractOne(..., scorer=fuzz.WRatio)`).

### 3.4 Arbre de décision de notation — implémentation

**Principe de design** : `grade` encode **comment** une réponse correcte a été reconnue (utile pour auditer le risque de faux positifs du fuzzy/contains), tandis que `wrong`/`unparseable` sont les deux issues terminales pour les réponses incorrectes/non-interprétables. `ai_correct` est **nullable** : `NULL` uniquement pour `unparseable` (on ne sait pas ce que le modèle voulait dire — c'est un échec d'instruction-following, pas de connaissance), `False` pour `wrong`, `True` pour `exact`/`letter`/`fuzzy`/`contains`.

**Variantes QCM (V2 à V5)** — priorité d'extraction :

```python
import json
import re

LETTER_ANCHORED_RE = re.compile(r"^\s*\(?([A-D])\)?[\.\):\s]")
ANSWER_PATTERN_MULTICHOICE = re.compile(r"(?i)Answer[ \t]*:[ \t]*\$?([A-D])\$?")


def extract_letter(raw_response: str, is_json_variant: bool) -> str | None:
    if is_json_variant:
        try:
            obj = json.loads(raw_response)
            letter = str(obj.get("answer", "")).strip().upper()
            return letter if letter in "ABCD" else None
        except (json.JSONDecodeError, AttributeError):
            return None  # falls through to free-text fallback below
    m = LETTER_ANCHORED_RE.match(raw_response)
    if m:
        return m.group(1).upper()
    m = ANSWER_PATTERN_MULTICHOICE.search(raw_response)
    if m:
        return m.group(1).upper()
    return None


def grade_mc_answer(
    raw_response: str,
    options: list[str],       # options_order, index 0..3 = A..D
    correct_letter: str,
    is_json_variant: bool = False,
) -> tuple[str, bool | None]:
    """Returns (grade, ai_correct)."""
    letter = extract_letter(raw_response, is_json_variant)
    if letter is not None:
        is_correct = letter == correct_letter
        return ("letter" if is_correct else "wrong", is_correct)

    # Model ignored the "letter only" instruction and wrote the option text instead.
    norm_resp = normalize_answer(raw_response)
    norm_options = [normalize_answer(o) for o in options]

    if norm_resp in norm_options:
        idx = norm_options.index(norm_resp)
        is_correct = "ABCD"[idx] == correct_letter
        return ("exact" if is_correct else "wrong", is_correct)

    scores = [(i, fuzz.ratio(norm_resp, o)) for i, o in enumerate(norm_options)]
    scores.sort(key=lambda t: t[1], reverse=True)
    if scores[0][1] >= 90 and (len(scores) == 1 or scores[0][1] - scores[1][1] >= 5):
        idx = scores[0][0]
        is_correct = "ABCD"[idx] == correct_letter
        return ("fuzzy" if is_correct else "wrong", is_correct)

    contained = [i for i, o in enumerate(norm_options) if len(o) >= 3 and o in norm_resp]
    if len(contained) == 1 and not _has_negation_before(norm_resp, norm_options[contained[0]]):
        idx = contained[0]
        is_correct = "ABCD"[idx] == correct_letter
        return ("contains" if is_correct else "wrong", is_correct)

    return ("unparseable", None)
```

**Variante texte libre (V1)** :

```python
def grade_freetext_answer(raw_response: str, gold_answer: str) -> tuple[str, bool | None]:
    norm_resp = normalize_answer(raw_response)
    norm_gold = normalize_answer(gold_answer)

    if not norm_resp:
        return ("unparseable", None)
    if norm_resp == norm_gold:
        return ("exact", True)
    if fuzz.token_sort_ratio(norm_resp, norm_gold) >= 90:
        return ("fuzzy", True)
    if len(norm_gold) >= 3 and norm_gold in norm_resp and not _has_negation_before(norm_resp, norm_gold):
        return ("contains", True)
    if _looks_like_refusal(norm_resp):  # "i don't know", "n/a", empty-ish hedges
        return ("unparseable", None)
    return ("wrong", False)
```

**Garde anti-négation** (évite qu'une bonne réponse citée pour la réfuter soit créditée à tort, ex. gold=`"Mercury"`, réponse=`"It's not Mercury, it's Venus"`) :

```python
_NEGATION_TOKENS = {"not", "n't", "except", "neither", "isn't", "wasn't", "aren't", "never"}

def _has_negation_before(response: str, matched_span: str, window: int = 3) -> bool:
    idx = response.find(matched_span)
    if idx == -1:
        return False
    preceding_tokens = response[:idx].split()[-window:]
    return any(tok.strip(".,!?") in _NEGATION_TOKENS for tok in preceding_tokens)
```

**Variante booléenne** — politique stricte séparant match littéral et synonyme récupéré :

```python
_STRICT_TRUE = {"true"}
_STRICT_FALSE = {"false"}
_SYNONYM_TRUE = {"yes", "y", "t"}
_SYNONYM_FALSE = {"no", "n", "f"}

def grade_boolean_answer(raw_response: str, gold_bool: bool) -> tuple[str, bool | None]:
    tok = normalize_answer(raw_response).strip()

    if tok in _STRICT_TRUE or tok in _STRICT_FALSE:
        pred = tok in _STRICT_TRUE
        return ("exact", True) if pred == gold_bool else ("wrong", False)

    if tok in _SYNONYM_TRUE or tok in _SYNONYM_FALSE:
        # Recovered via synonym mapping -> flags an instruction-following slip
        # (asked for True/False, got yes/no) even when ultimately correct.
        pred = tok in _SYNONYM_TRUE
        return ("fuzzy", True) if pred == gold_bool else ("wrong", False)

    words = tok.split()
    found_true = any(w in _STRICT_TRUE | _SYNONYM_TRUE for w in words)
    found_false = any(w in _STRICT_FALSE | _SYNONYM_FALSE for w in words)
    if found_true ^ found_false:  # exactly one of the two found, unambiguous
        pred = found_true
        return ("contains", True) if pred == gold_bool else ("wrong", False)

    return ("unparseable", None)
```

`ai_correct` final : `True` si `grade ∈ {exact, letter, fuzzy, contains}`, `False` si `grade = wrong`, `NULL` si `grade = unparseable`.

### 3.5 Reproductibilité en SQL/dbt — ce qui est portable, ce qui ne l'est pas

Les règles **exact**, **letter** (via regex) et **contains** sont portables en SQL (DuckDB supporte `regexp_matches`, `json_extract`, `position`/`contains`). Le **fuzzy matching** (rapidfuzz) n'a **pas d'équivalent SQL portable simple** — DuckDB expose des fonctions de similarité de chaînes natives (`jaro_winkler_similarity`, `levenshtein` — **NON VÉRIFIÉ** disponibilité/nom exact pour la version DuckDB épinglée dans ce projet, 1.5.5, à vérifier dans la doc DuckDB avant de s'y fier), mais ce ne sont pas les mêmes algorithmes que `fuzz.ratio`/`WRatio`, donc les résultats ne seraient pas identiques à un recalcul Python.

**Recommandation ferme** : calculer `grade` et `ai_correct` **une seule fois, en Python, à l'ingestion** (juste après l'appel au LLM, dans la commande `benchmark` de la CLI existante — voir `05_python_tooling.md` §6), et écrire ces colonnes directement dans la partition `answers/run_id=.../`. La couche dbt/SQL (couche gold) ne fait ensuite que de l'**agrégation** sur des colonnes déjà gradées — jamais de recalcul du grading en SQL. Cela évite de maintenir deux implémentations divergentes (Python vs SQL) du même arbre de décision.

---

## 4. Déterminisme : température 0, échantillonnage neutre, limites

### 4.1 Paramètres à neutraliser

Serveur llama.cpp (source : https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md, sous-jacent à LM Studio) — valeurs par défaut, **aucune n'est neutre par défaut à part `typical_p`** :

| Paramètre | Défaut llama.cpp | Valeur neutre pour greedy pur |
|---|---|---|
| `temperature` | 0.80 | `0` |
| `top_k` | 40 (0 = désactivé) | `1` ou `0` |
| `top_p` | 0.95 (1.0 = désactivé) | `1.0` |
| `min_p` | 0.05 (0.0 = désactivé) | `0.0` |
| `typical_p` | 1.0 (déjà désactivé) | `1.0` |
| `repeat_penalty` | **1.1** — **pas neutre !** | `1.0` |
| `dynatemp_range` | 0.0 (déjà désactivé) | `0.0` |
| `seed` | -1 (aléatoire) | valeur fixe, ex. `42` |

```python
GREEDY_PARAMS = {
    "temperature": 0,
    "top_k": 1,
    "top_p": 1.0,
    "min_p": 0.0,
    "typical_p": 1.0,
    "repeat_penalty": 1.0,   # default is 1.1 in llama.cpp — must override explicitly
    "dynatemp_range": 0.0,
    "seed": 42,
}
```

LM Studio expose les mêmes leviers via son API `/v1/chat/completions` (https://lmstudio.ai/docs/typescript/llm-prediction/parameters). **Piège documenté** : si un *preset* LM Studio est utilisé, les paramètres envoyés dans la requête peuvent être **silencieusement ignorés** (https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1389) — vérifier empiriquement sur l'installation cible que `GREEDY_PARAMS` est bien appliqué (ex. en comparant les logits/tokens produits avec et sans preset).

### 4.2 La reproductibilité bit-exacte n'est PAS garantie, même sur GPU avec seed fixe

Plusieurs issues llama.cpp documentent des sorties non déterministes malgré `temperature=0` et `seed` fixe :
- ROCm/RDNA3 — https://github.com/ggml-org/llama.cpp/issues/10197
- Serveur multi-slots : 5 à 8 complétions différentes sur 8 slots identiques (H100, A100, M1) — https://github.com/ggml-org/llama.cpp/issues/7052 (non résolu)
- Divergences CPU/CUDA à temp=0 — https://github.com/ggml-org/llama.cpp/issues/4458

Cause racine documentée : la **non-associativité de l'arithmétique flottante** ((a+b)+c ≠ a+(b+c)) combinée à un ordre de réduction des kernels GPU (GEMM, RMSNorm, attention) qui dépend de la taille de batch → les logits (et donc le token argmax) peuvent varier selon le batching/scheduling, même sans aléa de sampling. Sources : https://arxiv.org/html/2511.00025, synthèse https://www.startuphub.ai/ai-news/ai-research/2025/the-real-reason-for-llm-inference-nondeterminism/.

**Conséquence pour le protocole** : exécuter en **strictement séquentiel** (une seule requête en vol, pas de multi-slots/batching concurrent sur le serveur LM Studio/llama.cpp) pour maximiser (pas garantir) la reproductibilité run-à-run ; documenter explicitement dans le README que la reproductibilité bit-exacte n'est pas garantie même ainsi, et logger le texte complet de `ai_answer` + tous les paramètres + le hash du fichier modèle pour tout audit ultérieur.

---

## 5. Statistiques pour le rapport de benchmark

### 5.1 Intervalle de Wilson (proportion/accuracy)

Formule (https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval), avec `n_s` succès, `n_f` échecs, `n = n_s + n_f`, `z` = quantile normal (1.96 pour 95 %) :

```
p ∈ [ (n_s + z²/2) ± z·√(n_s·n_f/n + z²/4) ] / (n + z²)
```

Préféré à l'approximation normale (Wald) car il évite le dépassement hors `[0,1]` et reste fiable à petit `n`.

```python
from statsmodels.stats.proportion import proportion_confint

ci_low, ci_upp = proportion_confint(count=correct, nobs=n, alpha=0.05, method="wilson")
# NB: method par défaut de statsmodels est 'normal' -- toujours passer method="wilson" explicitement.
```

### 5.2 Test de McNemar (comparaison appariée de deux variantes)

Pour comparer deux variantes de prompt évaluées sur le **même** jeu de questions (données appariées), construire la table de contingence 2×2 des paires discordantes :

```
                 variant B correct   variant B wrong
variant A correct       a                  b
variant A wrong         c                  d
```

- Chi² de base (non corrigé) : `χ² = (b - c)² / (b + c)`, ddl=1
- Avec correction de continuité (McNemar standard) : `χ² = (|b - c| - 1)² / (b + c)`
- Version exacte (recommandée si `b + c` petit, règle de pouce < ~25) : test binomial exact sur `min(b, c)`

```python
from statsmodels.stats.contingency_tables import mcnemar

table = [[both_correct, a_correct_b_wrong],
         [a_wrong_b_correct, both_wrong]]
result = mcnemar(table, exact=True)          # exact=False, correction=True si b+c est grand
print(result.statistic, result.pvalue)
```

Source : https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html

### 5.3 Bootstrap apparié pour l'IC de la différence d'accuracy

Procédure : rééchantillonner les indices de questions **avec remise** B fois (ex. B=10 000), calculer `acc_A`, `acc_B` et `diff = acc_A - acc_B` sur chaque rééchantillon, prendre les percentiles 2.5/97.5 comme IC à 95 %.

Références : Efron & Tibshirani, *An Introduction to the Bootstrap* (1993, référence générale de la méthode, **NON VÉRIFIÉ** page exacte) ; spécifique NLP : Berg-Kirkpatrick, Burkett & Klein, *"An Empirical Investigation of Statistical Significance in NLP"*, EMNLP 2012 — https://aclanthology.org/D12-1091/ ; Dror, Baumer, Shlomov & Reichart, *"The Hitchhiker's Guide to Testing Statistical Significance in Natural Language Processing"*, ACL 2018 — https://aclanthology.org/P18-1128/ (companion arXiv : https://arxiv.org/pdf/1809.01448) — ce dernier propose un protocole de décision pour le choix du test de significativité en NLP.

```python
import numpy as np

rng = np.random.default_rng(seed=42)
correct_a = np.array(...)  # bool array, len N, correction de la variante A par question
correct_b = np.array(...)  # même N questions, variante B
N, B = len(correct_a), 10_000
idx_all = np.arange(N)
diffs = np.empty(B)
for i in range(B):
    idx = rng.choice(idx_all, size=N, replace=True)
    diffs[i] = correct_a[idx].mean() - correct_b[idx].mean()
ci_low, ci_high = np.percentile(diffs, [2.5, 97.5])
```

### 5.4 Baseline du hasard et accuracy au-dessus du hasard

QCM 4 options → hasard = 1/4 = **25 %**. Booléen → hasard = 1/2 = **50 %**. Rapporter l'**accuracy au-dessus du hasard** (et pas seulement l'accuracy brute) est nécessaire pour comparer équitablement les deux types de question : un modèle à 40 % sur du QCM 4 options (+15 points au-dessus du hasard) démontre plus de connaissance qu'à 55 % sur du booléen (+5 points), malgré un chiffre brut inférieur. Les baselines doivent être rapportées **séparément par type** — les pooler sans ajustement mélange deux planchers de hasard différents.

### 5.5 Taille d'échantillon minimale par catégorie

```
E = z · √(p(1-p)/n)   ⟹   n = p(1-p)·(z/E)²
```

Cas défavorable `p=0.5` (maximise `p(1-p)=0.25`) utilisé quand `p` est inconnu a priori. Exemple : `p=0.5`, `E=0.10`, 95 % (`z=1.96`) → `n = 0.25·(1.96/0.10)² ≈ 96` → **n≈97** par catégorie pour ±10 points de marge ; pour `E=0.05` → **n≈385**.

Règle de pouce complémentaire : `n≥30` est le seuil informel souvent cité pour l'approximation normale (moyennes, TCL) ; pour une **proportion** spécifiquement, la condition plus stricte est `n·p ≥ 5` et `n·(1-p) ≥ 5` (parfois `≥10`). Sources : https://online.stat.psu.edu/stat200/lesson/8/8.1/8.1.1/8.1.1.3, https://stats.libretexts.org/Bookshelves/Introductory_Statistics/Mostly_Harmless_Statistics_(Webb)/07:_Confidence_Intervals_for_One_Population/7.03:_Sample_Size_Calculation_for_a_Proportion.

```python
import numpy as np
from scipy.stats import norm

Z95 = norm.ppf(1 - 0.05 / 2)  # 1.959963985

def min_n(margin: float, p: float = 0.5, z: float = Z95) -> int:
    return int(np.ceil(p * (1 - p) * (z / margin) ** 2))

min_n(0.10)  # -> 97
min_n(0.05)  # -> 385
```

**Recommandation opérationnelle** : pour toute catégorie avec `n < 30` questions, calculer quand même l'IC de Wilson (valide à petit `n`, contrairement à l'approximation normale) mais **flaguer explicitement la catégorie comme non conclusive** dans le rapport (colonne `n_flag_low` dans la table gold correspondante, §7) plutôt que de l'omettre silencieusement.

### 5.6 Calibration — hors périmètre pour des réponses génératives

La calibration au sens strict (comparer une probabilité prédite à la fréquence empirique de succès) suppose l'accès à une probabilité/confiance associée à chaque réponse — non disponible ici puisque le pipeline est **génératif** (texte libre ou JSON, pas de score de confiance renvoyé par LM Studio pour une réponse composite). **Hors périmètre**, à documenter explicitement comme tel dans le README plutôt que de le passer sous silence.

---

## 6. Méthodologie du temps de réponse

### 6.1 Métriques à rapporter

Source de référence sur la taxonomie des métriques : Anyscale, *"Understand LLM latency and throughput metrics"* — https://docs.anyscale.com/llm/serving/benchmarking/metrics.

- **TTFT** (Time to First Token) : temps entre l'envoi du prompt et le premier token de sortie — capture le coût de *prefill*, qui **scale avec la longueur du prompt** (« *Longer prompts typically result in longer TTFT because the model must first process the entire input before generating any output* »).
- **ITL** (Inter-Token Latency, ≈ TPOT) : latence entre tokens en régime établi après le premier token — c'est ce dont le temps total de génération scale avec la **longueur de la complétion**.
- **Débit** : tokens/s (TPS), par requête (pertinent ici, exécution séquentielle).
- **Percentiles** : p50/médiane, p95 (« l'expérience des 5 % les moins chanceux »), p99.
- **Pourquoi la médiane plutôt que la moyenne** (même source) : « *Just looking at the average latency can be misleading and hide a wide range of experiences where a few very slow responses mask many fast ones* » — la moyenne est tirée par les outliers de queue, la médiane y est robuste.

Corroboré par : https://dev.to/wheynelau/how-to-benchmark-llm-inference-performance-ttft-itl-and-throughput-metrics-416p, https://arxiv.org/pdf/2507.09019, https://redis.io/blog/llm-speed-benchmarks/.

### 6.2 Warm-up et exécution séquentielle

**Warm-up** — pratique standard confirmée par deux sources dédiées au sujet : *Bench360: Benchmarking Local LLM Inference from 360 Degrees* (https://arxiv.org/pdf/2511.16682) exclut explicitement le temps de chargement/prefill à froid des analyses de latence/débit, et décrit l'exclusion d'« *one warm-up inference* » avant mesure ; *LLM Inference at the Edge* (https://arxiv.org/pdf/2603.23640) précise qu'une phase de warm-up « *mitigates cold-start effects such as memory allocation, CUDA graph capture, and JIT kernel compilation* ». → **Exclure systématiquement le premier appel** (chargement modèle/compilation de kernels) des statistiques de latence.

**Exécution séquentielle** : les méthodologies citées mesurent la latence par requête en régime établi, une requête à la fois — l'exécution concurrente introduit du *queuing*/*batching* qui confond l'attribution de latence par question ; à réserver aux mesures de débit système, pas de latence par appel.

### 6.3 Champs exacts à stocker (llama.cpp / LM Studio)

Réponse `/completion` de llama.cpp (source : https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), objet `timings` :

| Champ | Signification |
|---|---|
| `predicted_per_second` | débit de génération (tokens/s) |
| `prompt_per_second` | débit de traitement du prompt |
| `predicted_ms` | temps passé en génération |
| `prompt_ms` | temps passé en prefill |
| `tokens_predicted` | nb de tokens générés (complétion) |
| `tokens_evaluated` | nb de tokens du prompt |
| `tokens_cached` | tokens réutilisés depuis le cache KV |

LM Studio expose le même serveur llama.cpp sous-jacent — **NON VÉRIFIÉ** que la couche REST propre à LM Studio ré-expose `timings` à l'identique (uniquement confirmé sur le README llama.cpp upstream ; à valider par un appel de test sur l'installation cible).

```python
import time

t0 = time.perf_counter()
response = client.chat.completions.create(..., **GREEDY_PARAMS)
wall_clock_s = time.perf_counter() - t0

record = {
    "ai_answer": response.choices[0].message.content,
    "response_time": wall_clock_s,                 # perf_counter wall-clock autour de l'appel
    "ttft_ms": response.timings.prompt_ms,          # si exposé par LM Studio
    "tokens_per_s": response.timings.predicted_per_second,
    "prompt_tokens": response.timings.tokens_evaluated,
    "completion_tokens": response.timings.tokens_predicted,
    "prompt_variant": variant_id,
    "run_order": call_index,
}
```

### 6.4 Comparer les variantes équitablement

Les variantes n'ont **pas** la même longueur de prompt (V4 few-shot ≫ V2 nu) ni forcément la même longueur de sortie attendue (V5 JSON compact vs V3 avec préambule avant `Answer:`). Comparer uniquement `response_time` brut confond donc le coût de *prefill* (dépendant du prompt) et le coût de *decode* (dépendant de la sortie). → Rapporter **en plus** :
- `response_time` total (comparaison brute, utile pour l'UX réelle)
- `response_time / tokens_predicted` = temps par token généré (isole le coût de decode, comparable entre variantes)
- `ttft` séparément (isole le coût de prefill, directement lié à la longueur du prompt)

### 6.5 Détection de dérive thermique sur un run long

Sur un run de 4 000+ appels séquentiels, un throttling thermique du poste local peut faire dériver le débit à la baisse au fil du temps. Détection : médiane glissante de `tokens_per_s` en fonction de `run_order` (ordre séquentiel des appels, pas l'ordre logique des questions).

```python
import pandas as pd

df = df.sort_values("run_order")
df["rolling_median_tps"] = df["tokens_per_s"].rolling(window=50, min_periods=10).median()
# Tracer rolling_median_tps vs run_order -> une tendance baissière soutenue = signal de throttling
```

---

## 7. Structure du rapport — couche GOLD (dbt-duckdb)

Chaque table ci-dessous est un modèle dbt (`dbt-core` + `dbt-duckdb`, déjà retenu — voir `05_python_tooling.md`), construit sur la couche silver (`questions` avec `question_id`/`options_order`/`correct_letter`, et `answers` partitionné par `run_id` avec `grade`/`ai_correct`/`response_time`/timings déjà calculés en Python, §3.5).

| Table gold | Grain | Colonnes clés | Type de graphique |
|---|---|---|---|
| `gold_accuracy_by_model_variant` | (model, prompt_variant) | n, n_correct, n_unparseable, accuracy, wilson_lo, wilson_hi | Barres groupées avec barres d'erreur (IC Wilson) |
| `gold_accuracy_by_category_difficulty` | (model, prompt_variant, category, difficulty) | n, accuracy, wilson_lo/hi, n_flag_low (n<30) | Heatmap catégorie × difficulté, couleur = accuracy |
| `gold_accuracy_vs_chance_by_type` | (model, prompt_variant, question_type) | n, accuracy, chance_baseline, accuracy_above_chance, ci | Barres avec ligne de référence au niveau du hasard |
| `gold_unparseable_rate_by_variant` | (model, prompt_variant) | n_total, n_unparseable, rate, wilson_lo/hi | Barres triées décroissant (aussi une proportion → IC Wilson) |
| `gold_latency_distribution_by_variant_model` | (model, prompt_variant) | n, median/p90/p95/mean response_time, median tokens/s, median time/token, ttft_median | Box/violin plot (+ ECDF en complément pour repérer une bimodalité froid/chaud) |
| `gold_hardest_categories` | category | n, accuracy, rang | Barres horizontales triées croissant (accuracy la plus basse en haut) |
| `gold_consistency_cross_variant` | question_id | category, difficulty, n_variants_correct, all_agree_correct, all_agree_wrong, disagreement_flag | Donut/barres empilées (tout-correct / tout-faux / mixte) — flague les questions potentiellement ambiguës (tout le monde se trompe) |
| `gold_difficulty_calibration` | (model, prompt_variant, difficulty) | difficulty (easy/medium/hard), accuracy, corrélation ordinal (Spearman) | Barres/lignes accuracy par difficulté OpenTDB déclarée |
| `gold_answer_length_vs_correctness` | (model, prompt_variant, question_id) | response_length_tokens, ai_correct, grade | Box plot longueur de réponse par correct/incorrect/grade |
| `gold_drift_over_run_order` | (model, prompt_variant, run_order_bucket) | rolling_median_tokens_per_s, rolling_median_response_time | Ligne (x = ordre d'exécution, y = médiane glissante) |

Rendu : Streamlit (déjà retenu, `05_python_tooling.md`) — `st.bar_chart`/`st.line_chart` natifs n'ont pas de barres d'erreur ; utiliser Plotly ou Altair en dessous pour les IC/heatmap/box-violin/ECDF (choix d'implémentation, pas approfondi ici).

---

## 8. Menaces à la validité (README)

- **Contamination du dataset** : OpenTDB est public depuis ~2014 et largement indexé/republié (sites tiers, dumps GitHub) — il est **probable** qu'une partie significative apparaisse dans le corpus de pré-entraînement de la plupart des LLM modernes, y compris Gemma. **NON VÉRIFIÉ** de façon quantitative pour Gemma 4 spécifiquement (pas de carte de données publique détaillée trouvée) — à documenter comme limite structurelle : une haute accuracy peut refléter de la mémorisation plutôt qu'un raisonnement/une connaissance généralisable.
- **Bruit des entités HTML** : l'encodage par défaut d'OpenTDB renvoie des entités HTML (`&quot;`, `&#039;`, `&amp;`…) dans `question` et les réponses — à décoder (`html.unescape`) **avant** tout envoi au prompt et toute comparaison ; voir `01_opentdb.md` pour le détail des modes d'encodage (`default`, `url3986`, `base64` — ce dernier recommandé pour un scraping robuste).
- **Questions ambiguës** : certaines questions OpenTDB sont datées, mal formulées ou ambiguës (phénomène documenté en creux par des travaux comme *"Metric assessment protocol in the context of answer fluctuation on MCQ tasks"*, https://arxiv.org/pdf/2507.15581, 2025 — **NON VÉRIFIÉ** en détail dans cette passe). La table `gold_consistency_cross_variant` (§7) sert de détecteur pratique : les questions où **toutes** les variantes/modèles échouent sont des candidates à une revue manuelle d'ambiguïté plutôt qu'une pure lacune de connaissance.
- **Déséquilibre des catégories** : le pool total « verified » interrogeable via l'API est de **5 298 questions** (au 2026-09-10, voir `01_opentdb.md`), réparti très inégalement entre catégories (`api_count.php`/`api_count_global.php` par catégorie) — certaines catégories auront structurellement un `n` faible, avec IC large (§5.5) ; ne pas tirer de conclusion catégorique sur ces catégories sans flaguer `n_flag_low`.
- **Effets machine unique / thermiques** : un seul poste, exécution séquentielle sur plusieurs heures pour 4 000+ questions × plusieurs variantes × modèles → risque de dérive thermique du débit (détection §6.5) et de non-reproductibilité bit-exacte sur GPU même à seed fixe (§4.2, issues llama.cpp #10197/#7052/#4458). Les résultats de latence sont valides **pour cette machine à ce moment**, pas généralisables telles quelles.
- **Quantization QAT Q4 vs pleine précision** : les checkpoints QAT (*quantization-aware training*) Q4 sont optimisés pour minimiser la perte de qualité par rapport à une quantization post-training naïve, mais une dégradation résiduelle de rappel factuel (en particulier sur des faits de longue traîne) reste plausible par rapport au checkpoint pleine précision (bf16/fp16) de la même famille — **NON VÉRIFIÉ quantitativement pour Gemma 4 12B QAT spécifiquement** dans cette passe de recherche (raisonnement général issu de la littérature de quantization, pas une mesure sourcée sur ce modèle précis). Ne pas présenter les résultats de ce benchmark comme représentatifs de la capacité « vraie » de la famille de modèle sans ce caveat ; si les ressources le permettent, reproduire un sous-échantillon sur un checkpoint pleine précision comme sanity-check.
- **Petites catégories** : conséquence directe du déséquilibre ci-dessus et de la règle de taille d'échantillon (§5.5) — toute catégorie avec `n < ~30` doit être présentée avec IC de Wilson et flag explicite de non-conclusivité, jamais comme un chiffre isolé sans contexte.

---

## Pièges & recommandations

1. **`hash()` builtin Python est randomisé par process** (PEP 456) — utiliser `hashlib.sha256(question_id)` pour le seed de shuffle des options, jamais `hash()` nu (https://docs.python.org/3/using/cmdline.html#envvar-PYTHONHASHSEED).
2. **`repeat_penalty` par défaut de llama.cpp = 1.1, pas 1.0** — à repasser explicitement à `1.0` pour un greedy réellement neutre, sinon le decoding n'est pas purement argmax.
3. **`seed=-1` par défaut** (aléatoire) côté llama.cpp/LM Studio — toujours fixer une valeur entière explicite si un semblant de reproductibilité est recherché.
4. **La reproductibilité bit-exacte n'est jamais garantie sur GPU**, même temp=0 + seed fixe + repeat_penalty=1.0 — documenter ce fait dans le README plutôt que de le découvrir en re-run.
5. **Les presets LM Studio peuvent ignorer silencieusement les paramètres de la requête** (https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1389) — tester explicitement que `GREEDY_PARAMS` et le schéma JSON (V5) sont bien appliqués, ne pas supposer.
6. **Deux pages officielles Google se contredisent sur le support du rôle `system` pour Gemma** — laisser le chat template embarqué dans le GGUF (appliqué par LM Studio) faire foi, pas la doc web ; tester les deux formats empiriquement.
7. **L'ordre des champs dans un schéma JSON structuré compte** (débat Tam et al. 2024 vs dottxt) — si un CoT est souhaité en V5, placer `reasoning` avant `answer` dans le schéma.
8. **Pas de seuil rapidfuzz universel validé** — 90 est une convention d'ingénierie convergente (recherche web + pratique déjà adoptée dans ce projet), pas un résultat scientifique ; le justifier empiriquement sur un échantillon annoté à la main si possible.
9. **La règle « contains » sans garde anti-négation produit des faux positifs** — toujours vérifier l'absence de token de négation dans une fenêtre avant le span matché (ex. « not Mercury »).
10. **`ai_correct` doit être nullable**, pas juste `bool` — `NULL` pour `unparseable` évite de mélanger silencieusement échec de connaissance et échec de format dans le dénominateur de l'accuracy.
11. **Le grading fuzzy ne se fait pas en SQL/dbt** — le calculer une fois en Python à l'ingestion ; dbt n'agrège que des colonnes déjà gradées.
12. **Toujours exclure le premier appel (warm-up)** des statistiques de latence, et exécuter en strictement séquentiel pour une mesure de latence par appel propre (pas de queuing/batching concurrent qui la fausse).
13. **Comparer les variantes sur `response_time` brut seul est trompeur** — les longueurs de prompt (few-shot vs nu) et de sortie (JSON compact vs texte avec préambule) diffèrent structurellement ; toujours aussi rapporter le temps par token généré.
14. **Catégories à petit `n`** : calculer l'IC de Wilson quand même (valide à petit n) mais flaguer explicitement `n_flag_low`, ne jamais présenter un pourcentage isolé sans son IC pour une catégorie sous la règle de pouce (~n≥97 pour ±10 pts à 95%, ou au minimum n≥30 pour l'approximation).
15. **OpenTDB n'a pas d'ID natif** — utiliser l'ID déterministe déjà spécifié dans `01_opentdb.md` §8 (`sha256(category + type + difficulty + question + correct_answer)` normalisés) comme `question_id`, condition préalable au shuffle déterministe (§2.2) et à la jointure silver↔answers.

---

## Spécification de référence

### Table des variantes de prompt

| ID | System | Template utilisateur (résumé) | Format de sortie | Parser (priorité) |
|---|---|---|---|---|
| V1 | aucun | `{question}` seule, pas d'options | texte libre | normalize→exact→fuzzy(≥90)→contains(garde négation)→wrong/unparseable |
| V2 | aucun | Question + A–D (ou True/False), « letter/word only » | 1 lettre (QCM) / 1 mot (booléen) | regex ancrée début → texte d'option (exact/fuzzy/contains) → unparseable |
| V3 | rôle « rigorous quiz solver » | style simple-evals, cue final `Answer:` | bloc texte se terminant par `Answer: X` | `ANSWER_PATTERN_MULTICHOICE` exact → fallback V2 → texte d'option |
| V4 | aucun | 2 exemples few-shot fixes + question cible, même format que V3 | idem V3 | identique à V3 |
| V5 | rôle « JSON only » | Question + A–D, schéma JSON contraint | `{"answer": "A"}` | `json.loads` → `.answer` → validation enum ; fallback texte libre si JSON invalide |

(V5b optionnelle : `{"reasoning": "...", "answer": "A"}`, ablation sur l'ordre des champs.) Chaque variante existe en version QCM (4 options, A–D) et booléenne (2 options, généralement en mots True/False plutôt qu'en lettres, sauf V2 pour lequel une sous-variante lettrée A/B est possible en ablation).

### Arbre de décision de notation (pseudocode consolidé)

```
grade_answer(raw_response, question, options_order, correct_letter, variant):
    if variant.is_mc:
        letter = extract_letter(raw_response, variant.is_json)      # regex ancrée / "Answer:" / json.answer
        if letter is not None:
            return CORRECT("letter") if letter == correct_letter else WRONG
        matched_option = match_against_option_texts(raw_response, options_order)
        # -> tries exact, then fuzzy>=90, then contains-with-negation-guard, in that order
        if matched_option is not None:
            grade = matched_option.method   # "exact" | "fuzzy" | "contains"
            return CORRECT(grade) if matched_option.letter == correct_letter else WRONG
        return UNPARSEABLE

    if variant.is_boolean:
        token = normalize(raw_response)
        if token in {"true", "false"}:
            return CORRECT("exact") if (token == "true") == gold_bool else WRONG
        if token in {"yes", "y", "t", "no", "n", "f"}:
            return CORRECT("fuzzy") if maps_to(token) == gold_bool else WRONG
        extracted = find_unambiguous_bool_token(token)
        if extracted is not None:
            return CORRECT("contains") if extracted == gold_bool else WRONG
        return UNPARSEABLE

    if variant.is_freetext:  # V1
        norm_resp, norm_gold = normalize(raw_response), normalize(gold_answer)
        if not norm_resp or looks_like_refusal(norm_resp):
            return UNPARSEABLE
        if norm_resp == norm_gold:
            return CORRECT("exact")
        if fuzzy_ratio(norm_resp, norm_gold) >= 90:
            return CORRECT("fuzzy")
        if len(norm_gold) >= 3 and norm_gold in norm_resp and not negation_before(norm_resp, norm_gold):
            return CORRECT("contains")
        return WRONG

# CORRECT(g) -> grade=g, ai_correct=True
# WRONG      -> grade="wrong", ai_correct=False
# UNPARSEABLE -> grade="unparseable", ai_correct=NULL
```

### Tables gold (liste condensée — détail §7)

`gold_accuracy_by_model_variant` · `gold_accuracy_by_category_difficulty` · `gold_accuracy_vs_chance_by_type` · `gold_unparseable_rate_by_variant` · `gold_latency_distribution_by_variant_model` · `gold_hardest_categories` · `gold_consistency_cross_variant` · `gold_difficulty_calibration` · `gold_answer_length_vs_correctness` · `gold_drift_over_run_order`

---

## Sources

**Frameworks d'évaluation / format de prompt QCM**
- EleutherAI lm-evaluation-harness, `docs/new_task_guide.md` — https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/new_task_guide.md
- OpenAI simple-evals — https://github.com/openai/simple-evals (`common.py`, `mmlu_eval.py`)
- Inspect AI (UK AISI) — https://inspect.aisi.org.uk/reference/inspect_ai.solver.html, https://inspect.aisi.org.uk/reference/inspect_ai.scorer.html, source https://github.com/UKGovernmentBEIS/inspect_ai

**Biais de position en QCM**
- Zheng et al., *"Large Language Models Are Not Robust Multiple Choice Selectors"*, ICLR 2024 Spotlight — https://arxiv.org/abs/2309.03882
- Robinson, Rytting, Wingate, *"Leveraging Large Language Models for Multiple Choice Question Answering"*, arXiv 2022 — https://arxiv.org/abs/2210.12353
- *"Look at the Text: Instruction-Tuned Language Models are More Robust Multiple Choice Selectors than You Think"*, 2024 — https://arxiv.org/html/2404.08382v1
- *"Metric assessment protocol in the context of answer fluctuation on MCQ tasks"*, 2025 — https://arxiv.org/pdf/2507.15581 (NON VÉRIFIÉ en détail)

**Déterminisme / greedy decoding**
- llama.cpp server README — https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- LM Studio docs, paramètres — https://lmstudio.ai/docs/typescript/llm-prediction/parameters
- LM Studio bug tracker (presets ignorant les params de requête) — https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1389
- Non-déterminisme GPU : https://github.com/ggml-org/llama.cpp/issues/10197, /issues/7052, /issues/4458 ; https://arxiv.org/html/2511.00025 ; https://www.startuphub.ai/ai-news/ai-research/2025/the-real-reason-for-llm-inference-nondeterminism/
- Python hash randomization — https://docs.python.org/3/using/cmdline.html#envvar-PYTHONHASHSEED

**Gemma prompting**
- Gemma 4 model card — https://ai.google.dev/gemma/docs/core/model_card_4
- Gemma formatting (générique, potentiellement obsolète) — https://ai.google.dev/gemma/docs/core/prompt-structure
- Gemma 4 12B QAT sur LM Studio — https://lmstudio.ai/models/google/gemma-4-12b-qat
- Gemma 4 12B QAT GGUF — https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf

**Structured output / JSON-schema-constrained decoding**
- Tam et al., *"Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models"*, EMNLP 2024 Industry — https://arxiv.org/abs/2408.02442, https://aclanthology.org/2024.emnlp-industry.91/
- Réfutation dottxt — https://blog.dottxt.ai/say-what-you-mean.html, résumé tiers https://dylancastillo.co/posts/say-what-you-mean-sometimes.html
- Suivi 2025 — https://arxiv.org/html/2501.10868v1

**Grading texte libre**
- SQuAD evaluation script (canonique) — https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/evaluate-v2.0.py
- rapidfuzz docs — https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html

**Statistiques**
- Intervalle de Wilson — https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval
- statsmodels `proportion_confint` — https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportion_confint.html
- statsmodels `mcnemar` — https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html
- Berg-Kirkpatrick, Burkett & Klein, EMNLP 2012 — https://aclanthology.org/D12-1091/
- Dror et al., ACL 2018 — https://aclanthology.org/P18-1128/ (arXiv https://arxiv.org/pdf/1809.01448)
- Taille d'échantillon — https://online.stat.psu.edu/stat200/lesson/8/8.1/8.1.1/8.1.1.3, https://stats.libretexts.org/Bookshelves/Introductory_Statistics/Mostly_Harmless_Statistics_(Webb)/07:_Confidence_Intervals_for_One_Population/7.03:_Sample_Size_Calculation_for_a_Proportion

**Temps de réponse**
- Anyscale, métriques latence/débit LLM — https://docs.anyscale.com/llm/serving/benchmarking/metrics
- https://dev.to/wheynelau/how-to-benchmark-llm-inference-performance-ttft-itl-and-throughput-metrics-416p
- https://arxiv.org/pdf/2507.09019
- https://redis.io/blog/llm-speed-benchmarks/
- Warm-up : *Bench360* https://arxiv.org/pdf/2511.16682 ; *LLM Inference at the Edge* https://arxiv.org/pdf/2603.23640

**OpenTDB (voir aussi `01_opentdb.md` pour le détail complet, testé en live le 2026-09-10)**
- https://opentdb.com/api_config.php

**Contexte projet interne (déjà vérifié, réutilisé ici)**
- `01_opentdb.md` — référence API OpenTDB (pool verified, pas d'ID natif, encodages, rate limiting)
- `05_python_tooling.md` — stack Python (`normalize.py`, seuils rapidfuzz, modèles Pydantic, CLI Typer, pipeline bronze/silver/gold)
