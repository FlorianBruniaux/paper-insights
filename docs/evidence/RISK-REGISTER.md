# Registre des risques

Ce registre relie chaque risque durable aux contrôles existants, à la capacité qui porte son état de preuve et à la lacune résiduelle. La matrice `capability-matrix.json` reste l'autorité des statuts. Ce document ne les promeut pas.

<!-- evidence-governance:risk-register -->
```json
{
  "schema_version": "risk-register-v1",
  "risks": [
    {"id": "R1", "capability_ids": ["gate1.foundation", "gate2.local-retrieval"]},
    {"id": "R2", "capability_ids": ["gate1.foundation", "gate2.local-retrieval"]},
    {"id": "R3", "capability_ids": ["gate4.analysis-identity-federation"]},
    {"id": "R4", "capability_ids": ["gate2.local-retrieval"]},
    {"id": "R5", "capability_ids": ["gate3.mcp-monitoring-fulltext"]},
    {"id": "R6", "capability_ids": ["gate3.mcp-monitoring-fulltext"]},
    {"id": "R7", "capability_ids": ["gate4.analysis-identity-federation"]},
    {"id": "R8", "capability_ids": ["gate5.release"]}
  ]
}
```

| ID | Risque | Contrôles existants ou prévus | Source de preuve | Lacune résiduelle |
| --- | --- | --- | --- | --- |
| R1 | Métadonnées ou versions écrasées | Observations immuables, snapshots source, blobs adressés par contenu, clés étrangères | `gate1.foundation`, `gate2.local-retrieval` | Aucun corpus réel de référence ni restauration complète après incident n'a été mesuré. |
| R2 | Ingestion partielle présentée comme succès | Runs et outcomes fermés, compteurs, réparation explicite, publication par record | `gate1.foundation`, `gate2.local-retrieval` | Les fixtures hors réseau ne couvrent pas une panne réelle du provider ou du disque. |
| R3 | Instructions adversariales suivies depuis un papier | Frontière LLM fermée, texte traité comme donnée, test d'injection prévu dans WP-40 | `gate4.analysis-identity-federation` | Aucun backend LLM ni test comportemental n'est encore exécuté. |
| R4 | Recherche techniquement valide mais éditorialement inutile | Harnais aveugle de 30 requêtes, résultats liés aux empreintes, revue humaine obligatoire | `gate2.local-retrieval` | Revue humaine à 0 sur 30 et corpus de référence non approuvé. |
| R5 | Acquisition illégitime ou document hostile | Politique avant code, HTTPS, hôtes, redirections, taille, MIME et extraction bornée | `gate3.mcp-monitoring-fulltext` | WP-32 n'est pas ouvert et la politique de texte intégral n'est pas approuvée. |
| R6 | Mutation ou appel réseau depuis le MCP | Six outils fermés, ports read-only, SQLite `query_only`, instrumentation prévue | `gate3.mcp-monitoring-fulltext` | Le runtime MCP et son test stdio n'existent pas encore. |
| R7 | Fusion de deux auteurs sur un signal ambigu | Observations séparées, ORCID/OpenAlex, événements merge/split réversibles, LinkedIn manuel | `gate4.analysis-identity-federation` | Les providers et décisions d'identité ne sont pas implémentés. |
| R8 | Release annoncée sur preuves partielles | Gates ordonnées, deux benchmarks humains, audits indépendants, matrice de claim ceiling | `gate5.release` | Les Gates 2 à 5 restent ouvertes ou bloquées. |

## Règle de mise à jour

Tout nouveau contrôle ajoute ou modifie d'abord une capacité dans la matrice. Le registre référence ensuite cet identifiant et conserve la lacune qui subsiste. Une suite de tests verte ne suffit pas pour supprimer une lacune comportementale ou humaine.
