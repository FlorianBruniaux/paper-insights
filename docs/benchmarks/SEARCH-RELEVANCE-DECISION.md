# Paquet de décision du benchmark de pertinence

**Statut : D1, D2 et D3 `APPROVED` le 2026-09-07.** Les manifestes locaux du candidat `gate2-arxiv-metadata-v1` sont maintenant `OBSERVED` et lient une capture source, un catalogue, un index et un inventaire précis. La sélection observée respecte le cutoff approuvé, les 20 nouveaux papiers par étape de catégorie, les champs non vides et l'absence d'égalité de `submitted_at`; toutes les versions capturées sont `v1`. Cette preuve porte sur le candidat capturé, pas sur l'exhaustivité historique d'arXiv. Les requêtes restent proposées, aucune recherche n'a été exécutée et aucune revue humaine n'existe. Le Gate 2 reste `BLOCKED` à `0/30`.

Le seuil calculable reste 24 requêtes avec au moins un papier attendu dans le top cinq sur 30, et zéro P0 déclaré. Une sortie `SATISFIED` du harnais ne vaut pas approbation produit.

## Portée du benchmark approuvée

Le premier benchmark autoritaire mesurerait la recherche textuelle FTS5 sur les titres et résumés arXiv. Il ne prouverait ni la couverture de toute la littérature scientifique, ni la recherche par filtre auteur, catégorie, langue ou identifiant.

## D1. Corpus de référence, APPROVED

Options considérées avant décision:

| Option | Contenu | Limite |
| --- | --- | --- |
| C1 | Fixture locale actuelle | Vérifie le mécanisme, pas un corpus représentatif. |
| C2 | 120 versions courantes arXiv, 20 dans chacune des catégories `cs.AI`, `cs.CL`, `cs.IR`, `cs.LG`, `stat.ML` et `cs.SE` | Représente seulement ce périmètre arXiv et ces métadonnées. |
| C3 | Corpus hétérogène multi-source | Impossible avant les providers et les décisions de couverture correspondants. |

**Décision approuvée : C2**, nommé `gate2-arxiv-metadata-v1`. La cible exige 120 versions comme documents distincts, avec titre et résumé non vides, une version courante, une observation de métadonnées et un index publié à la même révision catalogue. Le candidat observé contient 120 documents et 120 papiers selon `inventory_manifest.json`; `selection_validation` lie 120 observations sans titre ou résumé vide, toutes en `v1`, avec 20 nouveaux papiers par étape de `category_order` et aucune égalité de `submitted_at`.

Les paramètres de sélection approuvés et leurs observations sont séparés:

| Champ | Statut | Règle ou valeur |
| --- | --- | --- |
| `source_snapshot_manifest.path` et `source_snapshot_manifest.sha256` | `OBSERVED` | `/Users/florianbruniaux/Sites/perso/paper-insights/output/worktrees/complete-program/output/search-relevance/gate2-arxiv-metadata-v1/source_snapshot_manifest.json`; `eeca3bd16d779f7228df0af8873455290f3f50846a54fd911cdf2f0cd95d394f`. |
| `source_snapshot_manifest.cutoff_binding` | `OBSERVED` | Cutoff approuvé `2026-09-05T23:59:59Z`; fin inclusive CLI `2026-09-05T23:59:59.999999Z`; maximum sélectionné `2026-09-04T17:59:00Z`; 0 sélection après le cutoff approuvé. |
| `cutoff_submitted_at_utc` | `APPROVED` | `2026-09-05T23:59:59Z` |
| `category_order` | `APPROVED` | `cs.AI`, `cs.CL`, `cs.IR`, `cs.LG`, `stat.ML`, `cs.SE`, dans cet ordre. |
| `selection_order` | `APPROVED` | Trier par `submitted_at` décroissant, puis par identifiant arXiv canonique croissant. |
| `deduplication_key` | `APPROVED` | Dédupliquer par identifiant arXiv canonique avant toute sélection. |
| `current_version_rule` | `APPROVED` | Pour une clé de déduplication, retenir la version de plus grand numéro arXiv soumise au plus tard à `cutoff_submitted_at_utc`; une égalité est `BLOCKED`. |

La règle approuvée consiste à appliquer `current_version_rule`, puis, pour chaque catégorie dans `category_order`, à sélectionner les versions courantes avec titre et résumé non vides. `selection_order` s'applique avant d'ignorer les clés déjà retenues et de conserver les 20 premières. Un candidat qui ne fournit pas exactement 20 entrées nouvelles par catégorie est `BLOCKED`. Le manifeste observé enregistre six snapshots et six runs `succeeded`, ordonnés comme `category_order`, 135 occurrences sélectionnées, 120 nouveaux papiers, 120 nouvelles versions, 15 records inchangés et aucun échec. `cutoff_binding` prouve qu'aucune sélection ne dépasse le cutoff approuvé. `selection_validation` prouve, dans le candidat capturé, 20 nouveaux papiers par étape, 120 observations, aucun titre ou résumé vide, aucune version autre que `v1` et aucune égalité de `submitted_at`. Ces observations lient C2 sans prouver l'exhaustivité historique d'arXiv.

