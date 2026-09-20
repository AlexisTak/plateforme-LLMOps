# Decision Models

Une primitive LLMOps générique, au même niveau que Generation/Embedding/Reranker :
au lieu de générer du texte libre, un Decision Model reçoit une entrée et retourne
une décision parmi un ensemble fermé, avec un score de confiance optionnel.

```json
{"decision": "billing", "confidence": 0.94}
```

## Quand l'utiliser

- Routage de tickets, d'intentions, d'emails
- Sélection d'outil/agent (tool routing) dans un système multi-agents
- Toute tâche de classification structurée à faible latence

## Architecture

Un Decision Model est un `Project` avec `model_kind="decision"` — il réutilise
le pipeline LoRA/QLoRA, le job runner, le dataset versioning et le model registry
existants (`Project.project_type` reste orthogonal : il ne choisit que le
template de dataset "générique").

Choix technique (délibéré, voir `decision/gateway.py`) : le training reste sur
le moteur `CAUSAL_LM` existant — un Decision Model est un modèle de *génération*
fine-tuné pour toujours produire `{"decision": ..., "confidence": ...}` en JSON.
Aucune tête de classification (`SEQ_CLS`) séparée n'a été ajoutée, pour ne pas
dupliquer le moteur de training (mission §22). La contrainte de sortie et la
validation stricte se font côté Decision Gateway (`decision/gateway.py`), pas
côté training.

- `decision/schema_store.py` — le `DecisionSchema` du projet (`decision/schema.json`)
- `decision/dataset.py` — dataset labellisé (`decision/dataset/{train,validation,test}.jsonl`), validation et stats
- `decision/metrics.py` — accuracy/precision/recall/F1/matrice de confusion/invalid_output_rate
- `decision/gateway.py` — inférence contrainte, validation stricte de la sortie, fallback
- `api/routes/decision.py` — endpoints REST, sous `/api/projects/{id}/decision/...`

## Créer un Decision Model

1. `POST /api/projects` avec `model_kind: "decision"` — crée le projet et son squelette `decision/`
2. `PUT /api/projects/{id}/decision/schema` — définit les décisions autorisées
3. Alimenter le dataset via `POST /api/projects/{id}/decision/dataset` (ou l'UI `/decision-models`)
4. `GET /api/projects/{id}/decision/dataset/validate` puis `.../stats` avant training
5. Entraîner via les endpoints `training` existants (le prompt système du projet contraint déjà la sortie JSON)
6. `POST /api/projects/{id}/decision/evaluate` — calcule les métriques et enregistre une entrée `model_versions` (draft) avec les métriques dans `artifacts`
7. Approuver/déployer via le registry existant (`api/routes/enterprise.py` — `draft → evaluated → approved → production`)
8. Appeler `POST /api/projects/{id}/decision/infer` (le Decision Gateway) en production

## Fallback

`PUT /api/projects/{id}/decision/fallback` configure un projet de secours
(`fallback_project_id`, autre Decision Model) appelé quand la confiance du
modèle primaire est sous le seuil configuré. Reste optionnel et auto-hébergé —
pas de dépendance à un fournisseur propriétaire.

## Exemples

### 1. Ticket classification
Schema : `{name: "Ticket Router", decisions: ["billing","technical","sales","spam"]}`.
Dataset : messages clients → décision. Fallback vers l'assistant généraliste du projet en cas de confiance faible.

### 2. AI Agent Tool Routing
Schema : `{name: "Tool Router", decisions: ["search","calculator","code_exec","none"]}`.
Utilisé en amont d'un agent pour choisir l'outil à invoquer sans coût d'un LLM généraliste à chaque tour.
