# Paper Insights: design initial

- Date: 2026-08-28
- Statut: historique, remplacé pour l'exécution par le plan complet et les specs Gate 0

Les décisions générales restent informatives. Le périmètre de tranche, les interfaces et le critère final ci-dessous ne sont plus normatifs lorsqu'ils diffèrent de `docs/superpowers/plans/2026-08-28-complete-program-execution.md` ou de `docs/specs/`.

## Objectif

Créer un corpus local de publications scientifiques qui complète YT Insights et Agentic Ecosystem Map. Le système recherche des papiers à la demande, suit des watchlists, conserve les métadonnées et artefacts, produit des citations, analyse les textes avec des preuves et expose une surface MCP read-only.

## Approche retenue

Le projet est un dépôt Python autonome. Il réutilise les principes de YT Insights pour les chemins, runs, artefacts, index SQLite et MCP, mais redécoupe les modules par responsabilité. Il reprend de Cayzn l'idée de séparer domaine, services, schémas et adaptateurs sans reprendre son état global, son scheduler embarqué ou son infrastructure distribuée.

SQLite suffit au mode local mono-utilisateur. SQLAlchemy et Alembic gèrent le catalogue relationnel. Un second fichier SQLite FTS5 peut être reconstruit et publié atomiquement sans modifier le catalogue.

## Périmètre de la première tranche verticale

La première tranche prouve le flux complet sur des métadonnées arXiv:

1. charger une configuration stricte;
2. prévisualiser une requête sur une fixture arXiv;
3. ingérer papiers, versions, auteurs et payload source;
4. rejouer l'ingestion sans doublon;
5. construire un index FTS5 pour titres et résumés;
6. rechercher un papier et un passage;
7. produire une citation BibTeX;
8. exposer ces lectures par MCP.

Les PDF, l'analyse LLM, OpenAlex, ORCID, LinkedIn, la veille automatique et la recherche fédérée restent hors de cette tranche.

## Architecture

Les couches et leurs dépendances sont définies dans `docs/ARCHITECTURE.md`. Le domaine ne dépend d'aucun framework. Les providers, le catalogue, le stockage d'artefacts et l'index implémentent des ports injectés dans les services.

La configuration dérive tous les chemins d'un `data_root`. Aucun client, moteur SQLAlchemy, scheduler ou connexion Redis n'est créé à l'import.

## Modèle et provenance

Le modèle exact se trouve dans `docs/specs/DATA-MODEL.md`. Une œuvre, ses versions et ses identifiants externes restent séparés. Les auteurs ne sont pas fusionnés sur leur seul nom.

Chaque artefact possède un chemin relatif, une taille, un type MIME et un SHA-256. Chaque analyse future conservera l'empreinte d'entrée, le prompt, le modèle et les passages probants.

## Ingestion

La preview et la mutation sont deux opérations distinctes. Une ingestion en lot exige une confirmation. Chaque item utilise une transaction courte et chaque erreur est liée à une run. Une nouvelle version ne remplace pas l'historique.

Le provider arXiv limite pagination, délais, reprises et taille de réponse. Les tests utilisent exclusivement des fixtures locales.

## Recherche et MCP

FTS5 indexe d'abord les titres et résumés. Le classement expose BM25 sans pourcentage inventé. Le MCP reste read-only, refuse les arguments inconnus et borne toutes ses réponses. Les outils exacts figurent dans `docs/specs/SEARCH-AND-MCP.md`.

## Erreurs

Les services utilisent des exceptions métier à codes stables. Le CLI traduit ces codes en messages et codes de sortie. Les réponses MCP ne contiennent ni traceback, ni secret. Un succès partiel conserve les succès et rend les erreurs visibles.

## Tests

La tranche suit TDD. Les tests unitaires couvrent les normalisations, parsers et contrats. Les tests d'intégration appliquent les migrations sur une base temporaire, ingèrent une fixture puis construisent l'index. Les tests de contrat MCP inspectent la surface et les bornes. Aucun test ne dépend du réseau ou d'un service installé.

## Critère final

La tranche est acceptée lorsqu'une base vide peut ingérer une fixture arXiv de trois notices comprenant deux versions d'un même papier, produire le nombre exact de papiers et versions, rester identique au second passage, retourner le titre par FTS5 et générer une citation reliée au payload source.

## Documents normatifs

- `docs/specs/PRODUCT.md`
- `docs/specs/DATA-MODEL.md`
- `docs/specs/INGESTION.md`
- `docs/specs/SEARCH-AND-MCP.md`
- `docs/decisions/ADR-0001-python-sqlite.md`
