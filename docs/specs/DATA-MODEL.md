# Spécification du modèle de données

## Autorités

Le catalogue distingue trois niveaux:

```text
paper, identité locale d'une oeuvre
  -> paper_version, identité d'une révision publiée par une source
       -> version_observation, état bibliographique immuable observé pour cette révision
```

`papers` ne contient aucune métadonnée externe. Le titre, le résumé, le DOI, l'ordre des auteurs, les catégories, le commentaire, la référence de journal, la langue, les dates source et l'URL source appartiennent à une `version_observation` ou à ses relations.

Une valeur externe absente reste `NULL`. Une chaîne vide signifie que la source a réellement fourni une chaîne vide. Les données observées, normalisées et inférées restent distinctes.

## Identifiants internes

Les identifiants suivants sont des UUIDv7 générés localement: `paper_id`, `paper_version_id`, `version_observation_id`, `author_id`, `blob_id`, `snapshot_id`, `artifact_id`, `run_id`, `collection_id`, `watchlist_id`, `analysis_id`, `identity_event_id`.

`passage_id` est un SHA-256 défini dans [SEARCH-AND-MCP.md](SEARCH-AND-MCP.md). Aucun identifiant arXiv, DOI, OpenAlex ou ORCID ne devient une clé primaire interne.

## Révision du catalogue

### `catalog_meta`

| Colonne | Règle |
| --- | --- |
| `singleton_id` | clé primaire, `CHECK(singleton_id = 1)` |
| `revision` | entier positif ou nul |
| `schema_contract_version` | chaîne fermée, initialement `catalog-v1` |

La migration initialise exactement une ligne avec `revision = 0`. Toute transaction catalogue validée qui contient au moins une mutation visible incrémente la révision exactement une fois dans cette transaction. Une lecture, un no-op, un rollback ou une erreur ne la change pas.

L'attachement de toutes les pages confirmées et de leurs records avec la création de la run forme une seule transaction visible et incrémente la révision une fois. Chaque item committé, la finalisation, une mutation de collection et une réparation explicite sont ensuite des mutations visibles séparées. La publication d'un blob non attaché ne change pas la révision.

## Sources, blobs et snapshots

### `sources`

| Colonne | Règle |
| --- | --- |
| `id` | clé primaire, slug stable comme `arxiv` |
| `base_url` | URL officielle |
| `terms_url` | nullable |
| `enabled` | booléen obligatoire |

### `stored_blobs`

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `sha256` | 64 caractères hexadécimaux minuscules, unique |
| `size_bytes` | entier positif ou nul |
| `media_type` | obligatoire |
| `relative_path` | chemin relatif confiné sous `data_root` |
| `created_at` | UTC |

Un blob est immuable et adressé par son contenu. Plusieurs snapshots ou artefacts peuvent référencer le même blob.

### `source_snapshots`

Une ligne représente une page ou réponse brute qui peut contenir plusieurs papiers.

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `capture_id` | UUIDv7 créé à la collecte, unique |
| `source_id` | FK vers `sources` |
| `stored_blob_id` | FK vers `stored_blobs` |
| `request_fingerprint` | SHA-256 de la requête HTTP canonique |
| `retrieved_at` | UTC, date de récupération source |
| `next_cursor` | nullable, opaque |

Un snapshot est l'événement source identifié par `capture_id`, indépendamment de la sélection qui l'utilise. Un batch refuse deux pages portant le même `capture_id`. Rejouer une sélection ou préparer une autre sélection sur la même capture réutilise ce snapshot uniquement si source, blob, empreinte de requête, date, curseur et graphe source ordonné des `snapshot_records` sont identiques. Ce graphe immuable compare seulement ordinal, `source_item_id`, `source_version_key` et `raw_record_sha256`. Le lien enrichi `version_observation_id` n'appartient pas à la collision: un replay le conserve sans le comparer, le remettre à NULL ni l'écraser. Toute collision divergente du graphe source produit `catalog_conflict` sans mutation. Une nouvelle collecte du même payload reçoit un nouveau `capture_id` et crée un nouvel événement source, tout en réutilisant le blob adressé par contenu.

