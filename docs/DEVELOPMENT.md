# Développement local

## État actuel

Le dépôt contient uniquement le socle documentaire et agentique. La validation actuelle ne nécessite ni environnement virtuel, ni accès réseau.

```bash
python3 scripts/validate_project.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Installation cible

La phase 0 utilisera `uv`:

```bash
uv sync --all-extras --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Ne pas générer de lockfile avant la première implémentation, car le socle actuel n'installe encore aucune dépendance.

## Ordre d'implémentation

Suivre `docs/superpowers/plans/2026-08-28-complete-program-execution.md`. WP-00 puis WP-01 sont les seuls travaux autorisés avant validation de Gate 0. L'ancien plan `2026-08-28-foundation-vertical-slice.md` reste une archive de conception et ne doit pas être exécuté.

Chaque work package suit test rouge, changement minimal, test ciblé, gate du package, revue puis commit ciblé. Un seul owner modifie SQLAlchemy et la chaîne Alembic. Les workers ne changent pas silencieusement une spec ou un port partagé.

## Tests hors réseau

Les réponses arXiv, OpenAlex, Crossref et ORCID utilisées par les tests doivent être enregistrées comme fixtures minimales. Retirer les tokens, cookies, adresses personnelles non nécessaires et paramètres signés. Chaque fixture indique sa source et sa date de capture.

Un test qui appelle le réseau échoue par défaut. Les clients HTTP sont injectés et simulés avec `respx`.

## Hooks Claude Code

Le hook de garde lit un événement JSON sur l'entrée standard. Cas autorisé:

```bash
CLAUDE_PROJECT_DIR="$PWD" python3 .claude/hooks/project-guard.py <<<'{"tool_name":"Bash","tool_input":{"command":"uv run pytest"}}'
```

Cas bloqué, code de sortie attendu 2:

```bash
CLAUDE_PROJECT_DIR="$PWD" python3 .claude/hooks/project-guard.py <<<'{"tool_name":"Bash","tool_input":{"command":"git add ."}}'
```

Le hook de routage reste non bloquant. Il ajoute du contexte uniquement si le prompt associe explicitement un papier ou arXiv à une intention de recherche ou d'ingestion.

Après une modification de hook:

1. exécuter les tests sous `tests/hooks/`;
2. ouvrir `/hooks` dans Claude Code;
3. vérifier le chemin et l'événement;
4. exécuter un cas autorisé;
5. exécuter un cas qui doit être bloqué.

## Skills

`.agents/skills/` est la source canonique. `.claude/skills` est un lien relatif suivi par Git. Ajouter une skill dans `.agents/skills/<nom>/SKILL.md`, puis ajouter `agents/openai.yaml` si Codex doit afficher un nom et un prompt par défaut.

Chaque skill doit:

- avoir un nom `kebab-case` identique à son répertoire;
- décrire ses déclencheurs et ses faux positifs;
- séparer les opérations read-only des mutations;
- arrêter le workflow si la CLI ou le MCP requis n'existe pas;
- ne pas présenter une commande planifiée comme disponible.

## Agents

Les agents de revue restent en `permissionMode: plan`. Un agent d'implémentation possède un périmètre de répertoires et ne modifie pas une frontière voisine sans mise à jour de spec.

## Changelog

Toute modification de fichier met à jour `CHANGELOG.md` sous `[Unreleased]`. Lorsqu'une phase produit une version utilisable, remplacer les entrées par une section datée et incrémenter la version dans `pyproject.toml`.
