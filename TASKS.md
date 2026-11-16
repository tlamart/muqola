# Muqola — Plan de livraison du MVP

> Les durées ne sont pas des engagements. Chaque lot doit être démontrable avant de passer au suivant.
> Les lots 0–5 ci-dessous décrivent les livraisons historiques ; leurs cases cochées
> ne valident pas les nouvelles exigences. Le prochain travail est le plan **B → A → C**
> en fin de document, soumis à validation avant toute implémentation.

## Lot 0 — Décision technique et socle
- [x] Lire le kit, rédiger `docs/adr/0001-stack.md` et documenter les compromis.
- [x] Initialiser dépôt, monolithe modulaire, PostgreSQL, migrations, Docker Compose, capture locale des e-mails.
- [x] Configurer lint/format, tests, CI, `.env.example`, README et healthcheck.
**Acceptation :** une commande documentée démarre l'application et la base localement ; CI passe sur un dépôt propre. Si Docker n'est pas exécutable dans Codex Cloud, exiger la validation locale de cette commande avant fusion.

## Lot 1 — Comptes
- [x] Inscription ouverte, validation serveur, hachage des mots de passe, nom d'affichage.
- [x] Vérification d'e-mail obligatoire, lien expirant/usage unique, renvoi limité ; lien après inscription utilisable même sans avoir de compte connecté.
- [x] Connexion, déconnexion, récupération de mot de passe, sessions sûres.
- [x] Protection contre abus et énumération ; tests des liens expirés et non vérifiés.
**Acceptation :** inscription autonome sans validation administrateur ; impossible d'accéder au métier sans vérification.

## Lot 2 — Communautés
- [x] Création, liste et détail privés ; rôles administrateur/membre.
- [x] Invitations partageables expirables/révocables ; inscription depuis invitation.
- [x] Adhésion confirmée après connexion/vérification (sans adhésion silencieuse), départ, retrait d'un membre, transfert minimal du rôle administrateur.
- [x] Tests de permissions et d'invitations invalides.
**Acceptation :** Bob rejoint la communauté d'Alice via lien ; un non-membre n'accède à rien.

## Lot 3 — Catalogue interne et exemplaires
- [x] Modèles `Game`, `OwnedGame`, `GameVisibility` et contraintes.
- [x] Recherche des fiches `Game` existantes, sélection, création manuelle si absente ; réemploi d'une fiche pour un second exemplaire.
- [x] Création/édition d'exemplaire, **zéro ou plusieurs** communautés de visibilité, retrait du prêt ; édition des métadonnées génériques sans écraser une fiche partagée.
- [x] Recherche/filtres dans les communautés autorisées ; aucun leak d'exemplaire privé. Visuel neutre sans images distantes requises.
**Acceptation :** deux membres ajoutent chacun un exemplaire de la même fiche ; seules les communautés choisies voient chaque exemplaire.

## Lot 4 — Prêts
- [x] Demande avec date civile de retour future obligatoire (Europe/Paris), acceptation/refus/annulation et revalidation d'éligibilité à l'acceptation.
- [x] **Propriétaire** confirme remise et retour ; historique privé par participant ; clôture possible après perte de communauté.
- [x] Exclusivité atomique d'un prêt accepté/en cours par exemplaire (contrainte DB + transaction), demandes concurrentes clôturées ; tests concurrents sur PostgreSQL.
- [x] E-mail de contact visible aux deux parties uniquement pendant `ACCEPTED`/`HANDED_OVER` ; jamais dans les résultats de catalogue.
**Acceptation :** prêt complet Alice/Bob ; double acceptation concurrente impossible.

## Lot 5 — Notifications et UX
- [x] E-mails transactionnels pour les événements prévus ; fournisseur configurable, outbox PostgreSQL, reprise des envois après erreur/redémarrage.
- [x] Écrans vides, erreurs, états de chargement, formulaires accessibles.
- [x] Vérification des parcours sur mobile, tablette et ordinateur (Chromium 360/768/1280 px ; matériel réel à valider).
**Acceptation :** parcours complet compréhensible sans assistance ; aucune dépendance aux e-mails réels en tests.

