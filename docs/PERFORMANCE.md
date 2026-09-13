# Optimisations du plan de contrôle

Les lectures individuelles des outils et approbations utilisent leur identifiant
et le projet directement en SQL. Elles ne chargent plus le catalogue ou
l’historique entier. La décision de politique ne charge que les règles actives
applicables à l’outil. Aucun cache de décision ne retarde les modifications.

Des index couvrent les historiques par projet et date, les règles par cible,
l’audit par projet et les outils par connecteur. Les connexions SQLite sont
fermées explicitement après commit ou rollback. Le mode WAL est configuré lors
de l’initialisation. La synchronisation MCP utilise un ensemble pour tester
l’appartenance des identifiants importés.

## Mesure reproductible

Depuis la racine de l’application :

```bash
PYTHONPATH=. .venv/bin/python scripts/benchmark_enterprise.py
```

Le script crée une base temporaire de 10 000 approbations et compare l’ancienne
recherche dans toute la liste à la lecture ciblée, en vérifiant l’égalité des
résultats. Il n’utilise pas les données utilisateur.

Mesure locale du 13 septembre 2026, médiane de 15 lectures :

| Lecture d’une approbation | Durée |
|---|---:|
| Recherche dans l’historique complet | 43,769 ms |
| Requête ciblée | 0,331 ms |

Le gain de 132,2× concerne cette opération et ce jeu synthétique uniquement.
Il ne mesure ni la génération du modèle ni la latence globale de l’application.
La machine, la taille des données et le cache disque influencent les résultats.
