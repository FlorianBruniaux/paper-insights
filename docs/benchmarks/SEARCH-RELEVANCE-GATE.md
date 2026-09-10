# Revue humaine de pertinence du Gate 2

Le Gate 2 reste bloqué tant que 30 revues humaines complètes ne placent pas un papier attendu dans le top cinq pour au moins 24 requêtes et qu'un humain n'a pas conclu à zéro P0. Le harnais exécute et enregistre la mesure. Il ne choisit pas les requêtes, les papiers attendus, l'identité du reviewer, le verdict P0 ou une approbation.

## Décisions produit enregistrées

Le paquet [SEARCH-RELEVANCE-DECISION.md](SEARCH-RELEVANCE-DECISION.md) enregistre les trois décisions du candidat autoritaire `gate2-arxiv-metadata-v1`:

1. D1 lie le corpus C2 de 120 papiers arXiv, sa sélection, son catalogue à la révision 147 et son index `fts-v2`.
2. D2 lie la distribution des 30 requêtes et le fichier préparé de SHA-256 `65d614cd22b1443f246f3e8545762b64b5be315c21436622c5c7d7db829524c7`.
3. D3 adopte P0-B: seul un slot must-find de 1 à 6 sans papier attendu dans le top cinq constitue un P0 de pertinence.

Ces décisions bornent seulement ce candidat. Une nouvelle instance de catalogue, un nouvel index, une autre distribution de requêtes ou une autre frontière P0 exige une nouvelle décision explicite avant exécution. Les décisions enregistrées ne remplacent ni les 30 revues humaines, ni l'approbation finale du Gate 2.

## Préconditions

- Le catalogue et l'index sont des fichiers réguliers sous la même racine de corpus.
- Le catalogue n'a aucun sidecar WAL ou SHM actif.
- L'index correspond à la révision courante du catalogue et son compteur de documents correspond à l'inventaire catalogue.
- Les artefacts sont écrits sous `output/`, déjà ignoré par Git.
- La commande fonctionne avec des fixtures locales ou un corpus local. Elle n'appelle aucun provider et n'ouvre aucun socket.

Utiliser des chemins absolus dans chaque commande. Choisir un nouveau répertoire de sortie pour chaque tentative. Le harnais refuse d'écraser un artefact existant.

## 1. Produire l'inventaire aveugle

```bash
uv run paper-insights-search-relevance inventory \
  --catalog /absolute/corpus/catalog.sqlite3 \
  --index /absolute/corpus/.search/search-v1.sqlite3 \
  --output-dir /absolute/repository/output/search-relevance/gate2-candidate
```

La commande produit:

- `corpus_inventory.jsonl`, trié par `paper_id` et sans requête, score, rang, résultat observé ou verdict;
- `inventory_manifest.json`, qui conserve chemins, SHA-256, révision, compteurs et reçu d'index.

L'humain utilise cet inventaire pour choisir les papiers attendus sans voir les résultats du moteur.

## 2. Préparer les 30 vérités attendues

Copier `tests/benchmarks/search_queries.jsonl` vers un fichier de travail sous `output/`. Pour chaque slot, remplir uniquement:

- `query`, avec une chaîne non vide de 500 caractères au maximum;
- `expected_relevant_paper_ids`, avec au moins un UUIDv7 présent dans l'inventaire.

Laisser `observed_top_five_paper_ids`, `p0_relevance_failure`, `reviewer_id` et `reviewed_at` à `null`. Les 30 slots doivent être présents, uniques et ordonnés de 1 à 30. Le harnais rejette un mélange d'états ou une vérité attendue partielle.

La personne qui définit les requêtes doit suivre la décision produit sur leur représentativité. En son absence, le fichier peut servir à tester le mécanisme, mais pas à fermer le Gate 2.

## 3. Exécuter les 30 recherches

```bash
uv run paper-insights-search-relevance run \
  --catalog /absolute/corpus/catalog.sqlite3 \
  --index /absolute/corpus/.search/search-v1.sqlite3 \
  --queries /absolute/repository/output/search-relevance/gate2-candidate/prepared_queries.jsonl \
  --output-dir /absolute/repository/output/search-relevance/gate2-candidate
```

Avant la première recherche, la commande recalcule les empreintes et vérifie le manifeste d'inventaire. Une dérive du catalogue, de l'index ou de l'inventaire bloque l'exécution. Chaque recherche utilise `limit=5` et exige une couverture `complete` sur la révision capturée.

La commande ne modifie pas `--queries`. Elle produit:

- `observed_results.jsonl`, qui contient les résultats observés sans les IDs attendus;
- `review_records.jsonl`, copie exécutable du contrat `search-relevance-v1` avec les trois champs humains à `null`;
- `review_form.md`, vue lisible des IDs attendus et observés avec champs humains vides;
- `run_manifest.json`, qui lie les entrées et sorties par SHA-256.

Une requête sans hit conserve une liste observée vide. Le harnais ne remplace jamais ce résultat par un papier attendu.

## 4. Réaliser la revue humaine

Le reviewer lit `review_form.md`, puis remplit chaque ligne de `review_records.jsonl`:

- `p0_relevance_failure` avec un booléen décidé selon la définition produit;
- `reviewer_id` avec son identifiant réel;
- `reviewed_at` avec un timestamp ISO 8601 UTC.

Les trois champs sont indissociables. Le validateur refuse toute ligne qui n'en remplit qu'une partie. Le reviewer ne change ni la requête, ni les IDs attendus, ni les IDs observés après l'exécution. Aucun des fichiers générés ne contient ou ne demande une approbation automatique.

Une fois les 30 revues terminées et vérifiées, l'humain peut remplacer explicitement le template suivi par Git dans `tests/benchmarks/search_queries.jsonl`. Cette mutation n'appartient pas au harnais. Pour le candidat `gate2-arxiv-metadata-v1`, appliquer la définition P0-B enregistrée dans le paquet de décision.

## 5. Valider les critères calculables

```bash
uv run paper-insights-search-relevance validate-review \
  --reviews /absolute/repository/output/search-relevance/gate2-candidate/review_records.jsonl \
  --run-manifest /absolute/repository/output/search-relevance/gate2-candidate/run_manifest.json
```

Le validateur recalcule les empreintes du fichier de vérité préparée et des résultats observés enregistrés dans le manifeste. Il refuse une revue qui modifie une requête, un ID attendu ou un ID observé après l'exécution.

Codes de sortie:

| Code | Signification |
| --- | --- |
| `0` | `SATISFIED`: 30 revues complètes, au moins 24 correspondances top cinq, zéro P0 déclaré. |
| `1` | `FAILED`: les 30 revues sont complètes, mais le seuil ou la règle zéro P0 échoue. |
| `2` | `BLOCKED` ou entrée invalide: revue incomplète, schéma faux ou artefact indisponible. |

`SATISFIED` n'est pas une approbation. Pour le candidat actuel, D1 à D3 sont enregistrées, mais la sortie de Gate 2 exige encore l'intégration humaine explicite du jeu revu et une approbation finale distincte.

## Vérification automatisée du harnais

```bash
uv run pytest --disable-socket tests/benchmarks -v
```

Le test du gate humain reste marqué `BLOCKED` tant que le fichier suivi contient moins de 30 revues complètes. Les tests du harnais utilisent uniquement la fixture arXiv locale, construisent un vrai catalogue et un vrai index, exécutent 30 recherches et vérifient qu'aucun verdict humain n'est prérempli.
