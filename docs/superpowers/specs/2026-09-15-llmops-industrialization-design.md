# Industrialisation LLMOps — Audit, Gap Analysis, Architecture cible

**Statut :** Lots 1, 2 et 3 livrés (voir `docs/OPENAGENT_SPEC_MAPPING.md` pour
le détail par lot, y compris les scopes explicitement écartés). Lot 4
(Ecosystem) reste à faire.
**Contexte :** Fait suite à la mission CLAUDE.md §1 (control plane local et souverain pour le cycle de vie des modèles IA).

## 1. Ce que le repository appelle "Biscuits Focus"

Le `pyproject.toml` déclare le package `biscuits-focus`, mais le code et l'API
(`api/main.py`) s'auto-décrivent encore comme **OpenAgent** (titre FastAPI,
docstrings, README). Il s'agit du même produit à deux noms — aucune
réécriture n'est nécessaire, mais toute nouvelle documentation doit assumer
que "Biscuits Focus" est le nom cible et "OpenAgent" une dénomination legacy
qui survit dans le code existant (ne pas la renommer en masse : hors périmètre
de cette mission, risque de diff massif inutile).

## 2. Audit — état réel du code (pas la doc)

| Domaine | Fichiers clés | État constaté |
|---|---|---|
| Control plane | `api/main.py`, `api/enterprise.py` (793 lignes), `api/routes/enterprise.py` (521 lignes) | FastAPI + SQLite (`.enterprise/control-plane.db`), middleware d'audit + RBAC (`viewer/operator/reviewer/admin`), mode `local` ou `proxy` (en-têtes SSO) |
| Projects (= Workspace/Project actuel) | `api/routes/projects.py`, `api/paths.py` | Isolation totale par projet (dataset/RAG/models/experiments par répertoire), pas de niveau Organization/Workspace au-dessus |
| Dataset | `api/routes/dataset.py`, `scripts/prepare_dataset.py`, `scripts/validate_dataset.py` | CRUD JSONL par catégorie, validation, dédup, split train/val/test. **`data/VERSION` est un simple fichier texte écrasé à chaque `prepare()`** : aucune immutabilité, aucun SHA-256 de version, aucun diff entre versions |
| Experiment tracking | `api/routes/experiments.py`, `training/scripts/train.py`, `api/schemas.py::ExperimentResult` | Chaque run écrit `experiments/<id>.json` (base_model, lora config, loss, VRAM, taille adapter, dataset_version). Lecture seule, **pas de commit Git, pas de comparaison multi-expériences, pas de SHA d'artefact dans ce fichier** (le SHA existe ailleurs, côté évaluation) |
| Model registry | `api/enterprise.py` table `model_versions`, `api/routes/enterprise.py` `/registry` | Workflow réel : `draft → evaluated → approved → production → archived`, avec garde-fous (benchmark requis avant approbation, séparation créateur/approbateur en mode proxy, rollback `archived → production` supporté). **Champs manquants vs spec** : adapter, quantification, version RAG, config prompt, artefacts, environnement |
| Provenance | `evaluation/reports.py::fingerprint/capture_metadata` | **Déjà solide** : SHA-256 + taille + mtime de `benchmark.jsonl`, `system_prompt.txt`, `meta.json`, tous les fichiers `data/*/*.jsonl`, `adapter_config.json` et `adapter_model.safetensors`. Détecte le "stale" (rapport périmé) et calcule des deltas de score entre rapports comparables |
| Evaluation | `evaluation/run.py`, `evaluation/reports.py`, `api/routes/evaluation.py` | Contrat texte naturel (`plain-text-v1`), contrôles automatiques (format/concision/refus) + grille de revue humaine explicite, historique archivé (`evaluation/history/`), comparaison auto avec rapport précédent si comparable. **Pas d'axes hallucination/grounding/safety/latence séparés, pas de test de régression bloquant** |
| RAG | `rag/index.py`, `rag/retriever.py`, `rag/context_builder.py`, `api/routes/rag.py` | Chroma persistant par projet, embedding `multilingual-e5-small` choisi via comparaison documentée (`rag/compare_embeddings.py`, 91.7% top-1), anti-injection testé (`tests/test_rag_injection.py`). Endpoint `/rag/search` renvoie chunks + scores. **Pas de Recall@K/MRR en continu, pas de vue "question → chunks → scores → contexte → réponse" dans l'UI** |
| Model Playground | `web/src/app/chat/page.tsx` (225 lignes) | Un seul modèle/adapter à la fois, streaming SSE, RAG optionnel. **Pas de comparaison côte-à-côte A/B/Production** |
| MCP / Tool governance | `api/enterprise.py` tables `tools`/`tool_policies`/`approvals`/`mcp_servers` | **Déjà solide** : politiques allow/deny/require_approval par priorité déterministe (deny prioritaire), import MCP restreint aux outils annotés `readOnlyHint`, timeout + limite d'octets par outil, audit de chaque décision. Pas de "risk level" explicite (LOW/MEDIUM/HIGH/CRITICAL) ni de distinction lecture/écriture typée |
| Secrets | `api/routes/enterprise.py::test_provider`, `_mcp_client` | Référencement par nom de variable d'environnement (`api_key_env`), jamais la valeur stockée en base. Pas d'abstraction Vault/Keyring — juste `os.getenv`, suffisant pour le MVP local |
| Supply chain | `api/routes/enterprise.py::backup_project` | Backup ZIP avec manifeste SHA-256 par fichier. Pas de SBOM, pas de restore |
| Multi-tenant | — | Un seul niveau : Project. Pas d'Organization/Workspace. RBAC vérifié côté serveur (`require_project_role`), jamais côté frontend seul — bon réflexe déjà en place |
| API | `api/main.py` (routers inclus) | Routes `/api/...` et `/api/enterprise/...`, pas de préfixe `/v1/` |
| Observability | `api/enterprise.py::Metrics`, `/api/enterprise/metrics/prometheus` | Compteurs RED (requests_total, status_2xx/4xx/5xx, latence p95), `x-request-id` propagé et loggé, export Prometheus texte. Pas d'OpenTelemetry, pas de traces de retrieval/LLM/tool en span structuré (mais `trace_events` par exécution existe déjà, voir Executions) |
| Executions / traces LLM | `api/enterprise.py` tables `executions`/`trace_events` | Chaque appel chat trace model/adapter/RAG utilisé/durée/tokens estimés + timeline d'événements, export JSON versionné par exécution. C'est une forme d'observability applicative déjà bonne |
| Resource tracking | `executions.estimated_tokens`, `experiments/*.json::peak_vram_mb` | Tokens estimés par exécution, VRAM pic par run d'entraînement. Pas de budgets configurables, pas d'agrégation GPU-heures |
| Docker | — | **Absent** — aucun Dockerfile, aucun docker-compose.yml |
| Backup/Restore | `backup_project` | Backup = **oui**. Restore = **absent** (aucun endpoint, aucune procédure documentée ou testée) |
| Tests | `tests/*.py` (14 fichiers), marker `gpu` | Bonne couverture ciblée : contrat dataset, jobs, enterprise, injection RAG, MCP, perf enterprise store. Pas de tests dédiés dataset-versioning/experiment-comparison/backup-restore car les features n'existent pas encore |
| CI/CD | — | Un commentaire dans `pyproject.toml` référence Jenkins mais aucun `Jenkinsfile` n'est versionné dans ce repo (pipeline externe, hors périmètre) |

