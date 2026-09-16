# ADR-0006 : Périmètre Enterprise du lot 3 — ce qui n'a pas été construit, et pourquoi

**Statut :** Accepté (Lot 3, 2026-09-15)

## Contexte

CLAUDE.md §28 (Phase 3) liste : multi-tenant, RBAC/ABAC, secret providers,
SSO/OIDC, tool risk scoring, approbations avancées, SBOM. L'audit préalable
au lot 3 a montré que plusieurs de ces besoins étaient déjà couverts par
l'existant : RBAC par projet (`viewer`/`operator`/`reviewer`/`admin`,
`project_members`, `store.require_project_role`), approbations (table
`approvals`, workflow de décision), et un mode d'authentification par proxy
de confiance (`BISCUITS_AUTH_MODE=proxy`, en-têtes `x-biscuits-user-*`) déjà
compatible avec une passerelle SSO en amont (Entra ID, Okta, Auth0…).

## Décision

Seuls le tool risk scoring typé et le SBOM (ADR-0003, et le manifeste
`GET .../registry/{item_id}/sbom`) ont été construits ce lot. Trois éléments
de la liste ont été explicitement écartés, avec justification, plutôt que
construits par anticipation :

- **Multi-tenant `Organization > Workspace > Project`** : l'isolation par
  projet + le RBAC par projet couvrent déjà le besoin observé (usage
  solo/petite équipe). Ajouter une couche organisationnelle au-dessus sans
  utilisateur multi-équipes réel serait spéculatif (YAGNI, CLAUDE.md §26).
- **Client OIDC natif** : le mode proxy délègue déjà l'authentification à une
  passerelle qui peut elle-même parler OIDC — ajouter un client OIDC dans le
  socle dupliquerait cette capacité pour un gain net nul, au prix d'une
  dépendance supplémentaire à maintenir.
- **Secrets provider (Vault/Keyring)** : les secrets sont déjà référencés par
  nom de variable d'environnement, jamais stockés en clair (`api_key_env`
  sur les fournisseurs). Ajouter un client Vault sans infrastructure Vault
  réelle chez l'utilisateur serait de la sur-ingénierie pure.
- **ABAC fin** (conditions par attribut au-delà de outil/politique/risque) :
  aucun besoin concret identifié au-delà de ce que `tool_policies` couvre
  déjà (cible : outil précis, effet, priorité).

## Conséquences

- Ces quatre éléments restent absents du système tant qu'un besoin concret
  ne les justifie pas — cette ADR documente le choix pour éviter qu'un futur
  lot ne les considère comme des oublis à corriger sans réévaluation.
- Si l'un de ces besoins devient réel (ex. un second client isolé demande une
  vraie séparation organisationnelle), il doit être réévalué comme un lot à
  part entière suivant la même méthode AUDIT → DESIGN → IMPLEMENTATION
  (CLAUDE.md §29), pas ajouté en périphérie d'un autre lot.
