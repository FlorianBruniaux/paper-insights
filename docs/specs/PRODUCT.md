# Spécification produit

## Périmètre

Paper Insights collecte et interroge un corpus scientifique local. La version initiale sert un utilisateur depuis une CLI et un serveur MCP local.

## Concepts

- Un `paper` représente une œuvre scientifique indépendamment de ses versions.
- Une `paper_version` représente un état daté provenant d'une source.
- Un `artifact` représente un fichier ou payload immuable associé à une version.
- Un `passage` représente un fragment déterministe d'un artefact textuel.
- Une `collection` regroupe des papiers sélectionnés par l'utilisateur.
- Une `watchlist` décrit une requête rejouable.
- Une `ingestion_run` enregistre une tentative de collecte.
- Une `analysis` représente une sortie structurée liée à une entrée exacte.

## Cas d'usage P1

### Rechercher une source externe

Commande cible:

```bash
paper-insights discover arxiv "agentic software engineering" --category cs.AI --limit 20 --json
```

Le résultat contient la requête normalisée, le nombre demandé, le nombre retourné, les identifiants arXiv, titres, auteurs, dates, catégories, résumés et URLs sources. La commande n'écrit rien dans le corpus.

### Ingérer une sélection

Commande cible:

```bash
paper-insights ingest arxiv "agentic software engineering" --category cs.AI --limit 20
```

La commande affiche d'abord la preview. Sans `--yes`, elle demande une confirmation avant toute écriture. En environnement non interactif, l'absence de `--yes` termine sans mutation avec un code de sortie documenté.

### Chercher dans le corpus

Commande cible:

```bash
paper-insights search papers "coding agents evaluation" --from 2025-01-01 --limit 10
```

Chaque résultat contient `paper_id`, titre, auteurs, version, date, source, identifiants et score. Le format JSON conserve les mêmes champs que le rendu terminal.

### Préparer une citation

Commande cible:

```bash
paper-insights cite arxiv:2608.01234 --format bibtex
```

La commande sélectionne une version explicite ou la version courante enregistrée. Elle échoue si l'identifiant est ambigu. Les champs absents sont omis et signalés dans les métadonnées du résultat.

### Créer une watchlist

Commande cible:

```bash
paper-insights watch add agents-weekly --source arxiv --query "AI coding agents" --category cs.AI
```

La watchlist conserve la requête canonique, les filtres, la source, la date de création et le dernier curseur validé.

### Exécuter la veille

Commande cible:

```bash
paper-insights watch run agents-weekly --json
```

Le résultat distingue `new_papers`, `new_versions`, `unchanged`, `failed` et `next_cursor`. Le curseur n'est publié qu'après validation de la run.

## Cas d'usage différés

- téléchargement et extraction systématique des PDF;
- analyse LLM en lot;
- rapprochement d'auteurs entre plusieurs sources;
- recherche fédérée avec YT Insights et Agentic Ecosystem Map;
- interface web;
- collaboration multi-utilisateur.

## Exigences fonctionnelles

| ID | Exigence |
| --- | --- |
| F-001 | Une preview externe ne modifie ni catalogue, ni artefact, ni index. |
| F-002 | Une ingestion rejouée avec la même source et la même version est idempotente. |
| F-003 | Une nouvelle version conserve les versions précédentes. |
| F-004 | Une erreur d'élément est enregistrée sans effacer les éléments réussis. |
| F-005 | Une recherche locale ne déclenche aucun appel réseau. |
| F-006 | Une citation provient des métadonnées du catalogue et indique sa provenance. |
| F-007 | Un hit de passage permet de retrouver l'artefact et la version du papier. |
| F-008 | Une analyse publiée référence ses passages probants. |
| F-009 | Un outil MCP ne modifie jamais le corpus. |
| F-010 | Une URL LinkedIn reste non confirmée tant qu'un humain ne la valide pas. |

## Exigences non fonctionnelles

| ID | Exigence |
| --- | --- |
| N-001 | Python 3.12 minimum. |
| N-002 | Les tests n'accèdent pas au réseau. |
| N-003 | Les réponses externes ont une taille et un délai maximum. |
| N-004 | Les fichiers publiés utilisent une validation et un remplacement atomique. |
| N-005 | Les erreurs utilisateur ne contiennent pas de traceback ou de secret. |
| N-006 | Le catalogue applique les clés étrangères et un délai d'attente SQLite. |
| N-007 | Une reconstruction échouée laisse le dernier index valide disponible. |
| N-008 | Les formats JSON sont versionnés et déterministes. |

## Codes de sortie cibles

| Code | Signification |
| --- | --- |
| 0 | Succès complet |
| 2 | Entrée ou configuration invalide |
| 3 | Confirmation requise, aucune mutation |
| 4 | Succès partiel avec erreurs enregistrées |
| 5 | Source externe indisponible |
| 6 | Corpus ou index invalide |

## Critère d'acceptation de la première tranche

Sur une fixture arXiv de trois entrées comprenant deux versions du même papier, la CLI peut prévisualiser puis ingérer les données, rejouer l'ingestion sans doublon, rechercher le titre et produire une citation BibTeX reliée à la réponse source enregistrée.
