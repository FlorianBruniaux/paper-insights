# Spécification de l'ingestion

## Contrat synchrone du provider

```python
class DiscoveryProvider(Protocol):
    source_id: SourceId

    def discover(self, query: DiscoveryQuery) -> DiscoveryBatch: ...
```

`DiscoveryQuery` est un DTO fermé qui contient texte, catégories, auteurs, identifiants explicites, fenêtre de dates UTC, limite et curseur opaque. Au moins un sélecteur est requis.

`DiscoveryBatch` contient:

- la source et la requête canonique;
- des `DiscoveryPage` ordonnées avec `capture_id` UUIDv7, payload brut borné, SHA-256, type MIME, date de récupération, empreinte de requête et curseur suivant;
- des records ordonnés, chacun relié à son ordinal de page et de record;
- les `ObservedPaperVersion` normalisés;
- les issues de collecte ou d'exclusion.

Le tuple `batch.records` doit être strictement égal, dans le même ordre, aux observations portées par les records des pages. Cette redondance immuable ferme la provenance exigée par le contrat Gate 0.

## Préparation sans mutation

`PrepareDiscovery` appelle le provider une fois, applique les limites et produit un `PreparedDiscovery` immuable. Cette opération ne crée ni racine de données, ni base, ni blob, ni fichier temporaire persistant.

L'aperçu versionné contient:

- `schema_version = "discovery-preview-v1"`;
- source et requête JSON canonique;
- nombres demandé, découvert et sélectionné;
- locators sélectionnés avec page, ordinal, identifiant source et identifiant complet de version;
- exclusions et erreurs avec codes stables;
- estimation des artefacts demandés;
- date de préparation, date d'expiration et digest.

Une preview expire après 15 minutes.

## Digest du manifeste

Le digest est le SHA-256 UTF-8 d'un JSON canonique avec clés triées, séparateurs `,` et `:`, sans espaces ajoutés. Il couvre exactement:

```json
{
  "schema_version": "prepared-discovery-v1",
  "source_id": "arxiv",
  "query": {},
  "selected_records": [
    {
      "page_ordinal": 0,
      "raw_record_sha256": "<64 hex>",
      "record_ordinal": 0,
      "source_item_id": "2608.01234",
      "source_version_key": "2608.01234v1"
    }
  ],
  "pages": [
    {
      "capture_id": "<uuidv7>",
      "page_ordinal": 0,
      "request_fingerprint": "<64 hex>",
      "retrieved_at": "2026-08-29T00:00:00Z",
      "sha256": "<64 hex>"
    }
  ]
}
```

`query` est l'objet canonique fermé. Les records sélectionnés conservent l'ordre déterministe après déduplication et leur locator complet: page, ordinal, identifiant d'oeuvre nullable, identifiant de version nullable et empreinte du record brut. Les pages conservent leur ordre, leur `capture_id`, leur empreinte de requête, leur date de récupération et leur SHA-256. Déplacer une sélection vers une autre occurrence de pagination change donc le digest même si sa version normalisée est identique. Modifier requête, sélection, ordre, version, capture ou payload change le digest. Rejouer le même objet préparé conserve le digest; une nouvelle collecte du même payload produit un `capture_id` distinct.

`PreparedDiscovery` conserve le batch exact, l'aperçu, le digest, `prepared_at` et `expires_at`. Le service vérifie la cohérence source/requête, le mapping total page-record et le digest avant toute mutation.

## Confirmation

- Un identifiant explicite unique peut être exécuté après une demande utilisateur explicite.
- Une recherche, catégorie, watchlist ou sélection multiple exige preview puis confirmation.
- `--yes` confirme uniquement le `PreparedDiscovery` construit dans la même exécution CLI.
- Un processus non interactif sans confirmation termine avec le code `3` et zéro mutation.
- Une preview expirée ou un digest différent est refusé avant ouverture d'une run.

Après confirmation, l'exécution consomme le `PreparedDiscovery` reçu. Elle ne rappelle jamais `discover()` et ne reconstruit jamais la sélection depuis la requête.

## Publication des pages et provenance

Pour toutes les pages confirmées:

1. publier le payload comme `stored_blob` content-addressed;
2. publier pour chaque observation sélectionnée le JSON bibliographique canonique comme blob `metadata` content-addressed;
3. ouvrir une transaction `BEGIN IMMEDIATE` unique;
4. attacher tous les `source_snapshots` et leurs `snapshot_records` ordonnés;
5. créer la run liée au même `prepared_digest`;
6. incrémenter la révision catalogue une fois et valider;
7. seulement ensuite ouvrir les transactions courtes par record.

Les blobs sont publiés hors transaction SQL. Un échec avant `os.replace` ne laisse aucun fichier final. Un échec SQL après publication laisse seulement des blobs orphelins que `doctor` signale sans les supprimer. Aucun snapshot ni record partiel n'est visible. Les tests d'injection de panne couvrent une interruption avant publication, après publication des blobs et avant le commit SQL.

