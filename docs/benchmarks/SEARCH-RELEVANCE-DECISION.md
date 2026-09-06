# Paquet de décision du benchmark de pertinence

**Statut : PROPOSED.** Ce document prépare trois décisions produit. Il ne désigne pas un corpus réel, ne remplit aucun champ de revue humaine et ne ferme pas le Gate 2.

Le seuil calculable reste 24 requêtes avec au moins un papier attendu dans le top cinq sur 30, et zéro P0 déclaré. Une sortie `SATISFIED` du harnais ne vaut pas approbation produit.

## Portée proposée

Le premier benchmark autoritaire mesurerait la recherche textuelle FTS5 sur les titres et résumés arXiv. Il ne prouverait ni la couverture de toute la littérature scientifique, ni la recherche par filtre auteur, catégorie, langue ou identifiant.

## D1. Corpus de référence

| Option | Contenu | Limite |
| --- | --- | --- |
| C1 | Fixture locale actuelle | Vérifie le mécanisme, pas un corpus représentatif. |
| C2 | 120 versions courantes arXiv, 20 dans chacune des catégories `cs.AI`, `cs.CL`, `cs.IR`, `cs.LG`, `stat.ML` et `cs.SE` | Représente seulement ce périmètre arXiv et ces métadonnées. |
| C3 | Corpus hétérogène multi-source | Impossible avant les providers et les décisions de couverture correspondants. |

**Recommandation : C2**, nommé `gate2-arxiv-metadata-v1`. Les 120 versions sont des documents distincts, avec titre et résumé non vides, une version courante, une observation de métadonnées et un index publié à la même révision catalogue.

C2 est volontairement **non exécutable** tant que le décideur humain n'a pas renseigné ces champs pré-inventaire, sans les déduire du premier résultat réseau disponible:

| Champ à décider | Règle appliquée après décision |
| --- | --- |
| `source_snapshot_path` et `source_snapshot_sha256` | Une capture locale immuable contenant les candidats arXiv. |
| `cutoff_submitted_at_utc` | Exclure toute version soumise après ce timestamp ISO 8601 UTC. |
| `category_order` | Utiliser exactement `cs.AI`, `cs.CL`, `cs.IR`, `cs.LG`, `stat.ML`, `cs.SE`, dans cet ordre. |
| `selection_order` | Trier par `submitted_at` décroissant, puis par identifiant arXiv canonique croissant. |
| `deduplication_key` | Dédupliquer par identifiant arXiv canonique avant toute sélection. |
| `current_version_rule` | Pour une clé de déduplication, retenir la version de plus grand numéro arXiv soumise au plus tard à `cutoff_submitted_at_utc`; une égalité est `BLOCKED`. |

Après ces décisions, appliquer `current_version_rule`, puis pour chaque catégorie dans `category_order`, sélectionner dans `source_snapshot_path` les versions courantes de cette catégorie, avec titre et résumé non vides. Appliquer `selection_order`, ignorer les clés déjà retenues, puis retenir les 20 premières. Un candidat qui ne fournit pas exactement 20 entrées nouvelles pour une catégorie est `BLOCKED`; il ne remplace pas silencieusement une catégorie et ne passe pas à l'inventaire. Cette règle fixe 120 entrées distinctes avant l'inventaire et sans consulter les résultats de recherche.

**Décision humaine attendue :** accepter C2 en renseignant les cinq champs ci-dessus, retenir C1 pour une preuve limitée au harnais, ou définir un autre corpus avec son périmètre, son nom et ses critères de sélection.

## D2. Distribution des 30 requêtes

| Slots | Classe proposée | Règle de préparation | P0 possible |
| --- | --- | --- | --- |
| 1 à 6 | Recherche « must-find » | 3 à 6 termes distinctifs du titre d'un seul papier attendu | Oui |
| 7 à 14 | Découverte thématique | 2 à 3 termes de sujet, 1 à 5 papiers attendus | Non |
| 15 à 22 | Besoin précis | 4 à 6 termes combinant méthode, objet et contexte, 1 à 3 papiers attendus | Non |
| 23 à 30 | Désambiguïsation | 2 à 4 termes communs à plusieurs documents, ensemble attendu explicitement justifié | Non |

Les 30 requêtes sont en anglais. Le corpus C2 ne garantit pas la langue des titres ni des résumés: le normaliseur arXiv actuel ne renseigne pas ce champ et la sélection ne le filtre pas. La préparation utilise seulement `corpus_inventory.jsonl`, avant toute exécution. Chaque `expected_relevant_paper_ids` doit contenir des `paper_id` de cet inventaire. Une requête n'emploie ni opérateur FTS brut, ni filtre CLI, ni identifiant absent du champ textuel indexé. Les six slots « must-find » visent six papiers distincts et au moins quatre des six catégories du corpus proposé. Les 24 autres slots couvrent les six catégories, avec au moins trois slots par catégorie.

