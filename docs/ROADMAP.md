# Roadmap de Paper Insights

La roadmap avance par tranches utilisables. Une phase ne se termine pas parce que les fichiers existent. Ses critères doivent passer sur des fixtures locales et une exécution contrôlée.

## Phase 0: fondations

Livrables:

- paquet Python installable avec `uv`;
- configuration stricte et chemins dérivés de `data_root`;
- schéma SQLAlchemy, migrations Alembic et base SQLite;
- modèles de domaine pour papiers, versions, auteurs, artefacts et runs;
- CI avec pytest, Ruff et mypy;
- commande `doctor` sans écriture ni réseau par défaut.

Critères de sortie:

- une base vide peut être créée puis migrée depuis zéro;
- une clé de configuration inconnue provoque une erreur;
- `doctor --json` ne révèle aucune valeur sensible;
- la suite fonctionne sans service externe.

## Phase 1: arXiv à la demande

Livrables:

- parser de réponse arXiv sur fixtures XML figées;
- preview d'une recherche avec pagination et limites;
- ingestion idempotente des métadonnées et versions;
- stockage du XML brut ou de la réponse normalisée avec SHA-256;
- recherche catalogue par identifiant, titre et auteur;
- export Markdown et BibTeX.

Critères de sortie:

- rejouer la même fixture ne crée aucun doublon;
- une nouvelle version met à jour le papier sans écraser l'historique;
- une erreur d'élément reste liée à la run;
- les exports ne contiennent aucun champ inventé.

## Phase 2: recherche plein texte locale

Livrables:

- passages déterministes pour titres et résumés;
- index FTS5 séparé, validé puis publié atomiquement;
- commandes `search papers`, `search passages` et `get passage`;
- filtres par catégorie, auteur, date et source;
- jeu de requêtes annoté pour évaluer la pertinence.

Critères de sortie:

- chaque hit possède un `passage_id` stable et un lien vers sa version;
- une reconstruction interrompue laisse l'ancien index lisible;
- les requêtes annotées satisfont le seuil de pertinence décidé par revue humaine;
- aucun résultat ne dépasse les limites de réponse.

## Phase 3: MCP read-only

Livrables:

- outils `list_collections`, `search_papers`, `get_paper`, `search_passages`, `get_passage` et `get_citation`;
- validation stricte des paramètres;
- tailles de réponse bornées;
- agent `paper-researcher` connecté au MCP.

Critères de sortie:

- aucun outil MCP ne possède de chemin de mutation;
- les annotations MCP déclarent lecture seule, idempotence et monde fermé;
- les tests refusent les arguments inconnus et identifiants malformés;
- chaque réponse de recherche contient sa couverture et ses limites.

## Phase 4: watchlists et veille

Livrables:

- watchlists par requête, catégorie et auteur;
- curseurs et fenêtres de recouvrement;
- rapport différentiel entre nouvelles publications, versions et doublons;
- commande planifiable et code de sortie stable;
- export d'un digest Markdown ou JSON.

Critères de sortie:

- deux exécutions identiques produisent zéro nouveauté la seconde fois;
- une publication multi-catégorie apparaît une seule fois dans le digest;
- une interruption reprend sans perdre le curseur validé précédent;
- le scheduler externe peut interpréter succès, succès partiel et échec.

## Phase 5: analyse sourcée

Livrables:

- extraction de texte autorisé avec provenance;
- chunking par sections et passages;
- protocole de backend LLM;
- schémas d'analyse Pydantic;
- synthèse, contributions, limites, méthodes et claims probants;
- cache lié à l'empreinte, au prompt et au modèle.

Critères de sortie:

- chaque claim publié référence au moins un passage existant;
- une sortie tronquée ou invalide ne remplace pas un cache valide;
- changer l'artefact, le prompt ou le modèle invalide la clé de cache;
- un évaluateur humain contrôle un échantillon avant une exécution en lot.

## Phase 6: enrichissement des auteurs

Livrables:

- enrichissement OpenAlex et ORCID;
- affiliations et pages institutionnelles avec provenance;
- candidats de rapprochement sans fusion automatique ambiguë;
- champ LinkedIn confirmé manuellement;
- historique des décisions de fusion et séparation.

Critères de sortie:

- deux homonymes restent distincts sans identifiant convergent;
- chaque fusion conserve ses preuves et peut être annulée;
- une URL de recherche LinkedIn n'est jamais étiquetée comme profil;
- aucun appel ni scraping LinkedIn n'est effectué.

## Phase 7: recherche fédérée

Livrables:

- contrat commun de résultat avec YT Insights et Agentic Ecosystem Map;
- requête fédérée exécutée par orchestration, sans fusionner les bases;
- citations propres à chaque type de source;
- export d'un dossier de preuves multi-corpus.

Critères de sortie:

- chaque résultat conserve le corpus qui fait autorité;
- une indisponibilité d'un corpus produit une couverture partielle explicite;
- aucune interprétation ne transforme une vidéo ou un README en papier scientifique.