`attach_prepared_run` génère les `source_snapshots.id` lors du premier attachement et retourne leur mapping ordonné dans `IngestionRunRef`. Au replay du même digest, il retourne exactement les identifiants existants. Le traitement ultérieur d'un record réutilise ce mapping sans requête de résolution implicite.

### `snapshot_records`

| Colonne | Règle |
| --- | --- |
| `source_snapshot_id` | FK vers `source_snapshots` |
| `ordinal` | position positive ou nulle dans la page |
| `source_item_id` | identifiant de l'oeuvre fourni par la source, nullable si parsing impossible |
| `source_version_key` | identifiant complet de version, nullable si parsing impossible |
| `raw_record_sha256` | empreinte du record brut borné |
| `version_observation_id` | FK nullable vers `version_observations` |

Clé primaire: `(source_snapshot_id, ordinal)`. Plusieurs occurrences peuvent pointer vers la même observation normalisée. Un échec conserve son snapshot et son ordinal sans inventer d'observation.

Une réponse multi-papiers est toujours un `source_snapshot`. `source_response` n'est pas un kind d'artefact de papier.

### `ingestion_run_snapshots`

Cette table relie explicitement une run aux captures de son manifeste:

| Colonne | Règle |
| --- | --- |
| `run_id` | FK vers `ingestion_runs` |
| `page_ordinal` | position positive ou nulle dans le manifeste |
| `source_snapshot_id` | FK vers `source_snapshots` |
| `source_id` | composante répétée pour fermer l'égalité de source |

Clé primaire: `(run_id, page_ordinal)`. Contrainte unique: `(run_id, source_snapshot_id)`. Les FKs composites `(run_id, source_id) -> ingestion_runs(id, source_id)` et `(source_snapshot_id, source_id) -> source_snapshots(id, source_id)` imposent la même source. Les parents exposent les contraintes uniques composites correspondantes. `IngestionRunRef.snapshots` restitue cette table dans l'ordre des pages.

### `ingestion_run_selected_records`

Cette table persiste le sous-ensemble confirmé, distinct de tous les records présents dans les pages:

| Colonne | Règle |
| --- | --- |
| `run_id` | FK vers `ingestion_runs` |
| `selection_ordinal` | ordre déterministe de sélection, positif ou nul |
| `source_snapshot_id` | composante de la FK vers `snapshot_records` |
| `record_ordinal` | composante de la FK vers `snapshot_records` |

Clé primaire: `(run_id, selection_ordinal)`. Contrainte unique: `(run_id, source_snapshot_id, record_ordinal)`. La FK `(run_id, source_snapshot_id) -> ingestion_run_snapshots(run_id, source_snapshot_id)` ferme l'appartenance au manifeste et la FK `(source_snapshot_id, record_ordinal) -> snapshot_records(source_snapshot_id, ordinal)` ferme l'existence du record. La création de run vérifie que le nombre de lignes égale `selected_records`. La réparation utilise uniquement ces lignes, jamais tous les records des pages ni le digest non décodable.

## Corpus versionné

### `papers`

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `created_at` | UTC |

Cette table porte uniquement l'identité locale de l'oeuvre.

### `paper_versions`

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `paper_id` | FK vers `papers` |
| `source_id` | FK vers `sources` |
| `source_version_key` | identifiant canonique complet de version |
| `is_current` | booléen |
| `created_at` | UTC |

Contrainte unique: `(source_id, source_version_key)`. Pour arXiv, une clé de version est par exemple `2608.01234v2`, jamais le suffixe isolé `v2`.

Un index unique partiel garantit une seule version courante par `(paper_id, source_id)` lorsque `is_current = 1`. La création d'une nouvelle version et la bascule de la version courante ont lieu dans la même transaction item.

