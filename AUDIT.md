# Audit complet — Biscuits Focus / OpenModels

**Date** : 2026-09-20
**Périmètre** : `api/`, `decision/`, `rag/`, `inference/`, `evaluation/`, `scripts/`, `training/`, `web/`, infra (Docker, scripts), dépendances, documentation, tests.
**État du dépôt au moment de l'audit** : branche `feat/local-login`, HEAD `af39106` (PR #8), working tree non commité contenant l'auth locale (`api/routes/auth.py`, `tests/test_auth.py`, `scripts/create_user.py`), la primitive Decision Models (`decision/`, `api/routes/decision.py`, `web/src/app/decision-models/`), la sidebar et le fix de la modale projet.
**Vérifications exécutées** : `pytest` (207 tests verts, hors marqueur `gpu`), `npm run lint`, `npm run build`, `tsc --noEmit` — tous au vert.

Sévérités : **critical** = exploitable / bloquant prod · **high** = à corriger avant tout déploiement non-local · **medium** = dette ou risque réel à planifier · **low** = hygiène.

---

## 1. Synthèse exécutive

Le projet est une console LLMOps cohérente et bien structurée pour son stade : architecture lisible (FastAPI + fichiers/SQLite, Next.js + design system maison), validation des chemins solide, SQL 100 % paramétré, aucun `shell=True`, aucun secret en dur, 207 tests backend isolés. Les fondations sont saines.

Les faiblesses sont concentrées sur trois axes :

