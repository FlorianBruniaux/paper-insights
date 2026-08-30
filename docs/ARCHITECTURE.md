# Architecture cible de Paper Insights

## État et décision d'ensemble

Cette architecture est le contrat cible du programme. Le runtime métier n'est pas encore disponible tant que les gates correspondantes ne sont pas passées.

Paper Insights reste un monolithe modulaire local avec trois autorités de stockage sous une racine de données unique:

- `catalog.sqlite3` conserve les identités, observations, relations, exécutions et preuves durables;
- `.search/search-v1.sqlite3` est une projection FTS5 remplaçable;
- `blobs/` contient les payloads et artefacts immuables adressés par SHA-256.

SQLite, le système de fichiers, HTTP, les backends LLM, la CLI et le MCP sont des adaptateurs. Ils ne définissent pas le domaine.

## Arborescence cible

```text
src/paper_insights/
├── domain/                 valeurs et invariants sans framework
├── application/
│   ├── ports/              protocoles synchrones
│   ├── ingestion/          préparation, exécution et réparation
│   ├── research/           index, recherche, collections et citations
│   ├── monitoring/         watchlists et digests
│   ├── analysis/           texte intégral, passages et analyses
│   ├── identity/           observations et décisions d'identité
│   └── federation/         orchestration de corpus indépendants
├── adapters/
│   ├── providers/          arXiv, OpenAlex et ORCID
│   ├── catalog/sqlite/     SQLAlchemy, Alembic et transactions
│   ├── artifacts/filesystem/
│   ├── search/sqlite_fts/
│   ├── analysis/
│   ├── identity/
│   └── federation/
├── interfaces/
│   ├── cli/
│   └── mcp/
├── config.py
├── paths.py
└── bootstrap.py
```

## Règle de dépendance

Les dépendances pointent vers le domaine et les ports:

```text
interfaces -> services d'application -> domain
                                 \----> application.ports
adapters ------------------------------> application.ports
bootstrap -> interfaces + services + adapters + configuration
```

Règles vérifiées par AST:

- `domain` n'importe ni `application`, ni `adapters`, ni `interfaces`, ni framework;
- `application` n'importe ni `adapters`, ni `interfaces`, ni racine de composition;
- `interfaces` appelle les services d'application et n'importe aucun modèle SQLAlchemy;
- les adaptateurs n'exposent que des DTO du domaine ou des ports;
- `bootstrap.py` est le seul module qui assemble les implémentations concrètes;
- aucun client HTTP, moteur SQLAlchemy, serveur MCP ou scheduler n'est créé à l'import.

Pydantic reste limité à la configuration, aux enveloppes CLI/MCP et aux schémas de frontière LLM. Les contrats métier utilisent des dataclasses immuables.

Les signatures publiques et DTO de frontière sont figés dans [PORTS.md](specs/PORTS.md).

## Autorités et frontières

| Contexte | Autorité | Ports publics |
| --- | --- | --- |
| Plateforme | horloge, identifiants, configuration et chemins | `Clock`, `IdGenerator` |
| Acquisition | requêtes, pages, snapshots, preview et runs | `DiscoveryProvider`, `CatalogUnitOfWorkFactory`, `BlobStore` |
| Corpus | papiers, versions, observations, auteurs, identifiants et collections | `CatalogReader`, `CatalogUnitOfWorkFactory` |
| Retrieval | générations FTS, documents, passages et BM25 | `SearchIndexBuilder`, `SearchIndexReader`, `CatalogRevisionGuard` |
| Citations | BibTeX, Markdown et CSL-JSON | `CitationRenderer` |
| Monitoring | watchlists, recouvrement, curseurs et digests | `WatchlistUnitOfWorkFactory` |
| Analysis | texte autorisé, extraction, passages, cache, claims et preuves | `FullTextProvider`, `TextExtractor`, `AnalysisBackend`, `AnalysisUnitOfWorkFactory` |
| Identity | observations, candidats et événements réversibles | `IdentityProvider`, `IdentityUnitOfWorkFactory` |
| Federation | résultats natifs, couverture partielle et dossiers de preuves | `FederatedCorpus`, `EvidenceBundleWriter` |
| Delivery | CLI et six outils MCP read-only | services d'application uniquement |

## Flux de découverte et d'ingestion

1. Un provider exécute une requête bornée et retourne un `DiscoveryBatch` immuable contenant pages brutes, enregistrements normalisés et issues.
2. Le service prépare un `PreparedDiscovery`, son aperçu, son digest et son expiration sans écrire dans le corpus.
3. La confirmation porte sur ce manifeste exact. L'exécution ne rappelle jamais le provider.
4. Les pages brutes et les JSON bibliographiques canoniques sont publiés comme blobs immuables.
5. Une transaction unique attache toutes les pages comme `source_snapshots`, crée leurs `snapshot_records` et crée la run. Une page multi-papiers n'est jamais un artefact de papier.
6. Chaque record sélectionné est ensuite traité dans une transaction courte `BEGIN IMMEDIATE`; l'artefact `metadata` relie son observation au JSON canonique exact.
7. La transaction item crée ou retrouve papier, version et observation, relie provenance, auteurs, catégories et identifiants, puis enregistre un outcome unique.
8. La finalisation recalcule les compteurs depuis les items et refuse un invariant faux.
9. Une interruption reste visible comme `running`. `doctor` la signale sans mutation; `repair interrupted-runs --yes` est la seule réparation.

