# Spécification de la recherche et du MCP

## Documents et passages

La phase 2 indexe le titre et le résumé de chaque version courante. L'extraction de texte intégral ajoute ensuite les sections autorisées sans changer le contrat de recherche.

Un passage contient:

- `passage_id`;
- `paper_id` et `paper_version_id`;
- type d'artefact et SHA-256;
- ordinal;
- titre de section facultatif;
- texte;
- offsets de caractères dans le texte normalisé;
- URL source.

Le chunking est déterministe pour une version de schéma donnée. Une modification de l'algorithme incrémente `chunk_schema_version` et reconstruit tout l'index.

## Construction de l'index

1. Ouvrir le catalogue en lecture seule.
2. Énumérer les documents dans un ordre stable.
3. Construire une base temporaire dans le répertoire de l'index final.
4. Insérer documents, passages, FTS et métadonnées dans une transaction.
5. Exécuter `PRAGMA quick_check` et contrôler les compteurs.
6. Fermer la base et calculer son SHA-256.
7. Écrire un reçu de génération privé.
8. Publier la base par remplacement atomique.

Une erreur laisse l'index publié précédent intact.

## Requêtes

La recherche FTS accepte une chaîne de 1 à 500 caractères. Le service transforme les termes utilisateur en expression FTS sûre et utilise des paramètres SQL. Les opérateurs FTS bruts ne sont pas exposés dans P1.

Filtres initiaux:

- source;
- catégorie;
- auteur;
- langue;
- date minimale et maximale;
- collection.

La limite par défaut est 10 et la limite maximale 50 pour la CLI. Le MCP impose une limite maximale de 20.

## Classement

P1 utilise BM25 de SQLite. Le résultat expose le score brut et le rang, sans transformer le score en pourcentage de pertinence. Un benchmark annoté compare les changements d'indexation avant publication.

## Citations

`get_citation` résout un papier et une version du catalogue. Les formats initiaux sont:

- `bibtex`;
- `markdown`;
- `csl-json`.

Le résultat contient `paper_id`, `paper_version_id`, format, contenu, champs manquants, source et date de récupération. Une citation n'utilise pas le texte d'une analyse LLM.

## Surface MCP P1

| Outil | Entrée | Sortie |
| --- | --- | --- |
| `list_collections` | aucune | collections et compteurs |
| `search_papers` | query, filtres, limit | métadonnées classées |
| `get_paper` | paper_id | papier, versions, auteurs et identifiants |
| `search_passages` | query, filtres, limit | passages classés et extraits |
| `get_passage` | passage_id | passage complet et provenance |
| `get_citation` | paper_id, version, format | citation et champs manquants |

Tous les outils déclarent:

- `readOnlyHint=true`;
- `destructiveHint=false`;
- `idempotentHint=true`;
- `openWorldHint=false`.

Le serveur refuse les noms d'outils inconnus, les arguments supplémentaires et les identifiants malformés avant d'appeler le service.

## Limites de réponse

- requête: 500 caractères;
- extrait: 1 500 caractères;
- auteurs par réponse de recherche: 20 avant troncature signalée;
- résultats MCP: 20;
- payload structuré: 24 Kio;
- réponse MCP totale: 64 Kio.

Une réponse tronquée contient `truncated=true`, `returned` et `available` lorsque le total est connu.

## Agent de recherche

L'agent `paper-researcher` suit l'ordre:

1. `list_collections` si le corpus est ambigu;
2. `search_papers` pour identifier les candidats;
3. `search_passages` pour trouver la preuve textuelle;
4. `get_passage` pour résoudre un passage retenu;
5. `get_citation` pour préparer la source de l'article.

Il sépare les métadonnées, le texte du papier et son interprétation. Une absence de résultat devient une limite de couverture, pas une preuve d'absence dans la littérature.

## Tests de contrat

Les tests MCP contrôlent:

- la liste exacte des outils;
- les annotations read-only;
- le refus des arguments inconnus;
- les bornes de chaîne, limite et identifiant;
- l'absence d'ouverture SQLite en écriture;
- la troncature déterministe des réponses;
- la conservation des identifiants et de la provenance.
