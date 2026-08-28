# Instructions agents pour Paper Insights

## Mission

Construire un corpus scientifique local qui permet de collecter, rechercher, analyser et citer des publications avec une provenance vérifiable.

## Ordre de lecture

Avant une modification substantielle, lire dans cet ordre:

1. `README.md`
2. `docs/VISION.md`
3. `docs/ARCHITECTURE.md`
4. la spec concernée dans `docs/specs/`
5. `docs/ROADMAP.md`
6. `CHANGELOG.md`

## Règles de preuve

- Une métadonnée externe conserve sa source, sa date de récupération et son identifiant d'origine.
- Une analyse LLM conserve le modèle, la version du prompt, l'empreinte de l'entrée et les passages utilisés.
- Une citation n'est jamais reconstruite à partir d'un résumé LLM.
- Un résultat absent ou ambigu reste `UNKNOWN`. Ne pas inventer un auteur, un DOI, un ORCID, une affiliation ou une URL LinkedIn.
- Distinguer les données observées, les données normalisées et les inférences.

## Périmètre technique

- Python 3.12 minimum.
- SQLite pour le catalogue et SQLite FTS5 pour l'index de recherche.
- SQLAlchemy 2 et Alembic pour le catalogue.
- Interfaces synchrones par défaut. Ajouter de l'asynchrone uniquement après une mesure ou une contrainte externe documentée.
- CLI avant API web.
- MCP en lecture seule.
- Aucun PostgreSQL, Redis, moteur vectoriel ou orchestrateur distribué sans ADR et mesure justificative.

## Frontières des composants

- `providers` traduit une source externe en objets bruts typés.
- `ingestion` orchestre une exécution, mais ne contient pas de logique propre à une source.
- `catalog` possède les transactions et les migrations.
- `artifacts` possède les fichiers, les empreintes et les écritures atomiques.
- `search` construit et interroge l'index publié.
- `analysis` dépend de passages stables, jamais d'un chemin implicite.
- `mcp` appelle les services en lecture seule et ne reconstruit aucune logique métier.

## Méthode de développement

1. Lire la spec et nommer le critère d'acceptation visé.
2. Écrire un test qui échoue pour le comportement demandé.
3. Implémenter le changement minimal.
4. Lancer le test ciblé, puis la suite complète.
5. Exécuter les contrôles statiques pertinents.
6. Mettre à jour la documentation et `CHANGELOG.md` si le comportement change.

Commandes de validation du socle actuel:

```bash
python3 scripts/validate_project.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

Commandes cibles après la phase 0:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Données et sécurité

- Ne jamais lire, afficher ou committer `.env`, tokens, cookies ou credentials.
- Les tests utilisent des fixtures locales figées. Ils n'appellent pas arXiv, OpenAlex, Crossref, ORCID ou un LLM.
- Une opération réseau et une mutation du corpus restent distinctes de la prévisualisation.
- Une ingestion multiple exige une prévisualisation puis une confirmation explicite.
- Les fichiers récupérés restent sous la racine de données configurée.
- Les écritures finales utilisent un fichier temporaire, une validation puis un remplacement atomique.
- Les données du corpus, les PDF et les bases SQLite restent ignorés par Git.

## Auteurs et LinkedIn

- Préférer ORCID, OpenAlex et les pages institutionnelles pour désambiguïser une personne.
- Une recherche LinkedIn peut être générée, mais elle n'est pas un profil confirmé.
- Stocker `linkedin_url` uniquement après confirmation humaine.
- Ne pas scraper LinkedIn et ne pas fusionner deux auteurs sur leur seul nom.

## Git

- Préserver les changements sans rapport avec la tâche.
- Utiliser des pathspecs explicites pour ajouter des fichiers.
- Ne pas employer `git add .`, `git reset --hard` ou un push forcé.
- Garder les commits petits et associés à un comportement vérifiable.

## Documentation

- Écrire les décisions avant le code qui en dépend.
- Les chemins référencés dans les rapports de travail sont absolus.
- Ne pas présenter une interface cible comme déjà disponible.
- Éviter l'em dash en prose.
- Après toute modification, mettre à jour `CHANGELOG.md` sous `[Unreleased]`.

## Fin de tâche

Rapporter:

1. les fichiers modifiés;
2. les commandes exécutées et leurs résultats;
3. les comportements non vérifiés;
4. le hash du commit et la branche si un commit a été créé.
