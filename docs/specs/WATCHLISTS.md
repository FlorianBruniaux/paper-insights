# Spécification des watchlists

## Autorité

Une watchlist décrit une découverte rejouable. Elle ne contient pas de scheduler et n'est jamais exécutée à l'import. `cron`, `launchd` ou une automation appelle la CLI.

## Modèle

`watchlists` contient:

- UUIDv7 et slug unique;
- `source_id` avec FK;
- `query_json` canonique et versionné;
- `validated_cursor_json` nullable;
- `overlap_seconds` positif ou nul;
- `enabled`, `created_at`, `updated_at` et `last_success_at`;
- version attendue de l'état pour empêcher un écrasement concurrent.

Les runs de watchlist référencent une `ingestion_run`, le curseur de départ, le curseur candidat, la fenêtre effective et le statut. Les digests référencent la run et conservent format, SHA-256 et compteurs.

## Exécution

1. Lire la watchlist et son curseur validé dans un snapshot cohérent.
2. Reculer la fenêtre de `overlap_seconds` sans modifier le curseur stocké.
3. Appeler `discover()` puis préparer le manifeste exact.
4. Exiger `--yes` pour cette exécution précise; aucune autorisation persistante n'est stockée ou déduite du scheduler.
5. Sans confirmation, afficher le manifeste et terminer avec le code `3` sans mutation.
6. Exécuter l'ingestion confirmée avec les mêmes snapshots et records.
7. Différencier nouveautés à partir des identifiants papier/version et hashes normalisés, jamais du curseur seul.
8. Construire un digest candidat déterministe.
9. Dans une transaction finale, vérifier la version d'état attendue, valider le curseur candidat, relier la run et mettre à jour `last_success_at`.

Une run `partial` ou `failed` conserve le curseur validé précédent. Une interruption avant finalisation produit le même effet. Deux exécutions identiques donnent zéro nouveauté à la seconde.

## Déduplication et compteurs

Une notice multi-catégorie apparaît une seule fois dans le digest. L'ordre est date source, identifiant papier, identifiant de version.

Le résultat contient:

- `new_papers`;
- `new_versions`;
- `metadata_updates`;
- `unchanged_records`;
- `failed_records`;
- curseur précédent et curseur candidat;
- couverture et erreurs fermées.

Les compteurs conservent les définitions de [INGESTION.md](INGESTION.md).

## Digests

Les formats sont Markdown et JSON `watchlist-digest-v1`. Ils proviennent de la même read model ordonnée. Le JSON conserve IDs, source, version, provenance, compteurs et couverture. Le Markdown ne transforme pas une erreur en absence de nouveauté.

## Codes de sortie

- `0`: run réussie;
- `3`: confirmation requise, aucune mutation;
- `4`: succès partiel;
- `5`: source indisponible;
- `6`: corpus invalide;
- `2`: entrée ou configuration invalide.

Cette table réutilise sans réattribution les codes de [PRODUCT.md](PRODUCT.md).

## Tests d'acceptation

- replay identique avec zéro nouveauté au second passage;
- overlap qui retrouve un item tardif sans doublon;
- notice multi-catégorie unique;
- run partielle, échec et interruption qui conservent le curseur précédent;
- conflit de version d'état qui refuse la finalisation;
- exécution sans `--yes` qui rend le code `3` avec zéro mutation;
- Markdown et JSON déterministes sur fixtures locales;
- aucun réseau réel dans les tests.
