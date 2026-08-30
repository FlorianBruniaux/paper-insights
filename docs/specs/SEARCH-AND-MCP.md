# Spécification de la recherche, des citations et du MCP

## Autorité des passages

La recherche FTS est une projection remplaçable. Elle indexe d'abord le titre et le résumé de l'observation courante de chaque version courante. Le texte intégral autorisé ajoute ensuite des passages sans modifier le contrat de lecture.

Chaque observation possède un artefact `metadata` dont le blob est le JSON bibliographique canonique exact. Les passages de titre et de résumé référencent cet artefact; les passages de texte intégral référencent l'artefact `text` correspondant. Un passage contient:

- `passage_id`;
- `paper_id`, `paper_version_id` et `version_observation_id`;
- kind et SHA-256 de l'artefact;
- `chunk_schema_version`;
- section nullable, ordinal et texte normalisé;
- offsets de début et fin;
- URL source nullable;
- révision catalogue source.

Les passages retenus comme preuves d'analyse sont aussi persistés dans le catalogue avec de vraies FKs. Une reconstruction FTS ne peut donc pas rendre un claim publié irrésoluble.

## Identifiant de passage

`passage_id` est le SHA-256 UTF-8 d'un JSON canonique avec clés triées, séparateurs `,` et `:`, sans espace ajouté:

```json
{
  "artifact_sha256": "<64 hex>",
  "chunk_schema_version": "chunk-v1",
  "end_offset": 42,
  "normalized_text": "...",
  "ordinal": 0,
  "paper_version_id": "<uuidv7>",
  "section": null,
  "start_offset": 0
}
```

Le texte est normalisé en Unicode NFC et les fins de ligne deviennent `\n`. Les offsets ciblent ce texte normalisé. Toute modification d'artefact, schéma, section, ordinal, texte ou offsets change l'identifiant.

## Construction et publication de l'index

1. Ouvrir un `CatalogSnapshot` read-only et lire sa révision avec ses documents.
2. Construire une base candidate sibling dans un ordre stable avec `journal_mode=DELETE`; le catalogue garde WAL, pas le fichier FTS publiable.
3. Insérer `documents`, `passages`, FTS et `index_meta` dans une transaction.
4. Exécuter `PRAGMA quick_check`, vérifier les compteurs et écrire le reçu autoritaire dans l'unique ligne `index_meta` de la candidate.
5. Valider que le reçu contient schémas, génération, révision catalogue, compteurs et empreinte logique du contenu indexé.
6. Committer, fermer toute connexion candidate, refuser la présence d'un fichier `-wal` ou `-shm`, forcer le fichier sur disque, puis le rouvrir en lecture seule pour un dernier `quick_check` et la lecture de `index_meta`.
7. Prendre un `CatalogRevisionGuard` avec `BEGIN IMMEDIATE`.
8. Relire la révision. Si elle diffère, abandonner et supprimer uniquement le candidat.
9. Publier la candidate fermée par un unique `os.replace`, puis forcer le répertoire parent avant de libérer la garde.

Une erreur ou une révision obsolète laisse l'index publié précédent intact. Une panne avant le remplacement laisse l'ancien index; une panne après le remplacement laisse une base nouvelle et auto-descriptive. Aucun journal SQLite ni second fichier ne participe à l'atomicité.

L'index publié actuel déclare `index_schema_version = "fts-v2"`. Son empreinte logique couvre aussi la source, les auteurs ordonnés, les identifiants canoniques avec leur scope, les catégories, la langue, la date de soumission et les couples collection ID/slug. Si le répertoire parent est renommé pendant le remplacement, l'ancien index est restauré au chemin canonique et l'opération échoue. Le code ne supprime aucun nom dans le répertoire déplacé, car son identité pourrait avoir changé; un résidu de la candidate peut donc y rester et doit être traité comme `UNKNOWN` par une inspection opérateur.

## Requêtes et résultats