**Décision humaine :** C2 et les cinq paramètres de sélection sont approuvés. Le manifeste source lie la sélection observée et ses limites. La prochaine autorité attendue est le fichier de requêtes approuvé humainement.

## D2. Distribution des 30 requêtes, APPROVED

| Slots | Classe proposée | Règle de préparation | P0 possible |
| --- | --- | --- | --- |
| 1 à 6 | Recherche « must-find » | 3 à 6 termes distinctifs du titre d'un seul papier attendu | Oui |
| 7 à 14 | Découverte thématique | 2 à 3 termes de sujet, 1 à 5 papiers attendus | Non |
| 15 à 22 | Besoin précis | 4 à 6 termes combinant méthode, objet et contexte, 1 à 3 papiers attendus | Non |
| 23 à 30 | Désambiguïsation | 2 à 4 termes communs à plusieurs documents, ensemble attendu explicitement justifié | Non |

Les 30 requêtes sont en anglais. Le corpus C2 ne garantit pas la langue des titres ni des résumés: le normaliseur arXiv actuel ne renseigne pas ce champ et la sélection ne le filtre pas. La préparation utilise seulement `corpus_inventory.jsonl`, avant toute exécution. Chaque `expected_relevant_paper_ids` doit contenir des `paper_id` de cet inventaire. Une requête n'emploie ni opérateur FTS brut, ni filtre CLI, ni identifiant absent du champ textuel indexé. Les six slots « must-find » visent six papiers distincts et au moins quatre des six catégories du corpus proposé. Les 24 autres slots couvrent les six catégories, avec au moins trois slots par catégorie.

**Décision approuvée :** cette distribution est adoptée. Elle couvre les usages textuels réellement mesurés, garde les recherches critiques explicites et ne présente pas les filtres hors harnais comme validés.

**État de préparation :** `proposed_queries.jsonl`, SHA-256 `65d614cd22b1443f246f3e8545762b64b5be315c21436622c5c7d7db829524c7`, contient 30 slots ordonnés qui passent la validation mécanique du contrat et dont les identifiants attendus appartiennent à l'inventaire observé. Ce fichier reste `PROPOSED`: il n'est pas approuvé humainement, n'est pas l'autorité `prepared_queries.jsonl` et n'est lié par aucun `run_manifest.json`. Aucune recherche n'a été exécutée.

## D3. Définition opérationnelle d'un P0 de pertinence, APPROVED

| Option | Définition | Effet |
| --- | --- | --- |
| P0-A | Toute absence d'un papier attendu du top cinq est un P0 | Rend le seuil 24/30 sans portée pratique. |
| P0-B | Un P0 existe seulement si un slot « must-find » ne retourne aucun de ses papiers attendus dans le top cinq, alors que le catalogue, l'index et la couverture sont ceux liés par le manifeste | Réserve le P0 à l'échec d'un besoin connu et sans ambiguïté; les autres misses restent comptés par le seuil 24/30. |
| P0-C | Aucun P0 de recherche n'est défini | Contredit la règle zéro P0 de la roadmap. |

**Décision approuvée : P0-B.** Pour les slots 1 à 6, le reviewer renseignera `p0_relevance_failure: true` si aucun `expected_relevant_paper_ids` n'apparaît dans `observed_top_five_paper_ids`. Il renseignera `false` dans tous les autres cas. Les slots 7 à 30 ne seront jamais marqués P0 par une absence de rang; cette absence peut néanmoins faire échouer le seuil 24/30. Une couverture incomplète, une dérive d'empreinte ou une révision différente bloquent le harnais avant revue, elles ne deviennent pas un verdict P0.

**Prochaine preuve attendue :** les 30 verdicts humains restent absents; aucun P0 n'est observé ou exclu à ce stade.

## Liaisons factuelles observées et encore attendues

Les champs `OBSERVED` ci-dessous sont recopiés depuis les deux manifestes locaux, sans estimation ni reconstruction manuelle. Ils lient le corpus candidat exact, pas sa pertinence ni l'exhaustivité historique d'arXiv.

