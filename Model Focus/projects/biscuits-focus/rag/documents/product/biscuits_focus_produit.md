# Biscuits Focus — présentation produit

Biscuits Focus est un assistant local d'organisation, basé sur un modèle de langage léger (Llama 3.2 1B fine-tuné), destiné à aider à découper des tâches, prioriser, et passer à l'action — en particulier pour les personnes ayant des difficultés d'attention et d'organisation.

## Ce que Biscuits Focus fait

- Découper une tâche vague en étapes concrètes.
- Proposer une "prochaine action" immédiatement exécutable.
- Aider à prioriser plusieurs tâches en tenant compte de l'urgence, l'importance, la durée, l'énergie disponible et les échéances.
- Réduire la charge cognitive en cas de sensation de débordement, en proposant une seule micro-action plutôt qu'un grand plan.
- Aider à reprendre le fil après une interruption.

## Ce que Biscuits Focus ne fait pas

- Il ne diagnostique pas de trouble, y compris le TDAH.
- Il ne prescrit pas de traitement ni de médicament, et ne donne pas de conseil médical personnalisé.
- Il n'est pas un dispositif médical et ne remplace pas un suivi professionnel.

## Fonctionnement technique (résumé)

Le comportement (style, découpage de tâches, structure des réponses) vient d'un fine-tuning LoRA sur un modèle de base Llama 3.2 1B. Les connaissances générales comme les méthodes d'organisation (Pomodoro, GTD, décharge mentale, time blocking) sont fournies dynamiquement via une recherche documentaire (RAG), pas mémorisées dans les poids du modèle. Les préférences utilisateur (fréquence de notification, projet en cours, etc.) sont stockées séparément et ne sont jamais utilisées pour l'entraînement.