La chaîne de recherche contient de 1 à 500 caractères. Le service transforme les termes en expression FTS sûre, utilise des paramètres SQL et n'expose pas les opérateurs FTS bruts en P1.

Filtres fermés:

- source;
- catégorie;
- auteur;
- langue;
- date minimale et maximale;
- collection par slug ou ID.

Source, catégorie, slug et ID utilisent une égalité exacte. Une valeur collection analysable comme UUID désigne uniquement un ID; toute autre valeur désigne uniquement un slug. Les slugs au format UUID sont invalides afin de garder cette résolution non ambiguë. Auteur et langue utilisent une égalité Unicode NFC insensible à la casse. Les bornes de date UTC sont inclusives. Les filtres se combinent par conjonction et utilisent uniquement des paramètres SQL.

Limites: 10 par défaut, 50 au maximum pour la CLI, 20 au maximum pour MCP.

`PaperSearchResult` et `PassageSearchResult` contiennent:

- hits ordonnés;
- couverture `complete`, `partial`, `unavailable` ou `unknown`;
- révision catalogue et révision index;
- `truncated`, `returned` et `available` nullable;
- limites appliquées.

Chaque hit contient rang et score BM25 brut. Aucun pourcentage de pertinence n'est inventé. Un benchmark annoté doit approuver un changement d'indexation avant publication.

Un hit papier restitue aussi la source, les auteurs ordonnés et les identifiants canoniques du papier et de la version, avec leur scope explicite. Cette projection est incluse dans l'empreinte de l'index; la CLI n'effectue aucune seconde lecture implicite pour la reconstruire.

Les lectures ouvrent SQLite avec URI `mode=ro`, `query_only=ON` et un délai borné. Elles ne déclenchent aucun réseau, ingestion, rebuild, extraction ou analyse.

## Résolution de papier et de version

Un `PaperSelector` accepte exactement:

- un `paper_id` interne UUIDv7;
- un identifiant arXiv canonique;
- un DOI canonique.

Le titre n'est jamais une clé de résolution. Une correspondance multiple est une erreur `catalog_conflict`.

Un `VersionSelector` accepte un `paper_version_id`, une version source complète ou `current`. `current` exige une seule version courante pour la source demandée. Toute citation et tout passage exposent la version et l'observation exactes utilisées.

## Collections

Les collections sont créées, renommées, alimentées et vidées par des services d'application appelés depuis la CLI. MCP reste read-only.

Règles:

- slug unique et stable;
- zéro ou plusieurs papiers;
- ajout idempotent d'un même papier;
- ordre de lecture déterministe par `added_at`, puis `paper_id`;
- compteurs calculés depuis la table de liaison;
- suppression d'une liaison sans suppression du corpus.

`list_collections` retourne aussi les collections vides.

## Citations source-backed

Les formats cibles sont `bibtex`, `markdown` et `csl-json`. Ils utilisent une observation catalogue exacte, jamais une analyse LLM.

`CitationResult v1` contient:

- `schema_version = "citation-v1"`;
- `paper_id`, `paper_version_id` et `version_observation_id`;
- format et media type;
- contenu déterministe;
- champs absents triés;
- source, identifiant source, snapshot, ordinal et `retrieved_at`;
- couverture et avertissements fermés.

Le vocabulaire `CitationWarning v1` est fermé et trié par valeur:

- `literal-author`: le nom a été observé sous forme littérale sans séparation fiable;
- `missing-required-field`: le format demandé omet un champ requis faute d'observation;
- `partial-date`: seule une partie de la date attendue est observée;
- `partial-provenance`: la citation est rendue, mais sa couverture de provenance est partielle.

Les avertissements et les champs absents sont uniques, non vides et triés. Une valeur hors vocabulaire fait échouer la construction du résultat.

Règles communes:

- ordre des auteurs préservé;
- champ absent omis, jamais remplacé par une valeur probable;
- dates tirées de l'observation exacte;
- DOI ou URL inclus uniquement s'ils sont observés;
- même entrée et même version de renderer donnent les mêmes octets UTF-8.

