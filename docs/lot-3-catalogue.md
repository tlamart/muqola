# Lot 3 — catalogue interne et exemplaires

Branche empilée sur le lot 2, sans fusion. Game contient uniquement les données
génériques réutilisables, visibles à tout compte vérifié même sans communauté.
OwnedGame représente chaque exemplaire distinct ; GameVisibility contient ses
partages explicites, zéro par défaut. Aucun catalogue externe, upload ou URL
image. Visuel neutre local. Recherche NFKD/casefold/accents et espaces normalisés,
champ title_key indexé ; la recherche contains reste un scan potentiel sur grand
catalogue, à mesurer avant ouverture plutôt que rajouter un moteur externe.

Game : UUID, créateur PROTECT, bornes de champs/validation serveur, ordre min/max
joueurs contraint en base. Titres non uniques ; paire source/id externe facultative,
contrainte de paire complète et index unique conditionnel. Un futur importeur
indépendant pourra alimenter le service de métadonnées ; aucun fournisseur n'est
implémenté ou appelé. ever_reused est irréversible : le créateur ne peut plus
corriger après réemploi par un autre utilisateur, même si celui-ci archive sa
copie. Correction/signalement persistant GameReport, un dossier ouvert par
utilisateur/fiche, à traiter par maintenance avant production.

OwnedGame : UUID, game/owner PROTECT, notes 500 caractères, retiré/archivé ; partage
unique (owned_game,community), OwnedGame CASCADE et Community PROTECT. Les services
transactionnels vérifient acteur propriétaire et toutes ses appartenances actuelles.
Une communauté étrangère ou un exemplaire inaccessible ne peut pas être obtenu
par un ID deviné. Un membre retiré perd immédiatement la lecture ; le départ du
propriétaire supprime ses visibilités dans cette communauté. Les autres communautés
restent utilisables. Aucun e-mail de propriétaire ni quantité privée dans le
catalogue générique, les compteurs/requêtes étant filtrés avant rendu.

Pages : catalogue/recherche/création manuelle/correction/signalement, sélection
d'une fiche, ajout/édition de copie, ma collection, découverte filtrée par titre,
communauté, disponibilité et joueurs. Les exemplaires retirés ne sont plus proposés
aux autres. L'exclusivité liée aux prêts et la clôture des demandes sont raccordées
au lot 4 ; aucune réservation fictive ici. Contrôle des transitions du catalogue
et partages avec le verrou court commun du lot 2.

Vérifications locales : ./scripts/check.sh, Ruff/format/mypy, migrations et 91 tests
PostgreSQL réussis : zéro communauté, multi-exemplaires, union/déduplication,
permissions, tampering, retrait/départ, réemploi irréversible, contraintes et XSS.
Le parcours Chromium de CI est étendu à Alice/Bob/Clara, copie partagée et copie
privée, réemploi d'une seule fiche et accès croisés refusés ; trois largeurs.
Ni téléphone physique, benchmark ni production ; limites générales du README.