## Lot 6 — Préproduction et mise en ligne

**État initial historique (après PR #22) :** Django 5.2/PostgreSQL 17, Compose **local**, Gunicorn/WhiteNoise, outbox et worker, logs JSON, CI, contrôles Django, catalogue interne, ajout rapide et commande d'import CSV local existent déjà. Ne pas les réimplémenter. Le lot 6 livre leur **configuration et validation de production**, sans modifier le développement local.

- [ ] Finaliser/valider la préparation Caddy et Compose distinct livrée en PR #24 (voir `docs/lot-6-infrastructure.md`), HTTPS réel, configuration DNS et **Compose de production distinct** (ne pas déployer `compose.yaml` local : `APP_ENV=development`, Mailpit et ports loopback). Configurer `APP_ENV=production`, `APP_BASE_URL` HTTPS, hôtes/CSRF, proxy de confiance, cookies, secrets distincts, PostgreSQL persistant à privilèges minimaux, services non exposés et limites adaptées au VPS.
- [ ] Configurer un fournisseur SMTP transactionnel réel **sur l'outbox et le worker existants**, DNS SPF/DKIM/DMARC, et vérifier délivrabilité, liens de vérification et réinitialisation ; ne pas utiliser Mailpit en production.
- [ ] Mettre en place sauvegardes PostgreSQL **externes, chiffrées, à rétention définie** (incluant les fiches importées), et tester une restauration isolée ; ajouter supervision, alertes, suivi du worker, disque et sauvegardes en réutilisant les logs JSON existants.
- [ ] Compléter mentions légales, politique de confidentialité, CGU, contact, conservation et procédure **effective** de traitement des demandes de suppression de compte existantes, avec données réelles de l'exploitant ; décider explicitement des conditions d'accès des mineurs.
- [ ] Vérifier limites de débit, permissions intercommunautés, transitions et prêts concurrents, erreurs, secrets, proxy/HTTPS et cookies réels, migrations, sauvegarde avant migration et rollback documenté. Exécuter CI, `check --deploy`, tests navigateur et parcours avec deux comptes.
- [ ] Appliquer la décision catalogue de la PR B : base neuve vide, aucun ancien import BGG/Wikidata ni catalogue réel dans Git/image. Inventorier les éventuelles données héritées sans les supprimer ; la commande CSV historique ne doit pas alimenter le nouveau catalogue.
- [ ] Déployer **uniquement après validation humaine explicite** et exécuter un test de fumée en production ; ne pas provisionner ni déployer pendant la préparation documentaire.
**Acceptation :** site HTTPS public ; un nouveau compte peut être créé et vérifié ; un prêt complet fonctionne ; sauvegarde restaurable ; aucun problème de sécurité bloquant connu.

## Scénarios E2E incontournables
1. Inscription libre → vérification → connexion.
2. Lien d'invitation → inscription → adhésion ; expiration/révocation.
3. Création fiche jeu → second utilisateur réutilise la fiche → exemplaire distinct ; un utilisateur sans communauté peut créer un exemplaire privé.
4. Visibilité A uniquement → utilisateur de B bloqué même via URL/API.
5. Demande → acceptation → partage e-mail → remise → retour.
6. Deux acceptations simultanées sur un même exemplaire → une seule réussit.
7. Membre retiré → accès aux exemplaires via cette communauté immédiatement révoqué ; prêt déjà accepté toujours clôturable par ses participants.
8. Réinitialisation de mot de passe, suppression de compte, erreur réseau et affichage mobile.

## Après le MVP — uniquement sur décision explicite
Intégration/synchronisation externe, rappels automatiques, chat, événements, notation, objets autres que jeux, applications natives, paiement/dons. Illustrations contrôlées, propositions et invitations permanentes sont désormais dans le plan B/A/C ; aucun import des anciens CSV n'est prévu.


## Prochaines PR — B → A → C (plan à valider)

**Périmètre de cette PR documentaire :** audit, décisions fonctionnelles et plan uniquement. Aucune modification Python, SQL, migration, template, CSS/JS ou CI. [Audit sourcé et décisions techniques](docs/plan-b-a-c.md). Base auditée initialement le 15 novembre 2026, puis réconciliée le 16 novembre sur `main` au commit `e0fa4caa26aeb38a2b505405ea8c4dd8772913d9`, après fusion de #25.

Les branches de travail futures seront créées **après validation du plan**. Une branche/PR par lot ci-dessous ; chaque PR doit fonctionner et passer la CI sans attendre la suivante. Ne pas confondre ces lettres avec les anciens lots 0–6 ou des numéros GitHub.

### PR B — Refonte du catalogue

**Objectif :** une fiche par jeu, propositions modérées, types/extensions/alias, correction et fusion sûres, catalogue neuf vide. Conserver `Game`/`OwnedGame`/`GameVisibility`, les prêts, les contrôles serveur et l'outbox.

**Dépendances :** `main` + validation du plan et des arbitrages B1–B4 de l'audit. Ne dépend pas de A ou C. La PR #25 Wikidata est désormais intégrée à `main` : réutiliser `GameAlias`, `GameIllustration`, recherche d'alias et métadonnées de licence/provenance. Conserver `0002_wikidata_catalogue` intacte ; les migrations B viennent après elle, sans recréer les modèles existants.

**Tâches techniques (ordre proposé)**
- [ ] B.1 Inventorier toutes les FK vers `Game`/`OwnedGame`, fiches externes, homonymes et types inconnus, sans exposer de données privées. Documenter le bilan attendu, sauvegarde/restauration et compatibilité de retour arrière ; utiliser une copie synthétique peuplée en tests, jamais la production.
- [ ] B.2 Préparer migrations **additives** : statut de modération distinct de `hidden`, type incluant inconnu pour proposition, relation de base ; réutiliser les alias normalisés existants et leurs contraintes. Ajouter contraintes des fiches validées et validations des extensions (base obligatoire si dépendante, pas d'auto-référence/cycle). Définir les index, unicité des alias par fiche, règles FK `PROTECT`, référence de fusion et conservation des identifiants externes.
- [ ] B.3 Distinguer les lignes héritées sans type connu des nouvelles propositions : aucune validation/type fabriqué, aucun `DELETE`/`TRUNCATE`/reset, pas de réécriture de `0001`. Garder les UUID et les références aux exemplaires/prêts ; documenter le traitement de chaque état hérité et les accès transitoires selon B1. Une base neuve reste vide sans compte/fiches d'import automatiques.
- [ ] B.4 Faire passer **tous** les chemins d'écriture (ajout rapide, ancien formulaire, correction, console et deux commandes d'import historiques) par les règles cible. Retirer le contournement « autre édition » ; conserver le réemploi et les exemplaires multiples/privés. Pour ces PR, neutraliser les parcours `import_games`/`import_wikidata_games` pour la cible BGG/Wikidata sans effacer leurs données existantes ; décider explicitement de la conservation du code historique. Garder une recherche synchrone fonctionnelle jusqu'à A.
- [ ] B.5 Implémenter proposition titre seul/type inconnu et suivi auteur ; l'exemplaire privé peut référencer cette fiche en attente (proposition B1). Interdire le réemploi public et le prêt d'une nouvelle proposition non validée. Aucun accès tiers par UUID aux propositions, commentaires ou photos ; partager l'exemplaire après validation selon les choix explicites du propriétaire, sans communauté ajoutée automatiquement.
- [ ] B.6 Étendre les services/commandes `operations` existants : file de propositions, décision motivée, validation avec contrôle serveur des doublons, correction, rejet et signalements. Un administrateur de communauté ne devient pas modérateur du catalogue. Journaliser acteur, motif, états et cible sans secrets.
- [ ] B.7 Fournir suggestions exactes normalisées sur titre/alias avant proposition et avant validation ; garde serveur atomique dans `domain_write` pour toutes les créations/validations. Ne pas imposer l'unicité globale du titre ; exiger une justification de vraie homonymie. Le fuzzy sera ajouté en A. Ne pas divulguer une proposition tierce parmi les suggestions utilisateur.
- [ ] B.8 Fusion administrative transactionnelle avec simulation/bilan, confirmation source/cible et motif : conserver `OwnedGame.id`/owner, ne pas fusionner les exemplaires physiques ni modifier les FK `Loan.owned_game`. Replacer références de fiches, alias, bases, signalements et IDs externes ; gérer conflits d'alias/ID et deux signalements ouverts d'un même auteur sans les perdre. Garder une trace/source redirigeable avec mêmes contrôles d'accès, sans boucle. Conserver `ever_reused` et les masquages ; fusion refusée si elle rétablit un accès ou crée un cycle.
- [ ] B.9 Réutiliser `GameIllustration` et préserver métadonnées licence/source/attribution, illustrations approuvées et visuel local par défaut ; prévoir une approbation séparée des futures photos utilisateur, sans affaiblir la validation Commons existante. Si upload retenu en B4 : stockage privé, endpoint de lecture autorisé, taille/type réel/limites, traitement d'image sûr et contrôle des droits, sans publication automatique. Sinon ne pas ouvrir de champ photo/URL non sécurisé ; documenter le report de collecte des photos.
- [ ] B.10 Adapter formulaires/messages, bornes et fixtures **synthétiques**, tests existants et scripts navigateur qui créent aujourd'hui directement une fiche ; maintenir le parcours complet après validation opérateur, sans préjuger de A. Actualiser README et documentation du schéma.

**Critères d'acceptation**
- [ ] Une nouvelle installation reste vide ; aucune donnée externe, aucun import implicite ni catalogue réel versionné/embarqué. Sur base peuplée, toutes les références et tous les états de prêts sont conservés.
- [ ] Un utilisateur vérifié sans communauté propose un titre et garde un exemplaire privé ; le type inconnu empêche la validation, pas la soumission. Un tiers ne trouve ni proposition ni photo. Une fiche validée exige titre/type/base applicable ; métadonnées facultatives réellement facultatives.
- [ ] Jeux autonomes, extensions dépendantes et extensions jouables seules sont représentables ; deux éditions commerciales ne justifient pas deux fiches. Alice et Bob possèdent des exemplaires distincts d'une même fiche.
- [ ] Seul un opérateur autorisé valide/corrige/fusionne ; le contrôle des doublons s'applique aussi sans JS et en concurrence. Une fusion préserve propriétaires, visibilités, demandes, prêts et liens ; un masquage n'est pas annulé.
- [ ] L'ajout/recherche synchrone, les prêts et leur clôture fonctionnent **avant A**. Pas d'ouverture des droits de communauté.

**Tests automatisés nécessaires**
- [ ] Migrations sur base vide et snapshot synthétique issu du schéma actuel : fiches manuelles/importées/masquées/réutilisées, alias/illustrations/crédits de `0002_wikidata_catalogue`, copies privées/multicommunautés/retirées/archivées, prêts de tous états, signalements ; comparer UUID/FK/états avant/après et tester reprise/retour compatible. Pas de purge en reverse migration.
- [ ] Contraintes type/base, alias, homonymes ; proposition titre seul, contrôle des champs facultatifs, XSS, droits auteur/opérateur/administrateur de communauté/non vérifié/tiers.
- [ ] Concurrence PostgreSQL : doubles propositions/validations, validation face à correction/fusion, fusion face à prêt/ajout d'exemplaire ; rollback complet sur conflit et absence de références perdues.
- [ ] Fusion avec plusieurs IDs externes, signalements en conflit, ancienne URL et fiche masquée ; prêts actifs toujours clôturables et exclusivité par exemplaire maintenue. Tests d'image privée si collecte autorisée.
- [ ] Adapter `test_quick_add`, `test_inventory`, `test_operations`, tests de migrations et parcours navigateur ; suite de prêts/communautés et CI complète de non-régression.

**Risques et réponses :** purge involontaire → migrations additives/bilan ; validation fictive des données héritées → statut transitoire explicite ; doublons d'éditions → révision humaine ; perte de références → fusion logique sans suppression ; fuite de propositions/photos → permissions avant toute lecture ; blocage du parcours existant → scénario synchrone livré en B ; régression du socle #25 → réemploi des modèles et conservation de sa migration.

**Validation manuelle**
1. Sur base locale neuve, constater l'état vide puis proposer un titre seul ; ouvrir avec un tiers et vérifier la confidentialité.
2. Faire compléter/valider par l'opérateur, réutiliser avec un second compte, ajouter deux copies et une copie sans communauté ; tester une extension avec/sans base.
3. Essayer le doublon par POST direct et « autre édition » ; corriger puis fusionner deux fiches synthétiques ayant des propriétaires/prêts/signalements différents.
4. Rejouer un prêt complet et clôturer un prêt déjà accepté après retrait de membre ; comparer UUID et références après migration/fusion, ouvrir ancienne URL ; tester à 360 px et au clavier.

### PR A — Recherche intelligente

**Objectif :** recherche instantanée, pertinente et accessible, dans deux périmètres distincts, avec regroupement par jeu et prévention serveur des doublons.

**Dépendances :** B intégrée (statuts, alias, types et canonisation stabilisés). Ne dépend pas de C. A doit fonctionner avec les communautés privées existantes.

**Tâches techniques**
- [ ] A.1 Réutiliser `normalized_title`, `title_condition` et `matching_title` déjà intégrés par #25 pour principal/alias ; centraliser la sélection des fiches canoniques sans dupliquer ce moteur synchrone. Définir recherches « ajouter » et « emprunter » explicitement. Pour emprunter, partir du sous-ensemble autorisé des exemplaires partageables dans les communautés actuelles ; ne pas utiliser le catalogue global comme résultat de repli. Garder collection personnelle et emprunt distincts.
- [ ] A.2 Évaluer `pg_trgm` avec `TrigramExtension` Django et index GIN sur clés normalisées principal/alias ; vérifier disponibilité et rôle de migration sur PostgreSQL 17 (rôle runtime sans privilège de création d'extension). Éviter `unaccent` supplémentaire si la clé normalisée suffit. Mesurer le plan sur corpus synthétique ; pas de nouveau service.
- [ ] A.3 Fixer classement déterministe : exact principal/alias, préfixe, contenu, similarité trigramme, puis titre/UUID. Calibrer seuils avec cas français, fautes, titres courts et homonymes ; stratégie exacte/préfixe pour deux caractères. Utiliser un meilleur score par fiche, sans multiplier les lignes par alias.
- [ ] A.4 Regrouper par `Game` canonique **après** droits/filtres ; compter chaque copie autorisée une fois même multicommunautés. Une carte par fiche ; détail listant les copies empruntables et leur disponibilité. Maintenir filtres communauté/joueurs/disponibilité, pagination bornée et URLs partageables. Aucun nom/compteur privé ni e-mail dans l'endpoint.
- [ ] A.5 Fournir endpoint GET de fragments HTML Django (proposition A1), authentifié/vérifié et sans cache partagé ; même sélection et même rendu pour GET classique/asynchrone. Borner longueur de saisie, pagination et travail serveur, mesurer SQL et latence ; mettre à jour attentes MUQ-05 si requêtes légitimement modifiées, sans supprimer la borne de requêtes.
- [ ] A.6 JavaScript local : seuil ~2 caractères, debounce ~250 ms, `AbortController` et numéro de requête pour ignorer réponses obsolètes, gestion saisie IME, remise à zéro et filtres. Retirer le bouton Rechercher ; repli GET avec Entrée sans JS. Ne pas déplacer le focus ou perdre une sélection de jeu/notes/partages durant la mise à jour.
- [ ] A.7 Autoriser `connect-src 'self'` dans la CSP actuelle (qui a `default-src 'none'`) pour le fetch local, sans ouvrir les autres origines. Prévoir `aria-busy`, zone de statut polie pour chargement/résultats/erreur, labels et liens clavier ; annulation, erreur réseau et aucun résultat utilisables.
- [ ] A.8 Réutiliser le moteur pour suggestions utilisateur **et administrateur** ; conserver garde serveur B à la soumission et recontrôle à la validation, même POST sans JS. Un score fuzzy seul ne fusionne ni ne rejette un homonyme.
- [ ] A.9 Mettre à jour UI, scripts/tests et documentation des index, scores, seuils, mesures et privilèges. Éviter logs de texte recherché et caches mélangeant les acteurs.

**Critères d'acceptation**
- [ ] Après deux caractères et ~250 ms sans nouvelle saisie, les résultats se mettent à jour sans bouton ni rechargement ; la dernière saisie gagne, y compris si les réponses arrivent dans le désordre. Les filtres restent effectifs.
- [ ] Titre principal/alias, accents/casse et fautes prévues retrouvent le jeu avec classement stable ; une carte par jeu, copie multicommunautés comptée une seule fois.
- [ ] En ajout, seules métadonnées validées ; en emprunt, seuls jeux ayant des copies autorisées. Ajouter une copie invisible ne change ni résultat, ni compte, ni rang, ni pagination. Aucun accès étranger par URL/fragment/suggestion.
- [ ] Clavier, lecteur d'écran, 360 px, absence de JS et panne réseau permettent de poursuivre le parcours. Le contrôle serveur des doublons reste actif.

**Tests automatisés nécessaires**
- [ ] PostgreSQL réel : extension/index appliqués depuis base vide et peuplée ; exact/préfixe/alias/accents/espaces/fautes, titres courts, seuils, ordre stable et absence de doublons d'alias.
- [ ] Matrice d'autorisations catalogue/emprunt : aucune communauté, A/B, plusieurs communautés, retrait de membre/propriétaire, exemplaire privé/retiré/archivé, fiche masquée/en attente/fusionnée. Vérifier compteurs, badges, ordre, filtres, pagination, JSON/HTML et IDOR.
- [ ] Navigateur avec contrôle du temps et des réponses : debounce/seuil, annulation/course de réponses, IME, effacement, filtres, sélection conservée, clavier, annonces, erreur réseau, JS désactivé et CSP réelle.
- [ ] Budgets SQL bornés sans N+1 (1/10/30/65 copies et plusieurs alias) ; benchmark synthétique plus volumineux avec p50/p95, protocole et matériel consignés avant de fixer un budget de latence.
- [ ] Suggestions et POST directs/concurrents ne contournent pas B ; CI complète, dont parcours des prêts.

**Risques et réponses :** fuite par agrégation/rang → filtrer d'abord ; faux positifs → classement et revue humaine ; lenteur sur petites saisies → index/borne/mesure ; fetch bloqué → test CSP navigateur ; courses JS → annulation + numéro ; changement de schéma B → A après B.

**Validation manuelle**
1. Chercher par principal/alias, accents et faute sur corpus synthétique ; taper vite, effacer, changer les filtres, naviguer au clavier et revenir à la page précédente.
2. Avec deux communautés et une collection privée, comparer les résultats/comptes avant et après retrait de membre ; ouvrir un endpoint directement et vérifier le refus au compte non vérifié/tiers.
3. Vérifier une fiche avec plusieurs copies dont une partagée deux fois et une privée ; sélectionner une copie et demander le prêt ; tester hors ligne, sans JS et à 360 px.

### PR C — Refonte des communautés et invitations

**Objectif :** cartes complètes et accessibles, création dédiée, lien permanent consultable par tous les membres et rotation réservée aux administrateurs, en maintenant les droits privés.

**Dépendances :** `main` + validation du plan et C1–C2. L'indépendance fonctionnelle de B est confirmée : tables/services `communities` autonomes, interactions inventory/loans déjà encapsulées. Développement possible en parallèle **sur branche séparée**. Intégration proposée après A ; résoudre les conflits potentiels sur CSS/JS, docs et scripts navigateur, puis rejouer toute la CI. Le mode de découverte publique reste à préciser avant implémentation ; ce n'est pas une dépendance du reste de C.

**Tâches techniques**
- [ ] C.1 Séparer liste GET et route dédiée GET/POST de création ; déplacer `CommunityForm`, conserver validation, CSRF, vérification e-mail, limitation de débit, création atomique du rôle admin, messages et redirection.
- [ ] C.2 Enrichir la liste des seules appartenances autorisées avec nombre de membres actifs (définition proposée C1), sans N+1 ; illustration locale facultative et remplacement par défaut, nom/visibilité. Lien de carte sémantique englobant, focus visible, pas d'éléments interactifs imbriqués, titres longs et tactile à 360 px.
- [ ] C.3 Prévoir visibilité explicite avec défaut privé et migration conservant toutes les communautés privées ; ni exposition de liste/détail/membres/exemplaires ni promesse de mode public avant définition de sa découverte. Choisir en C2 le support de l'illustration sans dépendance externe obligatoire ni URL arbitraire.
- [ ] C.4 Migration additive `CommunityInvite.expires_at` nullable et contrainte autorisant NULL ou date future ; service de validité = non révoqué ET (sans échéance OU échéance future). Garder digest unique 256 bits et copie chiffrée récupérable. Mettre à jour tous les comparatifs, formulaires et rendus ; « permanent » par défaut, expiration facultative explicite.
- [ ] C.5 Définir un lien courant par communauté et stratégie compatible pour les anciens liens multiples : proposition C1 = désigner le plus récent encore valide sans modifier ses dates, garder les autres anciens liens valides jusqu'à révocation/expiration ; aucune réactivation. Pour communauté sans lien valide, pas de secret créé sur GET, génération explicite par admin. En régénérant, invalider **tous** les liens encore actifs de cette communauté dans la même transaction ; sérialiser aussi adhésion/révocation/régénérations concurrentes via `domain_write`.
- [ ] C.6 Afficher le lien courant à tous les membres actifs/vérifiés, contrôle serveur avant déchiffrement ; copier via bouton et message accessible, sélection manuelle disponible sans presse-papiers/JS. Non-membres, anciens membres et autres communautés n'obtiennent ni lien ni digest/ciphertext.
- [ ] C.7 Séparer consultation membre des mutations admin POST + CSRF : révocation et régénération explicites, motif/trace bornée sans jeton. Garder limitation de débit, absence de référent/logs de secrets, `no-store` et origine issue d'`APP_BASE_URL`. Révoquer ne retire pas les membres déjà inscrits.
- [ ] C.8 Préserver intention d'invitation et vérification e-mail ; revalider le lien au POST d'adhésion et traiter l'ancien lien après régénération, y compris pendant inscription. Garder gestion d'une clé de chiffrement perdue : page utilisable, lien déjà distribué valide jusqu'à révocation, remplacement explicite par admin, pas de mutation sur GET. Adapter la procédure README pour liens permanents.
- [ ] C.9 Adapter tests supposant que le membre ne voit pas le lien ou que tous les liens expirent à sept jours ; déplacer les POST de création dans les scripts navigateur. Rejouer retraits, transfert du dernier admin, invalidation de visibilité et clôture des prêts après départ. Mettre à jour docs historiques par renvoi à la cible, sans réécrire leurs preuves de tests passées.

**Critères d'acceptation**
- [ ] Liste sans formulaire intégré, bouton vers formulaire dédié, cartes illustrées/fallback avec nom/compte/visibilité, carte entièrement ouvrable et accessible ; droits privés inchangés, communautés existantes privées.
- [ ] Un membre ordinaire copie le lien permanent courant ; il ne peut ni créer, révoquer ni régénérer par POST direct. Un ancien membre ou tiers ne le lit plus.
- [ ] Seul admin peut révoquer/régénérer ; ancien lien invalide immédiatement, lien courant unique après régénération, adhésion possible seulement avec compte actif/vérifié et confirmation explicite. Les anciens liens à échéance conservent leur date ; expirés/révoqués jamais réactivés.
- [ ] Retrait du propriétaire/membre et transfert restent sûrs ; prêts acceptés/remis clôturables. Aucune dépense ni nouveau service, aucun déploiement.

**Tests automatisés nécessaires**
- [ ] Migration communautés/invitations : aucune visibilité élargie ; NULL pour nouveaux liens permanents, dates historiques inchangées, cas multiples/sans lien/révoqué/expiré/illisible ; contrainte DB et validité aux bornes temporelles.
- [ ] Permissions membre/admin/tiers/ancien membre/non vérifié/inactif et communauté étrangère, accès direct au lien et mutations, CSRF/GET sans effet, absence de secrets dans logs/erreurs, récupération après rotation de clé.
- [ ] Concurrence PostgreSQL : adhésion face à révocation/régénération, deux régénérations, retrait face à consultation ; recontrôle au POST après passage par inscription/vérification.
- [ ] Carte, compte de membres, état vide, illustration/fallback, titres longs, clavier, annonce de copie, refus Clipboard et sans JS ; budget SQL stable avec plusieurs communautés ; création par page dédiée dans tous les smoke tests.
- [ ] Suite complète communautés/prêts/visibilités et CI après rebase sur A/B.

**Risques et réponses :** fuite de lien permanent → autorisation stricte, no-store/logs, rotation ; révocation incomplète d'anciens liens → rotation invalide tous les actifs ; élargissement public involontaire → défaut privé et blocage tant que règles non définies ; collision de fichiers frontend → branches séparées/rebase/tests ; membre retiré conserve un lien déjà copié → expliquer qu'un lien déjà partagé ne peut être repris, proposer révocation/régénération admin (politique existante de réadhésion conservée).

**Validation manuelle**
1. Créer par la page dédiée, tester cartes vides/longues/sans illustration à 360 px, clavier et desktop ; vérifier le compte après adhésion/départ et absence de communauté tierce.
2. Avec admin, membre et tiers, consulter/copier le lien permanent ; vérifier refus des mutations membre et de la lecture tiers. Révoquer puis régénérer ; tester ancien lien pendant une inscription et nouveau lien après vérification.
3. Rejouer invitation ancienne à échéance, clé illisible, deux onglets régénérant et retrait d'un membre ; confirmer que les prêts acceptés restent clôturables.

### Ordre d'intégration et portes de validation
1. Fusion documentaire **humaine** après lecture de SPEC, du présent plan et des décisions proposées dans l'audit ; cela valide le plan, sans autoriser purge, déploiement ou dépense.
2. **B**, livrable complet avec recherche synchrone et migrations sûres ; revue du traitement hérité, de la fusion et de la modération avant intégration.
3. **A**, rebasée sur B intégrée ; vérification des droits avant agrégation, du comportement navigateur et des index PostgreSQL.
4. **C**, éventuellement développée en parallèle de B depuis `main`, puis rebasée/testée après A. Sa découverte publique n'est implémentée qu'après définition explicite des droits associés.

Pour chaque PR : `./scripts/check.sh` sur PostgreSQL 17 synthétique, vérification production Django, audit runtime, build/healthcheck/capture SMTP et parcours navigateur de `.github/workflows/ci.yml`. Relire `makemigrations --check --dry-run`, `migrate --plan` et migrations forward/retour compatibles ; documenter les résultats effectifs et la validation mobile/clavier. Le détail des commandes locales est conservé dans README. Une CI verte ne vaut ni validation du plan ni autorisation de migration de production. Aucun merge automatique, aucune implémentation avant validation du plan.
