# Audit de `academic-research-skills`

Date d'observation: 2026-09-08

## Source observée

- dépôt: `https://github.com/Imbad0202/academic-research-skills`;
- clone local: `/Users/florianbruniaux/Sites/divers-tests/academic-research-skills`;
- branche: `main`;
- commit: `8e4c8777648cdb3a1b8c01e956cf902121216aa0`;
- état local après mise à jour: propre;
- licence déclarée: `CC-BY-NC-4.0`.

Le commit observé possède trois workflows GitHub Actions réussis: Spec Consistency, repository-hygiene et Command Invariants. Le clone contient 222 fichiers de test et 614 fichiers sous des répertoires `scripts`. Les validateurs Python ciblés n'ont pas été rejoués localement car le Python système ne contient pas `PyYAML`; cette absence locale n'est ni un succès ni un échec du dépôt.

La licence autorise la reproduction et l'adaptation pour des usages non commerciaux, avec attribution et conservation des mentions applicables. La compatibilité avec un usage ou une distribution commerciale de Paper Insights reste `UNKNOWN` et exige une décision séparée. Source normative consultée: [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/legalcode.en).

## Périmètre audité

Les quatre `SKILL.md` ont été lus intégralement. Les 189 chemins locaux déclarés vers agents, références, scripts, contrats, modèles et exemples ont été résolus, sans ressource manquante.

| Skill | Lignes | Références résolues | Description |
| --- | ---: | ---: | ---: |
| `academic-paper` | 542 | 39/39 | 564 caractères |
| `academic-paper-reviewer` | 491 | 42/42 | 699 caractères |
| `academic-pipeline` | 736 | 38/38 | 595 caractères |
| `deep-research` | 600 | 70/70 | 984 caractères |

## Résultat de l'audit des skills

Le score suit le contrat `eval-skills`, sur 24 points. Il mesure la qualité d'une adaptation portable vers les runtimes Claude Code et Codex. Il ne mesure pas la qualité scientifique des sorties.

| Skill | Nom | Pointeur | Outils | Effort | Workflow | Ressources | Économie | Routage | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `academic-paper` | 1 | 3 | 0 | 0 | 4 | 3 | 1 | 0 | 12/24, Fix |
| `academic-paper-reviewer` | 1 | 3 | 0 | 0 | 4 | 3 | 1 | 0 | 12/24, Fix |
| `academic-pipeline` | 1 | 4 | 0 | 0 | 4 | 3 | 1 | 0 | 13/24, Fix |
| `deep-research` | 1 | 2 | 0 | 0 | 4 | 3 | 1 | 0 | 11/24, Fix |

### `academic-paper`, 12/24

- Le périmètre et les onze modes sont explicites, mais la description accumule des synonymes multilingues.
- `allowed-tools` et `effort` sont absents. Effort inféré: `xhigh`, avec douze agents et des révisions multi-étapes.
- Le workflow possède des gates et des sorties observables.
- Les 39 ressources déclarées existent.
- Les protocoles propres à certains modes restent chargés dans un fichier principal de 542 lignes.
- Aucun `evals/scenarios.json` ne mesure le routage Claude Code et Codex.

### `academic-paper-reviewer`, 12/24

- La distinction entre cinq sièges séparés et cinq processus indépendants est correctement bornée.
- `allowed-tools` et `effort` sont absents. Effort inféré: `xhigh`, avec cinq revues, une synthèse et plusieurs modes.
- Le workflow, les verdicts et les checkpoints sont explicites.
- Les 42 ressources déclarées existent.
- Le fichier principal charge 491 lignes, dont des protocoles spécifiques au re-review et à la calibration.
- Aucun corpus de routage positif et négatif n'est fourni.

### `academic-pipeline`, 13/24

- Le pointeur distingue correctement l'orchestration complète des trois skills spécialisés.
- `allowed-tools` et `effort` sont absents. Effort inféré: `max`, avec dix stages, reprises et gates multi-skills.
- Les transitions, preuves et états de reprise sont explicites.
- Les 38 ressources déclarées existent.
- Le skill se décrit comme léger mais son fichier principal atteint 736 lignes et duplique de nombreux contrats aval.
- Aucun corpus de routage Claude Code et Codex n'est fourni.

