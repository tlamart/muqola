# Muqola — Direction UX/UI

## Intention
Une application conviviale, sobre et rassurante, centrée sur les communautés et le partage. Le jeu de société apporte une touche ludique, mais l'interface ne doit pas ressembler à un jeu vidéo. Identité **provisoire** tant que le nom et le logo ne sont pas validés.

## Principes
- Mobile-first, navigation claire en 3 à 5 entrées maximum ; actions prioritaires : « Trouver un jeu », « Ajouter un jeu », « Mes prêts », « Mes communautés ».
- Présenter d'abord les jeux réellement accessibles à l'utilisateur, pas un catalogue mondial vide.
- Lors de l'ajout : **Rechercher une fiche validée → sélectionner ou proposer → ajouter mon exemplaire → choisir les communautés (facultatif, partage immédiat possible pour une proposition en attente)**. Indiquer clairement qu'une fiche de jeu est partagée entre utilisateurs, tandis qu'un exemplaire appartient à une seule personne. Prévenir que la fiche générique validée est trouvable par tous les comptes vérifiés ; une proposition reste hors du catalogue général pendant la revue, mais est visible via les exemplaires partagés aux membres autorisés. Les motifs de revue restent privés. Une fiche représente un jeu, pas une édition commerciale.
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
- Communautés : bouton « Créer une communauté » vers page dédiée, cartes entièrement ouvrables avec illustration facultative/fallback, nom, membres actifs et visibilité. Garder un seul lien sémantique par carte, sans boutons imbriqués. Badge « Privée » uniquement ; aucune découverte publique, droits privés conservés.
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


### Indicateur et parcours P1

« Fiche en attente de validation » apparaît sur carte, détail d’exemplaire, fiche
et prêt. Le partage peut être choisi dès l’ajout manuel, sans case désactivée
ni attente de validation administrative. Sans communauté choisie, copie privée.
Un rejet affiche l’interdiction des nouvelles demandes ; les participants d’un
prêt accepté conservent ses actions de remise/retour et son historique privé.

## Retours du staging — 19 novembre 2026

- Détail de communauté : actions « Inviter des membres » et « Modifier les
  paramètres », contenu de gestion fermé au départ. Invitation en fenêtre avec
  copie et message ; roue dentée pour la révocation/régénération, crayon nommé
  par membre pour ses actions. Chaque mutation garde sa confirmation.
- Fenêtres natives avec titre accessible, fermeture explicite/Échap, focus
  contenu puis rendu au déclencheur. Sans JavaScript, les mêmes contenus sont
  des sections dépliables ; aucune fonction essentielle ne dépend d’une fenêtre.
- Connexion : inscription visible dans le contenu, avec cible tactile adaptée.
  Adhésion : confirmer ou annuler explicitement, sans adhésion automatique.
- Ajout : choix/proposition du jeu puis écran « Votre exemplaire », avec retour
  au choix conservant les données préparées et annulation sans création.
  Exemplaire existant : gestion sur sa page dédiée ; résumé, statut et action
  restent lisibles sur mobile, sans étirer un panneau dans la colonne du visuel.
- Cartes et états vides conservent leurs marges intérieures. Favicon SVG local
  reprenant le M et le point orange de la marque provisoire.

## Compte en cours de clôture

Afficher l'état de restriction dans Mon compte avec un accès direct à Mes prêts
et le contact de support. Bloquer les nouvelles activités côté serveur et garder
la consultation/remise/retour selon le rôle existant. Ne pas annoncer un effacement
immédiat lorsqu'une demande est seulement enregistrée ou qu'un prêt reste actif.
