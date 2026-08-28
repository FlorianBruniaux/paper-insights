# ADR-0003: Manifeste de preview et publication atomique

- Statut: accepté
- Date: 2026-08-29

## Contexte

Une interface `preview(query)` suivie de `iter_records(query)` peut interroger deux fois une source et ingérer une sélection différente de celle confirmée. Les blobs et l'index FTS ajoutent une autre frontière: un fichier peut être publié avant son attachement SQL, et un index peut devenir obsolète entre le contrôle de révision et `os.replace`.

## Décision

- le provider expose `discover(query) -> DiscoveryBatch`;
- `PrepareDiscovery` produit un `PreparedDiscovery` immuable avec batch, preview, digest et expiration;
- le digest couvre requête canonique, versions sélectionnées et SHA-256 ordonnés des pages;
- l'exécution consomme ce manifeste exact et ne rappelle jamais le provider;
- les blobs sont publiés hors transaction SQL par fichier sibling privé, `fsync`, validation puis `os.replace`;
- un échec d'attachement peut laisser un blob orphelin signalé par `doctor`;
- `doctor` reste read-only et la réparation est une commande distincte confirmée;
- `catalog_meta.revision` augmente une fois par transaction métier visible;
- la publication FTS garde un `BEGIN IMMEDIATE` depuis le contrôle final de révision jusqu'au remplacement atomique.

## Conséquences

- la confirmation est vérifiable et expire après 15 minutes;
- preview et absence de confirmation garantissent zéro mutation;
- l'ingestion peut reprendre par identifiants naturels sans refaire la découverte;
- une publication FTS bloque brièvement les writers pendant le contrôle et le remplacement;
- les orphelins sont des états attendus et auditables, jamais présentés comme ingérés.

## Options rejetées

### Rejouer la requête après confirmation

La source peut changer entre deux appels. Le consentement ne porterait pas sur les données exécutées.

### Contrôle de révision sans garde

Une écriture catalogue peut survenir entre le contrôle et `os.replace`. Le nouvel index serait déjà obsolète lors de sa publication.

### Réparation implicite dans `doctor`

Un diagnostic ne doit pas changer l'état qu'il mesure. La mutation exige un verbe et une confirmation explicites.
