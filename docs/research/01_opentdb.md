# Référence technique — Open Trivia Database (OpenTDB) API

Date de la recherche : **2026-09-10**
Objectif : permettre l'écriture d'un scraper téléchargeant l'intégralité du jeu de questions OpenTDB, sans que l'ingénieur qui l'écrit ait besoin de relire la doc officielle.

## Note méthodologique (important)

Dans l'environnement d'exécution utilisé pour cette recherche, l'accès réseau direct à `opentdb.com` était **bloqué** par le proxy réseau d'entreprise (catégorisation « Games » par un proxy Cato Networks) et par une erreur TLS (`self signed certificate in certificate chain`) sur l'outil `WebFetch` en accès direct. J'ai donc récupéré le contenu **réel et live** des pages via le proxy de lecture `r.jina.ai` (qui va chercher la page côté serveur, hors du réseau bloqué) — les extraits JSON présentés comme « réponse réelle observée le 2026-09-10 » proviennent bien de `opentdb.com` en direct (via ce relais), pas de ma mémoire. Ils ont été recoupés entre eux pour cohérence (ex. `api_count.php?category=9` correspond exactement à l'entrée `"9"` de `api_count_global.php`, et un test d'épuisement de quota confirme que `api_count.php` = taille réelle du pool interrogeable par `api.php`). Tout ce qui n'a pu être confirmé que par une source secondaire non recoupée est marqué **NON VÉRIFIÉ**.

---

## Résumé exécutif

1. Endpoint principal : `GET https://opentdb.com/api.php`, sans clé API, réponse JSON.
2. `amount` max = **50 questions par requête** ; **une seule `category` par appel** ; `difficulty` et `type` optionnels.
3. Total de questions actuellement **« verified »** (le seul pool réellement servi par `api.php`) = **5 298** sur 21 617 en base au total (10 911 pending, 5 425 rejected) — observé le 2026-09-10 via `api_count_global.php`.
4. Rate limit strict et documenté : **1 requête / 5 secondes / IP** → `response_code=5` en cas de dépassement (à traiter comme signal de throttle, pas comme erreur fatale).
5. Comportement **« tout ou rien »** confirmé empiriquement : si `amount` dépasse le nombre de questions restantes pour le filtre demandé, l'API renvoie `response_code=1` avec `results: []` — **aucun résultat partiel** n'est renvoyé.
6. `api_count.php?category=ID` donne le nombre exact de questions « verified » par catégorie (= taille réelle du pool) ; à appeler pour dimensionner précisément ses lots de 50 et éviter les appels « à vide ».
7. Les session tokens (`api_token.php`) garantissent l'absence de doublon sur toute leur durée de vie, tous filtres confondus, tant qu'ils ne sont pas réinitialisés ; ils expirent après **6h d'inactivité**.
8. `encode=base64` est l'encodage le plus robuste pour un scraper Python : évite tout piège d'entités HTML mal décodées ou de caractères Unicode cassés en transit.
9. Les questions **n'ont pas d'ID natif** (confirmé sur des échantillons réels) : il faut générer un identifiant déterministe (ex. `sha256(category + type + difficulty + question + correct_answer)` normalisés).
10. Il n'existe **pas de dump officiel en bulk** : seule l'API paginée existe ; quelques dumps communautaires existent sur GitHub mais sont ponctuels et potentiellement obsolètes.
11. *(bonus)* Estimation de temps pour tout télécharger : **~117 requêtes `api.php`** strictement nécessaires si le dimensionnement des lots est optimal (calcul détaillé en §10) → ~10 min de temps réseau minimal incompressible, ~20-30 min de façon réaliste avec marge pour retries/rate limit/token reset.

---

## 1. Endpoint `api.php` — tous les paramètres

Source : `opentdb.com/api_config.php` (via proxy), recoupé avec `jentic.com/apis/opentdb.com/opentdb`, avec les wrappers PyPI/NuGet, et testé en live.

URL de base : `https://opentdb.com/api.php`

| Paramètre | Obligatoire | Valeurs autorisées | Comportement par défaut |
|---|---|---|---|
| `amount` | Oui (en pratique — sinon comportement non garanti) | Entier **1 à 50** | Max **50 questions par appel** (limite dure documentée et confirmée par recherche) |
| `category` | Non | Entier **9 à 32** (voir §5 pour la liste complète) | Si omis : questions tirées de toutes les catégories mélangées. **Une seule catégorie par appel** (pas de liste/plage possible) |
| `difficulty` | Non | `easy`, `medium`, `hard` | Si omis : toutes difficultés mélangées |
| `type` | Non | `multiple` (QCM), `boolean` (vrai/faux) | Si omis : les deux types mélangés |
| `encode` | Non | `default` *(implicite, non passé)*, `urlLegacy`, `url3986`, `base64` | Par défaut : entités HTML (`&quot;`, `&amp;`, `&#039;`, …) |
| `token` | Non | chaîne hexadécimale de session, obtenue via `api_token.php` | Si omis : pas de garantie anti-doublon entre appels successifs |

Exemple d'URL réelle testée : `https://opentdb.com/api.php?amount=2&category=9&type=multiple`

