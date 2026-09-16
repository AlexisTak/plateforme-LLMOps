# ADR-0002 : Migrations SQLite additives uniquement

**Statut :** Accepté (Lot 1, 2026-09-15)

## Contexte

Le plan de contrôle (`api/enterprise.py`) utilise SQLite sans outil de
migration externe (Alembic, etc. — CLAUDE.md §26 interdit d'imposer une
infrastructure inutile pour un socle local). Plusieurs lots (registre de
modèles enrichi, `tools.risk_level`) devaient ajouter des colonnes à des
tables déjà en production sans casser les lignes existantes ni exiger une
étape de migration manuelle (CLAUDE.md §2.9 : « ne jamais modifier un contrat
API existant sans migration ou compatibilité »).

## Décision

Toute évolution de schéma passe par un bloc idempotent au démarrage de
`EnterpriseStore._initialize()` : lecture de `PRAGMA table_info(<table>)`,
puis `ALTER TABLE <table> ADD COLUMN <name> <definition> DEFAULT <valeur>`
pour chaque colonne absente. Jamais de `DROP COLUMN`, `RENAME COLUMN` ou
recréation de table. Chaque nouvelle colonne a une valeur par défaut non
nulle exploitable par le code existant (ex. `environment TEXT NOT NULL
DEFAULT 'local'`, `risk_level TEXT NOT NULL DEFAULT 'medium'`), pour qu'une
ligne créée avant la migration reste lisible et cohérente sans traitement
spécial côté application.

## Conséquences

- Aucune interruption de service ni script de migration séparé à exécuter :
  la migration se produit à la prochaine ouverture de la base.
- Le schéma ne peut que grandir — une colonne obsolète reste présente mais
  inutilisée plutôt que d'être supprimée. Acceptable en l'absence d'outil de
  migration dédié ; à revisiter si le nombre de colonnes mortes devient
  gênant (migration réelle avec fenêtre de maintenance, hors scope MVP).
- Toute future évolution de schéma doit suivre le même patron plutôt que
  d'introduire un outil de migration : cohérence avant tout.
