# Frontières et calendrier

| Module | Possède | Livraison |
| --- | --- | --- |
| core | Accueil, healthchecks, headers, logs sans données sensibles | 0 |
| identity | User technique (0), inscription, vérification, sessions, jetons | 1 |
| communities | Appartenances, rôles, invitations, retraits | 2 |
| catalogue | Fiches génériques Game et réemploi | 3 |
| inventory | OwnedGame, GameVisibility, retrait | 3 |
| loans | Transitions atomiques et accès des participants | 4 |
| notifications | SMTP de développement (0), outbox et reprise | 5 ; persistance des liens dès 1 |
| operations | Commandes de modération/audit, procédures d'exploitation | 6 |

Une seule base PostgreSQL. Le lot 0 ne crée que l'utilisateur technique et les
migrations standard Django (auth, permissions, content types, sessions).
Le schéma technique contient des tables de jointure utilisateur/permissions avec
suppression en cascade standard Django ; aucun lien métier n'existe encore.
Email unique, display_name limité à 80 caractères, vérification nullable.
La normalisation stricte et ses contraintes pour toutes les voies d'écriture
seront complétées/testées avec le lot 1 ; ne pas insérer de comptes réels ici.
Pas de console admin web. Aucun compte opérateur créé automatiquement.

Pour les lots suivants : services d'écriture dans le module propriétaire,
requêtes de lecture filtrées par acteur, pas d'autorisation à partir d'un ID
client seul. `loans` coordonnera les verrouillages communs aux retraits et aux
acceptations ; outbox dans la même transaction. Les contraintes FK/ON DELETE,
l'indexation et l'anonymisation seront documentées avant chaque migration métier.

Plan : un lot, une branche, une PR vérifiable ; validation du lot 0/ADR avant
le lot 1. Ensuite comptes → communautés → catalogue/exemplaires → prêts →
notifications/UX → préproduction validée. Pas de progression automatique.
