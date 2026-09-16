# Architecture Decision Records

Format léger (Context / Decision / Consequences), un fichier par décision
structurante, jamais réécrit rétroactivement — une décision annulée reçoit un
nouveau statut (`Remplacée par ADR-000X`) plutôt qu'une édition silencieuse.

| ADR | Titre | Statut |
|---|---|---|
| [0001](0001-dataset-versions-as-immutable-snapshots.md) | Versions de dataset en instantanés immuables adressés par contenu | Accepté |
| [0002](0002-additive-only-sqlite-migrations.md) | Migrations SQLite additives uniquement | Accepté |
| [0003](0003-tool-risk-level-as-non-bypassable-gate.md) | Le niveau de risque d'un outil comme garde non contournable | Accepté |
| [0004](0004-api-v1-as-path-rewrite-alias.md) | `/api/v1` comme alias de réécriture de chemin, pas une deuxième API | Accepté |
| [0005](0005-no-hand-maintained-sdk.md) | Pas de SDK maintenu à la main — génération OpenAPI + quickstarts d'auth | Accepté |
| [0006](0006-enterprise-scope-lot-3.md) | Périmètre Enterprise du lot 3 : ce qui n'a pas été construit, et pourquoi | Accepté |
| [0007](0007-filesystem-identifier-validation-pattern.md) | Tout identifiant filesystem passe par un motif fermé + un confinement `resolve()` | Accepté |
