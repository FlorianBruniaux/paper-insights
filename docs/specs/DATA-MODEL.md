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

La création d'une run, chaque item committé, la finalisation, une mutation de collection et une réparation explicite sont des mutations visibles séparées. La publication d'un blob non attaché ne change pas la révision.

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
| `source_id` | FK vers `sources` |
| `stored_blob_id` | FK vers `stored_blobs` |
| `prepared_digest` | SHA-256 du `PreparedDiscovery` exécuté |
| `page_ordinal` | entier positif ou nul |
| `request_fingerprint` | SHA-256 de la requête HTTP canonique |
| `retrieved_at` | UTC, date de récupération source |
| `next_cursor` | nullable, opaque |

Contrainte unique: `(prepared_digest, page_ordinal)`. Rejouer le même manifeste ne crée pas un second snapshot. Une nouvelle découverte identique peut enregistrer un nouvel événement source tout en réutilisant le même blob.

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
| `title` | obligatoire |
| `title_normalized` | obligatoire |
| `abstract` | nullable |
| `comment` | nullable |
| `journal_reference` | nullable |
| `language` | nullable |
| `source_url` | nullable |
| `submitted_at` | nullable, UTC |
| `announced_at` | nullable, UTC |

Contrainte unique: `(paper_version_id, normalized_sha256)`. Une correction de métadonnées sur une version connue crée une nouvelle observation et conserve l'ancienne. Une observation déjà connue est réutilisée et le nouveau `snapshot_record` y est relié.

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

### `paper_identifiers`

`paper_id` est une FK vers `papers`. La ligne contient `source_id`, `scheme`, `canonical_value`, `verified_at` nullable et la référence composite au snapshot record qui l'a prouvée. Contrainte unique: `(source_id, scheme, canonical_value)`.

### `version_identifiers`

`paper_version_id` est une FK vers `paper_versions`. La ligne contient les mêmes champs de provenance. Contrainte unique: `(source_id, scheme, canonical_value)`.

### `author_identifiers`

`author_id` est une FK vers `authors`. La ligne contient `source_id`, `scheme`, `canonical_value`, `verification_status`, `verified_at` et une preuve vers une observation de version ou une observation d'identité. ORCID et OpenAlex ne sont pas dupliqués comme colonnes sur `authors`.

Une valeur identique observée plusieurs fois garde plusieurs preuves sans dupliquer l'association canonique. Un conflit entre deux entités reste `catalog_conflict`; le titre ou le nom seul ne le résout jamais.

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

`created_paper` est vrai uniquement pour `new_version`. Contrainte unique: `(run_id, source_snapshot_id, record_ordinal)`.

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

Une erreur référence `run_id`, l'item ou le snapshot record, une étape fermée, un code stable, un message nettoyé et `occurred_at`. Elle ne contient ni traceback, ni secret, ni URL signée.

## Artefacts d'une version

### `artifacts`

| Colonne | Règle |
| --- | --- |
| `id` | UUIDv7, clé primaire |
| `paper_version_id` | FK vers `paper_versions` |
| `stored_blob_id` | FK vers `stored_blobs` |
| `kind` | `abstract`, `pdf`, `text`, `analysis` |
| `source_url` | nullable, observée |
| `parent_artifact_id` | FK nullable pour un dérivé |
| `producer_name` | nullable |
| `producer_version` | nullable |
| `created_at` | UTC |

Contrainte unique: `(paper_version_id, kind, stored_blob_id)`. Un texte dérivé référence son PDF parent, son extracteur et sa version.

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

La migration d'identité ajoute les observations de provider, affiliations observées, candidats, événements de merge/split et opérations inverses. Chaque événement conserve preuve, acteur, date et version attendue de l'état. Une URL LinkedIn confirmée est distincte d'une URL de recherche.

## Index de recherche

La base FTS séparée contient `documents`, `passages`, `passages_fts` et `index_meta`. Elle stocke la révision catalogue source, le schéma de chunk, sa génération et son propre SHA-256 dans un reçu privé.

La base FTS n'est pas l'autorité des claims d'analyse et ne porte aucune mutation corpus.

## SQLite et migrations

- toutes les connexions catalogue activent `foreign_keys=ON` et un `busy_timeout` configuré;
- les writers utilisent WAL, `synchronous=FULL` et `BEGIN IMMEDIATE`;
- les readers ouvrent une transaction cohérente en lecture seule;
- chaque changement de schéma passe par une seule chaîne Alembic, possédée par Worker A;
- les tests migrent de zéro à `head`, exécutent `foreign_key_check` et `quick_check`, puis testent chaque upgrade publié;
- une migration ne compte pas comme mutation métier et n'incrémente pas `catalog_meta.revision`.
