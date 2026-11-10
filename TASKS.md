# Muqola — Plan de livraison du MVP

> Les durées ne sont pas des engagements. Chaque lot doit être démontrable avant de passer au suivant.

## Lot 0 — Décision technique et socle
- [x] Lire le kit, rédiger `docs/adr/0001-stack.md` et documenter les compromis.
- [x] Initialiser dépôt, monolithe modulaire, PostgreSQL, migrations, Docker Compose, capture locale des e-mails.
- [x] Configurer lint/format, tests, CI, `.env.example`, README et healthcheck.
**Acceptation :** une commande documentée démarre l'application et la base localement ; CI passe sur un dépôt propre. Si Docker n'est pas exécutable dans Codex Cloud, exiger la validation locale de cette commande avant fusion.

## Lot 1 — Comptes
- [x] Inscription ouverte, validation serveur, hachage des mots de passe, nom d'affichage.
- [x] Vérification d'e-mail obligatoire, lien expirant/usage unique, renvoi limité ; lien après inscription utilisable même sans avoir de compte connecté.
- [x] Connexion, déconnexion, récupération de mot de passe, sessions sûres.
- [x] Protection contre abus et énumération ; tests des liens expirés et non vérifiés.
**Acceptation :** inscription autonome sans validation administrateur ; impossible d'accéder au métier sans vérification.

## Lot 2 — Communautés
- [x] Création, liste et détail privés ; rôles administrateur/membre.
- [x] Invitations partageables expirables/révocables ; inscription depuis invitation.
- [x] Adhésion confirmée après connexion/vérification (sans adhésion silencieuse), départ, retrait d'un membre, transfert minimal du rôle administrateur.
- [x] Tests de permissions et d'invitations invalides.
**Acceptation :** Bob rejoint la communauté d'Alice via lien ; un non-membre n'accède à rien.

## Lot 3 — Catalogue interne et exemplaires
- [x] Modèles `Game`, `OwnedGame`, `GameVisibility` et contraintes.
- [x] Recherche des fiches `Game` existantes, sélection, création manuelle si absente ; réemploi d'une fiche pour un second exemplaire.
- [x] Création/édition d'exemplaire, **zéro ou plusieurs** communautés de visibilité, retrait du prêt ; édition des métadonnées génériques sans écraser une fiche partagée.
- [x] Recherche/filtres dans les communautés autorisées ; aucun leak d'exemplaire privé. Visuel neutre sans images distantes requises.
**Acceptation :** deux membres ajoutent chacun un exemplaire de la même fiche ; seules les communautés choisies voient chaque exemplaire.

## Lot 4 — Prêts
- [x] Demande avec date civile de retour future obligatoire (Europe/Paris), acceptation/refus/annulation et revalidation d'éligibilité à l'acceptation.
- [x] **Propriétaire** confirme remise et retour ; historique privé par participant ; clôture possible après perte de communauté.
- [x] Exclusivité atomique d'un prêt accepté/en cours par exemplaire (contrainte DB + transaction), demandes concurrentes clôturées ; tests concurrents sur PostgreSQL.
- [x] E-mail de contact visible aux deux parties uniquement pendant `ACCEPTED`/`HANDED_OVER` ; jamais dans les résultats de catalogue.
**Acceptation :** prêt complet Alice/Bob ; double acceptation concurrente impossible.

## Lot 5 — Notifications et UX
- [x] E-mails transactionnels pour les événements prévus ; fournisseur configurable, outbox PostgreSQL, reprise des envois après erreur/redémarrage.
- [x] Écrans vides, erreurs, états de chargement, formulaires accessibles.
- [x] Vérification des parcours sur mobile, tablette et ordinateur (Chromium 360/768/1280 px ; matériel réel à valider).
**Acceptation :** parcours complet compréhensible sans assistance ; aucune dépendance aux e-mails réels en tests.

## Lot 6 — Préproduction et mise en ligne
- [ ] Préparer Caddy, HTTPS, configuration DNS et Docker Compose de production.
- [ ] Installer un fournisseur d'e-mails et vérifier la délivrabilité de base.
- [ ] Mettre en place sauvegarde externe + test de restauration, supervision minimale, journalisation.
- [ ] Compléter mentions légales, politique de confidentialité, CGU adaptées, contact, demande de suppression de compte et politique de conservation, avec données réelles de l'exploitant.
- [ ] Vérifier limites de débit, permissions intercommunautés, transitions, erreurs, secrets, migration et rollback.
- [ ] Déployer après validation humaine et exécuter un test de fumée en production.
**Acceptation :** site HTTPS public ; un nouveau compte peut être créé et vérifié ; un prêt complet fonctionne ; sauvegarde restaurable ; aucun problème de sécurité bloquant connu.

## Scénarios E2E incontournables
1. Inscription libre → vérification → connexion.
2. Lien d'invitation → inscription → adhésion ; expiration/révocation.
3. Création fiche jeu → second utilisateur réutilise la fiche → exemplaire distinct ; un utilisateur sans communauté peut créer un exemplaire privé.
4. Visibilité A uniquement → utilisateur de B bloqué même via URL/API.
5. Demande → acceptation → partage e-mail → remise → retour.
6. Deux acceptations simultanées sur un même exemplaire → une seule réussit.
7. Membre retiré → accès aux exemplaires via cette communauté immédiatement révoqué ; prêt déjà accepté toujours clôturable par ses participants.
8. Réinitialisation de mot de passe, suppression de compte, erreur réseau et affichage mobile.

## Après le MVP — uniquement sur décision explicite
Catalogue externe, upload d'images enrichi, rappels automatiques, chat, événements, notation, objets autres que jeux, applications natives, paiement/dons.
