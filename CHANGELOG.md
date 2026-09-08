# Changelog

Toutes les modifications notables du projet sont consignées ici.

## [Unreleased]

### Added

- Paquet de décision proposé pour le benchmark humain de pertinence, avec options réversibles de corpus, distribution des requêtes, frontière P0 et champs liés par empreinte à compléter après inventaire.
- Design and implementation plan for cross-cutting evidence governance without changing the existing work-package order.
- Machine-readable capability matrix with deterministic, behavioral and human evidence states, bounded claims and next evaluations.
- Dependency-free capability-matrix validator with fail-closed tests for invalid statuses, missing evidence, denominators and unjustified operational claims.
- Risk register and checked data-flow inventory tied to the capability matrix and direct network imports.
- Socle documentaire du projet Paper Insights.
- Specs initiales pour le produit, le modèle de données, l'ingestion, la recherche et le MCP.
- Configuration locale pour Claude Code et les agents compatibles.
- Hooks de sécurité et de routage accompagnés de tests unitaires.
- Découverte `unittest` vérifiée depuis la racine du répertoire `tests`.
- Garde Git vérifiée contre les stages larges sans bloquer les pathspecs relatifs explicites.
- Roadmap et plan d'implémentation de la première tranche verticale.
- Plan d'exécution complet des phases 0 à 7, avec contrats P0, lots parallèles, propriétaires de fichiers, gates et critères de release.
- Contrats Gate 0 pour observations versionnées, snapshots source multi-records, identifiants à clés étrangères et révision atomique du catalogue.
- Specs normatives pour watchlists, analyses sourcées, identité réversible des auteurs et fédération multi-corpus.
- Contrats fermés pour collections, trois formats de citation, six outils MCP, enveloppes JSON et codes de sortie CLI.
- Contrat complet des ports synchrones, preuves d'identifiants séparées et artefacts bibliographiques versionnés.
- Types de domaine immuables, ports synchrones et tests d'architecture de Gate 0.
- Catalogue SQLite révisionné avec migration Alembic, clés étrangères composites, historique de provenance et snapshots de lecture strictement read-only.
- Adaptateur arXiv borné avec validation des redirections, pagination déterministe, déduplication et normalisation versionnée testées sur fixtures locales.
- Socle Python installable, stockage de blobs atomique et diagnostics `doctor` read-only qui distinguent corruption prouvée et état `UNKNOWN`.
- Workflow CI séparant contrôles statiques, tests unitaires sans réseau et gate de frontière MCP avant l'implémentation du runtime MCP.
- Ingestion préparée avec confirmation exacte, attachement atomique du graphe de snapshots, transactions courtes par record, compteurs fermés, replay idempotent et réparation explicite des runs interrompues.
- Collections applicatives et citations BibTeX, Markdown et CSL-JSON rendues depuis une observation et une provenance exactes, sans champ bibliographique inventé.
- Index local FTS5 `fts-v2` auto-descriptif avec passages déterministes, publication sous garde de révision, lecture par descripteur en mode read-only et six filtres fermés.
- CLI Gate 2 pour discovery, ingestion confirmée, recherche papier et passage, reconstruction d'index, citations BibTeX, Markdown et CSL-JSON, collections et réparation explicite, avec enveloppes JSON versionnées et fixtures arXiv hors ligne.
- Harnais hors réseau du Gate 2 pour inventaire aveugle, exécution des 30 recherches, capture des cinq premiers `paper_id`, formulaire de revue et validation fermée des verdicts humains.

### Changed

