# Changelog

Toutes les modifications notables du projet sont consignées ici.

## [Unreleased]

### Added

- Socle documentaire du projet Paper Insights.
- Specs initiales pour le produit, le modèle de données, l'ingestion, la recherche et le MCP.
- Configuration locale pour Claude Code et les agents compatibles.
- Hooks de sécurité et de routage accompagnés de tests unitaires.
- Découverte `unittest` vérifiée depuis la racine du répertoire `tests`.
- Garde Git vérifiée contre les stages larges sans bloquer les pathspecs relatifs explicites.
- Roadmap et plan d'implémentation de la première tranche verticale.
- Plan d'exécution complet des phases 0 à 7, avec contrats P0, lots parallèles, propriétaires de fichiers, gates et critères de release.
- Contrats Gate 0 pour observations versionnées, snapshots source multi-records, identifiants à clés étrangères et révision atomique du catalogue.
- Specs normatives pour watchlists, analyses sourcées, identité réversible des auteurs et fédération multi-corpus.
- Contrats fermés pour collections, trois formats de citation, six outils MCP, enveloppes JSON et codes de sortie CLI.
- Contrat complet des ports synchrones, preuves d'identifiants séparées et artefacts bibliographiques versionnés.

### Changed

- `docs/DEVELOPMENT.md` et l'ancien plan vertical pointent désormais vers le plan complet comme seule autorité d'exécution.
- `doctor` est spécifié strictement read-only; la récupération passe par `repair interrupted-runs --yes`.
- Le manifeste de découverte distingue chaque capture, la création de run attache ses snapshots dans une transaction unique et l'index FTS se publie comme une base auto-descriptive unique.
