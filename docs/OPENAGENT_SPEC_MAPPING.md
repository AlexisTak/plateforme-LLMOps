# Intégration du cahier des charges OpenAgent Enterprise

Ce document relie la spécification 1.0 au produit OpenAgent existant. Le
projet conserve FastAPI comme plan de contrôle et son module de fine-tuning :
une réécriture Go et la suppression de fonctions existantes n'apporteraient pas
de valeur au MVP actuel.

## Couverture actuelle

| Exigence | État | Implémentation |
|---|---|---|
| F02 Espaces et rôles | Partiel | Projets isolés, membres et rôles dans le plan de contrôle SQLite |
| F03 CRUD agents | Couvert | Projets, Settings, activation par registre et archivage |
| F04 Fournisseurs | Couvert | Registre Ollama, API compatible OpenAI et API compatible Anthropic, secrets par référence d'environnement et test de connexion |
| F05 Conversation et historique | Partiel | Chat en streaming SSE et exécutions expurgées persistantes; historique conversationnel durable reste à faire |
| F06 PDF DOCX TXT MD | Couvert | Ingestion, extraction, indexation asynchrone et erreurs explicites |
| F07 Recherche filtrée | Partiel | Index séparé par projet; espaces multiples et ACL fines restent à faire |
| F08 Catalogue d'outils | Couvert | Outils HTTP GET ou POST et MCP Streamable HTTP en lecture, timeout et limite de réponse |
| F09 Politiques d'outils | Couvert | Règles globales ou ciblées allow, deny et require approval, priorités déterministes et audit des décisions |
| F10 Approbations | Couvert | Suspension, décision unique et exécution après approbation |
| F11 Traces et export | Couvert | Modèle, durée, volume, RAG, statut et chronologie d’événements persistés, détail interactif et export JSON versionné |
| F12 Audit | Couvert | Journal SQLite append-only applicatif avec chaîne de hash |
| F14 Budgets | Partiel | Quotas jobs et stockage; budgets jetons par agent restent à faire |
| F15 Versions et rollback | Couvert | Workflow évalué, approuvé, production, archive et rollback |
| F18 Évaluation | Couvert | Cas CRUD, rapports, graphiques et comparaison de variantes |
| NF04 Linux | Couvert | Scripts Linux et fonctionnement local sans SaaS obligatoire |
| NF05 Observabilité | Couvert | Correlation ID, métriques RED, export Prometheus, `/api/ready` distinct de `/api/health` |
| NF09 Sauvegarde | Couvert | ZIP portable avec manifeste SHA-256 + `POST .../restore` qui vérifie chaque fichier et restaure sous un nouvel id, testé par `tests/test_enterprise.py` |

## Industrialisation LLMOps (lot 1, 2026-09-15)

Voir [docs/superpowers/specs/2026-09-15-llmops-industrialization-design.md](superpowers/specs/2026-09-15-llmops-industrialization-design.md)
pour l'audit complet. Ajouté sans casser de contrat existant :

- **Dataset versioning** : instantanés immuables SHA-256 dans `data/versions/<version>/`
  (`scripts/dataset_versions.py`), diff par id stable, `data/VERSION` inchangé.
- **Experiment tracking** : `git_commit` capturé par `training/scripts/train.py`,
  `GET .../experiments/compare?ids=a,b` pour comparer des runs.
- **Model registry** : colonnes additives `adapter`, `quantization`, `rag_version`,
  `environment`, `artifacts` (SHA-256, réutilise `evaluation/reports.py`).
- **Backup/restore** : `POST .../restore` restaure sous un nouvel id, intégrité
  vérifiée fichier par fichier, restauration réellement testée (round-trip).
- **Docker** : `docker-compose.yml` (API + web, healthchecks sur `/api/ready`),
  `./start.sh`/`./start.ps1` restent le chemin principal.

## LLMOps (lot 2, 2026-09-15)

- **Évaluation multi-axes** : `refused` (heuristique hors ligne, FR/EN) et
  `latency_ms` réel ajoutés à `evaluation/run.py::score()`/`aggregate()` —
  `refusal_rate_pct`, `latency_ms_mean`.
- **Regression testing** : `evaluation/reports.py::comparison()` expose
  désormais `regressions` — toute baisse >5pt sur un axe qualité, toute hausse
  >5pt du taux de refus, ou toute hausse de latence >10 %, même si un autre
  axe s'améliore le même run.
- **RAG evaluation** : `rag/evaluation.py`, Recall@K + MRR sur un jeu de
  requêtes étiquetées (`rag/eval_queries.jsonl`), audit complet par requête
  (chunks + scores). Retrieval seul, pas l'ancrage de la réponse finale.

