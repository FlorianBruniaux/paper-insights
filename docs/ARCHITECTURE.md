# Architecture de Paper Insights

## Décision d'ensemble

Le projet utilise deux bases SQLite sous une racine de données unique:

- `catalog.sqlite3` contient les entités, relations, exécutions et erreurs;
- `.search/search-v1.sqlite3` contient les documents et passages FTS5 publiés.

Les artefacts bruts et dérivés restent sur disque. Le catalogue enregistre leur chemin relatif, leur taille, leur type MIME et leur SHA-256.

## Composants

```text
paper_insights/
├── cli/           commandes et rendu utilisateur
├── config.py      configuration stricte et précédence
├── paths.py       chemins dérivés de data_root
├── domain/        types métier sans accès externe
├── providers/     arXiv, puis OpenAlex, Crossref et ORCID
├── ingestion/     previews, runs, reprise et erreurs
├── catalog/       transactions SQLAlchemy et migrations Alembic
├── artifacts/     téléchargement borné, empreintes, publication atomique
├── search/        chunking, construction FTS5 et requêtes
├── analysis/      schémas, prompts et rattachement aux passages
├── citations/     BibTeX, Markdown et CSL-JSON
└── mcp/           façade locale strictement read-only
```

Chaque paquet possède un contrat public réduit. Le CLI et le MCP appellent des services d'application, jamais directement un provider ou une table.

## Flux d'ingestion

1. Un provider transforme une requête en page de résultats bruts.
2. Le service de preview applique les limites et produit un résumé sans écrire dans le corpus.
3. Après autorisation, une `ingestion_run` est ouverte.
4. Chaque résultat est normalisé en papier, version, auteurs et identifiants.
5. Les artefacts sont écrits dans un fichier temporaire, contrôlés, puis publiés par remplacement atomique.
6. Le catalogue enregistre les objets, les empreintes et les erreurs dans une transaction bornée.
7. La run se termine avec un statut et des compteurs exacts.
8. Une reconstruction séparée publie un nouvel index FTS5.

Une erreur sur un papier ne supprime pas les succès précédents de la run. Elle produit une `collection_error` liée à la source et à l'étape.

## Flux de recherche

1. La requête est normalisée et bornée.
2. Le service interroge l'index FTS5 en lecture seule.
3. Les passages retournent `paper_id`, `paper_version_id`, `passage_id`, rang et extrait.
4. Le catalogue complète les métadonnées et les identifiants.
5. Le CLI ou le MCP tronque sa réponse sous une limite documentée.

Le service de recherche ne déclenche ni collecte, ni analyse, ni reconstruction d'index.

## Flux d'analyse

1. L'utilisateur choisit un papier et une version.
2. Le service résout un artefact stable et vérifie son empreinte.
3. Le texte est découpé en passages déterministes.
4. Le backend LLM reçoit des lots bornés.
5. La sortie est validée avec Pydantic.
6. Chaque claim conserve les `passage_id` probants.
7. L'analyse finale est écrite atomiquement et enregistrée dans le catalogue.

Une réponse tronquée, invalide ou sans passage probant n'est pas publiée comme analyse complète.

## Dépendances

Le domaine ne dépend d'aucun framework. Les dépendances pointent vers l'intérieur:

```text
CLI / MCP -> services -> domain
                      -> ports
providers / catalog / search / LLM -> ports
```

Les clients HTTP, sessions SQLAlchemy, horloges et générateurs d'identifiants sont injectés. Aucun client réseau ou scheduler n'est créé à l'import d'un module.

## Processus

La première version utilise des commandes courtes:

- `paper-insights search` lit le corpus;
- `paper-insights ingest` collecte après preview;
- `paper-insights watch run` exécute une veille;
- `paper-insights index build` reconstruit l'index;
- `paper-insights mcp serve` démarre le serveur local.

Le planificateur reste externe. `cron`, `launchd` ou une automation appelle la CLI. Cette frontière évite les tâches dupliquées dans plusieurs workers web.

## Sécurité et données

- les fichiers de configuration ne contiennent pas de secret;
- les réponses HTTP ont une taille maximale;
- les redirections, schémas et hôtes sont contrôlés par provider;
- les chemins restent sous `data_root` après résolution;
- les lectures du MCP ouvrent SQLite en mode read-only;
- les messages d'erreur ne contiennent ni traceback, ni token, ni URL signée;
- le corpus et les PDF restent hors Git.

## Évolution

PostgreSQL devient une option seulement si plusieurs processus doivent écrire simultanément ou si les mesures SQLite dépassent les seuils documentés. Un index vectoriel devient une option seulement après un benchmark contre FTS5 sur un jeu de requêtes annoté manuellement.
