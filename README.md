# Paper Insights

Paper Insights sera un corpus local de publications scientifiques pour la recherche documentaire, la veille et la préparation de citations. Le projet reprend les garanties utiles de YT Insights sans importer sa dette historique ni déployer PostgreSQL ou Redis avant qu'un besoin mesuré ne le justifie.

## État du projet

Le dépôt contient le socle documentaire et la configuration des agents. L'ingestion, la recherche et le serveur MCP ne sont pas encore implémentés. Les commandes décrites dans les specs sont des contrats cibles, pas des fonctionnalités disponibles.

## Objectifs

- rechercher des papiers à la demande par sujet, auteur, catégorie ou identifiant;
- suivre des requêtes et des catégories afin de détecter les nouvelles publications;
- conserver les métadonnées, les versions, les artefacts et leur provenance;
- indexer les titres, résumés et textes autorisés dans SQLite FTS5;
- produire des analyses reliées aux passages qui les justifient;
- exporter des citations vérifiables pour des articles;
- enrichir les auteurs avec ORCID, OpenAlex et leurs pages institutionnelles;
- exposer une surface MCP locale et en lecture seule.

## Limites initiales

- arXiv constitue la première source, mais le modèle de domaine ne dépend pas d'arXiv;
- la première version reste locale et mono-utilisateur;
- SQLite remplace PostgreSQL et Redis tant que les mesures ne prouvent pas leur nécessité;
- l'analyse de PDF arrive après la collecte fiable des métadonnées et des résumés;
- aucune correspondance LinkedIn n'est validée automatiquement à partir d'un nom;
- aucun scraping LinkedIn n'entre dans le périmètre.

## Architecture cible

```text
providers -> ingestion -> catalog.sqlite3 -> search.sqlite3 -> CLI / MCP
                      \-> artifacts       \-> analyses
```

Le catalogue relationnel conserve les entités et la provenance. Un index FTS5 séparé contient des passages reproductibles. Les analyses référencent les identifiants de passages et l'empreinte de l'artefact utilisé.

## Documents de référence

| Document | Rôle |
| --- | --- |
| [Vision](docs/VISION.md) | Problème, utilisateurs et résultat attendu |
| [Architecture](docs/ARCHITECTURE.md) | Composants, dépendances et flux |
| [Roadmap](docs/ROADMAP.md) | Phases et critères de sortie |
| [Spécification produit](docs/specs/PRODUCT.md) | Cas d'usage et exigences |
| [Modèle de données](docs/specs/DATA-MODEL.md) | Entités, identifiants et provenance |
| [Ingestion](docs/specs/INGESTION.md) | Découverte, reprise et idempotence |
| [Recherche et MCP](docs/specs/SEARCH-AND-MCP.md) | FTS5, citations et outils MCP |
| [Watchlists](docs/specs/WATCHLISTS.md) | Curseurs, overlap, finalisation et digests |
| [Analyse](docs/specs/ANALYSIS.md) | Texte intégral, passages, cache, claims et preuves |
| [Identité des auteurs](docs/specs/AUTHOR-IDENTITY.md) | Observations, décisions réversibles et LinkedIn manuel |
| [Fédération](docs/specs/FEDERATION.md) | Contrat multi-corpus et couverture partielle |
| [Décision Python et SQLite](docs/decisions/ADR-0001-python-sqlite.md) | Choix techniques initiaux |
| [Décision observations et provenance](docs/decisions/ADR-0002-versioned-observations-and-provenance.md) | Autorité des versions, snapshots et preuves |
| [Décision manifeste et publication](docs/decisions/ADR-0003-preview-manifest-and-publication.md) | Batch confirmé, révision et publication atomique |
| [Décision monolithe modulaire](docs/decisions/ADR-0004-modular-monolith-ports.md) | Couches, ports et dépendances |

## Configuration des agents

- `AGENTS.md` définit les règles communes à Codex et aux autres agents.
- `CLAUDE.md` ajoute les conventions propres à Claude Code.
- `.claude/agents/` contient les rôles spécialisés.
- `.agents/skills/` contient les workflows portables.
- `.claude/skills` pointe vers le même répertoire afin d'éviter deux copies divergentes.
- `.claude/hooks/` contient des garde-fous locaux et testés.

## Validation du socle

```bash
python3 scripts/validate_project.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

Ces commandes n'installent aucune dépendance et n'accèdent pas au réseau.

## Sources officielles initiales

- [Aide arXiv pour la catégorie Computer Science](https://info.arxiv.org/help/cs/index.html)
- [Publications récentes en intelligence artificielle](https://arxiv.org/list/cs.AI/recent)

## Licence

Aucune licence publique n'est accordée à ce stade. Le dépôt reste privé jusqu'à une décision explicite.
