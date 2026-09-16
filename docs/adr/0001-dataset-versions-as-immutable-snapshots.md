# ADR-0001 : Versions de dataset en instantanés immuables adressés par contenu

**Statut :** Accepté (Lot 1, 2026-09-15)

## Contexte

CLAUDE.md §6 exige qu'une version de dataset identifie de façon reproductible
son auteur, sa date, son nombre d'exemples, sa configuration de préparation et
son SHA-256, avec un mécanisme de diff entre versions. Le pipeline existant
(`scripts/prepare.py`) écrit déjà `data/train.jsonl`/`data/val.jsonl` et un
fichier `data/VERSION`, mais les écrase à chaque exécution : aucune version
antérieure n'est récupérable, et il n'existe aucune trace de ce qui a produit
un instantané donné.

## Décision

Chaque version est un répertoire `data/versions/<version>/` créé une seule
fois et jamais modifié ensuite : les fichiers (`train.jsonl`, `val.jsonl`,
`manifest.json`) y sont copiés depuis la sortie de `prepare()`, le manifeste
contient le SHA-256 de chaque fichier, l'auteur, la date, la configuration de
préparation et le nombre d'exemples. Le nom de version est validé par un
motif strict (`_SAFE_VERSION` dans `scripts/dataset_versions.py`) avant toute
construction de chemin, pour interdire toute traversée de répertoire. Le
pipeline `prepare()`/`data/VERSION` existant n'est pas modifié : la
versioning est une couche additive au-dessus, pas un remplacement. Le diff
entre deux versions compare les ensembles d'exemples par un identifiant
stable (hash du contenu de l'exemple), pas par position dans le fichier.

## Conséquences

- Une version, une fois créée, ne peut plus être corrompue par une exécution
  ultérieure de `prepare()` — la reproductibilité ne dépend plus de l'état du
  répertoire de travail au moment de l'entraînement.
- Coût : chaque version duplique les fichiers du dataset sur disque (pas de
  déduplication inter-versions). Acceptable tant que les datasets restent de
  taille raisonnable (usage local/petite équipe) ; à revisiter avec un
  stockage adressé par contenu partagé si la taille des datasets devient un
  problème réel.
- Le nom de version n'est pas auto-incrémenté : l'appelant choisit `v1`,
  `v2`, une date, etc. — cohérent avec l'exemple de CLAUDE.md §6.