## 3. Gap Analysis

| Domaine | Existe | Partiel | Manquant | Risque si non traité | Priorité |
|---|---|---|---|---|---|
| Dataset versioning | | ✅ (VERSION string) | Immutabilité, SHA-256, diff, historique | Une régression de dataset est indétectable a posteriori ; un modèle en production devient non reproductible | Haute |
| Experiment tracking | ✅ (JSON par run) | | Comparaison multi-expériences, commit Git, endpoint API de comparaison | Difficile de justifier pourquoi une config a été retenue | Haute |
| Model registry | | ✅ (workflow + SQLite) | Champs adapter/quantization/RAG version/environnement | Une version "production" ne dit pas tout ce qui la compose | Haute |
| Provenance | ✅ (fingerprint SHA-256 éval) | | Chaîne complète Git→Dataset→Training→Adapter→RAG→Deployment en un seul objet consultable | Traçabilité dispersée entre plusieurs fichiers | Moyenne |
| Evaluation | ✅ (texte + historique) | | Axes séparés (hallucination/grounding/safety/latence), régression bloquante | Une amélioration peut masquer une régression critique | Moyenne |
| Regression testing | | | ✅ manquant (delta calculé mais non bloquant) | Déploiement d'une régression silencieuse | Moyenne |
| RAG evaluation | | ✅ (comparaison embeddings offline) | Recall@K/MRR continus, vue auditable par requête | Qualité RAG jugée à l'œil | Moyenne |
| Playground | | ✅ (chat mono-modèle) | Comparaison A/B/Production | Décision de mise en prod moins informée | Basse |
| MCP governance | ✅ (policies+approval+audit) | | Risk level typé, séparation read/write explicite | Cosmétique — le déterminisme existe déjà | Basse |
| Secrets | ✅ (référence par env var) | | Abstraction Vault/Keyring optionnelle | Faible tant que mono-poste | Basse |
| Supply chain | | ✅ (backup SHA-256) | SBOM, manifeste de déploiement complet | Faible en local-first | Basse |
| Multi-tenant | | ✅ (Project + RBAC serveur) | Organization/Workspace | Non bloquant pour un MVP entreprise mono-organisation | Basse |
| API v1 | | ✅ (`/api/...`) | Préfixe `/v1/` versionné | Cassera un contrat si on migre plus tard sans plan | Basse |
| Observability | ✅ (RED + request-id + traces exécution) | | OpenTelemetry structuré | Le custom actuel suffit au MVP | Basse |
| Resource tracking | ✅ (tokens estimés, VRAM pic) | | Budgets configurables | Non bloquant | Basse |
| Docker | | | ✅ manquant | Onboarding DSI plus lent, pas de démo reproductible en une commande | Haute |
| Backup/restore | ✅ (backup) | | Restore | Un backup non restaurable n'est pas un backup (CLAUDE.md §22) | Haute |

