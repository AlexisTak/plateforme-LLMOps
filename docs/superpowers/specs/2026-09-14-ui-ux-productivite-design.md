# Amélioration UI/UX — productivité interne

**Date :** 2026-09-14
**Statut :** approuvé en brainstorming, à découper en plan d'implémentation
**Objectif retenu :** productivité interne (usage quotidien par l'équipe), et non crédibilité commerciale ni conformité d'accessibilité — ces deux axes ne sont servis qu'incidemment.

## Problème

Les 16 pages du frontend partagent un thème sombre cohérent (`web/src/app/globals.css`) et huit primitives (`web/src/components/ui.tsx`). L'UI n'est pas incohérente : elle est **incomplète sur les retours d'état**, ce qui coûte du temps à chaque action.

Constats mesurés dans le code au 2026-09-14 :

| # | Constat | Mesure |
|---|---|---|
| 1 | `request()` lève `Error("404 /api/x: {\"detail\":\"...\"}")`, et cette chaîne est affichée telle quelle via `String(e)` | 26 occurrences de `setError(String(e))` dans 13 fichiers |
| 2 | Aucun retour de succès : une action réussie ne confirme rien, la page se rafraîchit silencieusement | toute l'application |
| 3 | Le trio `setBusy(true)` / `try` / `catch → setError` est réécrit à la main | 11 fichiers, dont 13 fois dans `dataset/page.tsx` |
| 4 | Aucun état de chargement : la page affiche des zéros ou du vide pendant le fetch | 8 pages sur les 15 qui chargent des données |
| 5 | `focus:outline-none` retire l'anneau de focus et le remplace par une bordure peu contrastée : la navigation clavier est presque invisible | `ui.tsx` + toutes les pages |
| 6 | Aucun `<form>` dans l'application : Entrée ne valide pas, sauf contournement manuel par `onKeyDown` | 2 pages contournent, 8 ne valident pas au clavier |
| 7 | `<select>` et `<textarea>` réimplémentés avec des classes copiées-collées | 13 `<select>` dans 8 fichiers, 9 `<textarea>` dans 6 fichiers |
| 8 | `window.confirm` natif pour les suppressions : rupture visuelle avec le thème sombre | 5 sites dans 4 fichiers |
| 9 | `StatusBadge` affiche les statuts bruts en anglais (`running`, `draft`, `denied`) dans une interface française | toute l'application |

## Périmètre

**Dans le périmètre :** les 9 constats ci-dessus, sur les 16 pages, plus une palette de commandes ⌘K pour la navigation au clavier.

**Hors périmètre :** toute refonte visuelle (couleurs, typographie, mise en page), toute nouvelle fonctionnalité métier, le backend, et le manque d'écrans identifié pendant le module Opportunités (formulaire de fiche incomplet, absence de formulaire de création de KPI) qui relève d'un incrément fonctionnel distinct.

## Contraintes globales

- Next.js 16.3.1, React 19, TypeScript strict — lire `web/node_modules/next/dist/docs/` avant d'écrire du code Next, cette version diverge des conventions courantes.
- **Aucune nouvelle dépendance npm.** Les primitives sont écrites à la main ; une bibliothèque de composants (shadcn/ui, Radix) a été explicitement écartée en brainstorming : elle imposerait de re-styler les 16 pages sans rien apporter à l'objectif de productivité.
- Les tokens de `globals.css` ne changent pas. Aucune couleur nouvelle.
- Tout texte visible par l'utilisateur est en français.
- Le backend n'est pas modifié : les 89 tests `pytest` doivent rester verts sans y toucher, comme garde-fou de non-régression.
- Pas de framework de test JS dans le repo : la vérification est `npx tsc --noEmit`, des `console.assert` en mode développement pour les fonctions pures (convention déjà en place en bas de `web/src/lib/simulator.ts`), et un parcours navigateur manuel.

## Architecture

Une couche partagée neuve, puis son application mécanique aux pages. Aucune page ne conserve de gestion d'erreur ou d'état de chargement artisanale.

```
lib/api.ts        ApiError (nouvelle classe) — point de passage unique des erreurs réseau
lib/errors.ts     humanError(e) — traduit n'importe quoi en une phrase française lisible
lib/use-action.ts useAction(fn, opts) — busy + erreur humanisée + toast de succès
components/toast.tsx           ToastProvider / useToast — pile de notifications
components/ui.tsx              + Select, Textarea, Field, Skeleton, ConfirmDialog
components/command-palette.tsx palette ⌘K, alimentée par LINKS
components/nav-menu.tsx        LINKS devient exporté (source unique de navigation)
app/layout.tsx                 monte ToastProvider et CommandPalette
```

### `lib/api.ts` — erreur structurée

`request()` est le point par lequel passent tous les appels API. C'est donc là que l'erreur doit être structurée, une fois, plutôt que d'être reparsée par 26 appelants.

```ts
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    readonly detail: string,
  ) {
    super(`${status} ${path}: ${detail}`);
    this.name = "ApiError";
  }
}
```

Dans `request()`, sur `!res.ok` : lire le corps, tenter `JSON.parse`, prendre `detail` s'il s'agit d'une chaîne (forme standard des erreurs FastAPI), sinon garder le texte brut ; lever `ApiError`. Le message de l'`Error` sous-jacente reste identique à l'actuel, ce qui préserve la lisibilité en console et dans les logs.

Les deux autres points de levée (`api.ts:408` flux de chat, `api.ts:445` upload de fichier) ne passent pas par `request()` et continuent de lever une `Error` simple : `humanError` doit donc rester correct sur une `Error` ordinaire.

### `lib/errors.ts`

```ts
export function humanError(e: unknown): string;
```

Quatre branches, dans cet ordre :

1. `e instanceof ApiError && e.detail` → `e.detail` seul (« Opportunité introuvable »).
2. `e instanceof ApiError` → `` `Erreur ${e.status} — le serveur n'a pas pu traiter la demande.` ``
3. `e instanceof TypeError` → `« API injoignable — vérifie que le backend tourne sur http://127.0.0.1:8000. »` (une requête `fetch` qui échoue au niveau réseau rejette avec un `TypeError`). L'URL provient de la même source que `api.ts`, à savoir `process.env.NEXT_PUBLIC_API_URL` avec ce défaut.
4. Sinon → `e instanceof Error ? e.message : String(e)`.

Vérification : un bloc `console.assert` en développement couvrant les quatre branches.

### `lib/use-action.ts`

Le cœur du gain. Remplace les 26 sites du constat 3.

```ts
export function useAction<A extends unknown[]>(
  fn: (...args: A) => Promise<unknown>,
  opts?: { success?: string },
): {
  run: (...args: A) => Promise<void>;
  busy: boolean;
  error: string | null;
  reset: () => void;
};
```

Comportement : `run` ignore les appels concurrents tant que `busy` est vrai (évite le double-clic qui crée deux fois la même ressource) ; en cas de succès, pousse un toast si `opts.success` est fourni ; en cas d'échec, place `humanError(e)` dans `error` **et** pousse un toast d'erreur. `error` reste exposé parce que les pages affichent déjà l'erreur en ligne près du formulaire concerné — le toast ne remplace pas cet affichage, il le double pour les actions déclenchées hors du champ de vision.

### `components/toast.tsx`

```tsx
export function ToastProvider({ children }: { children: ReactNode }): JSX.Element;
export function useToast(): (message: string, kind?: "success" | "error") => void;
```

Pile en bas à droite, `position: fixed`, au plus 3 notifications visibles (les plus anciennes sont retirées), disparition automatique après 4 s, fermeture au clic. Conteneur `aria-live="polite"` et `role="status"` pour que le message soit annoncé sans voler le focus. Couleurs : `success-soft`/`success` et `error-soft`/`error`, déjà définis dans les tokens.

### `components/ui.tsx` — primitives et focus

Ajouts, tous calqués sur le style de l'`Input` existant :

- `Select` — même API que `Input` (`value`, `onChange: (v: string) => void`), enfants `<option>`.
- `Textarea` — plus `rows` et `maxLength`.
- `Field` — libellé, contenu, texte d'aide optionnel, message d'erreur optionnel ; relie le libellé au champ par `htmlFor`/`id`.
- `Skeleton` — rectangle `bg-surface-hover` avec `animate-pulse`, dimensions par props ; sert à composer les états de chargement.
- `ConfirmDialog` — remplace `window.confirm` : titre, message, boutons « Annuler » / action en variante `danger`, fermeture par Échap, `role="dialog"` + `aria-modal="true"`, focus initial sur « Annuler » (le choix non destructeur) et focus rendu au déclencheur à la fermeture.

Correction du focus (constat 5) : sur `Button`, `Input`, `Select`, `Textarea` et `NavLink`, remplacer `focus:outline-none` seul par `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg`, en conservant la bordure accent actuelle. `focus-visible` plutôt que `focus` pour ne pas faire apparaître l'anneau au clic à la souris.

Statuts français (constat 9) : la table `STATUS_STYLES` gagne un champ `label` — `running` « en cours », `completed` « terminé », `failed` « échec », `stopped` « arrêté », `draft` « brouillon », `evaluated` « évalué », `approved` « approuvé », `pending` « en attente », `processing` « en traitement », `denied` « refusé », `production` « production », `archived` « archivé ». Un statut absent de la table continue de s'afficher brut, comme aujourd'hui.

### `components/command-palette.tsx`

Montée une fois dans `layout.tsx`. Sa source de données est le tableau `LINKS` **exporté** depuis `nav-menu.tsx` : une seule source de vérité pour la navigation, pas une seconde liste à maintenir.

Comportement : ⌘K (macOS) ou Ctrl+K ouvre ; le champ est focalisé à l'ouverture ; le filtre ignore la casse et les accents (`normalize("NFD")` puis suppression des diacritiques, pour que « executions » trouve « Exécutions ») ; ↑ et ↓ déplacent la sélection ; Entrée navigue et ferme ; Échap et le clic sur le fond ferment et rendent le focus à l'élément précédent. `role="dialog"`, `aria-modal="true"`. La fonction de filtre est exportée pure, donc couverte par `console.assert`.

## Changements par page

Quinze pages chargent des données et reçoivent donc un état de chargement fondé sur `Skeleton` ; `docs/page.tsx` est statique (aucun `useEffect`, aucun appel API) et ne reçoit que l'anneau de focus hérité des primitives.

| Page | `<form>` | `useAction` | `Select`/`Textarea` | `Skeleton` | `ConfirmDialog` |
|---|---|---|---|---|---|
| `/` | — | oui | — | remplace le texte | — |
| `/dataset` | oui | oui (13 sites) | 2 textarea | à ajouter | 2 |
| `/training` | oui | oui | 1 select | à ajouter | — |
| `/benchmarks` | oui | oui | 2 textarea | à ajouter | 1 |
| `/chat` | oui | oui | 1 select, 1 textarea | à ajouter | — |
| `/opportunities` | oui | oui | — | à ajouter | — |
| `/opportunities/[id]` | oui | oui | 3 select, 1 textarea | remplace le texte | — |
| `/opportunities/dashboard` | — | oui | — | remplace le texte | — |
| `/rag` | oui | oui | 1 select, 1 textarea | à ajouter | 1 |
| `/enterprise` | oui | oui | 1 select | remplace le texte | — |
| `/executions` | — | oui | — | remplace le texte | — |
| `/providers` | oui | oui | 1 select | à ajouter | 1 |
| `/tools` | oui | oui | 3 select | à ajouter | — |
| `/system` | — | oui | — | remplace le texte | — |
| `/docs` | — | — | — | — (page statique) | — |
| `/settings` | — | oui | 2 select, 2 textarea | remplace le texte | — |

`components/project-switcher.tsx` est traité avec les pages : son `<select>` de projet et les deux `<select>` de son formulaire de création passent aux primitives, et son `setError(String(e))` passe par `useAction`.

**Risque identifié — le chat.** `chat/page.tsx` envoie le message par `onKeyDown` sur un `<textarea>`. En passant à `<form>`, il faut conserver exactement le comportement actuel : Entrée envoie, Maj+Entrée insère un retour à la ligne. C'est le seul endroit où le passage à `<form>` peut casser une interaction existante ; il est à vérifier au navigateur et non seulement au compilateur.

## Vérification

1. `npx tsc --noEmit` à chaque tâche — le seul contrôle automatique disponible côté frontend.
2. `console.assert` en développement pour les deux fonctions pures : `humanError` (quatre branches) et le filtre de la palette (correspondance insensible aux accents et à la casse, aucune correspondance).
3. Parcours navigateur en fin de chantier : créer une opportunité en validant par Entrée ; arrêter le backend et vérifier que le message affiché est « API injoignable… » et non une trace ; déclencher une erreur 404 et vérifier que seul le `detail` s'affiche ; ouvrir ⌘K et naviguer vers trois pages au clavier ; parcourir un formulaire à la touche Tab pour voir l'anneau de focus ; supprimer un élément dans `rag` pour voir le `ConfirmDialog` ; envoyer un message dans le chat avec Entrée puis insérer un retour à la ligne avec Maj+Entrée.
4. `pytest` (89 tests) en fin de chantier pour confirmer que le backend n'a pas bougé.

## Découpage prévu

Environ huit tâches, la couche partagée d'abord parce que toutes les pages en dépendent :

1. `ApiError` dans `api.ts` + `lib/errors.ts` avec son auto-contrôle.
2. `components/toast.tsx` + `lib/use-action.ts`, provider monté dans `layout.tsx`.
3. Primitives `ui.tsx` (`Select`, `Textarea`, `Field`, `Skeleton`, `ConfirmDialog`), correction du focus, statuts français.
4. `LINKS` exporté + `components/command-palette.tsx` + montage dans `layout.tsx`.
5. Pages `dataset`, `training`, `benchmarks`.
6. Pages `chat`, `rag`, `providers`, `tools`.
7. Pages `opportunities` (liste, fiche, dashboard), `enterprise`, `project-switcher`.
8. Pages `/`, `executions`, `system`, `settings`, puis parcours navigateur complet.

Les tâches 5 à 8 sont mécaniques et indépendantes entre elles ; les tâches 1 à 4 sont séquentielles.
