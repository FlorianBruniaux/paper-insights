# Spécification produit

## Périmètre

Paper Insights collecte et interroge un corpus scientifique local. Le produit sert d'abord un utilisateur depuis une CLI et un serveur MCP local.

Les commandes de cette spec sont des contrats cibles livrés par gates successives. Leur présence ne prouve pas leur disponibilité.

## Concepts

- Un `paper` représente une oeuvre scientifique indépendamment de ses versions.
- Une `paper_version` représente une révision identifiée par une source.
- Une `version_observation` représente un état bibliographique immuable observé pour cette révision.
- Un `artifact` représente un fichier immuable associé à une version.
- Un `source_snapshot` représente une page ou réponse brute qui peut contenir plusieurs papiers.
- Un `passage` représente un fragment déterministe d'un artefact textuel.
- Une `collection` regroupe des papiers sélectionnés par l'utilisateur.
- Une `watchlist` décrit une requête rejouable.
- Une `ingestion_run` enregistre une tentative de collecte.
- Une `analysis` représente une sortie structurée liée à une entrée exacte.

## Cas d'usage du produit local

### Rechercher une source externe

Commande cible:

```bash
paper-insights discover arxiv "agentic software engineering" --category cs.AI --limit 20 --json
```

Le résultat contient la requête canonique, les compteurs, identifiants, observations et URLs source. La commande n'écrit rien dans le corpus.

### Ingérer une sélection

Commande cible:

```bash
paper-insights ingest arxiv "agentic software engineering" --category cs.AI --limit 20
```

La commande affiche le `PreparedDiscovery`. Sans `--yes`, elle demande une confirmation avant toute écriture. En environnement non interactif, l'absence de confirmation termine avec le code `3` et zéro mutation. L'exécution consomme le manifeste exact sans rappeler le provider.

### Chercher dans le corpus

Commande cible:

```bash
paper-insights search papers "coding agents evaluation" --from 2025-01-01 --limit 10
```

Chaque résultat expose papier, version, observation, auteurs, source, identifiants, rang, score BM25 brut, révision et couverture. Le JSON et le rendu terminal conservent les mêmes données métier.

Une date `YYYY-MM-DD` est interprétée en UTC. `--from` vise le début du jour et `--to` sa dernière microseconde, ce qui rend les deux bornes inclusives. Un timestamp RFC3339 UTC complet conserve son instant exact.

### Préparer une citation

Commande cible:

```bash
paper-insights cite arxiv:2608.01234 --format bibtex
```

La commande résout un identifiant exact et une version explicite ou courante. Elle échoue si la résolution est ambiguë. BibTeX, Markdown et CSL-JSON proviennent d'une observation exacte; les champs absents sont omis et signalés.

### Gérer une collection

Commandes cibles:

```bash
paper-insights collections create article-agents --title "Article agents"
paper-insights collections add article-agents arxiv:2608.01234
paper-insights collections remove article-agents arxiv:2608.01234
paper-insights collections list --json
```

Le slug est unique et ne peut pas avoir la forme d'un UUID, afin de rester distinct d'un identifiant interne. Un ajout répété est idempotent. Une collection vide reste listée. Ces mutations passent par la CLI et les services d'application; le MCP peut uniquement les lire.

### Créer et exécuter une watchlist

Commandes cibles:

```bash
paper-insights watch add agents-weekly --source arxiv --query "AI coding agents" --category cs.AI
paper-insights watch run agents-weekly --yes --json
```

La watchlist conserve requête canonique, filtres, source, overlap et dernier curseur validé. Chaque exécution exige `--yes`, y compris depuis un scheduler; sans confirmation, elle affiche la preview et termine avec le code `3` sans mutation. Le résultat distingue nouveaux papiers, nouvelles versions, observations mises à jour, inchangés et erreurs. Le curseur candidat n'est validé qu'après une run réussie.

### Diagnostiquer et réparer une interruption

Commandes cibles:

```bash
paper-insights doctor --json
paper-insights repair interrupted-runs --yes
```

`doctor` ne crée et ne modifie rien, n'appelle aucun réseau et rend `UNKNOWN` lorsqu'une preuve manque. `repair` est une mutation distincte. Sans `--yes`, elle présente la sélection puis termine avec le code `3` sans écrire.

