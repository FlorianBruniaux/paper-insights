# Spécification de l'identité des auteurs

## Principe

Un nom observé n'est pas une identité. arXiv, OpenAlex, ORCID et les pages institutionnelles produisent des observations avec source, identifiant d'origine, date et payload SHA-256. Ils ne modifient pas directement une identité locale.

## Observations et candidats

Une observation d'identité contient provider, identifiant source, nom, affiliations, co-auteurs, identifiants déclarés, pages institutionnelles, date de récupération et provenance du payload.

Le service produit des candidats avec signaux concordants et contradictions. Un score descriptif ne déclenche jamais seul une fusion.

Fusion automatique autorisée uniquement pour:

- un ORCID exact et vérifié;
- une règle équivalente ajoutée par spec, test et décision explicite.

Deux noms identiques sans identifiant convergent restent séparés.

## Décisions réversibles

Chaque merge, split ou confirmation conserve:

- type d'événement fermé;
- auteurs concernés;
- preuves référencées;
- acteur et timestamp UTC;
- version d'état attendue;
- opération inverse complète;
- événement inversé nullable.

Une décision en conflit avec la version courante est refusée. Reverser une fusion restaure identifiants, relations et états antérieurs sans perte.

## Affiliation

Une affiliation reste une observation rattachée à sa source et sa date. Elle n'est jamais copiée comme vérité permanente sur l'auteur. Les divergences sont conservées.

## LinkedIn

`LinkedInSearchSuggestion` et `ConfirmedLinkedInProfile` sont deux types distincts.

- une URL de recherche peut être générée;
- elle n'est jamais étiquetée comme profil;
- seul `authors confirm-linkedin --yes` accepte une URL de profil explicite;
- l'événement conserve acteur, date et preuve humaine;
- aucun scraping ou appel LinkedIn n'est permis.

## Tests d'acceptation

- deux homonymes restent distincts;
- un ORCID vérifié produit un candidat ou une fusion selon la règle approuvée;
- preuves contradictoires bloquent la fusion;
- merge puis reverse restaure l'état byte-for-byte des read models;
- suggestion LinkedIn impossible à passer au port de confirmation;
- URL non confirmée impossible à persister comme profil;
- fixtures OpenAlex/ORCID locales, aucun réseau réel.
