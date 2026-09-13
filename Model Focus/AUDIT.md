# Audit — Biscuits Focus

**Date** : 2026-08-17
**Périmètre** : 6382 lignes — `api/`, `web/`, `training/`, `rag/`, `evaluation/`, `scripts/`
**Contexte** : outil local mono-utilisateur, pas de dépôt Git prévu, pas d'exposition réseau.

Chaque point est classé par **valeur réelle**, pas par facilité. Les constats
s'appuient sur le code et sur les résultats produits par le projet lui-même
(`evaluation/report_summary.json`, `experiments/*.json`), pas sur des suppositions.

---

## 1. Ce qui bloque la qualité du modèle

### 1.1 Le dataset est le plafond du projet — CRITIQUE

```
datasets/*/*.jsonl   117 exemples
data/train           91
data/validation      9
data/test            17
evaluation/benchmark 14 prompts
```

**Conséquence mesurable.** L'`eval_loss` qui départage `r=8` / `r=16` / `r=32` se
calcule sur **9 exemples**. Un écart de 0.1 correspond à un seul exemple qui bouge.
Le sweep compare du bruit, pas des configurations.

Même problème côté évaluation : avec une poignée de prompts par catégorie, une
seule réponse peut déplacer fortement un pourcentage. Aucune conclusion robuste
ne tient sans davantage de cas indépendants.

**Ordre de grandeur cible** : 800–1500 exemples d'entraînement pour un SLM
spécialisé, avec une validation d'au moins 80–100 exemples pour que la métrique
cesse d'être du bruit.

> Tant que ce point n'est pas traité, tout le reste (choix de `r`, hyperparamètres,
> quantization) optimise dans le vide.

### 1.2 `experiment_002` (r=8) produit 0 % de JSON valide

`report_summary.json` :

| Variante | JSON valide % | Concision % |
|---|---|---|
| base (sans LoRA) | 0.0 | 35.7 |
| experiment_001 (r=16) | 88.9 | 92.9 |
| **experiment_002 (r=8)** | **0.0** | 57.1 |
| experiment_003 (r=32) | 100.0 | 85.7 |

r=8 n'est pas « un peu moins bon » : il est **au niveau du modèle de base**, donc
le fine-tuning n'a rien transmis. Avec 91 exemples d'entraînement, r=8 n'a pas assez
de pas de gradient utiles pour capter le format de sortie.

**Action** : soit retirer `r=8` du sweep (gain : sweep 33 % plus rapide), soit
augmenter ses `epochs` et le retester une fois le dataset agrandi.

---

## 2. Bugs réels dans le code

### 2.1 Race condition dans `ModelManager.generate` — `api/model_manager.py:72`

`ensure_loaded()` protège le chargement avec `self._lock`, mais `generate()`
utilise ensuite `self._model` **en dehors** du verrou :

```python
def generate(self, message, adapter, system_prompt, max_new_tokens=200):
    self.ensure_loaded(adapter)     # <- verrouillé
    ...
    out = self._model.generate(...)  # <- PAS verrouillé
```

Deux requêtes `/api/chat` simultanées avec des adapters différents : la seconde
exécute `del self._model` + `torch.cuda.empty_cache()` pendant que la première
génère. Résultat : crash CUDA, ou réponse produite par le mauvais adapter.

**Correctif** : étendre le verrou à toute la méthode `generate` (les requêtes chat
sont déjà sérialisées de fait par le GPU, on ne perd rien en débit).

### 2.2 `evaluation/run.py` ignore silencieusement les nouveaux adapters — `evaluation/run.py:32`

```python
VARIANTS = [
    ("base (no LoRA)", None),
    ("experiment_001 (r=16)", ROOT / "models/adapters/experiment_001"),
    ("experiment_002 (r=8)", ...),
    ("experiment_003 (r=32)", ...),
]
```

Depuis que l'interface permet de créer des configs (`POST /api/training/configs`),
tout adapter produit par une nouvelle config est **absent de l'évaluation**, sans
aucun message d'erreur. On croit avoir évalué, on n'a rien évalué.

**Correctif** : découvrir les adapters sur disque, comme
`ModelManager.available_adapters()` le fait déjà (`api/model_manager.py:31`).

### 2.3 `report_summary.json` sans horodatage ni `dataset_version`

Exactement la classe de bug déjà corrigée sur `train.py` (le champ `dataset_version`
figé). Le dashboard affiche « Qualité par variante » sans qu'aucune information
n'indique à quels adapters ni à quel dataset ces chiffres correspondent.

Après un sweep, ces pourcentages décrivent les **anciens** adapters jusqu'à ce
qu'une évaluation soit relancée manuellement — et rien ne le signale.

**Correctif** : ajouter `generated_at`, `dataset_version` et le `mtime` de chaque
adapter dans le JSON ; l'interface affiche un avertissement « périmé » si un
adapter est plus récent que le rapport.

### 2.4 Validation de chemin incohérente sur le dataset — `api/routes/dataset.py:247`

`add_example` valide le nom de fichier :

```python
if not body.file.endswith(".jsonl") or "/" in body.file or "\\" in body.file:
    raise HTTPException(400, "file must be a bare *.jsonl filename")
```

`update_example` et `delete_example` prennent `file` depuis l'URL **sans aucune
validation**, puis font `cat_dir / file`.

**Sévérité réelle : faible** — l'API n'écoute que sur localhost, le CORS est
restreint à `http://localhost:3000`, et le convertisseur de chemin de Starlette ne
laisse pas passer `/` dans un segment. Ce n'est pas une faille exploitable dans
l'usage actuel. Mais l'incohérence est gratuite à corriger et deviendrait un vrai
problème le jour où l'API sort de localhost.

