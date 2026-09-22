# Roadmap de Paper Insights

La roadmap avance par tranches utilisables. Une phase ne se termine pas parce que les fichiers existent. Ses comportements passent sur fixtures locales et exécutions contrôlées.

## Correspondance phases, waves et gates

| Progression produit | Wave du plan | Gate de preuve |
| --- | --- | --- |
| Contrats préalables | Wave 0, WP-00 et WP-01 | Gate 0 |
| Phase 0, fondation runtime | Wave 1, WP-10 à WP-12 | Gate 1 |
| Phase 1 et début Phase 2, verticale arXiv locale | Wave 2, WP-20 à WP-22 | Gate 2 |
| Fin Phase 2, Phase 3, Phase 4 et texte intégral | Wave 3, WP-30 à WP-32 | Gate 3 |
| Phases 5 à 7 | Wave 4, WP-40 à WP-42 | Gate 4 |
| Durcissement et release | Wave 5, WP-50 à WP-52 | Gate 5 et release gate |

Les termes `P1`, phase, wave et gate ne sont pas interchangeables. P1 désigne uniquement le premier périmètre d'un contrat dans une spec.

## Gouvernance transversale des preuves

La roadmap conserve une source machine-readable dans `docs/evidence/capability-matrix.json`. Chaque capacité distingue spécification, implémentation, preuve déterministe, mesure comportementale et revue humaine. Son `claim_ceiling` borne ce que le projet peut annoncer; un statut `not_run`, `blocked`, `mixed` ou `UNKNOWN` ne peut pas être résumé comme un succès.

Le plan complémentaire `docs/superpowers/plans/2026-09-05-evidence-governance-optimization.md` ajoute les contrôles transversaux. Il ne remplace pas le plan complet et n'ouvre aucune wave dont la gate précédente reste bloquée.

Critères permanents:

- toute preuve positive référence un artefact versionné présent dans le dépôt;
- toute mesure nomme sa population, son dénominateur et ses exclusions;
- le registre de risques ne peut pas promouvoir un statut indépendamment de la matrice;
- les flux réseau et stockages durables sont inventoriés avant activation;
- chaque gate met à jour son plafond de claim depuis des preuves fraîches.

## Gate 0: contrats

Livrables:

- modèle versionné et provenance multi-records;
- manifeste de preview immuable et publication sous révision;
- architecture `domain/application/adapters/interfaces`;
- DTO, ports, erreurs, enveloppes JSON et codes CLI fermés;
- specs watchlists, analyse, identité et fédération;
- ancien plan marqué historique.

Critères de sortie:

- aucun import infrastructure dans `domain` ou `application`;
- tests des identifiants, digest, expiration, compteurs et frontières verts;
- validateur structurel et suite existante verts;
- Gate 0 commitée dans un worktree propre avant toute migration ou adapter.

## Phase 0: fondation runtime

Livrables:

- paquet Python installable avec `uv`;
- configuration stricte et chemins dérivés de `data_root`;
- schéma SQLAlchemy, migrations Alembic et catalogue SQLite révisionné;
- stockage de blobs atomique et confiné;
- commande `doctor` strictement read-only et sans réseau;
- CI avec pytest, Ruff et mypy.

Critères de sortie:

- une base vide migre de zéro à `head`;
- FKs, `quick_check`, révision et concurrence de writers sont testés;
- une clé de configuration inconnue échoue;
- `doctor --json` ne crée rien et ne révèle aucune valeur sensible;
- la suite fonctionne sans service externe.

## Phase 1: arXiv à la demande

Livrables:

- parser arXiv sur fixtures XML figées;
- découverte bornée avec pages, overlap et limites;
- `PreparedDiscovery` puis ingestion idempotente du batch exact;
- blobs, snapshots, ordinals, observations et compteurs exacts;
- réparation explicite `repair interrupted-runs --yes`;
- collections locales;
- BibTeX, Markdown et CSL-JSON.

Critères de sortie:

- replay identique sans doublon;
- nouvelle version sans écrasement de l'historique;
- correction d'une version conservée comme observation;
- page multi-papiers stockée une fois et chaque record traçable;
- erreur d'item liée à sa run sans perte des succès;
- citations sans champ inventé et reliées au snapshot exact.

