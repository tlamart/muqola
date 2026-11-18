# Espacements des communautés et formulaires

Correctif du 18 novembre 2026, depuis `main` `27ec280`. Le signalement sur le
staging concerne le badge « Privée », le titre et le compteur d’une communauté,
sur téléphone et ordinateur.

## Comportements corrigés

- Le contenu de carte utilise une grille avec 12 px entre badge, titre et compteur,
  et 22 px de marge intérieure, à partir des variables CSS existantes. Le badge
  conserve sa largeur naturelle et toute la carte reste un seul lien accessible.
- La suppression du padding du conteneur vise uniquement les cartes illustrées.
  L’état « Aucune communauté pour le moment » conserve ainsi ses 22 px de padding.
- Une marge de 16 px sépare les actions et leur contenu suivant dans les panneaux
  de formulaire : liens de connexion/inscription, copie et statut d’invitation,
  et sections dépliables. Les marges du premier et dernier élément restent
  contenues dans le panneau.

La reproduction locale de la connexion mesurait 0 px entre le bouton et le lien
« Mot de passe oublié ? » à 360 et 1 200 px ; elle mesure désormais 16 px.

## Vérification

Sur la pile de développement locale, avec PostgreSQL et Mailpit. Les contrôles
reprennent l’environnement de CI (`APP_ENV=test` et paramètres PostgreSQL), sans
exporter les variables SMTP vides du profil de développement dans les tests Compose :

```sh
APP_ENV=test ./scripts/check.sh
docker build -t muqola:ui-spacing .
uv run --frozen --group browser python scripts/ui_browser_smoke.py --browser /usr/bin/chromium
```

Le parcours navigateur existant vérifie maintenant les espacements visibles des
formulaires de connexion et d’inscription, de la carte et des actions de copie
d’invitation à 360 et 1 200 px, ainsi que le padding de l’état vide. Il conserve
ses parcours avec deux comptes fictifs, navigation clavier/tactile, presse-papiers
refusé, absence de JavaScript, recherche, demande datée et contenus longs à
360 / 390 / 768 / 1 200 / 1 280 px. Il produit 22 captures et un résultat JSON dans
`work/ui-redesign/`, également conservés par la CI.

Les captures mobile de connexion et communautés ont été inspectées localement.
Résultats exécutés : Ruff/format et mypy réussis, contrôles Django/migrations/
statiques réussis, **552 tests PostgreSQL réussis en 123,57 s**, build Docker réussi
et parcours navigateur complet réussi avec 22 captures, sans erreur JS/réseau.
La vérification automatisée utilise Chromium ; la validation du correctif sur
Firefox Android physique reste à faire après livraison autorisée sur le staging.
Les essais locaux ne constituent pas un déploiement sur le VPS.