## Enterprise (lot 3, 2026-09-15)

Audit préalable : le RBAC par projet (`viewer`/`operator`/`reviewer`/`admin`,
`project_members`, `require_project_role`) et le mode d'authentification par
proxy de confiance (`BISCUITS_AUTH_MODE=proxy`, en-têtes `x-biscuits-user-*`,
compatible Entra ID/Okta/Auth0 en amont) existaient déjà et couvrent l'essentiel
de F02. Ajouté sans casser de contrat existant :

- **Tool risk scoring typé** : colonne additive `tools.risk_level`
  (`low`/`medium`/`high`/`critical`, défaut `medium`). `evaluate_tool_policy`
  force `require_approval` pour tout outil `critical` même si une politique
  `allow` matche — seule une politique `deny` explicite reste prioritaire
  (garde déterministe, non contournable par la configuration).
- **SBOM / supply chain** : `GET .../registry/{item_id}/sbom` — provenance de
  la version (modèle, dataset, adapter, quantification, RAG, artefacts
  SHA-256 déjà trackés par le registre) + dépendances Python épinglées
  (`requirements.txt`).

Scopé en dehors de ce lot, avec justification (cf. section « Gouvernance des
outils et supply chain » du README) :

- **Multi-tenant Organization/Workspace** : l'isolation par projet + RBAC
  par projet couvre déjà le besoin solo/petite équipe ; ajouter une couche
  au-dessus serait spéculatif sans un vrai besoin multi-équipes observé.
- **Client OIDC natif** : le mode proxy délègue déjà l'authentification à une
  passerelle qui peut parler OIDC, évitant une dépendance lourde côté socle.
- **Secrets provider (Vault/Keyring)** : les secrets sont déjà référencés par
  nom de variable d'environnement, jamais stockés en clair — ajouter un client
  Vault sans utilisateur ni infra Vault réels serait de la sur-ingénierie.
- **ABAC fin** (conditions par attribut au-delà de outil/politique/risque) :
  aucun besoin concret identifié au-delà de ce que `tool_policies` couvre déjà.

## Ecosystem (lot 4, 2026-09-16)

- **API v1** : `/api/v1/*` reflète `/api/*` via une réécriture de chemin ASGI
  (`api/main.py::ApiV1AliasMiddleware`) exécutée avant le routage — aucun
  endpoint dupliqué, tout endpoint futur est automatiquement disponible sous
  les deux préfixes. `/api/*` reste inchangé (contrat préservé pour la
  console web). Limite documentée dans le README : le schéma OpenAPI garde
  la forme `/api/*`.
- **SDK Python / TypeScript** : pas de package maintenu à la main — le schéma
  OpenAPI déjà exposé permet la génération d'un client typé avec un outil
  standard. `sdk/python/quickstart.py` et `sdk/typescript/quickstart.ts`
  couvrent la seule partie non déductible par génération : le contrat des
  en-têtes d'authentification. Testés en conditions réelles contre un serveur
  local (`uvicorn` + script), pas seulement en `pytest`.
- **Intégrations Hermes / SWEET / Anti-Pépins** : non implémentées, faute de
  toute spécification d'API pour ces produits dans ce dépôt — en fabriquer une
  serait de la pure invention. Documenté comme bloqué dans le README plutôt
  que silencieusement ignoré.

### Corrections de sécurité (revue automatique post-commit/push)

Deux failles réelles remontées par la revue de sécurité automatique ont été
corrigées avant la suite du lot 4, tests de non-régression inclus :

- **Path traversal** — `GET .../experiments/compare?ids=...`
  (`api/routes/experiments.py`) construisait un chemin fichier directement à
  partir d'`ids`, sans validation. Corrigé par un motif regex sur l'identifiant
  (même motif que `scripts/dataset_versions.py::_SAFE_VERSION`) plus une
  vérification que le chemin résolu reste dans `experiments/` (défense en
  profondeur, même schéma que `restore_project`).
- **Contournement d'isolation entre projets** —
  `POST .../opportunities/{id}/analyze` (`api/routes/opportunities.py`)
  n'exigeait qu'un rôle global `operator`, jamais une appartenance au projet
  ciblé par `project_id` dans le corps de la requête, alors que cet endpoint
  utilise le fournisseur IA (et le secret référencé) de ce projet. Un
  opérateur d'un projet A pouvait ainsi consommer le fournisseur d'un projet B
  dont il n'est pas membre. Corrigé en ajoutant
  `store.require_project_role(body.project_id, current, "operator")` avant
  tout accès aux données du projet ciblé.