## Transactions catalogue

Toutes les connexions catalogue activent `foreign_keys=ON`, un `busy_timeout` configuré, WAL et `synchronous=FULL`. Le moteur ouvre uniquement une base existante en `mode=rw` et vérifie l'identité du fichier régulier avant et après la configuration de chaque connexion; un remplacement par lien symbolique ou par un autre inode échoue avant les PRAGMA mutantes. Les writers utilisent `BEGIN IMMEDIATE`; un seul propriétaire produit les modèles SQLAlchemy et les migrations Alembic.

`catalog_meta.revision` commence à zéro après migration. Une transaction validée qui contient au moins une mutation visible l'incrémente exactement une fois dans la même transaction. Une lecture, un no-op, un rollback ou un échec ne l'incrémente pas.

Une lecture cohérente utilise un `CatalogSnapshot`: la révision et les lignes sont lues dans la même transaction read-only. Aucun iterator ne survit à la fermeture de ce contexte.

## Publication de l'index FTS5

1. Ouvrir un snapshot catalogue et mémoriser sa révision.
2. Construire une base candidate dans un fichier sibling avec `journal_mode=DELETE`.
3. Insérer documents, passages et métadonnées dans une transaction stable.
4. Exécuter `PRAGMA quick_check`, contrôler les compteurs et écrire le reçu autoritaire dans `index_meta`.
5. Committer, fermer toutes les connexions, refuser tout `-wal` ou `-shm`, forcer le fichier, puis le vérifier à nouveau en lecture seule.
6. Prendre un `CatalogRevisionGuard` avec `BEGIN IMMEDIATE`.
7. Relire la révision sous cette garde et abandonner si elle diffère.
8. Publier la candidate fermée par `os.replace`, puis forcer le répertoire parent avant de libérer la garde.

Une erreur ou une révision obsolète laisse l'index publié précédent intact. `index_meta` rend la nouvelle base auto-descriptive après le remplacement; aucun journal SQLite ou sidecar ne crée une seconde frontière atomique. Le service de recherche ouvre l'index en `mode=ro` avec `query_only=ON` et ne déclenche ni réseau, ni ingestion, ni analyse.

## Flux d'analyse et preuves durables

1. Résoudre une version et un artefact stable, puis vérifier son SHA-256.
2. Extraire sous limites et produire des passages déterministes.
3. Traiter le texte du papier comme donnée non fiable, jamais comme instruction système.
4. Appeler un backend LLM injecté avec un schéma de sortie fermé et versionné.
5. Enregistrer la tentative, le stop reason, les claims et leurs passages probants.
6. Publier `complete` seulement si chaque claim possède au moins une preuve valide.

Les passages utilisés comme preuves sont conservés dans le catalogue avec leur artefact et leurs offsets. L'index FTS reste une projection remplaçable. Une sortie invalide ou tronquée ne remplace jamais un cache valide.

## Interface CLI cible

Les commandes suivantes sont des contrats cibles, pas une preuve de disponibilité:

- `paper-insights discover` et `paper-insights ingest` pour l'acquisition;
- `paper-insights search`, `paper-insights index` et `paper-insights cite` pour la recherche;
- `paper-insights collections` pour les mutations de collections hors MCP;
- `paper-insights watch run <slug> --yes` pour chaque veille appelée par un scheduler externe;
- `paper-insights analyze` et `paper-insights authors` pour les gates ultérieures;
- `paper-insights repair interrupted-runs --yes` pour la récupération explicite;
- `paper-insights mcp serve` pour la façade locale read-only.

`doctor` reste strictement sans écriture et sans réseau. Le scheduler reste externe; aucun worker web ou scheduler embarqué n'est ajouté.

## Sécurité et évolution

- tous les chemins résolus restent sous `data_root` et les fichiers temporaires sont privés;
- schémas, hôtes, redirections, délais et tailles sont contrôlés par provider;
- les erreurs publiques portent un code stable et un message nettoyé;
- les réponses MCP ouvrent SQLite en lecture seule et sont bornées;
- aucun secret, corpus, PDF, base SQLite ou reçu privé n'entre dans Git;
- PostgreSQL, Redis, embeddings, async, file distribuée ou interface web exigent une mesure et un ADR séparé.

Décisions associées: [ADR-0001](decisions/ADR-0001-python-sqlite.md), [ADR-0002](decisions/ADR-0002-versioned-observations-and-provenance.md), [ADR-0003](decisions/ADR-0003-preview-manifest-and-publication.md) et [ADR-0004](decisions/ADR-0004-modular-monolith-ports.md).