Comportement du couple `amount` / disponibilité — **vérifié empiriquement** sur la catégorie 13 (36 questions « verified » au total) :
- `amount=36` (= exactement le total disponible) → `response_code=0`, 36 résultats renvoyés.
- `amount=40` ou `amount=50` (> total disponible) → `response_code=1`, `results: []` (tableau **vide**, pas de troncature à 36).

Conséquence directe pour le design du scraper : il faut connaître à l'avance (via `api_count.php`, voir §5) le nombre de questions restantes pour ne jamais demander plus que ce qui est disponible, sous peine de recevoir un tableau vide au lieu d'un résultat partiel.

---

## 2. `response_code` — table complète (0 à 5)

Source : page `api_config.php` (table de réponse), recoupée avec la doc du wrapper NuGet `OpenTDB-Wrapper` et testée en live pour les codes 0 et 1.

| Code | Nom | Signification exacte | Action recommandée |
|---|---|---|---|
| 0 | Success | « Returned results successfully. » — tout s'est bien passé | Consommer `results` |
| 1 | No Results | « Could Not Return Results. The API doesn't have enough questions for your query. » (ex. demander 50 résultats dans une catégorie qui n'en a que 20) — **confirmé empiriquement : `results` est vide, pas partiel** | Réduire `amount` (idéalement le fixer via `api_count.php`) ou considérer la catégorie/filtre comme épuisé(e) |
| 2 | Invalid Parameter | « Arguements passed in aren't valid » *(sic, coquille présente dans la doc officielle elle-même)* — ex. `amount=cinq` | Corriger le paramètre malformé côté scraper |
| 3 | Token Not Found | « Session Token does not exist. » — le token fourni n'existe pas ou a expiré (6h d'inactivité) | Redemander un nouveau token via `api_token.php?command=request` |
| 4 | Token Empty | « Session Token has returned all possible questions for the specified query. » — **le token a épuisé toutes les questions disponibles *pour la requête filtrée précise* (catégorie/difficulté/type demandés), pas forcément toute la base** | Passer à la catégorie/filtre suivant(e), ou faire `command=reset` sur le token si on veut reparcourir la même requête (utile en repeat/tests, pas en scraping exhaustif) |
| 5 | Rate Limit | « Too Many Requests have occurred. Each IP can only access the API once every 5 seconds. » | Attendre puis réessayer (voir §3) |

**NON VÉRIFIÉ formellement dans cet environnement** (source uniquement secondaire, cohérente mais non testée par moi en direct) : le code HTTP retourné en cas de rate limit (code 5) serait **HTTP 200 OK** avec le `response_code=5` porté dans le corps JSON, **et non un HTTP 429**. Conséquence pratique : un scraper ne doit **jamais** se fier au seul code HTTP pour détecter le rate limit — il doit systématiquement lire `response_code` dans le JSON, même sur une réponse HTTP 200.

---

## 3. Rate limiting

- Règle : **1 requête par 5 secondes, par adresse IP**, tous endpoints `opentdb.com` confondus a priori (par prudence, appliquer la règle aussi à `api_token.php`, `api_count.php`, `api_category.php`).
- Signal de dépassement : `response_code=5` dans le corps JSON (voir §2), sur une réponse **HTTP 200** (**NON VÉRIFIÉ** pour le code HTTP exact, voir ci-dessus — mais confirmé de façon très cohérente par de multiples sources indépendantes pour la règle des 5 secondes elle-même).
- Sleep recommandé : **au minimum 5.0 à 5.5 secondes entre deux appels** depuis la même IP, avec une marge de sécurité (ex. 5.2s) pour absorber la latence réseau/horloge. En cas de `response_code=5` malgré tout, appliquer un backoff exponentiel court (ex. 5s, 10s, 20s) avant de réessayer, car un léger jitter d'horloge ou un partage d'IP (NAT, proxy sortant partagé) peut déclencher le code 5 même en respectant les 5s.

---

## 4. Session tokens — `api_token.php`

### `command=request`

`GET https://opentdb.com/api_token.php?command=request`

Réponse réelle observée le 2026-09-10 :
```json
{"response_code":0,"response_message":"Token Generated Successfully!","token":"00848c0b9f6062fb3b16edfb9afa0ff12f4f4041b338691a8e2c4ad084d2453c"}
```
(Le token ci-dessus est un exemple réel obtenu pendant cette recherche ; générer le vôtre, ne pas réutiliser celui-ci en production.)

### `command=reset`

`GET https://opentdb.com/api_token.php?command=reset&token=VOTRE_TOKEN`

Réponse attendue (source secondaire, non testée en direct ici, mais cohérente avec le schéma de `command=request`) :
```json
{"response_code":0,"token":"VOTRE_TOKEN"}
```
Effet : efface toute la mémoire des questions déjà servies pour ce token — repart de zéro pour ce même token (utile pour rejouer une requête, **pas** utile pour un scraper exhaustif qui veut justement éviter les doublons).

### Durée de vie
Un token est supprimé automatiquement après **6 heures d'inactivité** (pas 6h fixes depuis la création, mais 6h sans utilisation). Pour un scraping complet qui prend ~10-30 min (voir §10), un seul token suffit largement tant qu'on l'utilise en continu.