## Phase 2: recherche plein texte locale

Livrables:

- passages déterministes pour titres et résumés, puis texte autorisé;
- FTS5 séparé, validé et publié sous garde de révision;
- recherche papiers et passages avec filtres;
- rang BM25 brut, couverture, révisions et troncature;
- jeu de 30 requêtes annotées.

Critères de sortie:

- chaque hit résout passage, version, observation et artefact;
- une reconstruction échouée ou obsolète laisse l'ancien index lisible;
- au moins 24 requêtes sur 30 placent un papier attendu dans le top cinq;
- zéro P0 de pertinence validé par revue humaine;
- aucune réponse ne dépasse les limites documentées.

## Phase 3: MCP read-only

Livrables:

- exactement `list_collections`, `search_papers`, `get_paper`, `search_passages`, `get_passage`, `get_citation`;
- schémas fermés et enveloppe `paper-insights.mcp.v1`;
- quatre annotations read-only;
- tailles bornées et client stdio réel en test;
- agent `paper-researcher` connecté au MCP local.

Critères de sortie:

- aucun outil ne possède de port de mutation ou réseau;
- arguments inconnus, booléens-entiers et IDs malformés refusés;
- SQLite ouvert en lecture seule avec `query_only`;
- chaque réponse conserve couverture, limites, version et provenance.

## Phase 4: watchlists et veille

Livrables:

- watchlists par requête, catégorie et auteur;
- overlap, curseur candidat et curseur validé;
- digests Markdown et JSON déterministes;
- commande planifiable avec les codes produit fermés.

Critères de sortie:

- deuxième exécution identique avec zéro nouveauté;
- notice multi-catégorie unique;
- interruption ou run partielle qui conserve le curseur précédent;
- scheduler externe qui distingue succès, confirmation, partiel, indisponibilité et corpus invalide.

## Phase 5: analyse sourcée

**Planned extension:** [Critical source review](specs/CRITICAL-REVIEW.md) adds a
separate appraisal stage before editorial selection. Deliver the paper rubric,
passage-backed findings, explicit evidence gaps, reversible decisions, and a
human calibration of false exclusions. Abstract screening cannot certify
methodological quality. This extends WP-40 after its existing prerequisites;
no runtime or automated filtering is delivered by the specification.

Livrables:

- politique de texte intégral revue avant activation;
- extraction bornée avec provenance;
- schémas LLM fermés et prompt versionné;
- claims avec preuves catalogue durables;
- cache lié à artefact, passages, prompt, modèle et paramètres.

Critères de sortie:

- chaque claim `complete` possède une preuve résoluble;
- une sortie invalide ou tronquée ne remplace pas un cache valide;
- chaque composant de la clé invalide le cache lorsqu'il change;
- au moins 18 analyses sur 20 jugées utiles et fidèles;
- zéro claim publiée sans preuve;
- batch désactivé jusqu'à signature humaine.

## Phase 6: identité des auteurs

Livrables:

- observations OpenAlex et ORCID avec provenance;
- affiliations et pages institutionnelles observées;
- candidats sans fusion ambiguë;
- événements de merge/split réversibles;
- LinkedIn confirmé manuellement.

Critères de sortie:

- homonymes séparés sans identifiant convergent;
- chaque fusion prouvée et réversible;
- URL de recherche LinkedIn jamais présentée comme profil;
- aucun appel ou scraping LinkedIn.

## Phase 7: recherche fédérée

Livrables:

- `FederatedResult v1` pour trois corpus;
- adapters par contrats publics versionnés;
- résultats et rangs groupés par corpus;
- dossier de preuves avec manifest et checksums.

Critères de sortie:

- chaque résultat conserve corpus, ID, type et citation autoritaires;
- indisponibilité d'un corpus rend une couverture partielle explicite;
- aucun score hétérogène transformé en pourcentage commun;
- vidéo ou README jamais rendu comme papier scientifique.

## Release gate

La release reste fermée si un P0 est ouvert, un P1 d'intégrité non mitigé, un benchmark humain incomplet, un comportement seulement validé structurellement ou une preuve `UNKNOWN`.
