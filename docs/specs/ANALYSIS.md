# Spécification du texte intégral et des analyses

## Politique avant code

Le texte intégral n'est acquis que depuis une source autorisée par `docs/policies/FULLTEXT-ACCESS.md`. La politique versionne hôtes, schémas, redirections, types MIME, taille, rétention et cas de refus. L'absence de droit ou de preuve reste `UNKNOWN` et bloque l'acquisition.

## Acquisition et extraction

- HTTPS et hôtes explicitement autorisés;
- chaque redirection revalidée;
- streaming sous limite d'octets;
- contrôle type MIME et signature PDF avant publication;
- blob privé, `fsync`, SHA-256 et `os.replace`;
- extraction locale sans réseau, sous limites de temps, pages et caractères;
- rejet fermé des PDF chiffrés, malformés, trop grands ou interrompus.

Le texte dérivé référence PDF, SHA-256, URL source, politique, extracteur, version, limites et date. Une extraction ne dépend jamais d'un chemin implicite.

## Passages durables

Le chunking est déterministe et versionné. Chaque passage utilisé comme preuve est enregistré dans le catalogue avec version, artefact, schéma de chunk, section, ordinal, texte normalisé et offsets. Son identifiant suit [SEARCH-AND-MCP.md](SEARCH-AND-MCP.md).

## Frontière LLM

Le texte et les métadonnées du papier sont des données non fiables. Ils restent dans les messages de données et ne deviennent jamais des instructions système ou développeur.

Le backend reçoit une requête bornée avec:

- version et artefact exacts;
- passages ordonnés et leurs IDs;
- version et SHA-256 du prompt;
- version du schéma de résultat;
- provider, modèle et paramètres canoniques.

La sortie Pydantic utilise `extra="forbid"`. Le système conserve payload brut borné, stop reason, provider, modèle, validation et erreur nettoyée.

## Claims et publication

Une tentative a les états `running`, `complete`, `invalid`, `truncated` ou `failed`. Chaque claim contient texte, catégorie, incertitude et au moins un `passage_id`.

La publication `complete` est une transaction qui:

1. valide le schéma fermé;
2. résout chaque passage dans le catalogue;
3. vérifie même version et même artefact d'entrée;
4. insère claims et `analysis_claim_evidence`;
5. refuse tout claim sans preuve;
6. publie l'entrée de cache.

Une tentative invalide, tronquée ou échouée reste auditée mais ne remplace jamais une entrée de cache complète.

## Cache

La clé SHA-256 couvre JSON canonique de:

- SHA-256 artefact;
- liste ordonnée des `passage_id`;
- `chunk_schema_version`;
- version et SHA-256 du prompt;
- version du schéma de résultat;
- provider et modèle;
- paramètres de requête.

Modifier un composant invalide la clé.

## Gate humaine

Le batch reste désactivé tant qu'un fichier d'évaluation signé ne contient pas 20 analyses sur au moins quatre types de papiers. Toute claim publiée sans preuve est un P0. Au moins 18 analyses sur 20 doivent être jugées utiles et fidèles.

## Tests d'acceptation

- chunking stable et passage résoluble après rebuild FTS;
- injection dans texte ou métadonnées sans changement d'instructions;
- sortie extra, invalide ou tronquée refusée;
- claim sans preuve impossible à publier;
- clé de cache modifiée par chaque composant;
- ancien cache valide préservé après un retry invalide;
- transport LLM simulé, aucun réseau réel.
