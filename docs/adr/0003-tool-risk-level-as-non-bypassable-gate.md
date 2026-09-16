# ADR-0003 : Le niveau de risque d'un outil comme garde non contournable

**Statut :** Accepté (Lot 3, 2026-09-15)

## Contexte

CLAUDE.md §14 exige un niveau de risque typé par outil (`LOW`/`MEDIUM`/
`HIGH`/`CRITICAL`) et pose une règle explicite : « une action critique ne
doit jamais être exécutée simplement parce qu'un LLM l'a demandée ». Le
moteur de politiques existant (`tool_policies` : `allow`/`deny`/
`require_approval`, priorité, `evaluate_tool_policy`) est déjà déterministe,
mais entièrement piloté par la configuration — un administrateur pourrait
par erreur (ou via une politique mal priorisée) créer une règle `allow` qui
laisse un outil dangereux s'exécuter sans supervision.

## Décision

`tools.risk_level` est un attribut de l'outil, pas seulement une entrée de
politique. `evaluate_tool_policy` calcule d'abord l'effet résultant des
politiques comme avant, puis applique une garde finale : si l'outil est
`critical` et que l'effet résolu est `allow`, il est forcé à
`require_approval`. Seule une politique `deny` explicite reste prioritaire
sur cette garde (un outil qu'on veut bloquer complètement doit pouvoir
l'être). Cette garde vit dans le code du moteur de politiques, pas dans une
politique elle-même — elle ne peut donc pas être désactivée en modifiant la
configuration.

## Conséquences

- Un outil `critical` ne peut jamais s'exécuter automatiquement, même si
  toutes les politiques configurées l'autorisent explicitement — défense en
  profondeur assumée, au prix de ne pas être configurable pour ce cas
  précis (choix délibéré, pas un oubli).
- La classification `risk_level` est déclarative (choisie par l'administrateur
  à la création de l'outil, cf. `web/src/app/tools/page.tsx`), pas déduite
  automatiquement de la méthode HTTP ou de l'action — un mauvais classement
  reste possible et relève de la responsabilité de qui déclare l'outil.