- Les décisions D1 à D3 sont approuvées et le paquet Gate 2 lie maintenant les manifestes observés du candidat `gate2-arxiv-metadata-v1`, son catalogue à la révision 147, son index `fts-v2` et son inventaire aveugle de 120 papiers. La sélection capturée respecte le cutoff approuvé, contient 20 nouveaux papiers par étape de catégorie et n'a ni titre ou résumé vide, ni version autre que `v1`, ni égalité de `submitted_at`; elle ne prouve pas l'exhaustivité historique d'arXiv. Les 30 requêtes restent proposées, aucune recherche ni revue humaine n'existe et le Gate 2 reste bloqué à 0/30.
- Les requêtes arXiv ordonnent désormais les records provider selon `submittedDate` décroissant. L'éligibilité d'une version à un cutoff historique doit être vérifiée séparément à partir des métadonnées de la version récupérée.
- Project validation now consumes the capability matrix, and README distinguishes the implemented Gate 2 integration surface from the blocked human relevance gate and unopened later waves.
- The roadmap and complete execution plan now reference the evidence-governance overlay as a cross-cutting control rather than a competing plan.
- Le contrat `search-relevance-v1` distingue désormais les états `blank`, `prepared`, `executed` et `reviewed`; seule une revue complète compte pour le Gate 2.
- The arXiv adapter scopes DOI identifiers to the paper while retaining each DOI observation on its exact version, allowing multiple arXiv revisions to share the same DOI without a catalog conflict.
- Paper search hits now carry their source, ordered authors and scoped canonical identifiers directly from the fingerprinted `fts-v2` projection.
- Catalog connections now open only an existing database and reject file or symlink binding changes before applying writable SQLite pragmas.
- CLI date filters accept documented UTC dates with inclusive day bounds, interrupted-run repair defaults to a 24-hour stale window, and interactive ingestion confirms the exact prepared manifest while non-interactive execution still requires `--yes`.
- Catalog snapshots now use immutable descriptor-bound reads and fail closed on active WAL or SHM sidecars, so repair previews do not create corpus files.
- Catalog snapshots now materialize a validated in-memory image before exposing a revision, preventing later concurrent writes from mixing newer rows with that revision while keeping previews free of corpus sidecars.
- CLI success envelopes now validate closed, operation-specific nested data models, and terminal passage search exposes the same revisions, coverage, counters and hit provenance as JSON output.
- Exit code 4 now explicitly covers any completed ingestion run with recorded item errors, including both `partial` and `failed` statuses.
- `docs/DEVELOPMENT.md` et l'ancien plan vertical pointent désormais vers le plan complet comme seule autorité d'exécution.
- `doctor` est spécifié strictement read-only; la récupération passe par `repair interrupted-runs --yes`.
- Le manifeste de découverte distingue chaque capture, la création de run attache ses snapshots dans une transaction unique et l'index FTS se publie comme une base auto-descriptive unique.
- Les locators sélectionnés participent au digest, les preuves d'identité différées évitent toute FK vers une table future et la publication FTS refuse les journaux compagnons.
- Les commandes catalogue transportent désormais le graphe complet des snapshots et des blobs non attachés; les DTO ferment outcomes, provenance de citation, filtres de recherche, reçu d'index et identité du cache d'analyse.
- L'attachement catalogue est lié directement au manifeste préparé; les DTO publics valident leurs valeurs à la construction, les résultats de recherche bornent et ordonnent leurs hits, et les chemins d'index sont absolus.
- Le contrôle d'architecture couvre les imports relatifs sans module, ignore les corps de lambda différés et gèle les signatures exactes de tous les ports annoncés.
- Les passages vérifient leur identité déterministe, les acquisitions de texte exigent HTTPS et les résultats de citation utilisent un vocabulaire d'avertissements fermé.
- Les deux couches internes refusent les imports d'infrastructure et tous les champs tuple des DTO rejettent les alias de collections mutables.
- Pydantic reste interdit dans le domaine, les ports et l'application hors du futur module exact de validation de la frontière LLM prévu par WP-40.
- L'attachement retourne un mapping stable des snapshots réutilisé au replay; les échecs d'item disposent d'un contrat fermé, traçable et idempotent après rollback.
- La réparation matérialise chaque record sélectionné non traité en échec `recovery/interrupted`; les références d'item incluent le snapshot et les messages d'erreur sont dérivés d'un vocabulaire fermé.
- Les runs persistent séparément leurs pages et leur sélection ordonnée, ce qui rend la reprise exacte possible sans décoder un digest ni confondre les records exclus.
- Les échecs de connexion source ont un code public distinct des timeouts et des réponses invalides.
- La reprise des runs interrompues possède des DTO et ports fermés pour la preview read-only, la revalidation verrouillée et la mutation atomique à révision unique.
- Les captures dupliquées sont refusées et les FKs composites ferment désormais l'appartenance entre run, source, sélection, item et erreur.
- Chaque observation de version conserve son record sélectionné d'origine, ce qui rend la reconstruction de page déterministe même après replay d'une capture.
- `record_item` devient l'unique mutation atomique du corpus et de l'item, et son résultat restitue les identifiants créés sans perdre le `run_id` de provenance.
- Les identifiants provider et additionnels déclarent désormais explicitement leur portée papier ou version, sans convention silencieuse côté catalogue.
- Les observations versionnées portent aussi `origin_source_id`, ce qui rend impossible une provenance croisée entre version, snapshot et run.
- Les diagnostics revalident les preuves catalogue et artefact après chaque phase afin de refuser les conclusions devenues obsolètes pendant une course concurrente.
- Les enums textuels publics utilisent `StrEnum`, ce qui rend `str(member)` identique à la valeur canonique sérialisée tout en conservant les mêmes noms et valeurs.
- La projection catalogue de recherche inclut source, auteurs ordonnés, catégories, langue, date et collections; son empreinte logique couvre désormais chaque valeur filtrable.
- La publication FTS restaure l'ancien index canonique après une mutation concurrente du répertoire et ne supprime jamais un nom devenu ambigu; un résidu dans un répertoire déplacé reste alors explicitement non réparé.
- Les slugs de collection au format UUID sont refusés et le filtre collection interprète sans ambiguïté une valeur UUID comme ID, toute autre valeur comme slug.
- La configuration refuse désormais une page arXiv supérieure à 100 et une limite de recherche supérieure à 50, conformément aux DTO et adapters publics.
