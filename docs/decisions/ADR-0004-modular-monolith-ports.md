# ADR-0004: Monolithe modulaire et ports synchrones

- Statut: accepté
- Date: 2026-08-29

## Contexte

Le programme couvre acquisition, catalogue, recherche, citations, monitoring, analyse, identité, fédération, CLI et MCP. Des paquets techniques de premier niveau laisseraient les interfaces appeler directement SQLAlchemy ou HTTP et pousseraient les workers à modifier les mêmes fichiers.

## Décision

Le code utilise `domain`, `application`, `adapters`, `interfaces` et une racine de composition.

- le domaine contient dataclasses immuables, enums et erreurs stables;
- les ports sont des `Protocol` synchrones et annotés;
- l'application orchestre les ports sans importer les adaptateurs;
- les adaptateurs implémentent HTTP, SQLite, fichiers, FTS et LLM;
- CLI et MCP appellent uniquement les services d'application;
- `bootstrap.py` assemble les dépendances sans créer de client à l'import;
- les read models transportent provenance, couverture, révision et troncature;
- un seul owner contrôle modèles SQLAlchemy et chaîne Alembic.

Les signatures publiques et les DTO autorisés à traverser ces frontières sont définis dans [PORTS.md](../specs/PORTS.md).

Les tests AST refusent les imports vers l'extérieur depuis `domain` et `application`, ainsi que la construction de clients externes au niveau module.

## Conséquences

- les workers disposent de frontières et chemins exclusifs;
- les modèles ORM ne quittent pas l'adapter catalogue;
- les opérations read-only utilisent des ports séparés des mutations;
- les contrats partagés doivent être gelés à Gate 0 ou modifiés par l'intégrateur;
- certaines interfaces exigent plus de DTO qu'un repository générique, mais les dépendances restent explicites.

## Options rejetées

### Services qui importent SQLAlchemy et httpx

Cette option réduit les fichiers mais rend les tests hors réseau et les transactions difficiles à isoler.

### Microservices ou file distribuée

Le produit est local et mono-utilisateur. Aucun besoin mesuré ne justifie déploiement, coordination ou sérialisation distante.

### Async généralisé

Les sources et SQLite sont servis par des opérations bornées et synchrones. Async exige une contrainte ou une mesure distincte.