Sans option supplémentaire, une run doit être inactive depuis 24 heures pour entrer dans la preview de réparation. `--stale-after-seconds` permet un override explicite strictement positif.

## Cas d'usage différés jusqu'à leurs gates

- téléchargement et extraction bornés des PDF après validation de la politique;
- analyse LLM après tests automatiques et revue humaine;
- rapprochement d'auteurs entre sources avec décisions réversibles;
- recherche fédérée avec YT Insights et Agentic Ecosystem Map;
- interface web et collaboration multi-utilisateur, hors programme actuel.

## Exigences fonctionnelles

| ID | Exigence |
| --- | --- |
| F-001 | Une preview externe ne modifie ni catalogue, ni blob, ni index. |
| F-002 | Une ingestion rejouée avec le même manifeste est idempotente. |
| F-003 | Une nouvelle version conserve les versions et observations précédentes. |
| F-004 | Une erreur d'item est enregistrée sans effacer les items réussis. |
| F-005 | Une recherche locale ne déclenche aucun appel réseau. |
| F-006 | Une citation provient d'une observation catalogue et indique sa provenance. |
| F-007 | Un hit permet de retrouver version, observation et artefact. |
| F-008 | Une analyse publiée référence des passages durables et probants. |
| F-009 | Un outil MCP ne modifie jamais le corpus. |
| F-010 | Une URL LinkedIn reste non confirmée tant qu'un humain ne la valide pas. |
| F-011 | Une réponse multi-papiers reste un snapshot unique relié aux records par ordinal. |
| F-012 | Les mutations de collection restent hors MCP. |

## Exigences non fonctionnelles

| ID | Exigence |
| --- | --- |
| N-001 | Python 3.12 minimum. |
| N-002 | Les tests n'accèdent pas au réseau. |
| N-003 | Les réponses externes ont taille, délai, reprise et redirections bornés. |
| N-004 | Les fichiers publiés utilisent validation, `fsync` et remplacement atomique. |
| N-005 | Les erreurs publiques ne contiennent ni traceback, ni secret. |
| N-006 | Le catalogue applique FKs, WAL, `busy_timeout`, `synchronous=FULL` et transactions courtes. |
| N-007 | Une reconstruction échouée ou obsolète laisse le dernier index valide disponible. |
| N-008 | Les formats JSON sont versionnés, fermés et déterministes. |
| N-009 | `doctor` reste strictement read-only; la réparation exige une commande distincte. |

## Enveloppes JSON

Toute sortie JSON publique contient un `schema_version` stable, le type d'opération, les données, une couverture, des erreurs fermées et les indicateurs de troncature applicables. Les clés inconnues sont refusées en entrée. Un changement incompatible crée une nouvelle version.

Les DTO du domaine restent des dataclasses immuables. Pydantic valide uniquement la configuration, les enveloppes CLI/MCP et la frontière LLM.

## Codes de sortie fermés

| Code | Signification |
| --- | --- |
| 0 | Succès complet |
| 2 | Entrée ou configuration invalide |
| 3 | Confirmation requise, aucune mutation |
| 4 | Exécution terminée avec erreurs d'items enregistrées, que la run soit `partial` ou `failed` |
| 5 | Source externe indisponible |
| 6 | Corpus ou index invalide |

Toutes les commandes, y compris watchlists et repair, utilisent cette table. Aucun sous-système ne réattribue un code.

## Correspondance avec le plan d'exécution

- Gate 0 fige specs, ADR, DTO et ports, sans annoncer de runtime métier.
- Gate 1 livre le catalogue, arXiv, la configuration et les blobs.
- Gate 2 livre la verticale arXiv offline, collections et trois citations.
- Gate 3 livre MCP, watchlists et texte intégral borné.
- Gate 4 livre analyse, identité et fédération sous leurs gates humaines.

Les phases dans `docs/ROADMAP.md` décrivent la progression produit. Les waves et gates décrivent l'ordre d'intégration technique.

## Critère d'acceptation de la première verticale utilisable

Sur des fixtures arXiv comprenant deux oeuvres, trois versions et une page multi-papiers, la CLI peut prévisualiser puis ingérer le manifeste exact, rejouer sans doublon, rechercher le titre, gérer une collection et produire BibTeX, Markdown et CSL-JSON reliés au snapshot et à l'ordinal source.