BibTeX échappe accolades, antislashs et caractères réservés de manière déterministe. La clé est dérivée d'un identifiant exact, jamais du titre seul.

Markdown produit une référence lisible et un bloc de provenance séparé. Un segment absent est omis sans ponctuation orpheline.

CSL-JSON produit un objet JSON canonique. Il contient `id`, `type`, `title`, `author` et `issued` seulement lorsque les données nécessaires sont observées; `DOI` et `URL` restent optionnels. Les auteurs utilisent `family` et `given` seulement si le parser les a observés séparément, sinon `literal`.

## Enveloppe MCP fermée

Chaque réponse utilise `paper-insights.mcp.v1`:

```json
{
  "schema_version": "paper-insights.mcp.v1",
  "tool": "search_papers",
  "data": {},
  "coverage": {"status": "complete"},
  "truncated": false,
  "returned": 0,
  "available": 0,
  "errors": []
}
```

Les schémas refusent les arguments supplémentaires et les booléens lorsqu'un entier est attendu. Les identifiants, limites et chaînes sont validés avant tout appel de service.

## Surface MCP exacte

| Outil | Entrée fermée | Sortie `data` |
| --- | --- | --- |
| `list_collections` | objet vide | collections: `collection_id`, slug, titre, compteur, dates |
| `search_papers` | query, filtres optionnels, limit 1..20 | `PaperSearchResult` borné |
| `get_paper` | `paper_id` UUIDv7 | identité, versions, observations, auteurs, identifiants et provenance |
| `search_passages` | query, filtres optionnels, limit 1..20 | `PassageSearchResult` borné |
| `get_passage` | `passage_id` SHA-256 | passage complet borné et provenance résolue |
| `get_citation` | `paper_id`, version optionnelle, format fermé | `CitationResult v1` |

Le serveur expose exactement ces six noms. Un identifiant externe est résolu par le service CLI avant l'appel MCP; les outils `get_*` utilisent des identifiants internes afin de garder un schéma non ambigu.

Tous les outils déclarent:

- `readOnlyHint=true`;
- `destructiveHint=false`;
- `idempotentHint=true`;
- `openWorldHint=false`.

Le MCP n'a aucun port de mutation et ne peut appeler ni réseau, ni rebuild, ni extraction, ni analyse. Un outil inconnu est refusé avant résolution des dépendances.

## Limites de réponse

- requête: 500 caractères;
- extrait: 1 500 caractères;
- auteurs par hit: 20 avant troncature signalée;
- résultats: 20;
- payload structuré sérialisé: moins de 24 Kio;
- réponse totale: moins de 64 Kio.

La troncature est déterministe: réduire extraits, puis auteurs, puis résultats en fin de liste. Elle pose `truncated=true` et conserve `returned` et `available` lorsque connu. Un élément individuel impossible à borner produit une erreur fermée au lieu d'une réponse surdimensionnée.

## Agent de recherche

L'agent cible suit l'ordre:

1. `list_collections` si le périmètre local est ambigu;
2. `search_papers` pour identifier les candidats;
3. `search_passages` pour localiser les preuves;
4. `get_passage` pour résoudre une preuve retenue;
5. `get_citation` pour préparer la source.

Il sépare métadonnées observées, texte du papier et interprétation. Une absence de hit devient une limite de couverture, pas une preuve d'absence dans la littérature.

## Tests de contrat

Les tests exécutent un vrai client MCP stdio et vérifient:

- la liste exacte des six outils et les quatre annotations;
- le refus des outils, arguments, types et identifiants inconnus;
- les bornes de requête, limite et payload;
- les trois formats de citation sur oracles figés;
- l'ouverture SQLite read-only et l'absence de port write ou socket;
- la troncature et l'ordre déterministes;
- la conservation des IDs, révisions, couverture et provenance.