| Champ à renseigner | Statut | Source autoritaire |
| --- | --- | --- |
| Répertoire absolu sous `output/search-relevance/` | `OBSERVED` | `/Users/florianbruniaux/Sites/perso/paper-insights/output/worktrees/complete-program/output/search-relevance/gate2-arxiv-metadata-v1` |
| `source_snapshot_manifest.json` | `OBSERVED` | Schéma `gate2-arxiv-source-snapshot-v1`; SHA-256 `eeca3bd16d779f7228df0af8873455290f3f50846a54fd911cdf2f0cd95d394f`; six snapshots; six runs, tous `succeeded`; 135 occurrences sélectionnées; 120 papiers distincts; 120 nouveaux papiers; 120 nouvelles versions; 15 records inchangés; 0 record échoué; maximum sélectionné `2026-09-04T17:59:00Z`; 0 sélection après le cutoff approuvé; 20 nouveaux papiers par étape de catégorie; 120 observations; 0 titre vide; 0 résumé vide; 0 version autre que `v1`; 0 groupe à `submitted_at` identique. |
| `inventory_manifest.json` | `OBSERVED` | Schéma `search-relevance-inventory-v1`; SHA-256 du manifeste `770fa19f67b8197f39cb04c5ff38c30f81269ca4073a5c058ec9d280e089b49a`; créé le `2026-09-08T05:30:17.850919+00:00`. |
| `catalog.path`, `catalog.sha256`, `catalog.revision`, `catalog.document_count`, `catalog.paper_count` | `OBSERVED` | `/Users/florianbruniaux/Sites/perso/paper-insights/output/worktrees/complete-program/output/corpora/gate2-arxiv-metadata-v1/catalog.sqlite3`; `2b37fc6175f8f967548a1aff7930e1469a692ad29768fa474f22766396ad7db1`; révision 147; 120 documents; 120 papiers. |
| `index.path`, `index.sha256`, `index.schema_version`, `index.chunk_schema_version`, `index.generation`, `index.catalog_revision`, `index.document_count`, `index.passage_count`, `index.content_sha256` | `OBSERVED` | `/Users/florianbruniaux/Sites/perso/paper-insights/output/worktrees/complete-program/output/corpora/gate2-arxiv-metadata-v1/.search/search-v1.sqlite3`; `6a0f3573c9c01f3fd23f996633ffbee210cc902a395bbb02dd6b47f3030b4716`; `fts-v2`; `chunk-v1`; génération 1; révision catalogue 147; 120 documents; 240 passages; contenu `680b66e113d55833e1ee0e52676f817af8f821099bc338643dad3400a2af6be4`. |
| `inventory.path`, `inventory.sha256`, `inventory.row_count` | `OBSERVED` | `corpus_inventory.jsonl`; `7c55bd522d26229d6f4caa21e3288eebbc2004192086835a9d9912897a0ffb23`; 120 lignes; aveugle aux requêtes, attentes de pertinence, rangs et scores BM25. |
| SHA-256 de `prepared_queries.jsonl` et `observed_results.jsonl` | `PENDING_OBSERVATION` | `run_manifest.json`, après l'exécution autorisée; ce sont les entrées vérifiées par `validate-review`. |
| `review_records_pre_review_sha256` | `PENDING_OBSERVATION` | `run_manifest.json` → `artifacts.review_records.jsonl`; empreinte de la copie générée avec les trois champs humains à `null`, obsolète après revue et non lue par `validate-review`. |
| `final_review_records_sha256` | `PENDING_OBSERVATION` | À calculer sur `final_review_records.jsonl`, copie immuable des 30 enregistrements après remplissage humain, puis à consigner avec l'approbation humaine. Cette empreinte d'audit ne figure pas dans `run_manifest.json`; aucune valeur n'est définie avant la revue. |

Le répertoire observé contient `source_snapshot_manifest.json`, `inventory_manifest.json`, `corpus_inventory.jsonl` et le fichier non autoritaire `proposed_queries.jsonl`. Il ne contient pas `prepared_queries.jsonl`, `observed_results.jsonl`, `review_records.jsonl`, `review_form.md` ni `run_manifest.json`. Ces artefacts de run ne peuvent pas être présentés comme existants ni reconstruits à partir de la proposition. Une future exécution est invalide si `catalog.revision` diffère de `index.catalog_revision` ou si les empreintes liées ont dérivé.

## Séquence après les décisions approuvées

1. Conserver les manifestes observés et leur limite explicite: ils prouvent le candidat capturé, pas l'exhaustivité historique d'arXiv.
2. Faire approuver humainement les 30 vérités proposées, puis créer l'autorité exacte `prepared_queries.jsonl` sous `output/`, jamais dans le fichier suivi.
3. Exécuter le harnais, puis réaliser les 30 revues humaines sans modifier requêtes, attentes ou résultats observés.
4. Exiger `SATISFIED`, 24 correspondances top cinq au minimum, zéro P0 et une approbation humaine distincte avant tout remplacement de `tests/benchmarks/search_queries.jsonl` ou changement de matrice de capacité.
