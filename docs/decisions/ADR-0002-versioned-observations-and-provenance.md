# ADR-0002: Observations versionnées et provenance

- Statut: accepté
- Date: 2026-08-29

## Contexte

Une oeuvre peut recevoir plusieurs versions et une même version peut être observée plusieurs fois avec des métadonnées corrigées. Une page arXiv contient plusieurs notices. Le modèle initial plaçait titre et résumé sur `papers`, utilisait des identifiants polymorphiques et attachait une réponse source à un papier. Ces choix empêchaient de conserver l'historique exact et d'appliquer de vraies clés étrangères.

## Décision

- `papers` porte uniquement l'identité locale de l'oeuvre.
- `paper_versions` porte l'identité d'une révision source.
- `version_observations` porte chaque état bibliographique normalisé immuable.
- auteurs ordonnés et catégories référencent `version_observation_id`.
- `stored_blobs`, `source_snapshots` et `snapshot_records` conservent la page brute multi-papiers et ses ordinals.
- chaque record normalisé ou échoué reste relié à son snapshot et son ordinal.
- `paper_identifiers`, `version_identifiers` et `author_identifiers` remplacent l'association polymorphe et utilisent des FKs réelles.
- les passages utilisés comme preuves d'analyse sont persistés dans le catalogue; FTS reste une projection.

## Conséquences

- une correction de métadonnées crée une observation au lieu d'écraser l'ancienne;
- une nouvelle récupération identique ajoute de la provenance sans dupliquer l'observation;
- une réponse brute n'est ni attribuée à un seul papier, ni copiée par papier;
- le schéma possède plus de relations et les citations doivent sélectionner une observation exacte;
- les migrations et repositories doivent préserver `NULL` pour un champ absent.

## Options rejetées

### Métadonnées canoniques mutables sur `papers`

Ce modèle simplifie la lecture courante mais perd la valeur utilisée pour une citation ou une analyse antérieure.

### Table `external_identifiers` polymorphe

SQLite ne peut pas garantir la FK vers plusieurs tables. Trois tables explicites rendent l'intégrité testable.

### Réponse source comme artefact du papier

Une page multi-papiers n'appartient à aucun papier unique. Snapshot et ordinal portent la bonne granularité.