Une page multi-papiers reste un snapshot unique. Elle n'est ni copiée, ni enregistrée comme artefact de chaque papier.

## Exécution par item

Une run est créée avant le premier item. Chaque item utilise une transaction `BEGIN IMMEDIATE` qui:

1. retrouve ou crée l'oeuvre par identifiant exact;
2. retrouve ou crée la version source complète;
3. compare le hash bibliographique normalisé;
4. crée une observation immuable si nécessaire;
5. relie snapshot, ordinal, auteurs, catégories, identifiants et artefact `metadata` à l'observation exacte;
6. enregistre un `ingestion_run_item` avec un outcome unique;
7. incrémente la révision catalogue une fois si la transaction contient une mutation visible.

Une erreur sur un item rollbacke ses mutations corpus, puis une transaction séparée enregistre l'item `failed` et son erreur nettoyée. Les succès précédents restent committés.

## Idempotence et mises à jour

Pour arXiv:

- identifiant de papier: forme canonique sans version, par exemple `2608.01234`;
- identifiant de version: forme canonique complète, par exemple `2608.01234v2`.

Un replay du même manifeste:

- réutilise blobs et snapshots logiques;
- retrouve papier, version et observation;
- compte `unchanged`;
- ne crée ni seconde observation identique, ni second artefact identique.

Une nouvelle récupération au payload identique peut ajouter une provenance source distincte tout en reliant l'observation existante. Une métadonnée différente pour la même version crée une `metadata_update`. Une nouvelle version crée `paper_version`, conserve les versions précédentes et met à jour `is_current` dans la même transaction.

## Compteurs et statuts

Les compteurs ont exactement ces sens:

- `selected_records`: records logiques sélectionnés après déduplication;
- `new_papers`: oeuvres localement inconnues créées;
- `new_versions`: versions source localement inconnues créées;
- `metadata_updates`: observations nouvelles attachées à une version source connue;
- `unchanged_records`: hash normalisé déjà connu;
- `failed_records`: records sélectionnés non committés dans le corpus.

La finalisation recalcule les compteurs depuis les items et refuse la transaction si:

```text
selected_records != new_versions + metadata_updates + unchanged_records + failed_records
new_papers > new_versions
```

Statuts:

- `succeeded`: aucune erreur, y compris zéro sélection;
- `partial`: au moins un item réussi et au moins un item échoué;
- `failed`: aucun item réussi et au moins un item échoué.

## Diagnostic et réparation

`paper-insights doctor` est strictement read-only:

- aucun réseau;
- aucune création de dossier, fichier, base ou connexion writable;
- aucun changement de statut;
- aucune suppression d'orphelin;
- aucune valeur sensible dans sa sortie.

Un fichier absent, inaccessible ou ambigu produit `UNKNOWN`, pas un succès.

La récupération est une commande distincte:

```bash
paper-insights repair interrupted-runs --yes
```

Sans `--yes`, elle prévisualise les runs concernées et termine avec le code `3` sans mutation. Avec confirmation, elle marque les runs `running` antérieures au seuil comme `failed`, ajoute le code `interrupted`, finalise leurs compteurs depuis les items et incrémente la révision. La réparation est idempotente et ne rejoue pas le réseau.

## Pagination, délais et reprises

- l'ordre provider est déterministe;
- la page et la limite totale sont bornées;
- les payloads sont streamés sous une limite stricte;
- seuls HTTPS et les hôtes explicitement autorisés sont acceptés;
- chaque redirection est revalidée;
- timeout, `429` et `5xx` peuvent être repris sous bornes;
- `Retry-After` est plafonné;
- les `4xx` permanents ne sont pas repris;
- l'agent utilisateur vient de la configuration sans secret;
- les tests utilisent transports simulés et fixtures figées, jamais le réseau réel.

## Watchlists

Une watchlist prépare puis exécute le même contrat avec fenêtre de recouvrement. Chaque invocation de `watch run` exige `--yes`; aucune autorisation persistante n'est déduite du scheduler ou de la définition de watchlist. Sans confirmation, le manifeste est affiché et le code `3` est rendu sans mutation. La déduplication repose sur les identifiants papier/version et les hashes normalisés, jamais sur le curseur seul. Le curseur candidat devient validé uniquement dans une finalisation réussie décrite dans [WATCHLISTS.md](WATCHLISTS.md).

## Erreurs fermées initiales

- `source_timeout`
- `source_rate_limited`
- `source_response_too_large`
- `source_invalid_payload`
- `source_redirect_refused`
- `record_invalid`
- `artifact_invalid`
- `catalog_conflict`
- `preview_expired`
- `preview_mismatch`
- `interrupted`

Chaque erreur publique contient version de schéma, code, étape et message nettoyé. Le traceback reste dans les logs de développement locaux si leur niveau l'autorise.

## arXiv P1

Le premier adapter cible accepte texte, catégories, limite de 1 à 100, fenêtre de dates et curseur. Le parser préserve ordre des auteurs, catégories, commentaire, journal de référence, DOI et URLs lorsqu'ils sont fournis. Un champ absent reste absent.
