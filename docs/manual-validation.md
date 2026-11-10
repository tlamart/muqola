# Validation manuelle des lots 1 à 5 sur ordinateur

Utiliser uniquement des comptes et jeux fictifs. Aucun SMTP externe, paiement
ou VPS nécessaire. Docker Desktop/Engine + Compose v2, Git et Python 3.12 requis.
Les lots 1 à 5 et le correctif Gunicorn sont intégrés dans `main`. Depuis une
copie de développement sans modification non enregistrée, récupérer cette version :

```sh
git fetch origin &&
git switch main &&
git pull --ff-only origin main &&
git rev-parse HEAD &&
python3 scripts/init_dev.py &&
docker compose up --build --wait --wait-timeout 120
```

Si `main` n'existe pas encore localement : `git switch --track origin/main`,
puis reprendre à `git pull --ff-only origin main`. Si Git refuse le changement
de branche ou la mise à jour, arrêter la procédure et résoudre la divergence
sans forcer ni effacer les modifications. Noter le commit affiché avec les
résultats de validation. Pour tester une PR non fusionnée, sélectionner
explicitement sa branche à la place de `main` et noter son commit.

Application http://localhost:8000 ; Mailpit http://localhost:8025.
Conserver **localhost** partout pour ne pas mélanger les cookies avec 127.0.0.1.
La base et SMTP ne sont pas publiés ; les ports HTTP écoutent sur la boucle locale.
Le worker livre automatiquement les e-mails capturés. Trois profils de navigateur
séparés (Alice, Bob, Clara) sont pratiques ; deux onglets partagent la même session.
Un troisième navigateur/profil évite les limites des fenêtres privées partagées.

## 1. Comptes

1. Inscrire Alice `alice-demo@example.test` avec un mot de passe fictif robuste
   de 12 caractères minimum. Vérifier les erreurs de formulaire et les labels.
2. Avant confirmation, essayer Mon espace : accès refusé. Ouvrir le message dans
   Mailpit, suivre le lien, confirmer, puis se connecter. Le tableau de bord doit
   expliquer l'absence de communauté et proposer une collection privée.
3. Déconnexion/reconnexion ; mot de passe oublié depuis l'écran de connexion :
   nouveau message Mailpit, nouveau mot de passe, ancien mot de passe refusé.
   Un lien déjà consommé échoue. Un renvoi rend le précédent lien invalide.

Les limites antiabus sont actives ; après plusieurs scénarios attendre le délai
annoncé (inscription : 10 tentatives/heure/IP). Ne pas les désactiver pour valider.

## 2. Communautés privées

1. Alice crée A dans Mes communautés, génère un lien d'invitation.
2. Dans le profil Bob, ouvrir ce lien, créer `bob-demo@example.test`, confirmer
   via Mailpit (possible dans une autre fenêtre), se connecter puis **confirmer
   l'adhésion**. Pas d'entrée silencieuse. Bob voit Alice et A.
3. Clara `clara-demo@example.test` s'inscrit sans lien : URL directe de A refusée.
   Alice révoque un lien ; essayer ce lien côté Clara : erreur sans contenu privé.
4. Pour les scénarios suivants, inviter Clara dans A via un nouveau lien.
   Alice crée aussi B ; Bob peut rejoindre B pour tester deux visibilités.
5. Vérifier les droits membre/administrateur et le refus de départ du dernier
   administrateur. Tester le transfert sur une communauté d'essai distincte.
   L'expiration et les courses de permissions sont aussi couvertes automatiquement.

## 3. Fiche générique et exemplaires physiques

1. Alice : Ajouter un jeu → rechercher avant création → créer une fiche fictive
   (titre, joueurs, durée). Le formulaire avertit que ces métadonnées sont partagées.
2. Ajouter son exemplaire, commentaire « boîte Alice », visibilité **A seulement**.
3. Bob recherche le même titre, réutilise la fiche et crée « boîte Bob » sans
   communauté : Alice ne voit pas cet exemplaire, même par URL directe.
4. Bob édite sa copie et choisit A et B : les membres autorisés la voient une seule
   fois dans Trouver un jeu. Retirer toute visibilité : elle redevient privée.
5. Tester titre avec accents/casse, filtres communauté/joueurs/disponibilité,
   résultat vide, retrait du prêt, et deuxième exemplaire de la même fiche.