## 4. Architecture cible

L'architecture actuelle (`Project` isolé contenant dataset/RAG/experiments/models)
correspond déjà à la hiérarchie cible `Project → {Dataset, Experiments, Models,
RAG, Agents, Tools, Deployments}` de la mission. Il n'y a **pas besoin de
réécrire cette base** : on ajoute une couche `Organization/Workspace`
au-dessus uniquement si le Lot 3 (Enterprise) est atteint — inutile de
l'anticiper maintenant (YAGNI).

Chaîne de provenance cible, construite en enrichissant l'existant plutôt qu'en
le remplaçant :

```
Git commit (déjà capturable, jamais stocké)
   -> Dataset version (SHA-256, à créer — Lot 1)
   -> Training config + Experiment (déjà tracé, à enrichir — Lot 1)
   -> Adapter (déjà fingerprinté par evaluation/reports.py)
   -> Evaluation report (déjà versionné avec SHA-256 — existant)
   -> RAG index (à fingerprinter — Lot 2)
   -> Model registry entry (à enrichir avec tous les SHA ci-dessus — Lot 1)
   -> Deployment manifest (existe déjà : /api/enterprise/projects/{id}/deployment)
```

## 5. Découpage en lots (rappel CLAUDE.md §28-29)

**Lot 1 — proposé pour cette session :**
1. Dataset versioning immuable (snapshots SHA-256 + diff), sans casser `data/VERSION`/`prepare()` existants (ajout, pas remplacement)
2. Experiment comparison endpoint (réutilise `experiments/*.json` existant, ajoute Git commit + comparaison)
3. Model registry enrichi (ajout de colonnes SQLite via migration additive : adapter, quantization, rag_version, artifacts)
4. Backup **restore** réel + test de restauration réelle
5. Docker Compose (API + web) avec healthchecks, sans casser le mode local sans Docker

Lots 2 à 4 : inchangés par rapport au prompt (LLMOps, Enterprise, Ecosystem), traités dans des sessions ultérieures une fois le Lot 1 stable et revu.

## 6. Risques identifiés pour le Lot 1

- **Migration SQLite additive uniquement** : `ALTER TABLE model_versions ADD COLUMN` (pattern déjà utilisé dans `_initialize()` pour `tools`) — jamais de `DROP`/`RENAME`, préserve les lignes existantes.
- **`data/VERSION` reste le contrat actuel** consommé par `training/routes.py`, `evaluation/reports.py`, `api/routes/enterprise.py::create_version` — le nouveau système de versioning s'ajoute à côté (snapshots dans `data/versions/<sha>/`), il ne remplace pas ce fichier tant que les consommateurs existants n'ont pas été migrés explicitement.
- **Docker ne doit pas devenir obligatoire** : `start.sh`/`start.ps1` restent la voie principale documentée ; `docker compose up` est une option supplémentaire.
- **Restore doit être testé réellement** (CLAUDE.md §22) : test d'intégration qui backup un projet, le restaure sous un autre id, et vérifie l'égalité des fichiers.
