# ADR-0001: Python et SQLite pour la première architecture

- Statut: accepté
- Date: 2026-08-28

## Contexte

Paper Insights doit collecter des métadonnées scientifiques, gérer des artefacts locaux, construire un index plein texte et exposer une CLI ainsi qu'un MCP. Le projet doit aussi partager des conventions avec YT Insights.

Rust, PostgreSQL et Redis ont été envisagés. Ils augmentent le coût d'intégration, de déploiement et de test avant qu'un besoin de performance ou de concurrence soit mesuré.

## Décision

La première architecture utilise:

- Python 3.12;
- SQLAlchemy 2 et Alembic;
- SQLite pour le catalogue;
- un second fichier SQLite FTS5 pour la recherche;
- `uv` pour l'environnement et les dépendances;
- une CLI locale avant toute API web.

## Raisons

- les bibliothèques d'accès aux APIs scientifiques et de traitement de documents sont disponibles en Python;
- YT Insights fournit des patrons éprouvés pour les chemins, artefacts, index et MCP;
- SQLite suffit à un corpus local mono-utilisateur;
- SQLAlchemy et Alembic clarifient les relations entre papiers, versions, auteurs et watchlists;
- séparer le catalogue de l'index permet une reconstruction atomique sans bloquer les lectures.

## Conséquences

- le code d'ingestion reste synchrone au départ;
- une seule écriture de catalogue est autorisée à la fois;
- les opérations en lot enregistrent leur progression et leurs erreurs;
- les migrations font partie des tests;
- un passage à PostgreSQL exige un nouvel ADR et un benchmark reproductible;
- un moteur vectoriel exige un benchmark de pertinence contre FTS5.

## Options rejetées

### Rust dès la première version

Rust renforcerait certains invariants, mais ralentirait l'intégration des providers, des parseurs et des outils de recherche. Aucun profil de performance actuel ne justifie ce coût.

### PostgreSQL et Redis

Cette combinaison convient à plusieurs workers distribués. Paper Insights commence comme outil local sans besoin prouvé de coordination distante.

### Une seule base SQLite

Mélanger catalogue et FTS simplifierait les fichiers, mais rendrait la publication atomique d'un nouvel index plus difficile. Deux bases donnent une frontière de lecture claire.
