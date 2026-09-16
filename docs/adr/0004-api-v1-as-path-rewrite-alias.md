# ADR-0004 : `/api/v1` comme alias de réécriture de chemin, pas une deuxième API

**Statut :** Accepté (Lot 4, 2026-09-16)

## Contexte

CLAUDE.md §18 demande de « prévoir progressivement une API versionnée »
(`/api/v1/...`) tout en préservant la compatibilité avec les endpoints
existants (`/api/...`, consommés par la console web). Les routeurs FastAPI
existants déclarent chacun leur préfixe complet en dur (ex.
`APIRouter(prefix="/api/projects/{project_id}/dataset")`). Dupliquer chaque
route sous un second préfixe, ou réécrire tous les routeurs pour retirer
`/api` de leur préfixe et les monter deux fois, aurait touché une dizaine de
fichiers de routes et tous les tests qui montent ces routeurs directement
(`app.include_router(dataset.router)` sans préfixe externe) — un risque de
régression disproportionné pour ce que ça apporte tant qu'il n'existe pas de
second comportement réel à distinguer entre versions.

## Décision

`ApiV1AliasMiddleware` (`api/main.py`) est un middleware ASGI minimal placé
avant le routage : toute requête dont le chemin commence par `/api/v1/` voit
ce préfixe réécrit en `/api/` avant que FastAPI ne route la requête. Aucune
route n'est dupliquée, aucun routeur n'est modifié — `/api/v1/*` et `/api/*`
appellent exactement le même code, y compris les vérifications de rôle par
projet (vérifié par test : un accès refusé sur `/api/projects/...` l'est
identiquement sur `/api/v1/projects/...`). Le middleware est ajouté après le
middleware d'audit/observabilité existant pour s'exécuter avant lui (l'ordre
d'ajout via `add_middleware` détermine l'ordre d'exécution — le dernier
ajouté s'exécute en premier).

## Conséquences

- Tout endpoint actuel ou futur est automatiquement disponible sous les deux
  préfixes, sans effort supplémentaire ni risque d'oubli.
- Limite assumée : le schéma OpenAPI (`/openapi.json`) référence toujours les
  chemins sous leur forme `/api/*`, jamais `/api/v1/*`, puisque la réécriture
  se fait en dessous de la couche de génération de schéma de FastAPI. Un
  client généré à partir du schéma devra donc cibler `/api/*` (ou remplacer
  le préfixe lui-même) — documenté dans le README plutôt que masqué.
- Il n'existe aujourd'hui aucune divergence de comportement entre versions :
  le jour où `/api/v1` doit réellement se comporter différemment de `/api`
  sur un endpoint donné, ce routeur spécifique devra sortir de l'alias et
  être monté séparément — pas avant, pour éviter de maintenir deux
  implémentations sans second besoin réel.