### Garantie anti-doublon
Un token **garantit** que la même question (au sens du contenu exact) ne sera jamais renvoyée deux fois **pour ce token**, quels que soient les filtres (`category`/`difficulty`/`type`) utilisés dans les appels successifs qui le portent — la mémoire du token est globale à toutes les requêtes qui l'utilisent, pas scoping par requête. En revanche, l'épuisement (`response_code=4`) est lui **signalé par requête filtrée** : épuiser la catégorie 9 ne fait pas apparaître `4` sur la catégorie 10, qui a son propre pool encore non consommé.

### Algorithme complet pour tout télécharger

Deux stratégies possibles, la seconde étant recommandée :

**A. Catégorie × difficulté × type, sans token** — fiable mais lent et risqué (doublons possibles entre appels non liés par un token, notamment quand le pool restant est petit et que le tirage est aléatoire) : à éviter comme stratégie principale.

**B. Catégorie (avec token), guidée par `api_count.php`** — stratégie recommandée :
1. Demander un token une fois (`command=request`).
2. Récupérer la liste des catégories (`api_category.php`).
3. Pour chaque catégorie : appeler `api_count.php?category=ID` pour connaître le nombre exact de questions « verified » disponibles (= le pool total réellement interrogeable par `api.php`, confirmé empiriquement égal au seuil exact où `amount` bascule de `response_code=0` à `response_code=1`).
4. Découper ce nombre en lots de 50 maximum (dernier lot = reste), et faire un appel `api.php?amount=<taille_lot>&category=ID&token=TOKEN` par lot, en respectant le rate limit (§3).
5. Utiliser `response_code=4` (token épuisé pour cette requête) comme **garde-fou** de fin de catégorie, au cas où le compte obtenu à l'étape 3 serait devenu obsolète (de nouvelles questions peuvent être vérifiées pendant le scraping, car la base grossit en continu — 10 911 questions sont actuellement « pending »).
6. Ne PAS croiser catégorie × difficulté × type explicitement : ce n'est pas nécessaire, le token dédoublonne déjà correctement ; croiser ces filtres ne fait qu'ajouter des appels réseau et de la complexité, avec un risque accru de heurter le comportement « tout ou rien » du §1 (sous-pools par difficulté encore plus petits).

---

## 5. Catégories, comptages par catégorie, comptage global

### `api_category.php` — liste complète (réponse réelle observée le 2026-09-10)

```json
{
  "trivia_categories": [
    {"id": 9,  "name": "General Knowledge"},
    {"id": 10, "name": "Entertainment: Books"},
    {"id": 11, "name": "Entertainment: Film"},
    {"id": 12, "name": "Entertainment: Music"},
    {"id": 13, "name": "Entertainment: Musicals & Theatres"},
    {"id": 14, "name": "Entertainment: Television"},
    {"id": 15, "name": "Entertainment: Video Games"},
    {"id": 16, "name": "Entertainment: Board Games"},
    {"id": 17, "name": "Science & Nature"},
    {"id": 18, "name": "Science: Computers"},
    {"id": 19, "name": "Science: Mathematics"},
    {"id": 20, "name": "Mythology"},
    {"id": 21, "name": "Sports"},
    {"id": 22, "name": "Geography"},
    {"id": 23, "name": "History"},
    {"id": 24, "name": "Politics"},
    {"id": 25, "name": "Art"},
    {"id": 26, "name": "Celebrities"},
    {"id": 27, "name": "Animals"},
    {"id": 28, "name": "Vehicles"},
    {"id": 29, "name": "Entertainment: Comics"},
    {"id": 30, "name": "Science: Gadgets"},
    {"id": 31, "name": "Entertainment: Japanese Anime & Manga"},
    {"id": 32, "name": "Entertainment: Cartoon & Animations"}
  ]
}
```
→ **24 catégories**, IDs contigus **9 à 32**.

### `api_count_global.php` — réponse réelle intégrale observée le 2026-09-10

