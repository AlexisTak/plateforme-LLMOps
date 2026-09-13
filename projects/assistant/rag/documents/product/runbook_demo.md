# Produit fictif — repères de démonstration

Ces informations décrivent uniquement l'environnement fictif utilisé dans la démo.

Les services principaux sont `web`, `api`, `orders` et `mailer`. Le service `orders` traite les commandes et reçoit les webhooks de paiement. `mailer` consomme une file d'attente pour envoyer les emails. Chaque requête possède un identifiant de corrélation visible dans les journaux applicatifs.

Avant une action corrective, relever l'heure, le service, la version déployée et l'identifiant concerné. Pour un incident après déploiement, comparer les métriques avec la version précédente et préparer un retour arrière contrôlé.
