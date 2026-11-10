# Frontières et calendrier

| Module | Possède | Livraison |
| --- | --- | --- |
| core | Accueil, healthchecks, headers, logs sans données sensibles | 0, UX au 5 |
| identity | User, inscription, vérification, sessions, jetons, compte privé | 1, UX au 5 |
| communities | Appartenances, rôles, invitations, retraits | 2 |
| catalogue | Fiches génériques Game, réemploi et signalements | 3 |
| inventory | OwnedGame, GameVisibility, retrait et archivage | 3 |
| loans | Transitions atomiques et accès des participants, historique minimal | 4 |
| notifications | Outbox chiffrée PostgreSQL, SMTP local, reprise/rétention | 1 et 5 |
| operations | Console de confiance, audit, demandes de suppression | 4 et 5 ; préproduction au 6 |

Une seule base PostgreSQL. Écritures dans les services du module propriétaire,
lectures filtrées par acteur, jamais une autorisation fondée sur le seul ID client.
`core.transactions.domain_write` coordonne les mutations métier (verrou transactionnel
PostgreSQL commun) ; `loans` revalide les droits et les invariants à chaque transition.
Index uniques partiels PostgreSQL pour l'exclusivité active et les demandes en double.
L'outbox est créée dans la transaction métier, livrée par un worker séparé sans broker.
Les contraintes FK/ON DELETE et compromis sont détaillés dans les documents de lots :
[comptes](lot-1-accounts.md), [communautés](lot-2-communities.md),
[catalogue/copies](lot-3-catalogue.md), [prêts](lot-4-loans.md),
[notifications/UX](lot-5-notifications.md).

Aucune console admin web, aucun opérateur créé automatiquement, aucune donnée réelle.
Plan autorisé : lots successifs 2 à 5, branche/PR dédiée et empilée pour chacun,
sans fusion automatique. Arrêt au lot 5 pour validation. La préproduction, les
engagements réels de suppression/anonymisation et la rétention des historiques
exigent le lot 6 et une validation avant ouverture publique.