1. **Autorisation incomplète** — le mode auth par défaut est ouvert (`local` = tout le monde admin), plusieurs routes GET n'exigent aucun acteur, et plusieurs routes enterprise ne vérifient pas l'appartenance au projet. Un déploiement « tel quel » hors localhost est exposé.
2. **Surface SSRF / exfiltration** via les outils, providers et MCP configurables par un admin de projet (URL libre, `api_key_env` = n'importe quelle variable serveur).
3. **Absence totale d'automatisation qualité** — pas de CI, pas de lint/format Python configuré, pas de couverture, pas de test frontend, pas de test e2e.

Aucun de ces points n'est structurel : ils se corrigent par des ajouts ciblés, sans refonte.

---

## 2. Sécurité

### 2.1 Authentification / autorisation

| Sév. | Constat | Localisation |
|---|---|---|
| **critical → corrigé** | `BISCUITS_AUTH_MODE` vaut `local` par défaut : tout appelant est `admin` sans authentification. Un serveur démarré sans la variable est intégralement ouvert. | `api/enterprise.py:53,66-67` |
| **high → corrigé** | Le middleware ne vérifie un acteur que pour les méthodes mutantes et pour le préfixe `/api/projects/{id}`. Toutes les autres routes GET sont accessibles sans session en modes `login`/`proxy` : `GET /api/jobs*` (logs stdout de tout projet), `GET /api/projects`, `GET /api/system/health` (GPU, disque, paquets), `GET /api/enterprise/metrics*`, `GET /api/enterprise/projects/{id}/registry`, `/sbom`, `/quota`, `/deployment` (expose le chemin de la DB). | `api/main.py:63-81`, `api/routes/jobs.py:81-106`, `api/routes/projects.py:131`, `api/routes/system.py:103`, `api/routes/enterprise.py:113-131,139,203,249,341` |
| **high → corrigé** | `POST .../registry` et `.../registry/{id}/transition` n'appellent que `require_role` (global), pas `require_project_role` : un operator du projet A peut créer/promouvoir des versions du projet B. | `api/routes/enterprise.py:144-176` |
| **medium** | `POST /api/jobs/{id}/stop` : operator global suffit, pas de vérification que le job appartient à un projet de l'acteur. | `api/routes/jobs.py:99` |
| **medium** | `DELETE /api/projects/{id}` : un simple `viewer` du projet (avec rôle global operator) peut supprimer un projet vide. | `api/routes/projects.py:193` |
| **medium** | Throttle login clé `(client.host, email)` : derrière un reverse proxy toutes les IP sont identiques → 5 tentatives verrouillent n'importe quel e-mail 15 min (DoS ciblé). | `api/routes/auth.py:64-66,119-121` |
| **medium** | Cookie `secure=` déduit de `request.url.scheme` : derrière un proxy TLS sans `--proxy-headers`, le cookie part sans `Secure`. `HttpOnly` + `SameSite=Lax` sont bien présents. | `api/routes/auth.py:88-92` |
| **low** | Secret proxy comparé avec `!=` au lieu de `secrets.compare_digest`. | `api/enterprise.py:80` |
| **low** | L'audit HTTP générique exclut `/api/enterprise/*` ; les routes y auditent manuellement — à vérifier une à une (`PUT /quota`, `PUT /budget`). | `api/main.py:88` |

### 2.2 SSRF / exfiltration / sorties réseau

| Sév. | Constat | Localisation |
|---|---|---|
| **high → corrigé** | `_provider_url` ne contrôle que le schéma `http(s)`. Tools, providers et MCP peuvent viser `127.0.0.1`, `169.254.169.254`, le réseau interne. `execute_tool` est ouvert à tout operator du projet avec arguments contrôlés → SSRF authentifié. Pas de blocage IP privées, redirections suivies. | `api/routes/enterprise.py:464-468,579` |
| **medium** | `api_key_env` accepte n'importe quel nom `^[A-Z][A-Z0-9_]{1,99}$` : un admin de projet peut faire envoyer `BISCUITS_PROXY_SECRET`, `BISCUITS_BOOTSTRAP_ADMIN_PASSWORD`, `AWS_*`… en `Bearer` vers une URL qu'il contrôle. | `api/routes/enterprise.py:63,98,507-518`, `api/ai_provider_client.py:32-39`, `api/mcp_client.py:44-48` |
| **medium → corrigé** | `max_response_bytes` est appliqué **après** `response.content` (téléchargement complet) — la limite mémoire n'est pas effective. Idem MCP. | `api/routes/enterprise.py:546,552-558` |
| ✅ | Timeouts présents sur tous les appels sortants (5 s test, 1-30 s tools, 10 s MCP, 60 s provider). | — |

### 2.3 Injection / traversal

| Sév. | Constat | Localisation |
|---|---|---|
| ✅ | Path traversal : `project_id`, `category` (dataset & RAG), `filename`, `config_filename`, `version`, `experiment_id`, `adapter`, restore ZIP — tous validés (regex + `resolve()` dans la racine attendue). Défense en profondeur correcte (ADR-0007). | `api/paths.py:23-32`, `api/routes/dataset.py:69-76`, `api/routes/rag.py:45-68`, `api/schemas.py:70,171-180`, `api/routes/chat.py:77`, `api/routes/enterprise.py:416-426` |
| ✅ | `subprocess` toujours en liste, jamais `shell=True`. Aucun `eval`/`exec`. SQL 100 % paramétré (les f-strings n'interpolent que des constantes internes). YAML via `safe_load`. | `api/jobs.py`, `api/enterprise.py:255,265,746`, `api/routes/training.py:42` |
| **low** | `StartPipelineRequest.dataset_version` / `StartSweepRequest.dataset_version` sont des `str` libres (pas de jointure de chemin, mais incohérent avec `PrepareDatasetRequest.version`). | `api/schemas.py:182,187` |

### 2.4 DoS / ressources

| Sév. | Constat | Localisation |
|---|---|---|
| **medium** | Aucune limite globale de taille de corps. `restore` et `upload_document` lisent tout en mémoire avant le contrôle de 150 Mo. `ToolExecute.arguments: dict` non borné. | `api/routes/enterprise.py:398`, `api/routes/rag.py:125`, `rag/ingest.py:33` |
| **medium** | Rate limiting uniquement sur `/login`. Le chat sérialise sur un `threading.Lock` GPU : quelques requêtes lentes bloquent tous les utilisateurs ; seul le budget agent limite. | `api/routes/chat.py:138,157`, `api/model_manager.py:128,160` |
| **low** | `job_metrics` charge tout `train_log.jsonl` en mémoire. | `api/routes/jobs.py:123` |
| ✅ | Pydantic borne les champs sensibles (chat 8000/12000, history ≤ 12, `max_new_tokens ≤ 1024`, `limit` audit ≤ 500). | — |

### 2.5 Divers

- **CORS** (`api/main.py:48-54`) : origines fixes `localhost:3000`, `allow_credentials=True`. Sûr mais non configurable → tout déploiement distant incite à mettre `*` à la main. **[low]**
- **Prompt injection RAG** : défense par instruction uniquement (`rag/context_builder.py:37,75`). Le test `test_rag_injection.py` est marqué `gpu` et télécharge un modèle 1B — jamais exécuté en pratique. **[low]**
- **Secrets** : aucun secret en dur, aucun `.env` tracké, bcrypt cost 12, sessions hashées SHA-256. ✅
- **PII dans l'audit** : e-mail en clair sur échec de login, `preview` 2000 caractères des réponses d'outils externes + arguments. **[medium]** (`api/routes/auth.py:125`, `api/routes/enterprise.py:560,596-597`)

---

## 3. Backend — qualité & architecture

| Sév. | Constat | Localisation |
|---|---|---|
| **medium** | **God-object** `api/enterprise.py` (1 109 lignes, 58 `Any`) : auth, sessions, audit chaîné, registry, quotas/budgets, membres, executions/traces, conversations, providers, tools, MCP, policies, ACL RAG, approvals, opportunités + KPIs + IA + seed, métriques HTTP. | `api/enterprise.py` |
| **medium** | Lecture de `meta.json` dupliquée 7× sans helper `read_meta(project)`. `generate` / `generate_stream` dupliquent ~15 lignes de construction de prompt. | `api/routes/{chat,training,enterprise,evaluation,projects}.py`, `api/model_manager.py:27,128-145,160-176` |
| **medium** | **Thread-safety** `generate_stream` : le lock est détenu dans un générateur ; à la déconnexion client, `GeneratorExit` libère le lock alors que le thread `model-stream` continue. Une requête suivante peut `del self._model` pendant la génération orpheline. Pas de cancellation. | `api/model_manager.py:96,160-197` |
| **low** | `job.stdout_lines` / `self._threads` mutés hors `_lock` ; `get()` sans lock. | `api/jobs.py:184-192,218` |
| **low** | `except: pass` masque toute erreur Chroma ; `pass` sur échec audit logout ; `except Exception` larges dans chat. | `rag/index.py:40-41`, `api/routes/auth.py:142-143`, `api/routes/chat.py:147,168,199` |
| **low** | `request: Request = None` (signature trompeuse). `BISCUITS_SESSION_TTL_SECONDS` → `int()` sans garde (ValueError au boot). | `api/routes/projects.py:138`, `api/enterprise.py:49` |
| **low** | Pas de config `logging` (niveau/format/rotation) ; `print()` dans `rag/*` et `inference/assistant.py:13`. | — |
| ✅ | Aucun TODO/FIXME. Type hints partout. Codes HTTP cohérents (400/403/404/409/502). | — |

### 3.1 Decision Models (ajout de cette session)

- Implémenté comme `model_kind="decision"` orthogonal à `project_type`, réutilisant registry/jobs/dataset versioning. Training resté sur `CAUSAL_LM` (contrainte de sortie au gateway, pas de tête `SEQ_CLS`). 19 tests dédiés.
- **[medium]** `decision/gateway.py` : `_run_once` appelle `manager.generate` sans `adapter` — il utilise toujours le modèle de base, jamais l'adapter entraîné. À brancher sur la version `production` du registry.
- **[medium]** `POST .../decision/evaluate` est synchrone (boucle sur tout le test set dans la requête HTTP). À basculer sur `api/jobs.py` comme `evaluation/run.py` dès que les datasets dépassent quelques dizaines d'exemples.
- **[low]** Pas de log `decision_logs` (request_id, input_hash, fallback…) : le monitoring §14/§18 de la spec n'est pas couvert ; les métriques passent uniquement par l'audit HTTP générique.
- **[low]** Le frontend ne permet pas encore de créer un projet `model_kind="decision"` (voir §4).

---

## 4. Frontend — `web/`

| Sév. | Constat | Localisation |
|---|---|---|
| **high → corrigé** | **Drift de types TS ↔ Pydantic** : `Project` et `CreateProjectParams` n'ont pas `model_kind` (exposé côté API). Impossible de créer un projet `decision` depuis l'UI. Aucune génération de types (`openapi-typescript`) — le drift se reproduira. | `web/src/lib/api.ts:179,203` vs `api/schemas.py:409,434` |
| **high → corrigé** | **Aucun framework de test** (pas de vitest/jest/playwright, pas de script `test`). Seuls « tests » : `console.assert` inline dans `command-palette.tsx:124-129` et `errors.ts:14-27`, non bloquants, embarqués dans le bundle dev. | `web/package.json` |
| **high → corrigé** | Modale de création de projet : pas de `role="dialog"`, `aria-modal`, `aria-labelledby`, ni fermeture Escape, ni focus trap. `ConfirmDialog` a role/aria mais pas Escape/focus trap non plus. | `web/src/components/project-switcher.tsx:80-83`, `ui.tsx:234-236` |
| **medium** | `dataset/page.tsx` : 552 lignes, 27 `useState`, mélange stats/upload/validation/dedup/liste/versions/2 dialogs. `rag` (433 l., 17 states) et `training` (432 l., 25 states) proches. | `web/src/app/{dataset,rag,training}/page.tsx` |
| **medium** | `api.ts` : 628 lignes, 76 types, 118 endpoints dans un fichier plat. | `web/src/lib/api.ts` |
| **medium** | 5 boucles `setInterval` écrites à la main (toutes nettoyées, aucune ne suspend sur `visibilitychange`). Dashboard (5 s) et Training (3 s) pollent **en permanence** même sans job. Pattern « fetch + catch + loaded » recopié ~12×. | `page.tsx:63`, `training/page.tsx:73,150`, `rag/page.tsx:70`, `benchmarks/page.tsx:61`, `health-badge.tsx:13` |
| **medium** | `training/page.tsx:57,66` : promesses sans `.catch` → unhandled rejection toutes les 3 s si l'API tombe. Dashboard : 5 `.catch(() => {})` muets → zéros silencieux. | `web/src/app/{training,}/page.tsx` |
| **medium** | `localStorage` sans `try/catch` dans le provider racine (Safari privé / storage désactivé → crash de toute l'app). `chat/page.tsx` le fait pourtant. | `web/src/lib/project-context.tsx:29,40,43` |
| **medium** | Pas de `Skeleton`/`loaded` sur dashboard, chat, settings, decision-models, opportunities/[id]. `executions` rend tous les items sans pagination. | — |
| **medium** | ~75 champs `Input/Select/Textarea` pour ~20 `label`/`aria-label` : majorité sans label associé. | pages |
| **low** | 5 `eslint-disable-line react-hooks/exhaustive-deps` (symptôme de `refresh` non mémoïsé). `<button>` sans `type` (×10). `suppressHydrationWarning` sur `<body>` non documenté. `NEXT_PUBLIC_API_URL` dupliqué dans `api.ts:1` et `errors.ts:7`. | — |
| ✅ | `strict: true`, aucun `any`, aucun `@ts-ignore`, aucun `dangerouslySetInnerHTML`. Pile `ApiError → humanError → useAction → toast` bien conçue. `command-palette.tsx` : clavier + a11y corrects. | — |

---

## 5. Infrastructure, build, dépendances

| Sév. | Constat | Localisation |
|---|---|---|
| **high → corrigé** | **Aucune CI** (pas de `.github/workflows`, ni GitLab, ni Jenkinsfile malgré la mention dans `pyproject.toml`). Les 207 tests ne tournent jamais automatiquement. | racine |
| **high → corrigé (ruff)** | **Aucun outillage qualité Python** : pas de `ruff`/`mypy`/`black`/`pre-commit` configuré (un `.ruff_cache` existe → lancé à la main). Côté web : `eslint` seul, pas de `tsc --noEmit` dans un script. | `pyproject.toml` |
| **medium** | Dockerfile API : `python:3.11-slim` (épinglé ✅), HEALTHCHECK ✅, pas de `--reload` ✅ — mais **tourne en root**, et le commentaire « never ships torch » est faux : `requirements.txt` tire `transformers/peft/trl/bitsandbytes/sentence-transformers` → torch CPU installé (plusieurs centaines de Mo). Pas de split `requirements-api` / `requirements-train`. | `Dockerfile`, `requirements.txt` |
| **medium** | `docker-compose.yml` : aucune `restart:` policy, `BISCUITS_PROXY_SECRET` vide par défaut, API exposée `0.0.0.0:8000`. `web/Dockerfile` root aussi. | `docker-compose.yml`, `web/Dockerfile` |
| **medium** | `requirements.txt` : 113 lignes 100 % épinglées (bien) mais `torch` uniquement en commentaire (aucune contrainte de version dans le repo) ; deps lourdes transitives figées et jamais importées : `kubernetes`, `onnxruntime`, `opentelemetry-*` (×6), `grpcio`, `pyarrow`, `pandas`, `scipy`, `scikit-learn`. `pytest` mélangé au runtime. | `requirements.txt` |
| ✅ | Imports ML paresseux : `api/routes/rag.py` n'importe que `rag.retriever` (→ `rag.settings`), et `rag/chunker.py:15` (import module-level de `transformers`) n'est atteint que via `rag/index.py`, lui-même importé paresseusement dans `api/jobs.py:205`. `transformers`/`torch` ne sont **pas** chargés au démarrage de l'API. | `rag/chunker.py:15`, `api/jobs.py:205` |
| **low** | `start.sh` lance `uvicorn --reload`, `start.ps1` non (incohérence). Pas de `setup.ps1`. `pyproject` sans `[project.dependencies]` → non installable via `pip install .`. `requires-python` très strict (`>=3.11,<3.12`, justifié dans `docs/ENVIRONMENT.md`). | — |
| ✅ | Frontend : versions stables (Next 16.3.1, React 19.2.8), lockfile présent, `npm ci`, `output: standalone`, toutes les deps utilisées. Pas de `engines` dans `package.json`. | `web/package.json` |

---

## 6. Hygiène du dépôt

| Sév. | Constat |
|---|---|
| **high → partiel** | `Cahier_des_charges_OpenAgent_Enterprise.docx` (54 Ko) est dans l'historique git (supprimé dans le working tree, pas encore commité). Seul binaire tracké. |
| **medium** | `projects/assistant/**` (20 fichiers JSONL démo) est tracké et `.gitignore` racine n'ignore pas `projects/` → futurs adapters/modèles LoRA commités par accident. `.dockerignore` l'exclut, `.gitignore` non. |
| **medium → corrigé** | `.gitignore` racine minimal : manquent `.ruff_cache/`, `.run/` (pids + logs de `start.sh`), `.claude/`, `*.db`, `*.sqlite`, `projects/*/models`, `*.safetensors`, `*.gguf`, `.superpowers`, `.playwright-mcp`. |
| **low** | Pas de `.env.example` alors que `.gitignore` prévoit `!.env.example` et que compose consomme `BISCUITS_AUTH_MODE` / `BISCUITS_PROXY_SECRET`. `prompt.md` et `.claude/` non trackés à la racine (artefacts de session). |
| ✅ | Aucun secret tracké (`BEGIN PRIVATE`, `sk-`, `hf_`, `ghp_`, `AKIA` : 0 résultat). `.enterprise/`, `.jobs/` ignorés. 192 fichiers trackés. |

---

## 7. Documentation

| Sév. | Constat |
|---|---|
| **medium** | **Rebrand OpenAgent → OpenModels incomplet** : 15 occurrences dans 8 fichiers, dont `FastAPI(title="OpenAgent — Management API")` visible dans `/docs`, le titre du `README.md`, `docs/ENVIRONMENT.md`, `docs/OPENAGENT_SPEC_MAPPING.md` (nom de fichier inclus), `docs/OUTPUT_SCHEMA.json`. Trois noms coexistent (`OpenAgent`, `OpenModels`, `biscuits-focus` / `BISCUITS_*`). |
| **medium** | `README.md` (20 Ko) obsolète : 0 mention de Decision Models, de la sidebar, du mode auth `login` en cours ; la section « Console web » décrit encore le lancement manuel en 2 terminaux au lieu de `start.*`. |
| **medium** | Manquent : `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`, export statique `openapi.json` (prérequis d'ADR-0005 « pas de SDK manuel, générer depuis OpenAPI » — aucun script ne l'exporte). |
| ✅ | 7 ADR en français bien tenus (`docs/adr/0001…0007`), `OPENAGENT_SPEC_MAPPING.md` tient le suivi de couverture à jour, `DECISION_MODELS.md` ajouté, `DATASET_GUIDELINES.md`, `PERFORMANCE.md`, `RUNTIME_FIXES.md`. |

---

## 8. Tests

| Sév. | Constat |
|---|---|
| **high → corrigé** | **Aucun test des règles d'autorisation** (401/403) sur les routes listées en §2.1 — c'est précisément là que se trouvent les failles. |
| **medium** | Pas de couverture (`pytest-cov` absent). Pas de test e2e API + web, aucun test frontend, aucun test de charge (`test_enterprise_performance.py` est en réalité 3 tests unitaires sur les index SQLite). |
| **medium** | Modules sans test dédié : `api/routes/system.py`, `api/routes/jobs.py` (endpoints HTTP jamais appelés), `api/model_preflight.py`, `rag/chunker.py`, `rag/index.py`, `rag/retriever.py`, `inference/assistant.py`, `scripts/*` (sauf `dataset_versions`), `training/scripts/*`, `evaluation/quantization_report.py`. |
| **low** | `test_rag_injection.py` : `gpu` + téléchargement HF Hub → jamais exécuté en CI standard. `test_jobs.py` utilise `sleep(120)` dans un sous-processus (test de kill). |
| ✅ | 29 fichiers, 207 tests, isolation `.enterprise`/`.jobs` par session via `conftest.py`, mocks propres (`monkeypatch`) pour MCP/providers. |

---

## 9. Plan d'action priorisé

### Bloquants avant tout déploiement hors localhost
1. **Auth par défaut** : refuser de démarrer sans `BISCUITS_AUTH_MODE` explicite (ou défaut `login`). `api/enterprise.py:53`
2. **Middleware** : exiger un acteur `viewer` sur toutes les routes `/api/*` sauf `/api/auth/*`, `/api/health`, `/api/ready`. `api/main.py:63-81`
3. **Scope projet** : `require_project_role` sur registry POST/transition, quota, budget, jobs stop/metrics, GET registry/sbom/deployment.
4. **SSRF** : allowlist d'hôtes (ou blocage loopback/privé/link-local, avec exception Ollama configurée), `allow_redirects=False`, `stream=True` + lecture bornée. `api/routes/enterprise.py:464-468,552-558`
5. **`api_key_env`** : restreindre à un préfixe dédié (`BISCUITS_SECRET_*`).
6. **Tests d'autorisation négatifs** pour chaque route ci-dessus.

### Industrialisation (semaine suivante)
7. **CI GitHub Actions** : `pytest -m "not gpu"`, `ruff check`, `npm run lint && tsc --noEmit && next build`.
8. **Outillage** : `ruff` + `pre-commit` dans `pyproject.toml`, `requirements-dev.txt` (pytest, pytest-cov, ruff, mypy), `vitest` + testing-library côté web.
9. **Hygiène git** : committer la suppression du `.docx` (ou purger l'historique), étendre `.gitignore` (§6), ajouter `.env.example`.
10. **Docker** : `USER` non-root, `restart: unless-stopped`, scinder `requirements-api.txt` / `requirements-train.txt`, épingler `torch`.

### Dette technique
11. Générer les types TS depuis l'OpenAPI (`openapi-typescript`) et exporter `openapi.json` (ADR-0005) ; ajouter `model_kind` à `Project` / `CreateProjectParams` / modale de création.
12. Corriger `generate_stream` (cancellation à la déconnexion avant libération du lock). `api/model_manager.py:160-197`
13. Découper `api/enterprise.py` en stores thématiques ; factoriser `read_meta()` et la construction de prompt.
14. Frontend : `useJobPolling` / `useApiResource`, arrêt des pollings permanents, a11y des modales (Escape, focus trap, labels), `safeStorage`, Skeleton sur les pages qui n'en ont pas, découpage de `dataset/page.tsx`.
15. Decision Models : brancher le gateway sur l'adapter de la version `production`, passer `evaluate` en job asynchrone, ajouter `decision_logs`.
16. Docs : finir le rebrand, mettre à jour le README, ajouter `CONTRIBUTING.md` / `CHANGELOG.md` / `SECURITY.md`.

---

## 10. Corrections appliquées (2026-09-20, même session)

Tous les **high** et le **critical** ont été traités, sauf la purge d'historique git (action destructive laissée au propriétaire du dépôt). Vérifications après correction : backend **233 tests verts** (+27 : `tests/test_authorization.py`), `ruff check .` propre, web **16 tests** (vitest), `tsc --noEmit`, `eslint`, `next build` verts.

| Constat | Correction | Fichiers |
|---|---|---|
| Auth par défaut `local` | Défaut `login` ; `local` explicite dans `start.sh`/`start.ps1`/`tests/conftest.py` ; compose `${BISCUITS_AUTH_MODE:-login}` ; lectures directes de l'env remplacées par `auth_mode()` | `api/enterprise.py`, `api/routes/enterprise.py`, `docker-compose.yml`, `start.sh`, `start.ps1`, `tests/conftest.py` |
| GET sans acteur | Middleware : tout `/api/*` exige `viewer` (GET) / `operator` (mutations), sauf `/api/auth/*`, `/api/health`, `/api/ready` | `api/main.py` |
| Registry cross-projet | Middleware étendu à `/api/enterprise/projects/{id}/...` (membership `viewer`) + `require_project_role` `operator`/`reviewer` sur create/transition | `api/main.py`, `api/routes/enterprise.py` |
| SSRF tools/providers/MCP | Nouveau `api/outbound.py` : http(s) seul, pas d'identifiants dans l'URL, résolution DNS, refus loopback/privé/link-local/réservé sauf `BISCUITS_OUTBOUND_ALLOW_PRIVATE` (défaut `127.0.0.1:11434,localhost:11434` pour Ollama) ; validé à l'enregistrement **et** à l'exécution ; `allow_redirects=False` partout ; lecture streamée bornée (`read_capped`) | `api/outbound.py`, `api/routes/enterprise.py`, `api/ai_provider_client.py`, `api/mcp_client.py` |
| Tests d'autorisation | 27 tests négatifs : défaut `login`, 401 sur GET anonymes, 403 membership/rôle projet registry, policy sortante (adresses internes, allowlist, schémas, revalidation à l'exécution d'un outil enregistré) | `tests/test_authorization.py`, `tests/conftest.py` (stub DNS autouse) |
| Drift TS `model_kind` | `Project.model_kind`, `CreateProjectParams.model_kind`/`ollama_equivalent` ; sélecteur « Nature du modèle » dans la modale (force `output_mode=json` pour `decision`) | `web/src/lib/api.ts`, `web/src/components/project-switcher.tsx` |
| A11y modales | `role="dialog"`, `aria-modal`, `aria-labelledby`, focus initial, fermeture Escape sur la modale projet **et** `ConfirmDialog` ; `ui.tsx` marqué `"use client"` (hooks) | `web/src/components/project-switcher.tsx`, `web/src/components/ui.tsx` |
| Tests frontend | vitest + jsdom + testing-library ; scripts `test`, `test:watch`, `typecheck` ; `console.assert` migrés en vrais tests + tests `ConfirmDialog`/`StatusBadge`/`ConfusionMatrix` ; `@types/node` → `^22` (peer de vitest 5) | `web/package.json`, `web/vitest.config.mts`, `web/vitest.setup.ts`, `web/src/**/*.test.ts(x)` |
| CI | GitLab CI : ruff + pytest `-m "not gpu"` (torch CPU) et eslint + typecheck + vitest + build, plus scanners de sécurité. Le workflow GitHub Actions initial a été retiré : il ne démarrait jamais sur le dépôt GitHub privé | `.gitlab-ci.yml` |
| Lint Python | `[tool.ruff]` dans `pyproject.toml` (E, F, B, UP, I ; B008/E402/B904 ignorés avec justification) ; 65 autofix (tri d'imports, `datetime.UTC`) + 6 corrections manuelles | `pyproject.toml`, 12 fichiers |
| `.gitignore` | `.ruff_cache/`, `.run/`, `*.db`, `projects/*/models/`, poids de modèles, `*.docx`, artefacts de session | `.gitignore` |

**Reste à faire par le propriétaire du dépôt** : committer la suppression du `.docx` (déjà `D` dans le working tree) — la purge de l'historique (`git filter-repo`) est optionnelle et réécrit l'historique partagé. La CI n'a pas encore tourné (aucun push) : le job backend installe `requirements.txt` complet sur Ubuntu CPU, à surveiller au premier run (`bitsandbytes`).

**Non traité (medium, hors demande)** : `api_key_env` sans préfixe (exfiltration de variables serveur via un provider public), throttle login derrière proxy, cookie `secure`, jobs stop/metrics non scoped projet, taille de corps globale, `generate_stream` lock/cancellation, god-object `enterprise.py`, pollings permanents et découpage des pages front, README/rebrand.

## 11. Points à vérifier (non confirmés par l'audit)

- Les routes `/api/enterprise/*` exclues de l'audit HTTP générique auditent-elles toutes manuellement (`PUT /quota`, `PUT /budget`) ?
- Le travail d'auth locale non commité (`api/routes/auth.py`, `tests/test_auth.py`, `scripts/create_user.py`) a été audité dans son état actuel ; il doit être relu une fois finalisé.
