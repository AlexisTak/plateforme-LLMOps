# Correctifs de la console — 9 septembre 2026

## Chat

Le client transmet les six derniers échanges complets et les préférences saisies
pour la conversation. Le serveur refuse les rôles autres que user/assistant dans
l'historique, conserve les paires complètes et retire les plus anciennes si elles
dépassent le budget de tokens. Un message courant trop long est refusé clairement.
Le RAG reste appliqué au message courant ; les préférences restent des données de
contexte, jamais des exemples d'entraînement.

Changer de projet remet à zéro la conversation, les préférences et les requêtes
affichées. La sélection du modèle est mémorisée par projet dans le navigateur,
avec retour au modèle de base si l'adapter n'existe plus. Les réponses reçues par
l'ancien composant ne peuvent pas modifier le chat du nouveau projet.

## Évaluation

Le contrat actif est le texte naturel (`plain-text-v1`). Les anciens critères
JSON ne produisent plus de faux échecs. Le benchmark partagé sert de modèle aux
nouveaux projets. Les contrôles automatiques portent sur le format, la concision
et les signaux de refus, sans prétendre mesurer la pertinence des étapes.

Une revue humaine doit vérifier pour chaque réponse : la première action est-elle
claire, réalisable avec les informations disponibles, adaptée aux contraintes et
exprimée sans jugement ? Le benchmark actuel ne mesure pas l'ancrage dans le RAG.

Les nouveaux `evaluation/report_summary.json` contiennent `metadata`, `summary`,
`outputs` et `comparison`. L'endpoint `/evaluation/report/summary` conserve son
ancien contrat (table de métriques). L'endpoint `/evaluation/report` expose aussi
les métadonnées, les raisons d'obsolescence et les écarts de scores.

Les métadonnées enregistrent la date, la version du dataset et les empreintes SHA-256
des données préparées, du benchmark, du prompt, des métadonnées du projet et des
adapters. L'interface détecte les fichiers modifiés, supprimés ou ajoutés. Les
rapports précédents sont archivés dans `evaluation/history/`. Les écarts ne sont
calculés que si les critères, le benchmark et les instructions sont comparables.
Les anciens rapports sont conservés et signalés comme devant être actualisés.

## Jobs

Les lancements depuis l'API (training, pipeline, sweep) passent par
`scripts/run_with_evaluation.py` : une évaluation suit la réussite du job complet.
Un sweep est évalué une seule fois à la fin. En cas d'échec du training, le wrapper
n'évalue pas ; en cas d'échec de l'évaluation, le job échoue mais l'adapter reste
disponible et les logs précisent l'étape en cause. Les commandes CLI directes
restent indépendantes.

Les jobs terminés, échoués ou arrêtés sont sauvegardés dans `.jobs/`, avec les
200 dernières lignes de logs. L'arrêt vise tout l'arbre de processus sous Windows
et le groupe de processus sous POSIX. L'état « arrêté » est préservé à la fin du
traitement des logs. Un arrêt normal de l'API arrête les jobs et sauvegarde leur
état ; la reprise d'un job actif après arrêt brutal de la machine/API n'est pas
implémentée.

## Vérification

`python -m pytest -m "not gpu"` couvre notamment le contrat de conversation,
l'évaluation texte, l'archivage/comparaison et la persistance/annulation réelle
d'un sous-processus avec enfant. Dans `web/` : `npx tsc --noEmit`, `npm run lint`
et `npm run build`.
