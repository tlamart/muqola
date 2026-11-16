# Muqola — Direction UX/UI

## Intention
Une application conviviale, sobre et rassurante, centrée sur les communautés et le partage. Le jeu de société apporte une touche ludique, mais l'interface ne doit pas ressembler à un jeu vidéo. Identité **provisoire** tant que le nom et le logo ne sont pas validés.

## Principes
- Mobile-first, navigation claire en 3 à 5 entrées maximum ; actions prioritaires : « Trouver un jeu », « Ajouter un jeu », « Mes prêts », « Mes communautés ».
- Présenter d'abord les jeux réellement accessibles à l'utilisateur, pas un catalogue mondial vide.
- Lors de l'ajout : **Rechercher une fiche validée → sélectionner ou proposer → ajouter mon exemplaire → choisir les communautés (facultatif, partage après validation pour une nouvelle proposition)**. Indiquer clairement qu'une fiche de jeu est partagée entre utilisateurs, tandis qu'un exemplaire appartient à une seule personne. Prévenir que la fiche générique validée est trouvable par tous les comptes vérifiés ; une proposition et sa photo éventuelle restent privées pendant la revue. Une fiche représente un jeu, pas une édition commerciale.
- Afficher les états de prêt en français clair : « Demandé », « Accepté », « Remis », « Rendu », « Refusé », « Annulé ».
- Éviter les formulaires longs ; champs facultatifs réellement facultatifs ; messages d'erreur contextualisés.
- La disponibilité et la date de retour doivent être lisibles sur mobile. Une demande en attente ne constitue pas une réservation ; l'expliquer lors de la demande.
- Indiquer explicitement le partage d'adresse e-mail après acceptation d'un prêt.

## Direction visuelle indicative
- Fond crème très clair, texte anthracite, vert profond pour les actions principales, accents corail/jaune parcimonieux.
- Typographie sans serif lisible, composants arrondis modérément, espaces généreux.
- Utiliser des variables de design plutôt que des couleurs codées en dur ; vérifier les contrastes WCAG AA.
- Logo texte provisoire « Muqola » ; ne pas bloquer le lancement sur une identité définitive.

## Composants et états
Boutons, champs, cartes jeu, badges de disponibilité, sélecteur de communautés, recherche avec résultats/absence de résultat, confirmations, alertes, skeletons, notifications accessibles, dialogue de confirmation pour actions destructrices.
Prévoir : chargement, liste vide, **aucune communauté (proposer d'en créer/rejoindre une et d'ajouter un exemplaire privé)**, recherche sans résultat, invitation expirée ou révoquée, e-mail non vérifié, demande devenue inéligible, accès refusé, prêt déjà attribué.

## Accessibilité
Navigation clavier, focus visible, labels de champs, erreurs annoncées, zones tactiles adaptées, alt text, sémantique HTML, pas d'information transmise uniquement par la couleur. Tester les principales pages à 360 px et sur desktop.

## Page publique
Expliquer en trois étapes : « Créez votre communauté », « Partagez vos jeux », « Empruntez entre vous ». Boutons « S'inscrire » et « Se connecter ». Aucun listing public de membres, communautés ou exemplaires.


## Cible des PR B/A/C (à implémenter après validation du plan)
- Ajout : titre seul pour proposer, type « Je ne sais pas » accepté ; statut d'attente et suivi compréhensibles, pas de validation fictive. Type/base obligatoires seulement pour l'approbation ; illustrations et métadonnées facultatives. Proposer la réutilisation avant création et expliquer une homonymie réelle, sans case « autre édition ».
- Recherche : sans bouton Rechercher, résultats sans rechargement à partir d'environ deux caractères après ~250 ms ; repli GET avec Entrée sans JS. Labels, focus conservé, annonce discrète des résultats/erreurs/chargement, résultat par jeu avec seules copies autorisées. Deux intentions claires : ajouter depuis le catalogue, emprunter dans les communautés accessibles.
- Communautés : bouton « Créer une communauté » vers page dédiée, cartes entièrement ouvrables avec illustration facultative/fallback, nom, membres actifs et visibilité. Garder un seul lien sémantique par carte, sans boutons imbriqués. Le badge public ne doit pas promettre un accès disponible : découverte publique à définir, droits privés conservés.
- Invitation : lien courant consultable par tout membre actif/vérifié, bouton copier avec annonce et solution manuelle ; mention « permanent » si sans échéance, absence de lien et lien illisible traités. Révocation/régénération réservées aux administrateurs avec confirmation claire de l'invalidation de l'ancien lien.


### Recherche intelligente (A)

Explorer regroupe les exemplaires autorisés par jeu ; la carte affiche le nombre
d'exemplaires et de disponibles après les filtres, sans propriétaire ni e-mail.
Le détail liste les exemplaires dans les communautés actuelles. « Ma collection »
reste distincte. L'ajout recherche seulement les fiches validées et conserve le
choix, les notes et les partages lorsque les résultats changent.

La saisie attend deux caractères et 250 ms ; les filtres relancent la recherche,
vider le titre restaure la liste initiale. Les résultats portent `aria-busy` et
un statut poli annonce chargement, nombre et panne. Le focus de saisie reste
stable. Aucun bouton Rechercher visible ; Entrée assure le GET natif sans JS et
la reprise après panne. Un bouton de soumission masqué permet la soumission
implicite HTML même en présence du champ numérique « joueurs ».