Audit de suivi (autonome, même classe de vulnérabilités puis §23 plus
largement) sur le reste des routes — quatre failles pré-existantes
supplémentaires trouvées et corrigées, non signalées par la revue automatique.
Le motif de validation appliqué aux trois failles de path traversal est
documenté comme convention durable dans
[ADR-0007](adr/0007-filesystem-identifier-validation-pattern.md) :

- **Path traversal sur la catégorie de dataset** —
  `GET/POST/PUT/DELETE .../dataset/{category}...` (`api/routes/dataset.py`)
  ne validait `category` que par `path.exists()`, sans motif ni vérification
  de confinement : `category=../../../etc` (ou toute autre valeur qui résout
  hors de `datasets/`) permettait de lire, écrire ou supprimer des fichiers
  `*.jsonl` en dehors du projet. Corrigé par le même motif que les autres
  identifiants filesystem de ce dépôt (`_SAFE_CATEGORY`) plus une vérification
  que le chemin résolu reste dans `datasets/`.
- **Path traversal sur la config d'entraînement** —
  `POST .../training/start` et `.../training/pipeline`
  (`StartTrainingRequest`/`StartPipelineRequest.config_filename`) étaient un
  `str` sans validation, concaténé dans un chemin puis passé tel quel à un
  sous-processus d'entraînement réel (`training/scripts/train.py`,
  `scripts/run_pipeline.py`). Corrigé par une contrainte `Field(pattern=...)`
  au niveau du schéma Pydantic — la valeur ne peut plus contenir `/` du tout,
  fermant la faille avant même d'atteindre `api/jobs.py`.
- **Path traversal sur `project_id`, y compris sur `DELETE` (`shutil.rmtree`)** —
  `api/paths.py::project_dir`, la dépendance partagée par quasiment toutes les
  routes de projet (dataset, RAG, training, evaluation, chat, enterprise,
  experiments…), ne validait `project_id` que par `path.exists()`. Un segment
  d'URL unique décodé en `..` (`%2e%2e`, atteignable car Starlette route sur
  le chemin brut mais décode chaque segment individuellement — un `/` littéral
  ou encodé change le nombre de segments et ne traverse donc pas ce chemin)
  atteignait le handler. Plus grave : `DELETE .../projects/{project_id}`
  dupliquait le même join non validé (`PROJECTS_DIR / project_id`) au lieu de
  réutiliser `project_dir()`, juste avant un `shutil.rmtree()` — une écriture
  destructive. Corrigé par le même motif que les autres identifiants de ce
  dépôt (`_SAFE_PROJECT_ID`, identique au `ID_PATTERN` déjà appliqué à la
  création de projet) plus une vérification de confinement dans
  `project_dir()`, et en faisant réutiliser cette dépendance par
  `delete_project` au lieu de dupliquer la logique.
- **Déni de service par expansion d'entités XML (« billion laughs ») sur les
  DOCX importés** — `rag/ingest.py::_extract_docx_text` parsait
  `word/document.xml` d'un `.docx` envoyé par l'utilisateur
  (`POST .../rag/documents/upload`) avec `xml.etree.ElementTree`, qui résout
  les entités internes déclarées en DTD ; confirmé en pratique qu'une entité
  personnalisée est bien résolue à l'analyse. Un DOCX conçu avec un
  `<!DOCTYPE>` à entités récursives (« billion laughs ») pouvait donc épuiser
  la mémoire/CPU du serveur au moment de l'import — un document malveillant au
  sens de CLAUDE.md §23. Corrigé en rejetant tout DOCX dont le XML contient un
  `<!DOCTYPE` avant analyse (un vrai `word/document.xml` n'en déclare jamais) —
  ferme à la fois ce vecteur et l'injection d'entité externe (XXE), sans
  ajouter de dépendance de parseur XML durci.

## Prochain lot prioritaire

Aucun — les 4 lots de la feuille de route (CLAUDE.md §28) sont couverts, dans
les limites explicitement documentées ci-dessus à chaque étape. Prochaines
étapes envisageables uniquement si un besoin concret apparaît : Model
Playground, OpenTelemetry, multi-tenant Organization/Workspace, client OIDC,
provider Vault/Keyring, intégrations Hermes/SWEET/Anti-Pépins dès que leurs
spécifications existeront.

Les politiques prévues concernent les permissions d'accès et l'exécution des
outils. Aucun contrôle de contenu médical n'est réintroduit.