### `version_observations`

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `paper_version_id` | FK vers `paper_versions` |
| `normalized_sha256` | empreinte du JSON bibliographique canonique |
| `observed_at` | UTC |
| `origin_source_id` | FK vers la source commune à la version, au snapshot et à la run d'origine |
| `origin_run_id` | composante de la provenance d'origine |
| `origin_source_snapshot_id` | composante de la provenance d'origine |
| `origin_record_ordinal` | composante de la provenance d'origine |
| `title` | obligatoire |
| `title_normalized` | obligatoire |
| `abstract` | nullable |
| `comment` | nullable |
| `journal_reference` | nullable |
| `language` | nullable |
| `source_url` | nullable |
| `submitted_at` | nullable, UTC |
| `announced_at` | nullable, UTC |

Contrainte unique: `(paper_version_id, normalized_sha256)`. `origin_source_id` ferme par clés étrangères composites l'appartenance de la version, du snapshot et de la run à la même source. La FK composite `(origin_run_id, origin_source_snapshot_id, origin_record_ordinal) -> ingestion_run_selected_records(run_id, source_snapshot_id, record_ordinal)` conserve le record sélectionné qui a créé l'observation. Son `page_ordinal` se dérive uniquement de `ingestion_run_snapshots` pour cette run et ce snapshot, jamais d'un item de replay choisi arbitrairement. Une correction de métadonnées sur une version connue crée une nouvelle observation et conserve l'ancienne. Une observation déjà connue est réutilisée et le nouveau `snapshot_record` y est relié sans modifier sa provenance d'origine.

L'observation courante d'une version est la dernière selon `(observed_at, id)`. La citation d'une version explicite peut aussi sélectionner une observation explicite lorsque la provenance doit être reproduite.

### `authors`

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `created_at` | UTC |
| `retired_at` | nullable, UTC |

Un auteur est une identité locale. Son nom observé et ses affiliations vivent dans les relations ou observations de provenance.

### `paper_authors`

Le nom historique est conservé pour la migration initiale, mais l'autorité est l'observation.

| Colonne | Règle |
| --- | --- |
| `version_observation_id` | FK vers `version_observations` |
| `position` | commence à 1 |
| `author_id` | FK vers `authors` |
| `raw_name` | valeur source conservée |
| `affiliation_raw` | nullable |

Clé primaire: `(version_observation_id, position)`.

### `paper_version_categories`

| Colonne | Règle |
| --- | --- |
| `version_observation_id` | FK vers `version_observations` |
| `position` | commence à 1 |
| `category` | valeur source |
| `is_primary` | booléen |

Clé primaire: `(version_observation_id, position)`. Contrainte unique additionnelle: `(version_observation_id, category)`.

## Identifiants externes avec vraies clés étrangères

Les associations polymorphiques sont interdites.

À l'ingestion, `source_item_id` produit toujours un `paper_identifier` dont le scheme est `source_id`, et `source_version_key` produit toujours un `version_identifier` du même scheme. Chaque `ObservedIdentifier` additionnel porte un `IdentifierScope` fermé, `paper` ou `version`, qui détermine la table cible. Aucun adapter catalogue ne déduit ce scope du nom du scheme. Le provider arXiv déclare explicitement son DOI normalisé au scope `paper`, car plusieurs révisions arXiv d'un même papier peuvent observer le même DOI. Les métadonnées DOI observées restent attachées à chaque `version_observation`; seule l'association canonique de l'identifiant est partagée par les versions du papier.

### `paper_identifiers`

`paper_id` est une FK vers `papers`. La ligne canonique contient `scheme`, `canonical_value` et `verified_at` nullable. Contrainte unique globale: `(scheme, canonical_value)`.

### `version_identifiers`

`paper_version_id` est une FK vers `paper_versions`. La ligne canonique contient les mêmes champs hors provenance. Contrainte unique globale: `(scheme, canonical_value)`.

### `author_identifiers`