**Recommandation :** adopter cette distribution. Elle couvre les usages textuels réellement mesurés, garde les recherches critiques explicites et ne présente pas les filtres hors harnais comme validés.

**Décision humaine attendue :** accepter ces 30 slots et leurs critères, ou enregistrer une autre distribution dont la somme vaut exactement 30 et dont les classes P0 sont identifiées avant l'exécution.

## D3. Définition opérationnelle d'un P0 de pertinence

| Option | Définition | Effet |
| --- | --- | --- |
| P0-A | Toute absence d'un papier attendu du top cinq est un P0 | Rend le seuil 24/30 sans portée pratique. |
| P0-B | Un P0 existe seulement si un slot « must-find » ne retourne aucun de ses papiers attendus dans le top cinq, alors que le catalogue, l'index et la couverture sont ceux liés par le manifeste | Réserve le P0 à l'échec d'un besoin connu et sans ambiguïté; les autres misses restent comptés par le seuil 24/30. |
| P0-C | Aucun P0 de recherche n'est défini | Contredit la règle zéro P0 de la roadmap. |

**Recommandation : P0-B.** Pour les slots 1 à 6, le reviewer renseigne `p0_relevance_failure: true` si aucun `expected_relevant_paper_ids` n'apparaît dans `observed_top_five_paper_ids`. Il renseigne `false` dans tous les autres cas. Les slots 7 à 30 ne sont jamais marqués P0 par une absence de rang; cette absence peut néanmoins faire échouer le seuil 24/30. Une couverture incomplète, une dérive d'empreinte ou une révision différente bloquent le harnais avant revue, elles ne deviennent pas un verdict P0.

**Décision humaine attendue :** accepter P0-B, retenir P0-A, ou définir une autre frontière qui précise les slots concernés et le traitement des absences hors P0.

## Champs liés par empreinte après création du corpus

Ces champs restent vides jusqu'à la création du corpus choisi et l'exécution de `inventory`. Ils sont recopiés depuis `inventory_manifest.json`, sans estimation ni reconstruction manuelle.

| Champ à renseigner | Source autoritaire |
| --- | --- |
| Nom du candidat et répertoire absolu sous `output/search-relevance/` | Décision humaine et chemin de l'artefact créé |
| `catalog.path`, `catalog.sha256`, `catalog.revision`, `catalog.document_count`, `catalog.paper_count` | `inventory_manifest.json` → `catalog` |
| `index.path`, `index.sha256`, `index.schema_version`, `index.chunk_schema_version`, `index.generation`, `index.catalog_revision`, `index.document_count`, `index.passage_count`, `index.content_sha256` | `inventory_manifest.json` → `index` |
| `inventory.path`, `inventory.sha256`, `inventory.row_count` | `inventory_manifest.json` → `inventory` |
| SHA-256 de `prepared_queries.jsonl` et `observed_results.jsonl` | `run_manifest.json`, après l'exécution autorisée; ce sont les entrées vérifiées par `validate-review`. |
| `review_records_pre_review_sha256` | `run_manifest.json` → `artifacts.review_records.jsonl`; empreinte de la copie générée avec les trois champs humains à `null`, obsolète après revue et non lue par `validate-review`. |
| `final_review_records_sha256` | À calculer sur `final_review_records.jsonl`, copie immuable des 30 enregistrements après remplissage humain, puis à consigner avec l'approbation humaine. Cette empreinte d'audit ne figure pas dans `run_manifest.json`; aucune valeur n'est définie avant la revue. |

Le répertoire candidat est nouveau au démarrage de `inventory`. Il doit ensuite conserver `inventory_manifest.json` et `corpus_inventory.jsonl`, requis par `run`. Avant ce premier `run`, il ne contient pas `observed_results.jsonl`, `review_records.jsonl`, `review_form.md` ni `run_manifest.json`. Ces artefacts signalent une exécution antérieure et ne peuvent pas être écrasés: créer alors un nouveau répertoire candidat et reprendre à `inventory`. La décision humaine est aussi invalide pour une exécution si `catalog.revision` diffère de `index.catalog_revision` ou si les empreintes ne correspondent plus.

## Séquence après décision humaine

1. Consigner les trois décisions et remplir les champs liés par empreinte après `inventory`.
2. Préparer les 30 vérités attendues dans une copie sous `output/`, jamais dans le fichier suivi.
3. Exécuter le harnais, puis réaliser les 30 revues humaines sans modifier requêtes, attentes ou résultats observés.
4. Exiger `SATISFIED`, 24 correspondances top cinq au minimum, zéro P0 et une approbation humaine distincte avant tout remplacement de `tests/benchmarks/search_queries.jsonl` ou changement de matrice de capacité.
