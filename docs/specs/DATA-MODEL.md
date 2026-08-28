# Spécification du modèle de données

## Identifiants

- `paper_id`: UUIDv7 généré localement.
- `paper_version_id`: UUIDv7 généré localement.
- `author_id`: UUIDv7 généré localement.
- `artifact_id`: UUIDv7 généré localement.
- `run_id`: UUIDv7 généré localement.
- `analysis_id`: UUIDv7 généré localement.
- `passage_id`: SHA-256 de `paper_version_id`, du type d'artefact, de l'ordinal et du texte normalisé.

Les identifiants externes sont normalisés dans une table dédiée. Aucun identifiant arXiv, DOI, OpenAlex ou ORCID ne devient la clé primaire interne.

## Tables du catalogue

### `papers`

| Colonne | Type | Règle |
| --- | --- | --- |
| `id` | TEXT | clé primaire UUIDv7 |
| `canonical_title` | TEXT | obligatoire |
| `title_normalized` | TEXT | obligatoire, indexé |
| `abstract` | TEXT | chaîne vide si absent |
| `first_seen_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |

### `paper_versions`

| Colonne | Type | Règle |
| --- | --- | --- |
| `id` | TEXT | clé primaire UUIDv7 |
| `paper_id` | TEXT | clé étrangère vers `papers` |
| `source_id` | TEXT | clé étrangère vers `sources` |
| `source_version` | TEXT | identifiant de version fourni par la source |
| `submitted_at` | DATETIME | nullable |
| `announced_at` | DATETIME | nullable |
| `retrieved_at` | DATETIME | UTC obligatoire |
| `is_current` | BOOLEAN | une seule version courante par papier et source |

Contrainte unique: `(source_id, source_version)`.

### `external_identifiers`

| Colonne | Type | Règle |
| --- | --- | --- |
| `entity_type` | TEXT | `paper`, `version` ou `author` |
| `entity_id` | TEXT | identifiant interne |
| `scheme` | TEXT | `arxiv`, `doi`, `openalex`, `orcid` |
| `value` | TEXT | forme canonique |
| `source_id` | TEXT | provenance |
| `verified_at` | DATETIME | nullable |

Contrainte unique: `(scheme, value, entity_type)`.

### `authors`

| Colonne | Type | Règle |
| --- | --- | --- |
| `id` | TEXT | clé primaire UUIDv7 |
| `display_name` | TEXT | nom observé |
| `name_normalized` | TEXT | recherche, pas fusion automatique |
| `orcid` | TEXT | nullable, unique si présent |
| `openalex_id` | TEXT | nullable, unique si présent |
| `linkedin_url` | TEXT | nullable, confirmation humaine requise |
| `linkedin_confirmed_at` | DATETIME | nullable |

### `paper_authors`

| Colonne | Type | Règle |
| --- | --- | --- |
| `paper_version_id` | TEXT | clé étrangère |
| `author_id` | TEXT | clé étrangère |
| `position` | INTEGER | commence à 1 |
| `raw_name` | TEXT | valeur source conservée |
| `affiliation_raw` | TEXT | nullable |

Clé primaire composite: `(paper_version_id, position)`.

### `sources`

| Colonne | Type | Règle |
| --- | --- | --- |
| `id` | TEXT | slug stable, par exemple `arxiv` |
| `base_url` | TEXT | URL officielle |
| `terms_url` | TEXT | nullable |
| `enabled` | BOOLEAN | obligatoire |

### `artifacts`

| Colonne | Type | Règle |
| --- | --- | --- |
| `id` | TEXT | clé primaire UUIDv7 |
| `paper_version_id` | TEXT | clé étrangère |
| `kind` | TEXT | `source_response`, `abstract`, `pdf`, `text`, `analysis` |
| `relative_path` | TEXT | sous `data_root` |
| `sha256` | TEXT | 64 caractères hexadécimaux |
| `size_bytes` | INTEGER | positif ou nul |
| `media_type` | TEXT | obligatoire |
| `created_at` | DATETIME | UTC |

Contrainte unique: `(paper_version_id, kind, sha256)`.

### `ingestion_runs`

| Colonne | Type | Règle |
| --- | --- | --- |
| `id` | TEXT | clé primaire UUIDv7 |
| `source_id` | TEXT | clé étrangère |
| `query_json` | TEXT | JSON canonique |
| `status` | TEXT | `running`, `succeeded`, `partial`, `failed` |
| `started_at` | DATETIME | UTC |
| `finished_at` | DATETIME | nullable |
| `selected_count` | INTEGER | zéro ou positif |
| `created_count` | INTEGER | zéro ou positif |
| `updated_count` | INTEGER | zéro ou positif |
| `unchanged_count` | INTEGER | zéro ou positif |
| `failed_count` | INTEGER | zéro ou positif |

### `collection_errors`

| Colonne | Type | Règle |
| --- | --- | --- |
| `id` | INTEGER | clé primaire |
| `run_id` | TEXT | clé étrangère |
| `source_item_id` | TEXT | nullable |
| `stage` | TEXT | découverte, parsing, artefact ou catalogue |
| `error_code` | TEXT | valeur stable |
| `message` | TEXT | message nettoyé |
| `occurred_at` | DATETIME | UTC |

### `collections` et `collection_papers`

Une collection possède un slug, un titre et des dates. La table de liaison conserve `paper_id`, `added_at` et une note facultative.

### `watchlists`

Une watchlist conserve `slug`, `source_id`, `query_json`, `cursor_json`, `overlap_seconds`, `enabled`, `created_at` et `last_success_at`. Le curseur change uniquement après une run validée.

### `analyses` et `analysis_claims`

Une analyse conserve `paper_version_id`, `artifact_sha256`, `analysis_type`, `schema_version`, `prompt_version`, `model_provider`, `model_name`, `status`, `result_json`, `created_at`. Chaque claim conserve son texte, sa catégorie, son niveau d'incertitude et une relation vers un ou plusieurs `passage_id`.

## Index de recherche

L'index séparé contient:

- `documents`: papier, version, titre, résumé, langue, source et empreinte;
- `passages`: identifiant, document, ordinal, section, texte et offsets;
- `passages_fts`: titre, section et texte;
- `index_meta`: version du schéma, génération, date et empreinte du catalogue.

## Normalisation et fusion

- un identifiant externe exact prime sur le titre;
- un DOI canonique peut relier des notices de sources différentes;
- un titre normalisé seul produit un candidat, jamais une fusion automatique;
- un ORCID exact peut relier un auteur;
- un nom exact sans identifiant ne suffit pas pour fusionner deux auteurs;
- chaque fusion ou séparation d'auteur produit un événement d'audit réversible.

## Migrations

Chaque changement de table passe par Alembic. Les tests créent une base vide, appliquent toutes les migrations, contrôlent le schéma, puis testent une mise à niveau depuis la version précédente lorsque celle-ci existe.