6. Alice ne peut plus réécrire sa fiche après réemploi par Bob : signaler/corriger
   par maintenance ; chacun conserve l'édition de sa propre copie.

## 4. Prêt et confidentialité

1. Bob demande la copie Alice : date future obligatoire, date du jour refusée
   (Europe/Paris), message facultatif. La demande ne réserve pas le jeu.
2. Clara demande aussi cette copie. Deux demandes en attente sont possibles ;
   Bob ne peut pas doubler la sienne. Aucun contact e-mail dans le catalogue ni
   dans une demande en attente.
3. Alice accepte Bob : adresses visibles aux **deux parties seulement** ; demande
   Clara annulée avec motif. Tenter d'accepter celle de Clara : refus. L'exclusivité
   simultanée réelle est vérifiée par tests PostgreSQL, pas par la seule UI.
4. Alice retire Bob de A (et retirer une autre visibilité commune si nécessaire) :
   Bob perd l'accès à la copie, garde son prêt accepté. Clara n'accède pas au prêt.
5. Alice seule confirme remise puis retour ; Bob ne dispose pas de ces actions.
   Après retour, les contacts disparaissent du détail et de l'historique rendu.
   Le jeu redevient disponible s'il n'a pas été retiré du prêt.
6. Autres demandes : essayer refus, annulation avant remise, perte de visibilité
   pendant l'attente. Les parties reçoivent une notification de clôture. Un prêt
   remis ne peut pas être annulé normalement. Archivage d'une copie active refusé.

## 5. Notifications, compte et ergonomie

1. Dans Mailpit, vérifier demande, acceptation/refus, annulation, remise et retour.
   Chaque message renvoie vers le prêt privé sans contenir l'adresse de l'autre.
   Un tiers connecté qui suit ce lien reçoit une erreur.
2. Pour tester la persistance sans panne réelle : `docker compose stop worker`,
   effectuer une demande, puis `docker compose start worker`. Le message doit
   arriver. Pour SMTP indisponible : arrêter Mailpit, effectuer une transition,
   constater que le prêt reste enregistré, redémarrer Mailpit et attendre la reprise
   (premier délai 60 secondes, puis jusqu'à une heure). Les 20 échecs et la reprise
   manuelle sont vérifiés par tests ; commandes de diagnostic dans le document lot 5.
3. Mon espace → Mon compte → confirmer la demande de suppression. Elle doit
   rester enregistrée après actualisation. Avec prêt actif, le préalable de clôture
   est indiqué. Il s'agit d'une demande persistée, pas encore d'un effacement définitif.
4. Réduire la fenêtre à 360, 768 puis 1280 px ; naviguer au clavier (Tab, Entrée,
   Espace), vérifier focus, labels, dates lisibles, confirmations, erreurs et absence
   de défilement horizontal. Vérifier également les listes vides et sans résultat.
5. Dans les outils navigateur, passer hors ligne : message compréhensible ; remettre
   en ligne et consulter Mes prêts avant de répéter un POST incertain. Tester aussi
   connexion/formulaires sans JavaScript. Ces actions restent validées au serveur.

## Vérifications reproductibles et arrêt

Avant ces contrôles sur l'hôte, suivre la préparation de
[Développement hors conteneur et vérifications du README](../README.md#développement-hors-conteneur-et-vérifications) :
environnement uv, chargement du `.env` local et accès PostgreSQL par le port
local documenté. Le démarrage Compose seul ne publie pas PostgreSQL sur l'hôte.

```sh
# Avec uv 0.13.5 ; base locale exposée uniquement à la boucle locale selon README :
./scripts/check.sh
uv sync --frozen --group browser
uv run --frozen --group browser python scripts/accounts_browser_smoke.py --browser /usr/bin/chromium
uv run --frozen --group browser python scripts/product_browser_smoke.py --browser /usr/bin/chromium
# Adapter --browser au chemin du Chromium/Chrome installé.
docker compose stop
```

Les scripts navigateur créent des données fictives ; ne jamais les lancer en
production. `docker compose down` conserve la base, `down --volumes` la détruit :
ne pas l'utiliser pour cette validation. Aucun déploiement de production à ce stade.
Pour Android, le [guide Codespaces](codespaces-android.md) reste applicable en
choisissant `main` ; conserver les URL HTTPS privées et les commandes du profil
Codespaces décrites dans ce guide.
