# Passe UX/UI finale du MVP

## Référence, périmètre et audit

Référence principale : image jointe `22421.png`, « Option 2 : Moderne et ludique »,
consultée directement. Le cadre du téléphone, le titre de la planche, « Points
forts » et la palette sont des annotations, pas des écrans à implémenter.
Les anciennes frames Figma ont guidé la première refonte ; cette passe privilégie
la nouvelle image. Celle-ci représente l’accueil desktop et mobile, sans maquette
séparée pour Explorer ou la fiche : ces deux écrans reprennent ses composants.

`main` a été actualisé : `6160534`. La PR #10 est encore ouverte ; la branche
`feat/ui-mvp-polish` reprend ses trois commits, puis cette passe ciblée. La nouvelle
PR vise `main`, comme demandé ; aucune fusion ni clôture de PR n’est effectuée.
Le diff propre à cette passe se consulte également en comparant avec `604a12e`.

| Priorité / écran | Trois écarts les plus visibles dans les captures initiales | Correction retenue |
| --- | --- | --- |
| P0 accueil | Grand bloc violet uni détaché de la navigation ; navigation sans icônes ; même longue composition desktop/mobile | Bandeau violet dégradé immédiatement sous la barre, dés décoratifs CSS et deux CTA ; onglet actif arrondi et icônes ; quatre raccourcis mobiles colorés puis prochaine action |
| P1 Explorer | Filtres peu différenciés ; visuels plats et badges minuscules ; hiérarchie typographique peu proche de la référence | Filtres en pastilles avec état sélectionné explicite ; cartes communes avec motifs neutres et statut à point + texte ; texte bleu nuit et header commun |
| P1 fiche | Grand rectangle mobile avant les informations ; disponibilité et demande trop bas ; carte d’exemplaire peu distincte | Petit visuel à côté du résumé mobile ; statut en tête et demande jaune pleine largeur ; bordure et propriétaire/communautés clairement regroupés |
| P2 autres écrans | Navigation et couleurs communes | Héritent des ajustements partagés ; pas de nouvelle refonte des formulaires, communautés ou prêts |

## Modifications limitées

- Django, templates, CSS, Inter locale et JavaScript existants conservés. Icônes
  SVG locales dans un seul partial ; décoration du hero en CSS, masquée aux aides
  techniques. Aucun téléchargement d’image, service, framework ou dépendance ajouté.
- Liens réels pour tous les raccourcis et filtres. Le lien « Par communauté » ouvre
  les filtres natifs sans JavaScript. Le libellé annonce aussi le filtre joueurs.
- Compteurs du mobile calculés sur les seules appartenances actives, exemplaires
  propres non archivés et prêts participant au compte dans les états déjà suivis.
  Aucun nombre de la maquette n’est codé dans l’application.
- Prochaine action issue des résumés de prêts existants ; aucun contact ajouté.
  État vide conservé. Les demandes en attente ne sont toujours pas des réservations.
- Visuels neutres de remplacement, titres et métadonnées dynamiques conservés.
  Disponible, indisponible et retiré restent distingués par du texte ; l’état
  indisponible n’est pas renommé « Emprunté » car il ne prouve pas ce motif.
- Aucun modèle, migration, service métier, règle d’autorisation, transition de prêt,
  configuration Gunicorn ou paramètre de production modifié.

## Comparaison visuelle exécutée

Playwright + Chromium local, vrai Gunicorn, PostgreSQL et Mailpit de développement.
Base isolée avec deux comptes fictifs, communauté privée, quatre jeux et demande
réelle créée via les formulaires. Même base, mêmes sessions et mêmes routes pour
les captures avant/après : les différences ne proviennent pas d’un changement de
contenu. Les valeurs de fixture ne sont jamais injectées dans les vues.

Trois passages visuels au maximum par écran :

1. Captures initiales 1200 / 390 px, inspection des six images et relevé des trois
   écarts par écran dans le tableau ci-dessus.
2. Corrections ciblées, nouvelles captures aux deux tailles, inspection des six
   images face à la référence. Vérification supplémentaire à 360 / 768 px.
3. Ajustement du détail en deux colonnes dès 700 px pour éviter un grand visuel
   empilé sur tablette ; nouvelles captures des trois écrans aux quatre largeurs.
   Inspection du résultat tablette. Les rendus 1200 / 390 px sont conservés.

Résultat : barre verte et hero contigus, deux CTA, rythme des cartes et filtres
cohérents ; mobile blanc avec raccourcis violet/jaune/corail/bleu et prêt à suivre.
Sur la fiche mobile, l’action de demande est visible dès le premier écran avec la
fixture, alors qu’elle était beaucoup plus basse dans la capture initiale.

| Écran | Avant desktop 1200 | Après desktop 1200 | Avant mobile 390 | Après mobile 390 |
| --- | --- | --- | --- | --- |
| Accueil | [Avant](screenshots/ui-final/before/accueil-1200.png) | [Après](screenshots/ui-final/after/accueil-1200.png) | [Avant](screenshots/ui-final/before/accueil-390.png) | [Après](screenshots/ui-final/after/accueil-390.png) |
| Explorer | [Avant](screenshots/ui-final/before/explorer-1200.png) | [Après](screenshots/ui-final/after/explorer-1200.png) | [Avant](screenshots/ui-final/before/explorer-390.png) | [Après](screenshots/ui-final/after/explorer-390.png) |
| Fiche | [Avant](screenshots/ui-final/before/jeu-1200.png) | [Après](screenshots/ui-final/after/jeu-1200.png) | [Avant](screenshots/ui-final/before/jeu-390.png) | [Après](screenshots/ui-final/after/jeu-390.png) |