### `deep-research`, 11/24

- Le mot déclencheur générique `research` entre en collision avec les recherches locales spécialisées.
- `allowed-tools` et `effort` sont absents. Effort inféré: `max`, avec treize agents, huit modes, PRISMA et méta-analyse.
- Les phases, checkpoints, échecs et sorties sont explicites.
- Les 70 ressources déclarées existent.
- Les protocoles de revue, Socratic mode, veille et systematic review restent dans un fichier principal de 600 lignes.
- Aucun corpus de routage positif et négatif n'est fourni.

## Décision d'adoption recommandée

### Reprendre comme principes, sans copier le runtime

1. Conserver la séparation entre préengagement aveugle, observation automatisée et vérité humaine. Paper Insights l'applique déjà au Gate 2.
2. Traiter les PDF et textes récupérés comme des données non fiables, jamais comme des instructions. L'architecture Paper Insights le prévoit déjà; le futur WP-32 doit le tester avec des fixtures hostiles.
3. Lier chaque étape générative à un manifeste immuable, des empreintes d'entrée, une version de prompt, un modèle et des passages. Ce contrat appartient à la Phase 5 de Paper Insights.
4. Distinguer les rôles de revue d'une indépendance réelle des erreurs. Une future évaluation multi-rôles doit enregistrer le modèle, le contexte partagé et le protocole de synthèse.
5. Garder des frontières déterministes entre préparation, génération, validation, replay et publication. Paper Insights possède déjà cette structure pour l'ingestion et l'index FTS5.

### Reporter après les gates actuelles

1. Un passeport de reprise inter-session peut compléter les manifests d'analyse après Gate 3, sans devenir un second orchestrateur.
2. La vérification d'existence, de rétractation ou de correction d'une citation peut devenir une observation provider sourcée. Elle ne prouve jamais qu'une citation soutient un claim.
3. PRISMA, risque de biais, GRADE et méta-analyse sont des capacités applicatives futures. Elles exigent une spec, des sources normatives, des jeux d'évaluation et une décision de périmètre distincts.
4. Les protocoles de patch de manuscrit sont utiles seulement si Paper Insights devient un outil de rédaction, ce qui n'appartient pas à la roadmap actuelle.

### Ne pas reprendre

- le pipeline de rédaction de manuscrit en dix stages;
- le fan-out par défaut vers 5, 12 ou 13 agents;
- la sélection de journal, le formatage LaTeX, DOCX ou PDF et les réponses aux reviewers;
- le model tiering et les variables `ARS_*` comme architecture Paper Insights;
- toute reconstruction de DOI, d'auteur ou de citation depuis une sortie LLM;
- une copie directe des prompts, scripts ou contrats tant que la compatibilité de licence et l'usage commercial ne sont pas décidés.

## Optimisation locale déclenchée

Les trois skills propres à Paper Insights ont été alignés sur le runtime Gate 2:

- `paper-ingest` utilise le preview et l'ingestion CLI avec confirmation exacte;
- `paper-research` utilise la recherche CLI read-only tant que le MCP Gate 3 est fermé;
- `paper-citation` utilise l'export CLI déterministe;
- chaque skill possède huit prompts positifs et trois négatifs;
- le hook Claude distingue citation autonome, recherche et ingestion;
- `.claude/skills` reste une projection du répertoire canonique `.agents/skills`.

Le rebuild et les canaries du routeur BM25 live restent `UNKNOWN`: aucun mécanisme local de rebuild Claude Code et Codex n'est exposé dans ce dépôt. Les corpus et tests déterministes sont présents, mais ne constituent pas une preuve de sélection par les deux runtimes.

## Prochaine séquence

1. Terminer les 30 revues humaines du Gate 2 avec un `reviewer_id` réel.
2. Fermer Gate 2 seulement si au moins 24 requêtes sur 30 passent et si aucun P0 humain n'est présent.
3. Ouvrir Gate 3 avec les six outils MCP read-only déjà spécifiés.
4. Reporter les idées `academic-research-skills` vers la Phase 5 sous forme de specs indépendantes, sans copier le pipeline amont.
