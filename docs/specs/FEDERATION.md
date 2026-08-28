# Spécification de la recherche fédérée

## Principe

La fédération orchestre Paper Insights, YT Insights et Agentic Ecosystem Map par leurs contrats publics versionnés. Elle n'importe ni module interne, ni base SQLite d'un autre corpus.

Chaque corpus garde l'autorité sur ses IDs, son type de source, son classement, sa provenance et sa citation. Les scores BM25 hétérogènes ne sont jamais convertis en pourcentage commun.

## Contrat `FederatedResult v1`

Un résultat contient:

- `schema_version = "federated-result-v1"`;
- `corpus_id` et version du contrat public;
- `native_id`;
- `source_type`: `paper`, `video` ou `repository`;
- titre et extrait bornés;
- rang natif et score natif nullable;
- provenance et couverture;
- citation discriminée par type;
- références de fichiers de preuve avec SHA-256.

Une citation de papier ne peut pas porter `video` ou `repository`. Une vidéo ou un README ne peut pas être rendu comme publication scientifique.

## Orchestration et couverture

`FederatedQuery` contient texte, filtres compatibles, corpus demandés et limite par corpus. Chaque adapter retourne un `CorpusSearchResult` avec `complete`, `partial`, `unavailable` ou `unknown`.

L'indisponibilité d'un corpus:

- ne supprime pas les résultats des autres;
- ne devient pas une absence de résultat;
- produit une couverture partielle explicite avec erreur nettoyée;
- conserve l'ordre et le rang natifs par corpus.

La vue agrégée groupe les résultats par corpus. Elle ne fabrique aucun classement global à partir des scores.

## Dossier de preuves

L'export construit d'abord un candidat sous une racine configurée, puis le publie atomiquement. Le manifeste versionné contient:

- requête canonique;
- couverture de chaque corpus;
- entrées groupées par corpus;
- chemin relatif, taille, media type et SHA-256 de chaque fichier;
- erreurs et éléments non exportés;
- SHA-256 du manifeste.

Une vérification échouée laisse le dossier publié précédent intact.

## Sécurité

- pas d'accès direct aux bases externes;
- aucun token, cookie ou chemin privé dans le manifeste;
- sorties et erreurs bornées;
- réseau simulé ou CLI/MCP fake dans les tests;
- aucune mutation des corpus interrogés.

## Tests d'acceptation

- trois adapters conformes au même port;
- panne d'un corpus avec couverture partielle et résultats restants;
- score et rang conservés sans normalisation croisée;
- confusion paper/video/repository refusée par le type et le renderer;
- manifeste déterministe et tous les checksums vérifiés;
- aucune importation d'une base ou d'un module interne des autres corpus.
