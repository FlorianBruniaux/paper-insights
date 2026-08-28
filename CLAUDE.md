# Claude Code dans Paper Insights

`AGENTS.md` contient les règles communes et reste la référence principale. Ce fichier décrit la configuration propre à Claude Code.

## Démarrage d'une session

1. Lire `AGENTS.md` et la spec liée à la demande.
2. Vérifier `git status --short` avant toute écriture.
3. Utiliser l'agent ou le skill le plus étroit qui couvre la tâche.
4. Garder les mutations du corpus dans la session principale.
5. Ne jamais présenter une prévisualisation comme une ingestion réussie.

## Agents locaux

| Agent | Utilisation |
| --- | --- |
| `paper-researcher` | Recherche locale, lecture seule et citations sourcées |
| `paper-ingestion-engineer` | Adaptateurs de sources, reprise et idempotence |
| `corpus-integrity-reviewer` | Transactions, artefacts, empreintes et publication atomique |
| `mcp-contract-reviewer` | Surface MCP, bornes et absence de mutation |
| `scientific-analysis-reviewer` | Schémas d'analyse, passages probants et incertitude |

Les agents de revue utilisent `permissionMode: plan`. Ils inspectent et rapportent, sans modifier les fichiers.

## Skills locaux

| Skill | Déclencheur |
| --- | --- |
| `paper-research` | Chercher et comparer des papiers déjà indexés |
| `paper-ingest` | Prévisualiser ou lancer une collecte autorisée |
| `paper-citation` | Préparer une citation depuis les métadonnées enregistrées |

Les sources canoniques se trouvent dans `.agents/skills/`. Le lien `.claude/skills` expose les mêmes fichiers à Claude Code.

## Hooks locaux

`.claude/settings.json` enregistre deux hooks:

- `project-guard.py` refuse les commandes destructrices larges, les écritures de secrets et les écritures hors du dépôt;
- `research-router.py` ajoute un rappel de workflow lorsqu'un prompt demande une recherche ou une ingestion de papiers.

Tester les hooks après toute modification:

```bash
python3 -m unittest discover -s tests/hooks -p 'test_*.py'
```

Une validation structurelle ne prouve pas que Claude Code a chargé le hook. Après un changement de hook, inspecter `/hooks`, vérifier le chemin affiché et exécuter un cas bénin puis un cas bloqué.

## Autorisations

- Ne pas élargir les permissions dans `.claude/settings.json` pour contourner une erreur.
- Les secrets et fichiers `.env` restent refusés en lecture.
- Toute opération de réseau suit le workflow de prévisualisation défini par `paper-ingest`.
- Une acquisition en lot nécessite la confirmation de l'utilisateur après la prévisualisation.

## Changements de configuration

La configuration de ce dépôt est locale. Ne pas modifier `~/.claude`, `~/.codex` ou la configuration partagée depuis ce projet. Une modification globale suit son propre inventaire, diff et accord explicite.
