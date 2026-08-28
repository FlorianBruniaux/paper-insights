# Spécification de l'ingestion

## Contrat d'un provider

Un provider expose une interface synchrone:

```python
class PaperProvider(Protocol):
    source_id: str

    def preview(self, query: DiscoveryQuery) -> DiscoveryPreview: ...
    def iter_records(self, query: DiscoveryQuery) -> Iterator[RawPaperRecord]: ...
```

`DiscoveryQuery` contient une requête, des catégories, une fenêtre de dates, une limite et un curseur facultatif. `RawPaperRecord` conserve l'identifiant source et le payload brut borné avant normalisation.

## Preview

La preview peut appeler la source externe mais ne crée ni répertoire de données, ni base, ni fichier temporaire persistant. Elle retourne:

- source et requête canonique;
- nombre demandé et nombre découvert;
- fenêtre de dates et filtres;
- identifiants sélectionnés;
- exclusions avec codes stables;
- erreurs de découverte;
- estimation des artefacts demandés.

Une preview expire après 15 minutes. Son empreinte SHA-256 couvre la requête canonique et les identifiants sélectionnés. L'exécution vérifie cette empreinte avant de commencer.

## Confirmation

- Une ingestion d'un identifiant explicite peut commencer après une demande utilisateur explicite.
- Une recherche, catégorie, watchlist ou liste de plusieurs identifiants exige une preview et une confirmation.
- `--yes` vaut confirmation seulement si la commande contient les mêmes paramètres que la preview affichée dans la même exécution.
- Un processus non interactif sans `--yes` termine avec le code 3 et zéro mutation.

## Pagination et politesse

- le provider respecte l'ordre déterministe de la source;
- chaque page possède une limite configurée;
- les délais et reprises utilisent des bornes explicites;
- les réponses 429 et 5xx peuvent être reprises avec attente bornée;
- les erreurs 4xx non transitoires ne sont pas reprises;
- l'agent utilisateur provient de la configuration et ne contient aucun secret;
- les tests utilisent des transports HTTP simulés et des fixtures figées.

## Idempotence

La clé naturelle d'une notice arXiv combine l'identifiant arXiv canonique et la version. Une ingestion identique:

- retrouve le papier existant;
- retrouve la version existante;
- vérifie les empreintes des artefacts;
- incrémente `unchanged_count`;
- ne modifie pas `first_seen_at`;
- n'écrit pas un second artefact identique.

Une nouvelle version crée `paper_version`, met à jour `is_current` dans la même transaction et conserve l'historique.

## Artefacts

Chemin cible:

```text
data/artifacts/arxiv/<paper-id>/<version>/<kind>-<sha256-prefix>.<ext>
```

Le writer:

1. résout la cible sous `data_root`;
2. crée un fichier temporaire privé dans le même répertoire;
3. écrit avec une limite de taille;
4. synchronise, ferme et calcule SHA-256;
5. valide le type et la taille;
6. publie par `os.replace`;
7. enregistre l'artefact dans la transaction catalogue.

Un échec avant l'étape 6 ne produit pas d'artefact final. Un échec catalogue après publication marque l'artefact comme orphelin détectable par `doctor`, sans le présenter comme ingéré.

## Transactions et reprise

Une run est créée avant le premier élément. Chaque élément utilise une transaction courte. Le statut final dépend des compteurs:

- `succeeded`: au moins zéro sélection, aucune erreur;
- `partial`: au moins un succès et au moins une erreur;
- `failed`: aucun succès et au moins une erreur.

Une run restée `running` après une interruption est marquée `failed` au prochain diagnostic avec le code `interrupted`. La reprise rejoue les éléments par identifiant naturel.

## Watchlists

Une watchlist utilise une fenêtre de recouvrement afin de résister aux retards et aux changements d'ordre. La déduplication repose sur les identifiants et versions, pas sur le curseur seul. Le nouveau curseur est écrit seulement après le traitement et la validation de la page finale.

## Erreurs

Les erreurs publiques utilisent un code stable, une étape et un message nettoyé. Le traceback reste dans les logs de développement locaux si le niveau le demande, jamais dans le JSON CLI, le MCP ou `collection_errors`.

Codes initiaux:

- `source_timeout`
- `source_rate_limited`
- `source_response_too_large`
- `source_invalid_payload`
- `record_invalid`
- `artifact_invalid`
- `catalog_conflict`
- `interrupted`

## arXiv P1

La première implémentation accepte une requête texte, une ou plusieurs catégories, une limite de 1 à 100 et une fenêtre de dates facultative. Elle conserve l'identifiant arXiv sans version comme identifiant de papier et la forme suffixée `vN` comme identifiant de version source.

Le parser préserve l'ordre des auteurs, toutes les catégories, le commentaire, le journal de référence et le DOI lorsqu'ils sont fournis. Un champ absent reste absent.
