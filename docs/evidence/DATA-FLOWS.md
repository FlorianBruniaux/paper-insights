# Flux de données et stockages

Ce document inventorie les chemins réseau et les stockages durables détenus par Paper Insights. Il ne couvre pas le trafic de la session Codex ou Claude qui exécute des commandes autour du dépôt. Aucun composant listé ne publie un papier ou un corpus vers un service tiers.

<!-- evidence-governance:data-flows -->
```json
{
  "schema_version": "data-flow-inventory-v1",
  "direct_network_modules": [
    {"path": "src/paper_insights/adapters/providers/arxiv/client.py", "flow_ids": ["N1"]},
    {"path": "src/paper_insights/bootstrap.py", "flow_ids": ["N1"]}
  ],
  "durable_stores": [
    {"id": "S1", "path": "<data_root>/catalog.sqlite3"},
    {"id": "S2", "path": "<data_root>/blobs/"},
    {"id": "S3", "path": "<data_root>/.search/search-v1.sqlite3"},
    {"id": "S4", "path": "<repository>/output/search-relevance/<candidate>/"}
  ]
}
```

## Appels réseau directs

| ID | Déclencheur | Données transmises | Destination | Credentials | Limites | Arrêt |
| --- | --- | --- | --- | --- | --- | --- |
| N1 | Commande explicite de découverte arXiv | Texte de requête, catégories, auteurs, identifiants, bornes de date, pagination et User-Agent | `https://export.arxiv.org/api/query` avec hôte fermé | Aucun | Timeout, tentatives, redirections, pages et réponse à 5 Mio maximum | Ne pas lancer la découverte ou définir `sources.arxiv.enabled = false` |

Le composition root dans `bootstrap.py` construit le client HTTP. Le seul module qui émet la requête est `adapters/providers/arxiv/client.py`. Les tests utilisent un transport local et `pytest-socket`; aucun test d'intégration n'appelle arXiv.

## Stockages durables

| ID | Contenu | Durée | Mutation | Suppression |
| --- | --- | --- | --- | --- |
| S1 | Catalogue, versions, observations, runs, erreurs, collections et reçus | Jusqu'à suppression explicite du corpus | CLI applicative et migrations uniquement | Supprimer le corpus choisi par l'utilisateur après sauvegarde |
| S2 | Payloads source et artefacts immuables par SHA-256 | Jusqu'à suppression explicite du corpus | Publication atomique sous `data_root` | Même frontière que S1 |
| S3 | Projection FTS5 reconstruisible et son reçu | Jusqu'à reconstruction ou suppression | Builder FTS sous garde de révision | Supprimable puis reconstruisible depuis S1 et S2 |
| S4 | Inventaires, résultats, formulaires et manifestes du benchmark Gate 2 | Jusqu'à suppression explicite de la tentative | CLI de benchmark, sans mutation du corpus | Supprimer le répertoire de tentative sous `output/` |

## Limites

- Les futurs providers OpenAlex, Crossref, ORCID et backends LLM ne sont pas inventoriés comme actifs avant leur implémentation.
- Une importation réseau directe ajoutée sous `src/paper_insights` doit obtenir une ligne avant que le checker passe.
- Un appel indirect via un CLI ou un outil d'agent exige une revue manuelle et une ligne dédiée avant activation.
- Les fichiers de configuration ne doivent pas contenir de secret; les valeurs sensibles ne sont jamais rendues par `doctor`.
