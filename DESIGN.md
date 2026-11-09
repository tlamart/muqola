# Muqola — Direction UX/UI

## Intention
Une application conviviale, sobre et rassurante, centrée sur les communautés et le partage. Le jeu de société apporte une touche ludique, mais l'interface ne doit pas ressembler à un jeu vidéo. Identité **provisoire** tant que le nom et le logo ne sont pas validés.

## Principes
- Mobile-first, navigation claire en 3 à 5 entrées maximum ; actions prioritaires : « Trouver un jeu », « Ajouter un jeu », « Mes prêts », « Mes communautés ».
- Présenter d'abord les jeux réellement accessibles à l'utilisateur, pas un catalogue mondial vide.
- Lors de l'ajout : **Rechercher une fiche existante → sélectionner ou créer → ajouter mon exemplaire → choisir les communautés (facultatif)**. Indiquer clairement qu'une fiche de jeu est partagée entre utilisateurs, tandis qu'un exemplaire appartient à une seule personne. Prévenir que la fiche générique est trouvable par tous les membres vérifiés.
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
