# Vision de Paper Insights

## Décision

Paper Insights devient le troisième corpus spécialisé de l'écosystème personnel:

- YT Insights couvre les vidéos et leurs transcriptions;
- Agentic Ecosystem Map couvre les projets et dépôts GitHub;
- Paper Insights couvrira les publications scientifiques et leurs auteurs.

Ces projets peuvent être interrogés ensemble par un agent, mais chaque corpus garde ses propres sources, règles de collecte et preuves.

## Problème

Une recherche ponctuelle sur arXiv produit une liste volatile. Elle ne conserve pas les requêtes, les versions, les artefacts, les décisions de sélection ni les passages utilisés dans un article. La veille ajoute un second problème: la même publication peut apparaître dans plusieurs catégories, être révisée et recevoir ensuite un DOI ou des métadonnées enrichies.

Paper Insights doit transformer ces résultats externes en un corpus local, reproductible et interrogeable.

## Résultats attendus

### Recherche à la demande

Une requête thématique retourne des papiers classés avec titre, auteurs, résumé, dates, identifiants, source et raison du classement. L'utilisateur peut ouvrir le papier, récupérer une citation et conserver la sélection dans une collection.

### Veille

Une watchlist enregistre une requête, des catégories ou des auteurs. Chaque exécution incrémentale distingue les nouvelles publications, les nouvelles versions et les documents déjà connus.

### Analyse sourcée

Une analyse relie chaque affirmation importante à un ou plusieurs passages stables. Le système conserve l'empreinte du document, la version du prompt et le modèle utilisé.

### Auteurs

Le corpus normalise les auteurs sans les fusionner sur leur seul nom. ORCID, OpenAlex et les pages institutionnelles servent de signaux de désambiguïsation. Une URL LinkedIn reste une donnée confirmée manuellement.

### Citations

Les exports BibTeX, Markdown et CSL-JSON proviennent des métadonnées enregistrées. Ils indiquent les champs absents ou ambigus au lieu de les inventer.

## Utilisateur initial

Le premier utilisateur est le propriétaire du corpus, depuis une CLI locale et des agents compatibles MCP. Une interface web multi-utilisateur, les comptes et les permissions par équipe ne font pas partie des premières phases.

## Mesures de réussite

- une ingestion rejouée ne duplique ni papier, ni version, ni auteur;
- une exécution interrompue peut reprendre sans corrompre le catalogue;
- chaque résultat de recherche possède un identifiant de source stable;
- chaque citation expose son identifiant canonique et sa provenance;
- chaque analyse permet de retrouver les passages et l'artefact d'entrée;
- les recherches MCP ne peuvent pas modifier le corpus;
- les tests d'intégration n'appellent aucun service externe.

## Ce que Paper Insights ne promet pas

- une couverture exhaustive de toute la littérature scientifique;
- un accès légal au texte intégral de chaque publication;
- une vérité scientifique produite par un LLM;
- l'identification automatique certaine d'une personne;
- un classement bibliométrique neutre ou universel.