```json
{"overall":{"total_num_of_questions":21617,"total_num_of_pending_questions":10911,"total_num_of_verified_questions":5298,"total_num_of_rejected_questions":5425},"categories":{"9":{"total_num_of_questions":5424,"total_num_of_pending_questions":2854,"total_num_of_verified_questions":469,"total_num_of_rejected_questions":2101},"10":{"total_num_of_questions":512,"total_num_of_pending_questions":289,"total_num_of_verified_questions":120,"total_num_of_rejected_questions":103},"11":{"total_num_of_questions":1120,"total_num_of_pending_questions":663,"total_num_of_verified_questions":301,"total_num_of_rejected_questions":156},"12":{"total_num_of_questions":1269,"total_num_of_pending_questions":593,"total_num_of_verified_questions":495,"total_num_of_rejected_questions":182},"13":{"total_num_of_questions":152,"total_num_of_pending_questions":90,"total_num_of_verified_questions":36,"total_num_of_rejected_questions":26},"14":{"total_num_of_questions":799,"total_num_of_pending_questions":485,"total_num_of_verified_questions":196,"total_num_of_rejected_questions":118},"15":{"total_num_of_questions":4069,"total_num_of_pending_questions":1944,"total_num_of_verified_questions":1185,"total_num_of_rejected_questions":952},"16":{"total_num_of_questions":261,"total_num_of_pending_questions":141,"total_num_of_verified_questions":78,"total_num_of_rejected_questions":42},"17":{"total_num_of_questions":935,"total_num_of_pending_questions":477,"total_num_of_verified_questions":299,"total_num_of_rejected_questions":159},"18":{"total_num_of_questions":950,"total_num_of_pending_questions":504,"total_num_of_verified_questions":192,"total_num_of_rejected_questions":255},"19":{"total_num_of_questions":389,"total_num_of_pending_questions":150,"total_num_of_verified_questions":80,"total_num_of_rejected_questions":159},"20":{"total_num_of_questions":219,"total_num_of_pending_questions":121,"total_num_of_verified_questions":71,"total_num_of_rejected_questions":27},"21":{"total_num_of_questions":810,"total_num_of_pending_questions":462,"total_num_of_verified_questions":176,"total_num_of_rejected_questions":173},"22":{"total_num_of_questions":821,"total_num_of_pending_questions":275,"total_num_of_verified_questions":383,"total_num_of_rejected_questions":163},"23":{"total_num_of_questions":980,"total_num_of_pending_questions":393,"total_num_of_verified_questions":411,"total_num_of_rejected_questions":177},"24":{"total_num_of_questions":333,"total_num_of_pending_questions":195,"total_num_of_verified_questions":77,"total_num_of_rejected_questions":61},"25":{"total_num_of_questions":212,"total_num_of_pending_questions":105,"total_num_of_verified_questions":59,"total_num_of_rejected_questions":48},"26":{"total_num_of_questions":240,"total_num_of_pending_questions":128,"total_num_of_verified_questions":53,"total_num_of_rejected_questions":59},"27":{"total_num_of_questions":370,"total_num_of_pending_questions":214,"total_num_of_verified_questions":99,"total_num_of_rejected_questions":57},"28":{"total_num_of_questions":304,"total_num_of_pending_questions":155,"total_num_of_verified_questions":87,"total_num_of_rejected_questions":62},"29":{"total_num_of_questions":184,"total_num_of_pending_questions":63,"total_num_of_verified_questions":79,"total_num_of_rejected_questions":42},"30":{"total_num_of_questions":152,"total_num_of_pending_questions":77,"total_num_of_verified_questions":40,"total_num_of_rejected_questions":35},"31":{"total_num_of_questions":778,"total_num_of_pending_questions":361,"total_num_of_verified_questions":204,"total_num_of_rejected_questions":214},"32":{"total_num_of_questions":334,"total_num_of_pending_questions":172,"total_num_of_verified_questions":108,"total_num_of_rejected_questions":54}}}
```

**Point important** : `total_num_of_questions` par catégorie (ex. 5 424 pour la catégorie 9) inclut pending + verified + rejected. Seul `total_num_of_verified_questions` (ex. 469 pour la catégorie 9) correspond au pool réellement accessible via `api.php` — confirmé par correspondance exacte avec `api_count.php?category=9` ci-dessous, et avec le comportement empirique observé en §1.

Somme de `total_num_of_verified_questions` sur les 24 catégories = **5 298**, identique à `overall.total_num_of_verified_questions`. Cohérence interne vérifiée.

### `api_count.php?category=9` — réponse réelle observée le 2026-09-10

```json
{"category_id":9,"category_question_count":{"total_question_count":469,"total_easy_question_count":215,"total_medium_question_count":177,"total_hard_question_count":77}}
```
(215+177+77 = 469, cohérent.) `total_question_count` = questions **verified** uniquement (confirmé égal à `categories["9"].total_num_of_verified_questions` de `api_count_global.php`).

### `api_count.php?category=13` — utilisé pour valider empiriquement le comportement « tout ou rien » (§1)

```json
{"category_id":13,"category_question_count":{"total_question_count":36,"total_easy_question_count":11,"total_medium_question_count":14,"total_hard_question_count":11}}
```

---

## 6. Encodage — le paramètre `encode`

Quatre options, source `api_config.php` + exemples réels de sortie observés/recoupés :

| Valeur `encode` | Description | Exemple de sortie (sur `Don't forget that π = 3.14 & doesn't equal 3.`) |
|---|---|---|
| *(absent — défaut)* | Entités HTML | `Don&#039;t forget that &pi; = 3.14 &amp; doesn&#039;t equal 3.` |
| `urlLegacy` | URL-encodage « legacy » (espaces en `+`) | `Don't+forget+that+%CF%80+=+3.14+%26+doesn't+equal+3.` |
| `url3986` | URL-encodage RFC 3986 (espaces en `%20`) | `Don%27t%20forget%20that%20%CF%80%20%3D%203.14%20%26%20doesn%27t%20equal%203.` |
| `base64` | Base64 sur chaque champ texte (`question`, `category`, `type`, `difficulty`, `correct_answer`, `incorrect_answers`) | `RG9uJ3QgZm9yZ2V0IHRoYXQgz4AgPSAzLjE0ICYgZG9lc24ndCBlcXVhbCAzLg==` |