`author_id` est une FK vers `authors`. La ligne canonique contient `scheme`, `canonical_value`, `verification_status` et `verified_at`. Contrainte unique globale: `(scheme, canonical_value)`. ORCID et OpenAlex ne sont pas dupliqués comme colonnes sur `authors`.

### Preuves d'identifiants

Les preuves sont séparées des associations canoniques afin de conserver plusieurs observations sans dupliquer l'identifiant:

- `paper_identifier_evidence` référence un `paper_identifier`, une `source` et un `snapshot_record` par la FK composite `(source_snapshot_id, record_ordinal)`;
- `version_identifier_evidence` applique la même structure à un `version_identifier`;
- `author_identifier_evidence`, présente dès la migration initiale, référence un `author_identifier` et une `version_observation`;
- `author_identity_identifier_evidence`, ajoutée avec les tables d'identité par la migration `0004_author_identity.py`, référence un `author_identifier` et une `identity_observation`.

Chaque preuve conserve `observed_at` et, lorsqu'elle vient d'une source externe, `source_id`. Une valeur identique observée plusieurs fois garde plusieurs preuves sans dupliquer l'association canonique. Un conflit entre deux entités reste `catalog_conflict`; le titre ou le nom seul ne le résout jamais.

## Runs et erreurs

### `ingestion_runs`

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `source_id` | FK vers `sources` |
| `prepared_digest` | SHA-256 du manifeste confirmé |
| `query_json` | JSON canonique, versionné |
| `status` | `running`, `succeeded`, `partial`, `failed` |
| `started_at` | UTC |
| `finished_at` | nullable, UTC |
| `selected_records` | positif ou nul |
| `new_papers` | positif ou nul |
| `new_versions` | positif ou nul |
| `metadata_updates` | positif ou nul |
| `unchanged_records` | positif ou nul |
| `failed_records` | positif ou nul |

### `ingestion_run_items`

Chaque record sélectionné possède un item avec snapshot, ordinal, identifiants résolus et exactement un outcome:

- `new_version`: une version inconnue et sa première observation sont créées;
- `metadata_update`: la version existe et une observation nouvelle est créée;
- `unchanged`: le hash normalisé existe déjà;
- `failed`: aucune mutation corpus de cet item n'est committée.

`created_paper` est vrai uniquement pour `new_version`. Contrainte unique: `(run_id, source_snapshot_id, record_ordinal)`, également FK vers `ingestion_run_selected_records(run_id, source_snapshot_id, record_ordinal)`. Aucun item ne peut donc viser un record non sélectionné.

À la finalisation, les compteurs sont recalculés depuis les items et doivent respecter:

```text
selected_records = new_versions + metadata_updates + unchanged_records + failed_records
new_papers <= new_versions
new_papers = count(items where created_paper = true)
```

Statut final:

- `succeeded` si `failed_records = 0`, y compris zéro sélection;
- `partial` si une réussite et une erreur coexistent;
- `failed` si tous les items sélectionnés ont échoué.

### `collection_errors`

Une erreur d'item référence `run_id`, le snapshot record, une combinaison fermée d'étape et de code, un message public calculé depuis le code et `occurred_at`. `catalog_write` accepte `record_invalid`, `artifact_invalid` ou `catalog_conflict`; `recovery` accepte uniquement `interrupted` pour un record sélectionné resté sans item. Aucun message libre ne traverse le DTO. Après rollback de l'item métier, le premier `record_failure` crée atomiquement l'item `failed` et son unique erreur dans une transaction courte distincte, avec une révision. Contrainte unique et FK `(run_id, source_snapshot_id, record_ordinal) -> ingestion_run_items(run_id, source_snapshot_id, record_ordinal)`. Un replay de même stage et code ne mute rien et conserve le premier `occurred_at`; un replay divergent ou en conflit avec un item réussi produit `catalog_conflict`. Une erreur purement liée à la run ne crée pas d'item. La réparation crée toutefois un item `recovery/interrupted` pour chaque record sélectionné non traité, car chacun est bien un record sélectionné non committé et participe à `failed_records`. Tous les items et erreurs manquants d'une même run sont créés dans la transaction de réparation, qui finalise les compteurs et incrémente la révision une seule fois.

