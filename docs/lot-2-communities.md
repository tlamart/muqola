# Lot 2 — communautés privées

Branche empilée sur Codespaces (PR 3), elle-même sur les comptes (PR 2).
Aucune fusion automatique. Ce lot livre communautés privées, noms/descriptions,
adhésion explicite par lien multiusage, révocation, départ/retrait et transfert
administrateur. Pas de suppression de communauté.

Les jetons ont 256 bits d'entropie, un digest SHA-256 unique et une copie Fernet
chiffrée avec contexte distinct pour que l'administrateur retrouve le lien.
Expiration 7 jours par défaut, 1–30 jours au formulaire. Aucune journalisation
ni référent depuis les URL à secret ; redirection immédiate vers URL propre.
Après rotation de clé, un lien illisible reste révocable depuis la page admin,
sans révocation automatique sur GET. Suivre la
[procédure de rotation du README](../README.md#rotation-du-secret-django).
Les noms ne sont révélés qu'aux comptes vérifiés ayant le lien valide ou membres.
L'intention d'adhésion est conservée comme digest en session et, pour une nouvelle
inscription, dans PendingJoin. Elle survit à une vérification dans un autre
navigateur ; aucun compte existant n'est modifié sur inscription en doublon.
Expiration/révocation sont revérifiées à la confirmation transactionnelle.

Schéma : Community UUID, créateur PROTECT ; Membership unique (communauté,user),
FK PROTECT, rôle contraint, actif/inactif et index (user,active). CommunityInvite
UUID, digest unique, créateur/communauté PROTECT et contrainte d'expiration future.
PendingJoin OneToOne utilisateur CASCADE : intention temporaire, pas une adhésion.
Toutes les mutations exigent utilisateur actif/vérifié et autorisations serveur.
Un retrait conserve la ligne d'appartenance inactive ; un retour par invitation
réactive comme membre ordinaire. Le dernier administrateur ne peut pas partir.
Aucun e-mail de membre dans les listes ou détails de communauté.

Arbitrage de concurrence MVP : les écritures métier courtes prennent d'abord un
verrou advisory transactionnel PostgreSQL commun (core.transactions), en plus des
contraintes et futurs verrous de ressource. Cela sérialise aussi les retraits et
acceptations qui seront raccordés aux lots 3/4 et évite des ordres de verrouillage
contradictoires. Aucun IO réseau dans cette section. Compromis : débit d'écriture
limité ; à mesurer avant production, sans architecture distribuée prématurée.

Vérifications : lint/format/mypy et 84 tests PostgreSQL réussis localement, dont
accès croisés, refus admin, multiusage/unicité, expiration entre ouverture et POST,
parcours d'inscription/invitation et départs concurrents du dernier admin.
La CI ajoute un vrai parcours Chromium avec capture SMTP et trois largeurs
360/768/1280. Le retrait de visibilité et la clôture des demandes seront raccordés
lorsque leurs modèles seront livrés aux lots 3/4. Aucun service réel, coût ou
mécanisme de production introduit. Les limites générales restent celles du README.