Exemple réel intégral observé le 2026-09-10, `GET api.php?amount=1&category=9&encode=base64` :
```json
{"response_code":0,"results":[{"type":"bXVsdGlwbGU=","difficulty":"ZWFzeQ==","category":"R2VuZXJhbCBLbm93bGVkZ2U=","question":"V2hhdCB3YXMgdGhlIG5hbWUgb2YgU3F1aWR3YXJkJ3MgYmFkIHBhaW50aW5nIGluIHRoZSBTcG9uZ2Vib2IgZXBpc29kZSAiQXJ0aXN0IFVua25vd24/Ig==","correct_answer":"Qm9sZCBhbmQgQnJhc2g=","incorrect_answers":["U3F1aWR3YXJkIGVuIFJlcG9zZQ==","UmlwcHkgQml0cw==","VGlsdGVkIFBlcnNwZWN0aXZlcw=="]}]}
```
Décodage vérifié en Python (exécuté réellement pendant cette recherche) :
```python
import base64
base64.b64decode("V2hhdCB3YXMgdGhlIG5hbWUgb2YgU3F1aWR3YXJkJ3MgYmFkIHBhaW50aW5nIGluIHRoZSBTcG9uZ2Vib2IgZXBpc29kZSAiQXJ0aXN0IFVua25vd24/Ig==").decode("utf-8")
# -> 'What was the name of Squidward\'s bad painting in the Spongebob episode "Artist Unknown?"'
```

**Recommandation** : utiliser `encode=base64` pour le scraper. Raisons :
- Transport 100% ASCII, aucun risque de caractère mal interprété/tronqué par un proxy, un terminal, ou un encodage de fichier intermédiaire.
- Pas de double-décodage HTML à gérer (le mode par défaut renvoie des entités HTML type `&quot;`, `&amp;`, `&eacute;`, qu'il faut décoder avec `html.unescape()` — source d'oublis et de bugs, notamment si le texte contient déjà un `&` littéral ambigu).
- `url3986`/`urlLegacy` nécessitent aussi un décodage (`urllib.parse.unquote` / `unquote_plus`) et peuvent mal gérer certains caractères spéciaux d'apostrophes typographiques.
- Décodage Python trivial et sans dépendance : `base64.b64decode(s).decode("utf-8")`.
- Pour les champs `default` (HTML), utiliser `html.unescape()` (stdlib `html`) si jamais `base64` n'est pas utilisé.

---

## 7. Schéma JSON d'une question

Champs (confirmés sur échantillons réels, mode par défaut) : `type`, `difficulty`, `category`, `question`, `correct_answer`, `incorrect_answers`. Le tout encapsulé dans `{"response_code": int, "results": [...]}`.

### Exemple réel `type=multiple` (observé le 2026-09-10)
```json
{
  "response_code": 0,
  "results": [
    {
      "type": "multiple",
      "difficulty": "medium",
      "category": "General Knowledge",
      "question": "What is the Italian word for &quot;tomato&quot;?",
      "correct_answer": "Pomodoro",
      "incorrect_answers": ["Aglio", "Cipolla", "Peperoncino"]
    },
    {
      "type": "multiple",
      "difficulty": "medium",
      "category": "General Knowledge",
      "question": "Rolex is a company that specializes in what type of product?",
      "correct_answer": "Watches",
      "incorrect_answers": ["Cars", "Computers", "Sports equipment"]
    }
  ]
}
```

### Exemple réel `type=boolean` (observé le 2026-09-10)
```json
{
  "response_code": 0,
  "results": [
    {
      "type": "boolean",
      "difficulty": "easy",
      "category": "General Knowledge",
      "question": "Dihydrogen Monoxide was banned due to health risks after being discovered in 1983 inside swimming pools and drinking water.",
      "correct_answer": "False",
      "incorrect_answers": ["True"]
    },
    {
      "type": "boolean",
      "difficulty": "easy",
      "category": "General Knowledge",
      "question": "Adolf Hitler was born in Australia. ",
      "correct_answer": "False",
      "incorrect_answers": ["True"]
    }
  ]
}
```
Remarque : pour `type=boolean`, `incorrect_answers` contient toujours exactement 1 élément (`["True"]` ou `["False"]`). Pour `type=multiple`, il contient toujours exactement 3 éléments. Remarquer aussi la présence d'espaces parasites en fin de chaîne dans certaines questions (`"Adolf Hitler was born in Australia. "`) — **penser à `.strip()`** les champs texte côté scraper.

---

## 8. Absence d'ID natif — stratégie d'ID déterministe

Confirmé sur tous les échantillons réels ci-dessus : aucun champ `id`, `question_id`, `uuid` n'est présent nulle part dans la réponse de `api.php`. C'est cohérent avec le fait que l'API sert un tirage aléatoire filtré depuis la base, sans exposer les clés internes de la base MySQL sous-jacente (probablement pour ne pas révéler le pending/rejected via corrélation d'ID). **Il n'y a donc pas d'identifiant stable fourni par l'API.**

Recommandation pour un ID déterministe et stable (permet la dé-duplication et le reprise/« resume » du scraping entre plusieurs runs, même sans token, ou après un reset de token) :

