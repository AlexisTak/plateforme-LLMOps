# ADR-0005 : Pas de SDK maintenu à la main — génération OpenAPI + quickstarts d'auth

**Statut :** Accepté (Lot 4, 2026-09-16)

## Contexte

CLAUDE.md §28 (Phase 4) demande un « SDK Python » et un « SDK TypeScript ».
FastAPI expose déjà un schéma OpenAPI complet et à jour (`/openapi.json`) pour
l'ensemble des endpoints, y compris ceux ajoutés dans les lots précédents. Il
n'existe aujourd'hui aucun consommateur externe connu de cette API — la
console web (`web/src/lib/api.ts`) est le seul client, et c'est un client
interne au dépôt, pas un SDK public.

## Décision

Pas de paquet Python (`setup.py`/`pyproject.toml`) ni npm publié dans ce
dépôt pour l'instant. À la place, deux scripts minimaux et exécutables —
`sdk/python/quickstart.py` et `sdk/typescript/quickstart.ts` — montrent la
seule chose qu'un outil de génération de client à partir du schéma OpenAPI
(`openapi-python-client`, `openapi-typescript`, etc.) ne peut pas déduire : le
contrat des en-têtes d'authentification (`api/enterprise.py::
actor_from_request` — rien en mode `local`, quatre en-têtes `x-biscuits-*` en
mode `proxy`). Chaque quickstart a été exécuté contre un serveur réel
(`uvicorn` local), pas seulement vérifié par lecture.

## Conséquences

- Aucune deuxième implémentation à maintenir en synchronisation avec l'API à
  chaque nouvel endpoint — le schéma généré suit automatiquement le code.
- Si un besoin concret de SDK publié apparaît (distribution PyPI/npm,
  version figée pour des intégrateurs externes), cette décision devra être
  révisée : elle part du principe qu'aucun consommateur externe réel n'existe
  encore, pas que ce sera toujours le cas.
