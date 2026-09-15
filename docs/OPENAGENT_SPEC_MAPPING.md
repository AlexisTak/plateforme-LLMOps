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

## Prochain lot prioritaire

4. Ecosystem : API v1 versionnée, SDK Python, SDK TypeScript.

Reporté (priorité basse, cf. gap analysis du lot 1) : Model Playground
(comparaison A/B/Production dans le chat) et OpenTelemetry — l'observabilité
RED + correlation ID + traces d'exécution déjà en place couvre le besoin MVP.

Les politiques prévues concernent les permissions d'accès et l'exécution des
outils. Aucun contrôle de contenu médical n'est réintroduit.