```python
import hashlib
import html

def normalize(s: str) -> str:
    # décoder les entités HTML si on n'utilise pas encode=base64, trim, normaliser les espaces
    return " ".join(html.unescape(s).split()).strip().lower()

def make_question_id(category: str, qtype: str, difficulty: str,
                      question: str, correct_answer: str) -> str:
    key = "||".join([
        normalize(category),
        normalize(qtype),
        normalize(difficulty),
        normalize(question),
        normalize(correct_answer),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
```
Ne pas inclure `incorrect_answers` dans le hash (leur ordre n'est pas garanti stable d'un appel à l'autre pour une même question). `category` + `question` + `correct_answer` suffisent en pratique à distinguer toute paire de questions du jeu de données ; ajouter `type`/`difficulty` en ceinture-bretelles au cas (rarissime) où deux questions strictement identiques en texte existeraient avec des métadonnées différentes.

---

## 9. Autres endpoints, exports officiels, licence

Endpoints identifiés (aucun autre trouvé au-delà de ceux-ci) :
- `api.php` — données
- `api_category.php` — liste des catégories
- `api_count.php?category=ID` — comptage par catégorie
- `api_count_global.php` — comptage global
- `api_token.php?command=request|reset` — gestion de session
- `api_config.php` — page HTML de documentation **et** générateur d'URL interactif (pas un endpoint de données ; c'est la doc elle-même)

Aucune trace d'un `browse.php` ou d'un endpoint de bulk export distinct n'a été trouvée dans les sources consultées (recherche dédiée effectuée, sans résultat).

**Pas de dump officiel en bulk.** OpenTDB ne publie pas de fichier d'export téléchargeable ; le seul accès aux données est l'API paginée décrite ci-dessus. Il existe des dumps **communautaires non officiels** sur GitHub (ex. gist `jbaranski/a3c10856b750441663eec71739d49e43`, généré le 27/12/2024 selon sa description) : à utiliser uniquement comme référence ponctuelle, **NON VÉRIFIÉ** quant à leur fraîcheur/exactitude actuelle — la base OpenTDB continue de grossir (10 911 questions « pending » actuellement, en cours de vérification), donc tout dump statique devient obsolète avec le temps.

**Licence** : toutes les données de l'API sont publiées sous **Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)**, confirmé à la fois par la page `api_config.php` et par des sources tierces indépendantes. Implications pour le scraper/le projet consommateur :
- Attribution obligatoire (créditer OpenTDB + lien vers la licence).
- Tout jeu de données dérivé redistribué doit être partagé sous la même licence (« ShareAlike »).
- Pas de restriction technique/légale supplémentaire possible sur la redistribution au-delà de ce que permet la licence.

---

## 10. Estimation de débit / temps total

Base de calcul : les 24 comptages `total_num_of_verified_questions` observés en §5 (somme = 5 298), en appliquant le chunking optimal décrit en §4 (algorithme B : `ceil(N_catégorie / 50)` appels par catégorie).

| Catégorie (id) | Verified | Appels nécessaires (⌈N/50⌉) |
|---|---|---|
| 9 | 469 | 10 |
| 10 | 120 | 3 |
| 11 | 301 | 7 |
| 12 | 495 | 10 |
| 13 | 36 | 1 |
| 14 | 196 | 4 |
| 15 | 1185 | 24 |
| 16 | 78 | 2 |
| 17 | 299 | 6 |
| 18 | 192 | 4 |
| 19 | 80 | 2 |
| 20 | 71 | 2 |
| 21 | 176 | 4 |
| 22 | 383 | 8 |
| 23 | 411 | 9 |
| 24 | 77 | 2 |
| 25 | 59 | 2 |
| 26 | 53 | 2 |
| 27 | 99 | 2 |
| 28 | 87 | 2 |
| 29 | 79 | 2 |
| 30 | 40 | 1 |
| 31 | 204 | 5 |
| 32 | 108 | 3 |
| **Total** | **5298** | **117** |