**Correctif** : extraire un helper `_safe_jsonl_path(category, file)`, sur le modèle
de `_safe_md_path()` qui existe déjà dans `api/routes/rag.py:47`.

---

## 3. Risques opérationnels

### 3.1 Absence de contrôle de version — risque accepté

Décision prise : pas de dépôt Git pour l'instant. Le risque reste réel et mérite
d'être nommé plutôt qu'ignoré :

`training/scripts/train.py:92` exécute `shutil.rmtree(output_dir)` dès que
`--resume` est passé. Le bouton « Entraîner » du dashboard passe `resume=true`.
Une erreur de `output_dir` dans un YAML supprime le dossier visé sans confirmation
et sans possibilité de récupération.

**Mitigation sans Git** : une sauvegarde datée du projet hors `models/` et `.venv`
(léger — le code fait quelques centaines de Ko), déclenchée par le job Jenkins
`archive` décrit plus bas.

### 3.2 Jobs perdus au redémarrage de l'API — `api/jobs.py:1`

Le registre est un `dict` en mémoire. C'est documenté et assumé, mais l'API s'est
arrêtée deux fois en séance et l'historique a disparu à chaque fois. Persister les
enregistrements terminés dans un `jobs.jsonl` représente ~20 lignes et rend le
dashboard fiable après un crash.

### 3.3 Couverture de tests

Un seul fichier : `tests/test_rag_injection.py`. Il est bon (il teste la **vraie**
génération, pas seulement le formatage du prompt) mais il charge le modèle 1B en
4-bit : il exige un GPU et dure plusieurs minutes.

Il n'existe donc **aucun test rapide** exécutable en intégration continue. Manquent
notamment, tous purement CPU et rapides :

- `scripts/validate_dataset.py` — règles de validation
- `scripts/prepare_dataset.py` — le split stratifié, et surtout **l'absence de fuite**
  entre `train` et `test`
- `rag/chunker.py` — découpage et chevauchement
- `evaluation/run.py::score` — les contrats de format et de concision

---

## 4. Fonctionnalités à ajouter — classées par valeur

| # | Fonctionnalité | Justification |
|---|---|---|
| **F1** | **Atelier de génération de dataset** : gabarit par catégorie, file d'attente d'exemples candidats, validation humaine une par une dans l'interface | Attaque le point 1.1, le seul qui plafonne la qualité. Plus de valeur que tout le reste réuni. |
| **F2** | **Évaluation automatique après un sweep + comparaison avec le rapport précédent** | Aujourd'hui entraîner et évaluer sont deux actions déconnectées : une régression passe inaperçue. Transforme le rapport en garde-fou. |
| **F3** | **Évaluation du RAG (recall@k)** | `evaluation/run.py:8` dit lui-même « hallucination: NOT evaluated — no RAG/retrieved context exists yet ». Le RAG existe désormais. Mesurable sans juge LLM : un prompt dont la réponse est dans un document connu, on vérifie que son `doc_id` remonte dans le top-k. |
| **F4** | **Flux « promouvoir un modèle »** : adapter → merge → GGUF → Ollama en une action | `models/merged/` et `models/quantized/` existent, `scripts/merge_adapter.py` et `scripts/build_ollama_model.py` aussi, mais rien dans l'interface ne les relie et aucun pointeur ne désigne le modèle retenu. La chaîne s'arrête au milieu. |
| **F5** | **Vue d'évaluation par exemple** : quel prompt a échoué, côte à côte entre variantes | Le dashboard affiche `report.md` brut. On voit le *quoi* (« 66.7 % »), jamais le *pourquoi*. |
| **F6** | **Persistance des jobs** | Voir 3.2. ~20 lignes. |
| **F7** | **Tests rapides + intégration continue Jenkins** | Voir 3.3 et `Jenkinsfile`. |
| **F8** | **Mesure des performances CPU seul** | Déjà identifié comme manquant dans `evaluation/performance.md`. Détermine si le modèle est utilisable sans GPU — question de faisabilité produit, pas de confort. |

---

## 5. Ce qui est solide

À ne pas casser en corrigeant le reste :

- **La séparation fine-tuning / RAG / mémoire utilisateur** est tenue partout, y
  compris dans les commentaires (`inference/assistant.py:1`). C'est la décision
  d'architecture la plus importante du projet et elle n'a pas dérivé.
- **Les défenses contre l'injection de prompt** sont réelles et testées à la
  génération, pas seulement dans le gabarit (`tests/test_rag_injection.py`,
  `USER_CONTEXT_FRAMING` dans `inference/assistant.py:28`).
- **Les commentaires documentent les pièges**, pas le code évident : ordre des
  routes FastAPI (`api/routes/dataset.py:7`), sémantique des checkpoints Hugging
  Face (`training/scripts/train.py:85`), invalidation du cache Chroma
  (`rag/retriever.py:45`). C'est ce qui a permis de retrouver les bugs vite.
- **Le débounce du réindexage** (`api/jobs.py:108`) traite un vrai problème de
  concurrence, pas un problème imaginaire.

---

## 6. Ordre d'exécution recommandé

1. **2.1 et 2.2** — deux bugs silencieux, petits, qui faussent les résultats
2. **F7** — les tests rapides d'abord, pour que la suite soit vérifiable
3. **F1** — agrandir le dataset : le vrai goulot d'étranglement
4. **F2 + F3** — pour que l'agrandissement du dataset devienne *mesurable*
5. **F4** — fermer la chaîne jusqu'à Ollama

Le reste est du confort et peut attendre.
