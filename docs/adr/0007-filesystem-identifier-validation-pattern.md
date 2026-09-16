# ADR-0007 : Tout identifiant filesystem passe par un motif fermé + un confinement `resolve()`

**Statut :** Accepté (audit de sécurité de suivi, 2026-09-16)

## Contexte

Plusieurs identifiants reçus de l'extérieur (segment d'URL ou champ de
requête) sont joints à un chemin sur disque avant lecture, écriture ou
suppression : la catégorie de dataset (`api/routes/dataset.py`), le nom de
fichier de config d'entraînement (`api/schemas.py`, consommé par
`api/jobs.py` puis passé à un sous-processus d'entraînement réel), et
`project_id` lui-même (`api/paths.py::project_dir`, la dépendance partagée
par la quasi-totalité des routes de projet, y compris `DELETE
.../projects/{id}` qui appelle `shutil.rmtree`). Dans chaque cas, la seule
validation initiale était `path.exists()` — insuffisant : un identifiant
peut décoder vers `..` (un segment d'URL encodé en `%2e%2e` atteint bien le
handler, confirmé en le testant directement ; un `/` littéral ou encodé
échoue en revanche à la mise en correspondance de route côté framework et
n'atteint jamais le handler, cette nuance a été vérifiée empiriquement avant
de conclure). L'impact va de la lecture/écriture de fichiers hors projet à
une suppression récursive de répertoire arbitraire.

## Décision

Tout identifiant filesystem-facing suit désormais le même patron à deux
niveaux, déjà utilisé par `scripts/dataset_versions.py::_SAFE_VERSION` et
généralisé aux autres identifiants lors de cet audit :

1. **Motif fermé à la frontière** : une regex ancrée qui exclut
   structurellement `/` et interdit un `.` en tête (donc `..` seul ne peut
   jamais matcher) — via `Field(pattern=...)` côté Pydantic quand
   l'identifiant vient du corps de requête, ou une regex explicite quand il
   vient d'un segment d'URL brut.
2. **Confinement en profondeur** : au point d'accès disque, `path.resolve()`
   puis vérification que le répertoire parent attendu figure dans
   `path.parents` — au cas où un identifiant validé par le motif serait
   malgré tout rejoint d'une façon inattendue plus loin dans l'appel.

Le second niveau est délibérément conservé même quand le premier suffirait
déjà à bloquer l'entrée observée aujourd'hui : le coût est de deux lignes,
et il protège contre un futur appelant qui joindrait l'identifiant
autrement (concaténation partielle, sous-répertoire supplémentaire) sans
repasser par la même validation.

## Conséquences

- Tout nouvel identifiant reçu de l'extérieur et utilisé pour construire un
  chemin doit suivre ce même patron plutôt que se contenter de
  `path.exists()` — une revue de code doit le signaler s'il manque.
- Quand l'identifiant a déjà une charte de création restrictive côté
  serveur (ex. `project_id` n'est jamais que minuscules/chiffres/tirets à la
  création, `api/routes/projects.py::ID_PATTERN`), réutiliser exactement ce
  motif à la lecture ne rejette aucun cas légitime — vérifié par des tests
  de non-régression dédiés (`tests/test_paths.py`,
  `tests/test_dataset_routes.py`, `tests/test_training_routes.py`).
- Une dépendance partagée (`project_dir()`) qui applique ce patron une seule
  fois vaut mieux qu'une validation dupliquée par endpoint : découvert lors
  de cet audit que `delete_project` avait recopié le join non validé au lieu
  de réutiliser `project_dir()`, ce qui avait fait disparaître la validation
  sur le chemin le plus destructeur (`shutil.rmtree`). Réutiliser la
  dépendance plutôt que dupliquer la logique est donc aussi une exigence de
  sécurité, pas seulement de style.