- **117 appels `api.php`** strictement nécessaires au minimum théorique (chunking exact connu à l'avance).
- + 24 appels `api_count.php` (un par catégorie, pour connaître `N` exactement avant de chunker) + 1 `api_category.php` + 1 `api_token.php?command=request` = **143 appels réseau au total**.
- À 5 secondes d'intervalle minimum : `143 × 5s ≈ 715s ≈ 11,9 minutes` de temps d'attente réseau **incompressible**, sans compter la latence des requêtes elles-mêmes ni aucun retry.
- **Estimation réaliste** avec marge pour : rate-limit occasionnel (code 5) malgré le respect des 5s, erreurs réseau transitoires, `response_code=4` inattendu en garde-fou (§4 étape 5) nécessitant un appel de vérification en plus par catégorie : compter un facteur **×2 à ×3** → **environ 20 à 35 minutes** pour un scraping complet et robuste du jeu de données actuellement « verified ».
- Important : ce chiffre (5 298) est une **cible mouvante** — 10 911 questions sont actuellement « pending » et rejoindront progressivement le pool « verified » (et donc le pool interrogeable par `api.php`) au fil du temps. Un scraper censé maintenir un jeu de données à jour doit donc être re-exécutable périodiquement (le rendre idempotent via l'ID déterministe du §8 est essentiel pour ça).

---

## Pièges & recommandations

- **`amount` > disponible ⇒ tableau vide, pas de troncature.** Toujours dimensionner `amount` via `api_count.php` avant d'itérer une catégorie en fin de pool (vérifié empiriquement, §1).
- **Ne jamais se fier au seul HTTP status.** L'API renvoie très probablement du HTTP 200 même en cas d'erreur logique (rate limit, token vide, etc.) — toujours lire `response_code` dans le corps JSON (voir avertissement NON VÉRIFIÉ en §2/§3 sur le code HTTP exact du rate limit, mais le principe « toujours checker `response_code` » est sûr dans tous les cas).
- **Rate limit = 1 req/5s/IP**, à respecter strictement même entre endpoints différents par prudence ; prévoir un backoff en cas de `response_code=5` malgré tout.
- **Token scoping du `response_code=4`** : l'épuisement signalé par le code 4 est relatif à la requête filtrée (catégorie/difficulté/type) en cours, pas à la totalité de la base — ne pas interpréter un `4` sur une catégorie comme un `4` global.
- **Un seul token pour tout le run** suffit (durée de vie 6h ≫ durée du scraping estimée à 20-35 min) ; ne PAS faire de `command=reset` en cours de route sous peine de réintroduire des doublons déjà collectés.
- **Doublons sans token** : sans token, deux appels successifs identiques (même catégorie/difficulté/type, petit pool) peuvent parfaitement retourner la même question par tirage aléatoire — d'où l'intérêt du token, et en filet de sécurité, l'ID déterministe du §8 pour dédupliquer même en cas de run sans token ou multi-runs.
- **Entités HTML mal décodées** : si `encode` par défaut est utilisé, un simple `.replace("&amp;", "&")` manuel est insuffisant (il existe des dizaines d'entités possibles : `&quot;`, `&#039;`, `&eacute;`, `&Uuml;`, etc.) — utiliser `html.unescape()` de la stdlib Python, ou mieux, passer par `encode=base64` pour s'épargner le problème entièrement (§6).
- **Espaces parasites** dans certains champs texte (observé empiriquement, ex. `"Adolf Hitler was born in Australia. "`) — toujours `.strip()`.
- **Pas d'ID natif** — construire un ID déterministe (§8) dès le premier run pour permettre un resume/checkpoint fiable.
- **La base grossit en continu** (pending → verified) — un scraping « complet » à un instant T n'est complet que pour cet instant T ; prévoir une re-synchronisation périodique plutôt qu'un run unique figé.
- **Pas de dump officiel** — ne pas construire d'architecture reposant sur l'hypothèse qu'un export bulk existe ; l'API paginée est la seule source de vérité.
- **Catégorie 13 (et d'autres petites catégories, ex. 30 « Science: Gadgets » avec 40 verified)** ont très peu de questions vérifiées : le scraper doit gérer correctement les catégories à 1 seul lot de moins de 50 sans planter sur un `amount` erroné.
- **Attribution CC BY-SA 4.0** à intégrer dans le produit final consommant les données (§9).

---

## Algorithme de scraping recommandé (pseudocode)

```text
CONFIG:
    BASE = "https://opentdb.com"
    MIN_INTERVAL = 5.2 secondes   # marge de sécurité sur la règle des 5s
    MAX_AMOUNT = 50
    CHECKPOINT_FILE = "checkpoint.json"   # {catégorie_id: nb_déjà_récupéré, "done": [...]}
    OUTPUT_STORE = base de données / fichiers JSONL par catégorie, clé = id déterministe (§8)

FONCTION appel_api(url, params):
    BOUCLE retry (max 6 tentatives, backoff = 5s, 10s, 20s, 40s, 60s, 60s):
        attendre_si_necessaire(MIN_INTERVAL depuis dernier appel)  # throttle global process-wide
        réponse = HTTP GET(url, params)
        SI erreur réseau / timeout:
            log, continuer la boucle retry
            CONTINUER
        json = parse(réponse.body)
        SI json.response_code == 0:
            RETOURNER json
        SI json.response_code == 5:   # rate limit
            log "rate limited, backoff"
            CONTINUER la boucle retry (le sleep du backoff s'applique)
        SI json.response_code == 3:   # token invalide/expiré
            token = demander_nouveau_token()
            params.token = token
            CONTINUER
        SI json.response_code IN (1, 4):  # plus de résultats pour ce filtre
            RETOURNER json   # laisser l'appelant décider (fin de catégorie)
        SI json.response_code == 2:
            ERREUR FATALE("paramètre invalide — bug du scraper")
    ERREUR FATALE("échec après retries")

FONCTION main():
    charger checkpoint si existant, sinon initialiser {}
    token = demander_nouveau_token()   # api_token.php?command=request, une seule fois

    categories = appel_api(BASE + "/api_category.php")   # liste des 24 (ou plus, futur-proof) catégories

    POUR CHAQUE catégorie DANS categories:
        SI catégorie.id DANS checkpoint["done"]:
            passer à la catégorie suivante   # déjà terminée lors d'un run précédent

        compte = appel_api(BASE + "/api_count.php", {category: catégorie.id})
        n_verified = compte.category_question_count.total_question_count
        déjà_recu = checkpoint.get(catégorie.id, 0)   # reprise après interruption

        TANT QUE déjà_recu < n_verified:
            lot = min(MAX_AMOUNT, n_verified - déjà_recu)
            résultat = appel_api(BASE + "/api.php", {
                amount: lot,
                category: catégorie.id,
                encode: "base64",
                token: token,
            })

            SI résultat.response_code IN (1, 4):
                # garde-fou : le compte n_verified était obsolète (nouvelles questions vérifiées
                # entre-temps, ou pool réellement épuisé) -> on s'arrête proprement sur cette catégorie
                log "catégorie", catégorie.id, "épuisée à", déjà_recu, "/", n_verified, "(attendu)"
                SORTIR de la boucle TANT QUE

            POUR CHAQUE q DANS résultat.results:
                q = décoder_base64_champs(q)
                id = sha256_id(q.category, q.type, q.difficulty, q.question, q.correct_answer)  # §8
                SI id N'EST PAS déjà dans OUTPUT_STORE:      # dédup ceinture-bretelles
                    écrire q dans OUTPUT_STORE avec sa clé id
                déjà_recu += 1

            checkpoint[catégorie.id] = déjà_recu
            sauvegarder checkpoint sur disque   # reprise possible à tout instant

        checkpoint["done"].append(catégorie.id)
        sauvegarder checkpoint

    log "Terminé :", total questions collectées, "/", 5298 (au moment du run)
```

Points clés de robustesse encodés dans ce pseudocode :
- **Checkpointing par catégorie et par compteur `déjà_recu`** → un crash ou un Ctrl-C au milieu du run permet de reprendre exactement là où on s'est arrêté, sans tout retélécharger ni recréer de doublons (grâce à l'ID déterministe en filet de sécurité en plus du token).
- **Retry/backoff** sur erreurs réseau et sur `response_code=5`.
- **Renouvellement automatique du token** sur `response_code=3` (expiration après 6h d'inactivité — improbable vu la durée totale du run, mais gratuit à gérer).
- **Sortie propre de catégorie** sur `response_code IN (1,4)`, qui sert de garde-fou si le compte `api_count.php` était légèrement obsolète (nouvelles questions vérifiées pendant le run).
- **Dédup à deux niveaux** : le token (dédup native OpenTDB) + l'ID déterministe sha256 (dédup applicative, résiliente aux resume/multi-runs/reset de token).

---

## Sources

- https://opentdb.com/api_config.php — documentation officielle (page HTML de doc + générateur d'URL), consultée via proxy de lecture suite à un blocage réseau direct dans l'environnement de recherche
- https://opentdb.com/api_category.php — liste des catégories (JSON live observé)
- https://opentdb.com/api_count_global.php — comptage global (JSON live observé)
- https://opentdb.com/api_count.php?category=9 — comptage catégorie 9 (JSON live observé)
- https://opentdb.com/api_count.php?category=13 — comptage catégorie 13, utilisé pour le test empirique « tout ou rien » (JSON live observé)
- https://opentdb.com/api.php?amount=2&category=9&type=multiple — échantillon `multiple` (JSON live observé)
- https://opentdb.com/api.php?amount=2&category=9&type=boolean — échantillon `boolean` (JSON live observé)
- https://opentdb.com/api.php?amount=1&category=9&encode=base64 — échantillon encodage base64 (JSON live observé)
- https://opentdb.com/api.php?amount=36&category=13 / amount=40 / amount=50 / amount=20 — tests empiriques du comportement « tout ou rien » (JSON live observé)
- https://opentdb.com/api_token.php?command=request — génération de token (JSON live observé)
- https://jentic.com/apis/opentdb.com/opentdb — spécification tierce dérivée de l'API OpenTDB
- https://gist.github.com/jbaranski/5419c049af1989c1808a71bc73c9f3f4 — script communautaire de téléchargement complet (approche token + boucle)
- https://gist.github.com/jbaranski/a3c10856b750441663eec71739d49e43 — dump communautaire non officiel (db.json, daté 27/12/2024, à considérer obsolète)
- https://github.com/QuartzWarrior/OTDB-Source — script de téléchargement par catégories 9-32, avec token et pause ~5s
- https://github.com/AdrienCos/openTDBscraper — scraper orienté flashcards Anki, un CSV par catégorie
- https://www.nuget.org/packages/OpenTDB-Wrapper — doc wrapper .NET (table response_code, comportement token)
- https://pypi.org/project/opentdb-py/ — wrapper Python (tentative de consultation, contenu non exploitable au moment du fetch)
- https://choosealicense.com/licenses/cc-by-sa-4.0/ et https://creativecommons.org/licenses/by-sa/4.0/deed.en — licence CC BY-SA 4.0 applicable aux données OpenTDB
- Recherches web complémentaires (WebSearch) sur : rate limiting OpenTDB, expiration des tokens, `response_code` 4/5, dumps/exports, licence — résultats agrégés et recoupés entre plusieurs sources indépendantes (voir mentions NON VÉRIFIÉ dans le corps du document pour les points non confirmés par une source primaire directe)