## Artefacts d'une version

### `artifacts`

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `paper_version_id` | FK vers `paper_versions` |
| `version_observation_id` | FK nullable vers `version_observations` |
| `stored_blob_id` | FK vers `stored_blobs` |
| `kind` | `metadata`, `pdf`, `text`, `analysis` |
| `source_url` | nullable, observée |
| `parent_artifact_id` | FK nullable pour un dérivé |
| `producer_name` | nullable |
| `producer_version` | nullable |
| `created_at` | UTC |

Contrainte unique: `(paper_version_id, kind, stored_blob_id)`. Un artefact `metadata` référence obligatoirement une `version_observation` et son blob contient exactement le JSON bibliographique canonique dont `normalized_sha256` est l'empreinte. Les passages de titre et de résumé utilisent cet artefact comme autorité. Un texte dérivé référence son PDF parent, son extracteur et sa version.

## Collections

### `collections`

Une collection contient `id`, un `slug` unique, un titre, `created_at` et `updated_at`. Les mutations passent par un service d'application CLI, jamais par MCP.

### `collection_papers`

La clé primaire `(collection_id, paper_id)` interdit les doublons. La ligne conserve `added_at` et une note nullable. Supprimer un papier d'une collection ne supprime pas le papier du corpus.

## Watchlists

La migration dédiée ajoute `watchlists` et les tables de runs/digests précisées dans [WATCHLISTS.md](WATCHLISTS.md). Le curseur validé et le curseur candidat restent distincts jusqu'à une finalisation réussie.

## Analyses et preuves

La migration d'analyse ajoute:

- `evidence_passages`, avec FK vers version et artefact, texte normalisé, offsets et composants du `passage_id`;
- `analysis_attempts`, avec empreinte d'entrée, versions de chunk/prompt/schéma, provider, modèle, paramètres, stop reason et validation;
- `analysis_claims`;
- `analysis_claim_evidence`, avec vraies FKs vers claim et passage;
- `analysis_cache_entries`, qui pointe seulement vers une tentative `complete`.

Une tentative ne devient `complete` que si chaque claim possède au moins un passage de la même version et de l'artefact d'entrée. Une tentative invalide ou tronquée reste auditée sans remplacer le cache valide.

## Identité des auteurs

La migration d'identité ajoute les observations de provider, `author_identity_identifier_evidence`, affiliations observées, candidats, événements de merge/split et opérations inverses. Chaque événement conserve preuve, acteur, date et version attendue de l'état. Une URL LinkedIn confirmée est distincte d'une URL de recherche.

## Index de recherche

La base FTS séparée contient `documents`, `passages`, `passages_fts` et `index_meta`. `index_meta` est le reçu privé autoritaire et stocke la révision catalogue source, le schéma de chunk, la génération, les compteurs et l'empreinte logique du contenu indexé. La base candidate est le seul fichier publié par remplacement atomique; aucun sidecar n'est requis pour valider une génération.

La base FTS n'est pas l'autorité des claims d'analyse et ne porte aucune mutation corpus.

## SQLite et migrations

- toutes les connexions catalogue activent `foreign_keys=ON` et un `busy_timeout` configuré;
- les writers utilisent WAL, `synchronous=FULL` et `BEGIN IMMEDIATE`;
- les readers ouvrent une transaction cohérente en lecture seule;
- chaque changement de schéma passe par une seule chaîne Alembic, possédée par Worker A;
- les tests migrent de zéro à `head`, exécutent `foreign_key_check` et `quick_check`, puis testent chaque upgrade publié;
- une migration ne compte pas comme mutation métier et n'incrémente pas `catalog_meta.revision`.