Les douze captures sont versionnées. Les captures des cinq largeurs du parcours
complet sont aussi produites par le script existant et archivées par la CI.

## Vérifications

Exécuter sur une pile de développement isolée avec le worker d’outbox et Mailpit :

```sh
./scripts/check.sh
uv run --frozen --group browser python scripts/browser_smoke.py --browser /usr/bin/chromium
uv run --frozen --group browser python scripts/accounts_browser_smoke.py --browser /usr/bin/chromium
uv run --frozen --group browser python scripts/product_browser_smoke.py --browser /usr/bin/chromium
uv run --frozen --group browser python scripts/ui_browser_smoke.py --browser /usr/bin/chromium
```

Pour un serveur sur un autre port, ajouter `--url=http://127.0.0.1:PORT` aux scripts.
La pile Compose documentée dans le README utilise le port 8000 par défaut. Aucun
port PostgreSQL ou SMTP n’est publié par la configuration Compose du projet.

Résultats locaux exécutés :

- `./scripts/check.sh` : Ruff, formatage (123 fichiers), mypy (79 sources), contrôles
  Django, absence de migration et collecte statique réussis ; **135 tests réussis
  en 55,90 s** avec PostgreSQL, dont confidentialité et concurrence.
- Les quatre scripts Playwright : **succès**. Inscription/vérification/connexion/reset,
  invitation et adhésion explicite, fiche réutilisée et exemplaire privé, recherche,
  disponibilité, demande datée, acceptation/remise/retour et contacts temporaires.
- Parcours UI à **360 / 390 / 768 / 1200 / 1280 px** : clavier, focus visible,
  menu tactile émulé, Escape/resize/compte, filtres, absence de résultat, quatre
  raccourcis avec compteurs réels, ouverture du filtre communauté sans JS et
  contenus longs ; aucune erreur JavaScript ou ressource réseau signalée.
- Contrôle complémentaire communautés/collection/prêts/compte à 360 / 768 / 1200 px :
  aucun débordement ; inspection des captures mobile des pages secondaires.
- Dix paires texte/fond principales calculées : contrastes **4,78:1 à 12,24:1**.
  Disponibilité lisible sans couleur ; labels et erreurs serveur conservés.
- Régression serveur incluse : connexions HTTP silencieuses au-delà du watchdog
  réel, keep-alive et requêtes fragmentées, sans modifier Gunicorn.

Les liens et résultats de CI sont consignés dans la PR ; ils incluent le build
Docker complet et les parcours existants sur le profil HTTPS Codespaces.

## Différences et limites assumées

- Couvertures neutres selon SPEC §5, sans les illustrations commerciales des boîtes.
  Les dés CSS sont décoratifs, moins détaillés que le rendu 3D de la référence.
- Avatar initiale du compte ; pas de cloche sans fonctionnalité de notifications.
  « Communautés » reste explicite ; pas de nouveau concept « groupes » distinct.
- Données et ordre réels ; trois exemplaires dans l’aperçu desktop, deux sur mobile.
  Le détail permet toujours de gérer son propre exemplaire, pas de se l’emprunter.
- En dessous de 700 px, l’accueil privilégie les raccourcis de la référence mobile ;
  le hero illustré reste réservé aux écrans plus larges. Avec des titres longs,
  les cartes et le résumé s’agrandissent naturellement.
- Chromium émulé, pas de téléphone Android physique, Safari ou audit exhaustif de
  lecteur d’écran. Inspection visuelle et contrôles clavier/labels/contrastes ciblés,
  pas de certification d’accessibilité.
- PostgreSQL et Mailpit sous Docker local ; application lancée sur l’hôte. Le build
  complet Compose est réservé à la CI à cause de l’espace Docker vfs local limité.
- Aucun déploiement, aucune dépense, aucune tâche du lot 6. Arrêt à cette passe MVP.

## Validation manuelle proposée

1. À 1200 px puis sur téléphone : ouvrir `/` après connexion, vérifier l’accueil
   privé, les quatre raccourcis mobiles et les compteurs de son propre compte.
2. Accéder à sa communauté ; ouvrir « Par communauté », sélectionner un groupe,
   rechercher un titre, filtrer les exemplaires disponibles, essayer un résultat vide.
3. Ouvrir une fiche, identifier le propriétaire et la disponibilité, demander un
   exemplaire d’un autre membre avec une date future.
4. Depuis « Mes prêts », faire accepter, remettre puis rendre ; vérifier que les
   e-mails de contact n’apparaissent que pendant le prêt actif accepté.
5. Parcourir au clavier le menu, le compte, la recherche et les actions ; essayer
   aussi avec JavaScript désactivé. Vérifier les écrans avec collection/communauté vide.
