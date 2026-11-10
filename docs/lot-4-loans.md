# Lot 4 — prêts

Branche empilée sur le lot 3, sans fusion. Date de retour DATE obligatoire, future
à la demande ET acceptation selon Europe/Paris ; événements TIMESTAMPTZ/UTC.
Demandes REQUESTED multiples, sans réservation. Un emprunteur ne peut avoir
qu'une demande en attente pour le même exemplaire. Le propriétaire seul accepte,
refuse, confirme remise et retour. Chaque partie peut annuler avant remise.
Après remise : retour ou résolution opérateur explicite et tracée.

Contraintes PostgreSQL effectives : index unique partiel owned_game où
ACCEPTED/HANDED_OVER, et (owned_game,borrower) où REQUESTED ; propriétaire différent
de l'emprunteur, états contraints et échéance non nullable. FK exemplaire et
participants PROTECT ; événements LoanEvent PROTECT, index par participant/état.
Transactions courtes et verrou commun, puis verrou de ressource/du prêt ;
éligibilité revérifiée depuis les appartenances/visibilités actuelles. Aucun IO
réseau dans la transaction ; les événements persistés seront notifiés au lot 5.

Une acceptation clôt les demandes concurrentes avec un motif lisible. Retrait,
archivage, suppression de partage ou appartenance ferment les demandes inéligibles,
sans toucher aux prêts acceptés/remis. L'accès par une autre communauté préserve
l'éligibilité. L'archivage conserve l'historique et est refusé pendant un prêt
actif ; aucune suppression physique depuis l'interface.

Liste/détail réservés aux deux parties, sans passe-droit administrateur de
communauté. Présentation fermée : noms et métadonnées nécessaires seulement,
contacts e-mail vérifiés uniquement ACCEPTED/HANDED_OVER ; ni catalogue ni
historique clos ne les expose. Prêt accepté toujours consultable et clôturable
après retrait de communauté, sans rétablir l'accès au catalogue de copies.

Résolution opérateur, en développement seulement dans ce stade :

```
docker compose exec web python manage.py resolve_loan <uuid> --operator operateur@example.test --resolution RETURNED --reason 'Retour confirmé par les parties'
```

Un superutilisateur actif ET vérifié doit déjà exister ; aucun n'est créé
automatiquement. Pas d'interface d'administration générale. RETURNED après remise,
CANCELLED avant remise, motif obligatoire non sensible ; acteur, date, état et
motif dans LoanEvent, sans consultation globale de données privées.

Vérifications : 106 tests PostgreSQL, y compris deux acceptations concurrentes via
services et deux écritures SQL concurrentes sans advisory, contraintes en base,
Paris à minuit/dates passées, toutes autorisations/transitions, retrait de partage,
retrait de membre, accès alternatif et contacts clos. Parcours navigateur étendu
jusqu'au retour après retrait du membre, avec trois largeurs et refus d'un tiers.
CI doit confirmer le commit final. Notifications d'événements au lot 5 ; pas de
rappel automatique, calendrier de réservation, production, dépense ni lot 6.
