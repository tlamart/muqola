# Frontières et calendrier

| Module | Possède | Livraison |
| --- | --- | --- |
| core | Accueil, healthchecks, headers, logs sans données sensibles | 0 |
| identity | User technique (0), inscription, vérification, sessions, jetons | 1 livré |
| communities | Appartenances, rôles, invitations, retraits | 2 |
| catalogue | Fiches génériques Game et réemploi | 3 |
| inventory | OwnedGame, GameVisibility, retrait | 3 |
| loans | Transitions atomiques et accès des participants | 4 |
| notifications | SMTP de développement (0), outbox des comptes et reprise (1) | Notifications de prêt au 5 |
| operations | Commandes de modération/audit, procédures d'exploitation | 6 |

Une seule base PostgreSQL. Le lot 0 a créé l'utilisateur technique et les
migrations standard Django (auth, permissions, content types, sessions).
Le schéma technique contient des tables de jointure utilisateur/permissions avec
suppression en cascade standard Django ; aucun lien métier n'existe encore.
Email unique, display_name limité à 80 caractères, vérification nullable.
Le lot 1 ajoute les jetons, les budgets de débit et la file chiffrée des e-mails
de compte, avec contraintes et tests de normalisation. Ne pas insérer de comptes
réels dans cet environnement de développement.
Pas de console admin web. Aucun compte opérateur créé automatiquement.

Pour les lots suivants : services d'écriture dans le module propriétaire,
requêtes de lecture filtrées par acteur, pas d'autorisation à partir d'un ID
client seul. `loans` coordonnera les verrouillages communs aux retraits et aux
acceptations ; outbox dans la même transaction. Les contraintes FK/ON DELETE,
l'indexation et l'anonymisation seront documentées avant chaque migration métier.

Plan : un lot, une branche, une PR vérifiable ; ADR/lot 0 validés ; validation du lot 1 avant
le lot 2. Ensuite comptes → communautés → catalogue/exemplaires → prêts →
notifications/UX → préproduction validée. Pas de progression automatique.
