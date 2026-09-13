# Intégration du cahier des charges OpenAgent Enterprise

Ce document relie la spécification 1.0 au produit OpenAgent existant. Le
projet conserve FastAPI comme plan de contrôle et son module de fine-tuning :
une réécriture Go et la suppression de fonctions existantes n'apporteraient pas
de valeur au MVP actuel.

## Couverture actuelle

| Exigence | État | Implémentation |
|---|---|---|
| F02 Espaces et rôles | Partiel | Projets isolés, membres et rôles dans le plan de contrôle SQLite |
| F03 CRUD agents | Couvert | Projets, Settings, activation par registre et archivage |
| F04 Fournisseurs | Couvert | Registre Ollama, API compatible OpenAI et API compatible Anthropic, secrets par référence d'environnement et test de connexion |
| F05 Conversation et historique | Partiel | Chat en streaming SSE et exécutions expurgées persistantes; historique conversationnel durable reste à faire |
| F06 PDF DOCX TXT MD | Couvert | Ingestion, extraction, indexation asynchrone et erreurs explicites |
| F07 Recherche filtrée | Partiel | Index séparé par projet; espaces multiples et ACL fines restent à faire |
| F08 Catalogue d'outils | Couvert | Outils HTTP GET ou POST et MCP Streamable HTTP en lecture, timeout et limite de réponse |
| F09 Politiques d'outils | Couvert | Règles globales ou ciblées allow, deny et require approval, priorités déterministes et audit des décisions |
| F10 Approbations | Couvert | Suspension, décision unique et exécution après approbation |
| F11 Traces et export | Couvert | Modèle, durée, volume, RAG, statut et chronologie d’événements persistés, détail interactif et export JSON versionné |
| F12 Audit | Couvert | Journal SQLite append-only applicatif avec chaîne de hash |
| F14 Budgets | Partiel | Quotas jobs et stockage; budgets jetons par agent restent à faire |
| F15 Versions et rollback | Couvert | Workflow évalué, approuvé, production, archive et rollback |
| F18 Évaluation | Couvert | Cas CRUD, rapports, graphiques et comparaison de variantes |
| NF04 Linux | Couvert | Scripts Linux et fonctionnement local sans SaaS obligatoire |
| NF05 Observabilité | Couvert | Correlation ID, métriques RED et export Prometheus |
| NF09 Sauvegarde | Partiel | ZIP portable avec manifeste SHA-256; restauration guidée reste à faire |

## Prochain lot prioritaire

1. Docker Compose, healthchecks et démonstration reproductible.

Les politiques prévues concernent les permissions d'accès et l'exécution des
outils. Aucun contrôle de contenu médical n'est réintroduit.
