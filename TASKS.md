# Muqola — Plan de livraison du MVP

> Les durées ne sont pas des engagements. Chaque lot doit être démontrable avant de passer au suivant.
> Les lots 0–5 ci-dessous décrivent les livraisons historiques ; leurs cases cochées
> ne valident pas les nouvelles exigences. B, A, C et P1 sont fusionnées ; le travail courant est la préparation du lot 6.
> **P1 — décision du 16 novembre 2026 :** prêt immédiat des exemplaires en attente dans les communautés autorisées ; B1 est amendé ci-dessous. Le catalogue général reste réservé aux fiches validées.
> Arbitrages **B1–B4 et C1–C2 validés le 16 novembre 2026** ; B (#29) et A (#30) sont intégrées dans `main` ; C (#28) et le correctif P1 (#31) sont aussi fusionnés.

## Maintenance CI — runtimes GitHub Actions (19 novembre 2026)

Lot indépendant de la correction UI, depuis `main` `27ec280`.

- [x] Remplacer les actions Node.js 20 de la CI et de la CD manuelle par des
  versions déclarant Node.js 24, vérifiées dans leurs manifestes officiels :
  checkout 7.0.1, setup-python 7.1.0, setup-uv 10.3.3, upload-artifact 7.0.2
  et download-artifact 8.0.2 ; figer leurs SHA et documenter les versions.
- [x] Fixer les trois jobs sur `ubuntu-24.04` pour éviter la migration implicite
  du label `ubuntu-latest` vers Ubuntu 26.
- [x] Valider les deux workflows avec actionlint 1.7.12, Ruff/format, le build
  Docker et les 134 tests de publication/CD (8,25 s) : permissions,
  déclenchements, provenance, transfert d’artefact par identifiant et barrières
  de livraison conservés.

- [x] Corriger l’échec du run 44599753813 : déclarer explicitement le sous-réseau
  alloué par Docker dans les deux smokes avant l’attachement de Caddy à IP fixe.
  Seul le réseau synthétique encore vide est recréé ; réseaux existants et
  volumes conservés. Build et smoke production réels réussis après correction
  (TLS/CSRF, rôles, backup/restauration chiffrés, six états de prêt) ; les
  134 tests de publication/CD restent réussis (3,95 s).

La CI GitHub du nouveau commit et son smoke staging/CD restent à vérifier. Aucun workflow CD déclenché,
aucune fusion, aucune modification du VPS, du runtime applicatif ou des données.

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

**Préparation du 17 novembre 2026**, après les PR #24/#25/#28/#29/#30/#31 fusionnées.
Aucun déploiement ni infrastructure réelle. [Audit, preuves et procédures](docs/lot-6-infrastructure.md).
La décision **18+ est définitive** ; les validations réelles restent ouvertes.

- [x] Compose de production distinct : HTTPS/proxy préparés, secrets fichiers isolés, cookies/CSRF, volumes, healthchecks web/worker/DB, limites, redémarrage et logs bornés, images de base épinglées.
- [x] Séparer `muqola_admin`, `muqola_migrate` et `muqola_app` ; runtime sans DDL ni suppression d'historique, migration ponctuelle et réattribution explicite des droits ; migrations historiques inchangées.
- [x] Préparer sauvegarde `pg_dump → age → rclone`, rétention configurable, statut/échecs, restauration authentifiée uniquement dans une base distincte vide ; test synthétique reproductible.
- [x] Préparer SMTP TLS sur l'outbox/worker existants, heartbeat, documentation SPF/DKIM/DMARC et protocole de délivrabilité.
- [x] Préparer supervision HTTPS/DB/worker/outbox/disque/backup/erreurs JSON, timers et modèle de canal d'alerte indépendant.
- [x] Réserver la bêta aux 18+ : attestation serveur explicite et migration additive sans consentement inventé ; préserver la clôture des prêts existants.
- [x] Modèles légaux/contact/confidentialité/CGU, pages échappées, contrôle de complétude et blocage inscription production avant revue ; procédure de droits et limites documentées.
- [ ] **BLOQUANT ouverture** : VPS/domaine/DNS, HTTPS ACME réel, pare-feu, mémoire et charge, secrets réels, rôles et persistance validés sur l'instance cible.
- [ ] **BLOQUANT ouverture** : SMTP transactionnel, SPF/DKIM/DMARC et délivrabilité réelle (vérification/reset/prêt), bounces et quotas.
- [ ] **BLOQUANT ouverture** : stockage externe chiffré réellement configuré, restauration autorisée sur pile isolée et RPO/RTO mesurés ; alertes et sonde indépendante réellement testées.
- [ ] **BLOQUANT ouverture** : identité/coordonnées et politique de conservation fournies, revue juridique, traitement effectif des demandes de suppression éprouvé (désactivation ≠ effacement).
- [ ] Vérifier sur infrastructure cible permissions, concurrence, cookies/CSRF, parcours avec deux comptes et téléphone réel ; sauvegarde préalable et rollback éprouvés.
- [ ] Catalogue neuf vide ; éventuelles données héritées inventoriées/revue des droits sans suppression. Aucun ancien import BGG/Wikidata ni catalogue réel dans Git/image ; aucune commande d'import au lancement.
- [ ] Déployer **uniquement après autorisation humaine explicite distincte** et accomplissement de LAUNCH_CHECKLIST.md. Cette préparation n'autorise aucun déploiement.

**Acceptation finale non satisfaite à ce stade :** site HTTPS public, compte vérifié par e-mail réel, prêt complet, sauvegarde hors VPS restaurable et conformité effective. La préparation technique est vérifiable localement ; les validations externes restent des prérequis.

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


## Prochaines PR — B → A → C (arbitrages validés)

**État :** le plan documentaire de la PR #26 est intégré. Arbitrages fonctionnels B1–B4 et C1–C2 **validés par le propriétaire le 16 novembre 2026** et détaillés ci-dessous ; B (#29) et A (#30) sont intégrées dans `main`. C (#28) est fusionnée ; P1 (#31) amende le prêt des fiches en attente. Les bilans ci-dessous constituent la trace historique des validations. [Audit sourcé et décisions](docs/plan-b-a-c.md). Base auditée le 15 novembre, réconciliée le 16 novembre après fusion de #25.

Créer une branche/PR par lot ci-dessous, sans pousser directement sur `main` ; chaque PR doit fonctionner et passer la CI sans attendre la suivante. **B et C peuvent démarrer indépendamment depuis `main`**, A dépend de B fusionnée ; intégration recommandée B → A → C avec rebase/tests de C. Ne pas confondre ces lettres avec les anciens lots 0–6 ou des numéros GitHub.

### PR B — Refonte du catalogue

**Objectif :** une fiche par jeu, propositions modérées, types/extensions/alias, correction et fusion sûres, catalogue neuf vide. Conserver `Game`/`OwnedGame`/`GameVisibility`, les prêts, les contrôles serveur et l'outbox.

**Dépendances :** `main` ; arbitrages B1–B4 validés. Ne dépend pas de A ou C. La PR #25 Wikidata est désormais intégrée à `main` : réutiliser `GameAlias`, `GameIllustration`, recherche d'alias et métadonnées de licence/provenance. Conserver `0002_wikidata_catalogue` intacte ; les migrations B viennent après elle, sans recréer les modèles existants.

**Arbitrages B validés**
- **B1 :** conserver une seule entité `Game` avec modération `pending` / `approved` / `rejected` / `legacy_to_review`, séparée de `hidden`. Proposition titre seul et exemplaire privé autorisés en attente ; **P1 remplace la restriction de prêt initiale** : partage explicite et prêt immédiat autorisés dans les communautés actuelles, sans publication ni recherche dans le catalogue général avant validation. Les fiches héritées conservent leurs accès déjà autorisés et prêts existants jusqu'à révision, sans être réputées validées.
- **B2 :** une extension dépendante référence **un seul jeu de base** ; distinguer jeu autonome, extension dépendante et extension jouable seule. Type inconnu seulement avant validation ; aucun cycle/autolien.
- **B3 :** **fusion logique sans suppression** de la source : redirection contrôlée vers la fiche canonique, préservation de tous les exemplaires, prêts, droits, UUID, alias, images et IDs externes ; audit et transaction.
- **B4 :** **aucun upload utilisateur dans B**. Conserver les illustrations Commons déjà approuvées avec leurs crédits/licences et le visuel local par défaut ; reporter stockage, modération et publication de photos utilisateur à une future décision.

**Tâches techniques — implémentées et vérifiées**

Bilan, commandes et limites : [docs/catalogue-refonte.md](docs/catalogue-refonte.md). Les tests d’import historique ont été remplacés par la vérification de leur neutralisation ; alias/Commons et migrations restent testés. Aucun critère B laissé sans implémentation ; pas de test sur téléphone physique ni donnée réelle. La CI de la PR complète les contrôles locaux, sans autoriser déploiement ou fusion.
- [x] B.1 Inventorier toutes les FK vers `Game`/`OwnedGame`, fiches externes, homonymes et types inconnus, sans exposer de données privées. Documenter le bilan attendu, sauvegarde/restauration et compatibilité de retour arrière ; utiliser une copie synthétique peuplée en tests, jamais la production.
- [x] B.2 Préparer migrations **additives** : statut de modération distinct de `hidden`, type incluant inconnu pour proposition, relation de base ; réutiliser les alias normalisés existants et leurs contraintes. Ajouter contraintes des fiches validées et validations des extensions (base obligatoire si dépendante, pas d'auto-référence/cycle). Définir les index, unicité des alias par fiche, règles FK `PROTECT`, référence de fusion et conservation des identifiants externes.
- [x] B.3 Distinguer les lignes héritées sans type connu des nouvelles propositions : aucune validation/type fabriqué, aucun `DELETE`/`TRUNCATE`/reset, pas de réécriture de `0001`. Garder les UUID et les références aux exemplaires/prêts ; documenter le traitement de chaque état hérité et les accès transitoires selon B1. Une base neuve reste vide sans compte/fiches d'import automatiques.
- [x] B.4 Faire passer **tous** les chemins d'écriture (ajout rapide, ancien formulaire, correction, console et deux commandes d'import historiques) par les règles cible. Retirer le contournement « autre édition » ; conserver le réemploi et les exemplaires multiples/privés. Pour ces PR, neutraliser les parcours `import_games`/`import_wikidata_games` pour la cible BGG/Wikidata sans effacer leurs données existantes ; décider explicitement de la conservation du code historique. Garder une recherche synchrone fonctionnelle jusqu'à A.
- [x] B.5 Implémenter proposition titre seul/type inconnu et suivi auteur ; l'exemplaire référence cette fiche en attente. Réemploi public toujours interdit ; P1 autorise partage et prêt immédiats selon les choix explicites du propriétaire, sans communauté ajoutée automatiquement. Aucun accès tiers sans exemplaire autorisé, ni aux motifs privés de revue.
- [x] B.6 Étendre les services/commandes `operations` existants : file de propositions, décision motivée, validation avec contrôle serveur des doublons, correction, rejet et signalements. Un administrateur de communauté ne devient pas modérateur du catalogue. Journaliser acteur, motif, états et cible sans secrets.
- [x] B.7 Fournir suggestions exactes normalisées sur titre/alias avant proposition et avant validation ; garde serveur atomique dans `domain_write` pour toutes les créations/validations. Ne pas imposer l'unicité globale du titre ; exiger une justification de vraie homonymie. Le fuzzy sera ajouté en A. Ne pas divulguer une proposition tierce parmi les suggestions utilisateur.
- [x] B.8 Fusion administrative transactionnelle avec simulation/bilan, confirmation source/cible et motif : conserver `OwnedGame.id`/owner, ne pas fusionner les exemplaires physiques ni modifier les FK `Loan.owned_game`. Replacer références de fiches, alias, bases, signalements et IDs externes ; gérer conflits d'alias/ID et deux signalements ouverts d'un même auteur sans les perdre. Garder une trace/source redirigeable avec mêmes contrôles d'accès, sans boucle. Conserver `ever_reused` et les masquages ; fusion refusée si elle rétablit un accès ou crée un cycle.
- [x] B.9 Réutiliser `GameIllustration` et préserver métadonnées licence/source/attribution, illustrations Commons approuvées et visuel local par défaut. **Ne créer ni upload ni champ photo/URL utilisateur** dans B ; documenter le report de ces fonctionnalités et maintenir les contrôles de droits existants.
- [x] B.10 Adapter formulaires/messages, bornes et fixtures **synthétiques**, tests existants et scripts navigateur qui créent aujourd'hui directement une fiche ; maintenir le parcours complet après validation opérateur, sans préjuger de A. Actualiser README et documentation du schéma.

**Critères d'acceptation**
- [x] Une nouvelle installation reste vide ; aucune donnée externe, aucun import implicite ni catalogue réel versionné/embarqué. Sur base peuplée, toutes les références et tous les états de prêts sont conservés.
- [x] Un utilisateur vérifié sans communauté propose un titre et garde un exemplaire privé ; le type inconnu empêche la validation, pas la soumission. Un tiers sans exemplaire autorisé ne trouve aucune proposition ; les données privées de revue restent réservées à l’auteur/opérateur. Une fiche validée exige titre/type/base applicable ; métadonnées facultatives réellement facultatives.
- [x] Jeux autonomes, extensions dépendantes et extensions jouables seules sont représentables ; deux éditions commerciales ne justifient pas deux fiches. Alice et Bob possèdent des exemplaires distincts d'une même fiche.
- [x] Seul un opérateur autorisé valide/corrige/fusionne ; le contrôle des doublons s'applique aussi sans JS et en concurrence. Une fusion préserve propriétaires, visibilités, demandes, prêts et liens ; un masquage n'est pas annulé.
- [x] L'ajout/recherche synchrone, les prêts et leur clôture fonctionnent **avant A**. Pas d'ouverture des droits de communauté.

**Tests automatisés nécessaires**
- [x] Migrations sur base vide et snapshot synthétique issu du schéma actuel : fiches manuelles/importées/masquées/réutilisées, alias/illustrations/crédits de `0002_wikidata_catalogue`, copies privées/multicommunautés/retirées/archivées, prêts de tous états, signalements ; comparer UUID/FK/états avant/après et tester reprise/retour compatible. Pas de purge en reverse migration.
- [x] Contraintes type/base, alias, homonymes ; proposition titre seul, contrôle des champs facultatifs, XSS, droits auteur/opérateur/administrateur de communauté/non vérifié/tiers.
- [x] Concurrence PostgreSQL : doubles propositions/validations, validation face à correction/fusion, fusion face à prêt/ajout d'exemplaire ; rollback complet sur conflit et absence de références perdues.
- [x] Fusion avec plusieurs IDs externes, signalements en conflit, ancienne URL et fiche masquée ; prêts actifs toujours clôturables et exclusivité par exemplaire maintenue. Vérifier l'absence d'upload/URL arbitraire et la conservation des crédits/licences Commons.
- [x] Adapter `test_quick_add`, `test_inventory`, `test_operations`, tests de migrations et parcours navigateur ; suite de prêts/communautés et CI complète de non-régression.

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
- [x] A.1 Réutiliser `normalized_title`, `title_condition` et `matching_title` déjà intégrés par #25 pour principal/alias ; centraliser la sélection des fiches canoniques sans dupliquer ce moteur synchrone. Définir recherches « ajouter » et « emprunter » explicitement. Pour emprunter, partir du sous-ensemble autorisé des exemplaires partageables dans les communautés actuelles ; ne pas utiliser le catalogue global comme résultat de repli. Garder collection personnelle et emprunt distincts.
- [x] A.2 Évaluer `pg_trgm` avec `TrigramExtension` Django et index GIN sur clés normalisées principal/alias ; vérifier disponibilité et rôle de migration sur PostgreSQL 17 (rôle runtime sans privilège de création d'extension). Éviter `unaccent` supplémentaire si la clé normalisée suffit. Mesurer le plan sur corpus synthétique ; pas de nouveau service.
- [x] A.3 Fixer classement déterministe : exact principal/alias, préfixe, contenu, similarité trigramme, puis titre/UUID. Calibrer seuils avec cas français, fautes, titres courts et homonymes ; stratégie exacte/préfixe pour deux caractères. Utiliser un meilleur score par fiche, sans multiplier les lignes par alias.
- [x] A.4 Regrouper par `Game` canonique **après** droits/filtres ; compter chaque copie autorisée une fois même multicommunautés. Une carte par fiche ; détail listant les copies empruntables et leur disponibilité. Maintenir filtres communauté/joueurs/disponibilité, pagination bornée et URLs partageables. Aucun nom/compteur privé ni e-mail dans l'endpoint.
- [x] A.5 Fournir endpoint GET de fragments HTML Django (proposition A1), authentifié/vérifié et sans cache partagé ; même sélection et même rendu pour GET classique/asynchrone. Borner longueur de saisie, pagination et travail serveur, mesurer SQL et latence ; mettre à jour attentes MUQ-05 si requêtes légitimement modifiées, sans supprimer la borne de requêtes.
- [x] A.6 JavaScript local : seuil ~2 caractères, debounce ~250 ms, `AbortController` et numéro de requête pour ignorer réponses obsolètes, gestion saisie IME, remise à zéro et filtres. Retirer le bouton Rechercher ; repli GET avec Entrée sans JS. Ne pas déplacer le focus ou perdre une sélection de jeu/notes/partages durant la mise à jour.
- [x] A.7 Autoriser `connect-src 'self'` dans la CSP actuelle (qui a `default-src 'none'`) pour le fetch local, sans ouvrir les autres origines. Prévoir `aria-busy`, zone de statut polie pour chargement/résultats/erreur, labels et liens clavier ; annulation, erreur réseau et aucun résultat utilisables.
- [x] A.8 Réutiliser le moteur pour suggestions utilisateur **et administrateur** ; conserver garde serveur B à la soumission et recontrôle à la validation, même POST sans JS. Un score fuzzy seul ne fusionne ni ne rejette un homonyme.
- [x] A.9 Mettre à jour UI, scripts/tests et documentation des index, scores, seuils, mesures et privilèges. Éviter logs de texte recherché et caches mélangeant les acteurs.

- [x] A.10 Consolider les performances sur corpus synthétique, le budget p95, la vérification finale et le bilan de PR, conformément à la demande d’implémentation (le plan initial allait de A.1 à A.9).

**Critères d'acceptation**
- [x] Après deux caractères et ~250 ms sans nouvelle saisie, les résultats se mettent à jour sans bouton ni rechargement ; la dernière saisie gagne, y compris si les réponses arrivent dans le désordre. Les filtres restent effectifs.
- [x] Titre principal/alias, accents/casse et fautes prévues retrouvent le jeu avec classement stable ; une carte par jeu, copie multicommunautés comptée une seule fois.
- [x] En ajout, seules métadonnées validées ; en emprunt, seuls jeux ayant des copies autorisées. Ajouter une copie invisible ne change ni résultat, ni compte, ni rang, ni pagination. Aucun accès étranger par URL/fragment/suggestion.
- [x] Clavier, lecteur d'écran, 360 px, absence de JS et panne réseau permettent de poursuivre le parcours. Le contrôle serveur des doublons reste actif.

**Tests automatisés nécessaires**
- [x] PostgreSQL réel : extension/index appliqués depuis base vide et peuplée ; exact/préfixe/alias/accents/espaces/fautes, titres courts, seuils, ordre stable et absence de doublons d'alias.
- [x] Matrice d'autorisations catalogue/emprunt : aucune communauté, A/B, plusieurs communautés, retrait de membre/propriétaire, exemplaire privé/retiré/archivé, fiche masquée/en attente/fusionnée. Vérifier compteurs, badges, ordre, filtres, pagination, JSON/HTML et IDOR.
- [x] Navigateur avec contrôle du temps et des réponses : debounce/seuil, annulation/course de réponses, IME, effacement, filtres, sélection conservée, clavier, annonces, erreur réseau, JS désactivé et CSP réelle.
- [x] Budgets SQL bornés sans N+1 (1/10/30/65 copies et plusieurs alias) ; benchmark synthétique plus volumineux avec p50/p95, protocole et matériel consignés avant de fixer un budget de latence.
- [x] Suggestions et POST directs/concurrents ne contournent pas B ; CI complète, dont parcours des prêts.

**Preuves :** [implémentation, protocole, mesures, budgets et limites de validation](docs/recherche-intelligente.md). Les tests ARIA/clavier ne sont pas présentés comme un audit humain avec lecteur d’écran ou sur téléphone physique.

**Risques et réponses :** fuite par agrégation/rang → filtrer d'abord ; faux positifs → classement et revue humaine ; lenteur sur petites saisies → index/borne/mesure ; fetch bloqué → test CSP navigateur ; courses JS → annulation + numéro ; changement de schéma B → A après B.

**Validation manuelle**
1. Chercher par principal/alias, accents et faute sur corpus synthétique ; taper vite, effacer, changer les filtres, naviguer au clavier et revenir à la page précédente.
2. Avec deux communautés et une collection privée, comparer les résultats/comptes avant et après retrait de membre ; ouvrir un endpoint directement et vérifier le refus au compte non vérifié/tiers.
3. Vérifier une fiche avec plusieurs copies dont une partagée deux fois et une privée ; sélectionner une copie et demander le prêt ; tester hors ligne, sans JS et à 360 px.

### PR C — Refonte des communautés et invitations

**Objectif :** cartes complètes et accessibles, création dédiée, lien permanent consultable par tous les membres et rotation réservée aux administrateurs, en maintenant les droits privés.

**Dépendances :** `main` ; arbitrages C1–C2 validés. L'indépendance fonctionnelle de B est confirmée : tables/services `communities` autonomes, interactions inventory/loans déjà encapsulées. Développement possible en parallèle **sur branche séparée**. Intégration proposée après A ; résoudre les conflits potentiels sur CSS/JS, docs et scripts navigateur, puis rejouer toute la CI. **Aucune découverte publique dans C**, même si elle pourra faire l'objet d'une décision distincte plus tard.

**Arbitrages C validés**
- **C1 :** lien permanent par défaut (expiration facultative), consultable et copiable par tout membre actif et vérifié ; seuls les administrateurs révoquent ou régénèrent. Lien courant = plus récent encore valide ; anciens liens à échéance conservés et valides jusqu'à expiration/révocation ; rotation révoque atomiquement **tous** les anciens liens actifs. Nombre de membres = appartenances actives de comptes actifs et vérifiés.
- **C2 :** communautés **privées uniquement**, sans annuaire ni découverte publique ; illustrations **prédéfinies locales** sélectionnables et visuel local par défaut, sans upload ni URL distante arbitraire.

**Tâches techniques**
- [x] C.1 Séparer liste GET et route dédiée GET/POST de création ; déplacer `CommunityForm`, conserver validation, CSRF, vérification e-mail, limitation de débit, création atomique du rôle admin, messages et redirection.
- [x] C.2 Enrichir la liste des seules appartenances autorisées avec nombre d'appartenances actives de comptes actifs et vérifiés (C1), sans N+1 ; illustration prédéfinie locale sélectionnable ou visuel local par défaut, nom et badge « Privée ». Lien de carte sémantique englobant, focus visible, pas d'éléments interactifs imbriqués, titres longs et tactile à 360 px.
- [x] C.3 Maintenir **toutes** les communautés privées et les contrôles d'accès existants ; **ne pas implémenter d'option publique ni d'annuaire/découverte**. Proposer un choix borné d'illustrations locales prédéfinies avec fallback (migration additive si champ nécessaire) ; aucune URL arbitraire ni upload.
- [x] C.4 Migration additive `CommunityInvite.expires_at` nullable ; création d'une expiration optionnelle seulement si future, **sans contrainte DB qui invaliderait les dates historiques expirées** ; service de validité = non révoqué ET (sans échéance OU échéance future). Garder digest unique 256 bits et copie chiffrée récupérable. Mettre à jour tous les comparatifs, formulaires et rendus ; « permanent » par défaut, expiration facultative explicite.
- [x] C.5 Définir un lien courant par communauté et stratégie compatible pour les anciens liens multiples **selon C1 validé** : désigner le plus récent encore valide sans modifier ses dates, garder les autres anciens liens valides jusqu'à révocation/expiration ; aucune réactivation. Pour communauté sans lien valide, pas de secret créé sur GET, génération explicite par admin. En régénérant, invalider **tous** les liens encore actifs de cette communauté dans la même transaction ; sérialiser aussi adhésion/révocation/régénérations concurrentes via `domain_write`.
- [x] C.6 Afficher le lien courant à tous les membres actifs/vérifiés, contrôle serveur avant déchiffrement ; copier via bouton et message accessible, sélection manuelle disponible sans presse-papiers/JS. Non-membres, anciens membres et autres communautés n'obtiennent ni lien ni digest/ciphertext.
- [x] C.7 Séparer consultation membre des mutations admin POST + CSRF : révocation et régénération explicites, motif/trace bornée sans jeton. Garder limitation de débit, absence de référent/logs de secrets, `no-store` et origine issue d'`APP_BASE_URL`. Révoquer ne retire pas les membres déjà inscrits.
- [x] C.8 Préserver intention d'invitation et vérification e-mail ; revalider le lien au POST d'adhésion et traiter l'ancien lien après régénération, y compris pendant inscription. Garder gestion d'une clé de chiffrement perdue : page utilisable, lien déjà distribué valide jusqu'à révocation, remplacement explicite par admin, pas de mutation sur GET. Adapter la procédure README pour liens permanents.
- [x] C.9 Adapter tests supposant que le membre ne voit pas le lien ou que tous les liens expirent à sept jours ; déplacer les POST de création dans les scripts navigateur. Rejouer retraits, transfert du dernier admin, invalidation de visibilité et clôture des prêts après départ. Mettre à jour docs historiques par renvoi à la cible, sans réécrire leurs preuves de tests passées.

**Bilan :** [Implémentation, migration et preuves](docs/communautes-refonte.md). Après intégration de B/A (`main` 47b47ff), 322 tests PostgreSQL et les parcours Chrome complets passent. La CI GitHub de la tête finale reste exigée avant fusion.

**Critères d'acceptation**
- [x] Liste sans formulaire intégré, bouton vers formulaire dédié, cartes illustrées/fallback avec nom/compte et badge « Privée », carte entièrement ouvrable et accessible ; droits privés inchangés, communautés existantes privées.
- [x] Un membre ordinaire copie le lien permanent courant ; il ne peut ni créer, révoquer ni régénérer par POST direct. Un ancien membre ou tiers ne le lit plus.
- [x] Seul admin peut révoquer/régénérer ; ancien lien invalide immédiatement, lien courant unique après régénération, adhésion possible seulement avec compte actif/vérifié et confirmation explicite. Les anciens liens à échéance conservent leur date ; expirés/révoqués jamais réactivés.
- [x] Retrait du propriétaire/membre et transfert restent sûrs ; prêts acceptés/remis clôturables. Aucune dépense ni nouveau service, aucun déploiement.

**Tests automatisés nécessaires**
- [x] Migration communautés/invitations : aucune visibilité élargie ; NULL pour nouveaux liens permanents, dates historiques inchangées, cas multiples/sans lien/révoqué/expiré/illisible ; contrainte DB et validité aux bornes temporelles.
- [x] Permissions membre/admin/tiers/ancien membre/non vérifié/inactif et communauté étrangère, accès direct au lien et mutations, CSRF/GET sans effet, absence de secrets dans logs/erreurs, récupération après rotation de clé.
- [x] Concurrence PostgreSQL : adhésion face à révocation/régénération, deux régénérations, retrait face à consultation ; recontrôle au POST après passage par inscription/vérification.
- [x] Carte, compte de membres, état vide, illustration/fallback, titres longs, clavier, annonce de copie, refus Clipboard et sans JS ; budget SQL stable avec plusieurs communautés ; création par page dédiée dans tous les smoke tests.
- [x] Suite complète communautés/prêts/visibilités après mise à jour sur A/B : 322 tests PostgreSQL, lint/format/typage/Django/migrations/statiques, contrôle production, audit runtime, build Docker et parcours Chrome comptes/recherche/produit/ajout/Commons/UI réussis. **CI GitHub de la tête finale à vérifier avant fusion.**

**Risques et réponses :** fuite de lien permanent → autorisation stricte, no-store/logs, rotation ; révocation incomplète d'anciens liens → rotation invalide tous les actifs ; élargissement public involontaire → communautés strictement privées, aucun mode public dans C ; collision de fichiers frontend → branches séparées/rebase/tests ; membre retiré conserve un lien déjà copié → expliquer qu'un lien déjà partagé ne peut être repris, proposer révocation/régénération admin (politique existante de réadhésion conservée).

**Validation manuelle**
1. Créer par la page dédiée, tester cartes vides/longues/sans illustration à 360 px, clavier et desktop ; vérifier le compte après adhésion/départ et absence de communauté tierce.
2. Avec admin, membre et tiers, consulter/copier le lien permanent ; vérifier refus des mutations membre et de la lecture tiers. Révoquer puis régénérer ; tester ancien lien pendant une inscription et nouveau lien après vérification.
3. Rejouer invitation ancienne à échéance, clé illisible, deux onglets régénérant et retrait d'un membre ; confirmer que les prêts acceptés restent clôturables.

### Ordre d'intégration et portes de validation
1. **Fait :** fusion documentaire #26 et validation humaine des arbitrages B1–B4/C1–C2 le 16 novembre 2026. Cela n'autorise ni purge, ni déploiement, ni dépense.
2. **B**, livrable complet avec recherche synchrone et migrations sûres ; revue du traitement hérité, de la fusion et de la modération avant intégration.
3. **A**, rebasée sur B intégrée ; vérification des droits avant agrégation, du comportement navigateur et des index PostgreSQL.
4. **C**, développable en parallèle de B depuis `main`, puis rebasée/testée après A. Aucun mode public ni découverte publique dans cette PR.

Pour chaque PR : `./scripts/check.sh` sur PostgreSQL 17 synthétique, vérification production Django, audit runtime, build/healthcheck/capture SMTP et parcours navigateur de `.github/workflows/ci.yml`. Relire `makemigrations --check --dry-run`, `migrate --plan` et migrations forward/retour compatibles ; documenter les résultats effectifs et la validation mobile/clavier. Le détail des commandes locales est conservé dans README. Une CI verte ne vaut ni validation de la PR ni autorisation de migration de production. **Les arbitrages sont validés, pas les implémentations** : aucun merge automatique, aucune opération sur données réelles.


## Correctif P1 — prêt immédiat des fiches en attente

**Décision produit du 16 novembre 2026**, après fusion B #29 et A #30, appliquée
sur `main` e57b9b2 (qui contient aussi C #28). Remplace la restriction initiale
de B1 ; les autres protections du catalogue, doublons, types et modération restent
conservées. [Règles, droits et preuves](docs/pret-fiches-en-attente.md).

- [x] P1.1 Autoriser création/partage explicite d’exemplaires de l’auteur liés à un Game pending, titre seul/type inconnu inclus, sans approbation globale ni réemploi arbitraire par un tiers.
- [x] P1.2 Aligner disponibilité, éligibilité et transitions ; garder vérification à demande/acceptation, appartenance des deux parties, exclusivité et transactions PostgreSQL.
- [x] P1.3 Inclure pending dans la recherche d’emprunt seulement via les copies autorisées ; garder catalogue général/suggestions sans pending, comptes/rang/pages sans fuite et indicateur accessible.
- [x] P1.4 Préserver UUID, exemplaires, partages et prêts lors de validation/correction/fusion/rejet ; au rejet annuler REQUESTED, empêcher nouveaux prêts, conserver clôture des ACCEPTED/HANDED_OVER. Une correction auteur ne lève pas le rejet ; ses propres titres/alias rejetés ne peuvent pas être reproposés à l’identique pour le contourner.
- [x] P1.5 Adapter formulaires, messages et documentation ; tester accès directs et fragments, privé/A/B/multicommunautés, retraits, concurrence rejet/demande/acceptation, tous états des prêts et budgets SQL.
- [x] P1.6 Exécuter suite complète, lint/format/typage, migrations, contrôles production, audit/build et navigateur (demande/acceptation avant validation, validation pendant prêt actif), puis PR indépendante sans fusion/déploiement.

## Lot 6 — Intégration VPS, Caddy partagé et CI/CD

**Audit documentaire du 17 novembre 2026, avant accord d'implémentation.**
Base synchronisée : `origin/main` `ff9e0c208be067b993f22b5f4b3b5751d5a8579d`.
La PR #32 est fusionnée ; ses preuves et toutes les tâches historiques ci-dessus
sont conservées. [Audit et stratégie proposés](docs/lot-6-infrastructure.md#audit-caddy-partagé-staging-et-cicd--17-novembre-2026).
L'infrastructure OVH/Debian/Caddy/HTTPS est déclarée disponible par l'exploitant ;
elle n'a pas été inspectée par SSH. Aucun déploiement autorisé par ces cases.
P0 = sécurité/prérequis bloquant ; P1 = livraison ; P2 = exploitation/mesures ;
P3 = améliorations ultérieures. Aucun P3 nécessaire à ce périmètre.

### V0 — Audit et porte d'accord

- [x] **V0 / P0 — Vérifié (audit uniquement).** Dépendances : aucune.
  Acceptation : lire les références, synchroniser main, vérifier la fusion #32,
  cartographier les dépendances Caddy/SMTP/backup/tests et préparer le découpage.
  Preuves : `git fetch origin`, `git rev-parse origin/main`, API GitHub PR #32
  (`merged=true`, fusion `ff9e0c2`), `docker compose --env-file .env.production.example -f compose.prod.yaml config --quiet` réussi ; lecture du code.
  Fichiers : `AGENTS.md`, documents de référence, `deploy/`, `scripts/production_smoke.py`, tests, workflows.
  Manuel : **accord reçu** par réponse « oui » au découpage en quatre PR ; aucune autorisation de déploiement ni de fusion.
  CI du merge `ff9e0c2` : [run 44088074202 réussi](https://github.com/tlamart/muqola/actions/runs/44088074202), vérifié par API. Les 373 tests de #32 restent une preuve historique, pas une nouvelle exécution locale de cet audit.

### PR proposée 1 — Caddy partagé et compatibilité d'exploitation

- [x] **V1 / P0 — Vérifié en synthétique : réseau et Compose production.** Dépendances : V0 + accord.
  Acceptation : retirer le service Caddy et ses ports du Compose applicatif,
  garder ses anciens volumes hors suppression ; seul web rejoint le réseau externe
  `proxy` sous `muqola-web`, en plus du réseau privé ; db/worker/migrate restent privés.
  Préserver rôles, secrets, healthchecks et budgets ; aucun build ni port web/DB publié.
  Validation exécutée : rendu Compose avec profil maintenance et tests `test_deploy_configuration.py` réussis (réseaux, ports, volume stable, rôles/secrets, GHCR immuable et refus des configurations dangereuses).
  Fichiers : `compose.prod.yaml`, `.env.production.example`, `tests/test_deploy_configuration.py` (prévu).
  Manuel **à faire sur VPS** : vérifier/créer `proxy`, y connecter le Caddy commun ; préserver noms de projet/volumes existants.

- [x] **V2 / P0 — Vérifié en synthétique : extrait Caddy commun et rechargement.** Dépendance : V1.
  Acceptation : domaines `muqola.tlam.art` et futur staging, alias uniques ; limite
  de corps, en-têtes réécrits, URI/cookies/Authorization exclus des logs même en erreur.
  Ne pas recopier `admin off` ni remplacer les options globales des autres sites ;
  admin de rechargement local au conteneur, jamais exposé au public.
  Validation exécutée : validate puis reload sur Caddy séparé 2.11.9 ; 20 sondes du site témoin sans échec, nouvelle réponse visible et Muqola disponible ; erreur proxy avec cookie/Authorization/URI secrets expurgés.
  Fichiers : `deploy/Caddyfile` (extrait à adapter), `scripts/production_smoke.py`, runbook existant.
  Manuel **à faire sur VPS** : fusionner l'extrait dans `/opt/caddy/Caddyfile`, vérifier la configuration complète puis recharger ; aucune modification du VPS par l'agent.

- [x] **V3 / P0 — Vérifié en synthétique : identité du proxy et limites par IP.** Dépendances : V1–V2.
  Acceptation : conserver HTTPS/CSRF ; distinguer les IP clientes derrière Caddy,
  accepter les en-têtes d'identité uniquement depuis les adresses Caddy explicitement
  approuvées ; refuser l'usurpation et ne pas approuver tout le réseau partagé.
  Validation exécutée : tests IP distinctes/budget e-mail commun, source non approuvée, faux X-Forwarded-For/protocole, cookies/CSRF et passage réel par Caddy ; aucune confiance au subnet entier.
  Fichiers : `config/settings.py`, `muqola/identity/ratelimit.py`, middleware ciblé si nécessaire, tests comptes/proxy.
  Manuel **à faire sur VPS** : confirmer adressage/identité stable du Caddy sur `proxy` et les autres applications connectées.

- [x] **V4 / P1 — Vérifié en synthétique : monitoring/backup compatibles.** Dépendance : V1.
  Acceptation : réutiliser backup/restore sans réécriture ; identifier explicitement
  le projet et sa configuration ; dissocier supervision Caddy commun et app,
  éviter le faux `caddy_unhealthy` et les chemins/états partagés entre environnements.
  Adapter le cleanup du smoke : le `down --volumes` actuel est incompatible avec
  cette mission ; conserver les volumes, y compris synthétiques, sans commande de destruction.
  Validation exécutée : tests monitoring/backup et exercice age/rclone sur projet explicite, restauration comparée à la source et six états de prêt préservés ; modules hôte importés seuls sous Python 3.13.18.
  Fichiers : `deploy/common.py`, `deploy/monitor.py`, exemples JSON/systemd, tests et smoke existants.
  Manuel **à faire sur VPS** : configurer séparément chemins, états, alertes et cible de sauvegarde ; vérifier l'interpréteur hôte Debian 13 sans changer le Python 3.12 de l'image.

### PR proposée 2 — Staging éphémère isolé

Branche `feat/staging-ephemere`, issue de `origin/main` `67df970` après fusion de #33.
Les validations ci-dessous sont synthétiques ; aucune intervention sur le VPS.

- [x] **V5 / P0 — Vérifié en synthétique : isolation du staging.** Dépendance : PR 1 intégrée.
  Acceptation : projet `muqola-staging`, DB `muqola_staging`, volumes/secrets/
  chemins indépendants, alias `muqola-staging-web`, domaine staging, cookies
  sécurisés propres à l'hôte ; aucun lien avec la DB production ni copie réelle.
  Validation exécutée : rendu Compose, tests positifs/négatifs de collision
  projets/volumes/réseaux/chemins/valeurs des secrets, aucune publication de ports,
  production témoin inchangée pendant deux stop/restart et volumes conservés.
  La composition partagée conserve le rendu production de #33 (hors label de contexte).
  Fichiers : `compose.runtime.yaml`, `compose.prod.yaml`, `compose.staging.yaml`,
  `.env.staging.example`, `deploy/staging_config.py`, tests et smoke staging.
  Manuel **à faire sur VPS** : DNS staging, chemins et secrets indépendants,
  référence privée de configuration production ; ne jamais copier un dump réel.

- [x] **V6 / P0 — Vérifié en synthétique : accès privé, noindex et SMTP capturé.** Dépendance : V5.
  Acceptation : authentification Caddy sur toutes les routes, noindex/no-store,
  capture interne sans relais/credentials Brevo/interface publiée ni sortie SMTP worker.
  `APP_ENV=production`, HTTPS/CSRF, 18+ et contrôle légal conservés ; contrôle
  staging distinct sans assouplir `production_readiness`.
  Validation exécutée : 401 anonyme/mauvais accès, 200 authentifié, logs expurgés,
  refus d'activation avant démarrage si la barrière anonyme manque, sonde TLS sans
  redirection ni proxy d'environnement, outbox réellement capturée dans Mailpit,
  refus serveur du SMTP extérieur et des comptes hors `@example.test`, inscription
  fermée avant revue légale et attestation adulte toujours explicite.
  Fichiers : `deploy/Caddyfile.staging`, `deploy/probe.py`, `deploy/monitor.py`,
  contrôles operations, settings/formulaire/service, bannière, tests et smoke.
  Manuel **à faire sur VPS** : hash d'accès privé et testeurs, certificats/DNS,
  validation/rechargement Caddy avec témoin, documents légaux revus et alertes stage.

- [ ] **V7 / P2 — En cours : cycle de vie vérifié, capacité VPS non satisfaite.** Dépendances : V5–V6.
  Acceptation : staging arrêté par défaut ; start/stop sans build ni destruction,
  admission capacité et mesure de pointe sous charge synthétique sur cible 4 Go.
  Implémenté/vérifié : profils opt-in, restart=no, verrou/état indépendants,
  arrêt ciblé ; start exige données fictives/revue humaine, isolation et secrets,
  Docker local avec limites cgroups, mémoire/disque/CPU suffisants et migrations
  déjà appliquées. Aucune migration appliquée automatiquement ni rollback DB.
  Budgets staging : web 256 + worker 128 + DB 384 + Mailpit 64 = **832 Mio** ;
  migration 384 Mio + marge 512 Mio, soit **1 728 Mio disponibles** exigés.
  Tests : refus ressources/cgroups/revue insuffisants, Docker distant et migrations
  en attente ; smoke Docker avec échantillonnage et résultat JSON conservé en CI.
  **Non satisfait :** mesure mémoire/CPU de pointe et disponibilité sur VPS réel.
  Docker local rootless sans cgroups : métriques invalides, valeurs nulles dans
  `work/staging-smoke.json`, refus d'admission ; aucun chiffre assimilé au VPS.
  Fichiers : `deploy/staging.py`, exemples JSON de cycle/monitoring/backup,
  `scripts/staging_smoke.py`, runbook Debian 13 existant.
  Manuel **à faire après autorisation distincte** : mesurer avant/pendant/après
  charge/migration avec `docker stats --no-stream`, `free -m`, `df -h`, journaux
  OOM et sonde production, puis choisir seuils/créneaux. Garder `capacity_reviewed=false`
  et staging arrêté tant que la marge réelle n'est pas démontrée.

Preuves locales du 17 novembre : `scripts/check.sh` (**415 tests réussis**, lint,
format, typage, check Django, migrations sans dérive et statiques), contrôle Django `check --deploy`, audit
runtime et build Docker ; `production_smoke.py` (rôles, TLS/CSRF, backup chiffré,
restauration, six états de prêt) et `staging_smoke.py` réussis sur données fictives.
Les résultats navigateur et la CI sont consignés dans la PR ; les preuves
historiques des lots précédents restent inchangées. Aucun déploiement ni volume supprimé.

### PR proposée 3 — Image validée et publication GHCR

Branche `feat/ghcr-publication` depuis `origin/main` `3ac1ac3`, après fusion #34.
Périmètre : préparation/test V8–V9 ; aucune publication réelle avant fusion.

- [x] **V8 / P0 — Vérifié en synthétique : publication exclusivement après main validé.** Dépendance : PR 1–2 intégrées et accord reçu.
  Acceptation : tous les contrôles PR/main conservés ; une seule construction sur
  runner, même image testée puis transférée par artefact immuable et ID explicite,
  aucun rebuild dans le publisher ; push main seulement après succès de checks.
  Digest canonique extrait de save et transmis comme sortie de checks, puis
  configuration re-sauvegardée après load : identité indépendante du handle moteur.
  Dockerfile durci inchangé ; contents:read global, packages:write au seul publisher,
  GITHUB_TOKEN éphémère sur stdin, configuration Docker isolée/logout ; aucun SSH.
  Validation exécutée : politique du vrai workflow parsée/testée (PR, fork, mauvais
  ref/événement, échec/annulation refusés), actionlint 1.7.12 ; garde du script avant
  toute mutation, transfert save/load avec hash/ID/labels/commit/run/tentative vérifiés.
  Fichiers : `.github/workflows/ci.yml`, `scripts/image_candidate.py`, tests livraison.
  Manuel **après fusion** : vérifier droits Actions/association et visibilité du
  package GHCR (privée par défaut), succès de checks puis publish sur le nouveau main.

- [x] **V9 / P0 — Vérifié en synthétique : traçabilité et promotion du même digest.** Dépendance : V8.
  Acceptation : tag SHA complet + tag run/tentative, référence déployable strictement
  ghcr.io/tlamart/muqola@sha256:<64 hex>, manifeste relu au registre avec digest de
  configuration identique aux octets testés/sauvegardés ; preuve conservée 90 jours.
  Validation distante obligatoire avant promotion : API GitHub, push main réussi,
  dépôt source/workflow/tentative exacts, jobs checks ET publish réussis et preuve
  unique de ce run ; aucune confiance à un label, tag ou record local seul.
  Validation exécutée : refus tag/mauvais dépôt, archive altérée, commit/run/ID ou
  tentative incohérents, publication manquante/expirée/étrangère, CI échouée,
  manifeste absent ou divergent ; même résultat pour staging/production sans rebuild.
  Essai Docker réel save/load/push/readback dans un registre **loopback synthétique**,
  identité conservée et volume retenu, formats Docker ET OCI relus ; refus si
  config chargée différente malgré des labels corrects. Aucun push GHCR réel.
  Fichiers : `deploy/image_provenance.py`, `scripts/image_delivery_smoke.py`, tests,
  workflow et runbook. PyYAML dev seulement ; aucune dépendance runtime ajoutée.
  Manuel **après fusion** : vérifier la première preuve réelle et le digest dans
  GHCR ; conserver preuves/runs/digests de rollback et définir l'accès en lecture.

- [ ] **V8–V9 / P0 — Validation GHCR réelle à faire après fusion humaine.**
  Premier run main réussi : 44125680324 sur `98a5a61`, image publiée et manifeste
  relu par le publisher. Vérifier visibilité/droits du package, puis exécuter `deploy.image_provenance` sur le digest publié et
  conserver la preuve distante ; aucune image n'est admissible avant ce contrôle.
  Pas de changement automatique de visibilité ni d'achat en cas de quota.

Preuves locales du 17 novembre : `scripts/check.sh` **483 tests réussis**,
Ruff lint/format, mypy, Django/migrations/statiques ; `check --deploy` et audit
runtime réussis ; actionlint et build Docker réussis ; essai registre loopback
réussi, volumes conservés. La CI et les smokes finaux sont consignés dans la PR.
Correctif de régression : le champ officiel Docker `CpuCfsQuota` remplace le
nom erroné qui refusait à tort les limites CPU disponibles. Test reproduisant
l'échec avant correction puis reconnaissance/refus selon les capacités réelles ;
contrôleur staging et son échantillonneur corrigés. V7 (mesure capacité VPS)
reste ouverte ; ce lot ne constitue aucune autorisation
SSH, de déploiement, de migration réelle ou de fusion.

### PR proposée 4 — CD manuel avec plan contrôlé et reprise

- [x] **V10 / P0 — Vérifié en synthétique : workflow et transport SSH strict.** Dépendances : PR 3 et PR 1–2 intégrées.
  Acceptation : `workflow_dispatch`, choix staging/production, provenance V9,
  checkout exclusivement de code de confiance ; host key SSH vérifiée par canal
  indépendant, `StrictHostKeyChecking=yes`, pas de confiance au seul ssh-keyscan.
  Configs/secrets propres à l'environnement ; transfert par liste explicite de
  fichiers versionnés correspondant à la version déployée, sans .env/secret/données.
  Concurrence par environnement et verrou hôte ; aucun build ni action sur Caddy commun.
  Validation exécutée en simulation : refus empreinte inconnue, image/injection/chemin invalide,
  environnement inattendu, accès concurrents ; simulation SSH et pile locale jetable.
  Fichiers : `.github/workflows/deploy.yml`, `deploy/delivery.py`, `deploy/release.py`, exemples privés et tests.
  Manuel : environnements `staging`/`production` déjà créés selon l'exploitant
  (17 novembre), chacun avec vars SSH_KNOWN_HOSTS/VPS_HOST/VPS_USER et secret
  VPS_SSH_KEY ; valeurs non inspectées. Vérifier restrictions main, reviewers
  production disponibles et host keys hors bande au lot CD. VPS_USER sans sudo
  ni Docker : aucun changement pendant les tests. Avant exécution CD autorisée,
  préparer l’accès au même démon Docker (privilèges équivalents administrateur),
  sans sudo général ; aucune clé à transmettre à l’agent.

- [x] **V11 / P0 — Vérifié en synthétique : plan puis application autorisée.** Dépendances : V4, V9–V10.
  Acceptation : mode `plan` puis mode `apply` séparé avec référence/hash du plan
  approuvé, image et état du schéma revérifiés sous verrou ; sauvegarde récente
  réussie, preuve d'exercice de restauration, échec fermé si prérequis absents.
  Plan examiné avant toute migration ; opération inconnue/destructive bloquée,
  aucune option de confirmation générique ne permet une migration destructive.
  Un seul lancement de migration par tentative autorisée ; reprise après échec
  sans relance aveugle. Bootstrap base neuve traité explicitement.
  Validation exécutée : absence/âge de backup, preuve invalide, plan périmé,
  migration inconnue/destructive, changement de schéma, double apply et échec partiel.
  Fichiers : `deploy/release.py`, `deploy/migrate.sh` réutilisé, `release_snapshot`, politique de migrations et tests.
  Manuel : reviewer examine le plan ; approbation GitHub production si disponible,
  sinon validation manuelle explicite liée au plan/run/digest ; aucune restauration automatique.

- [x] **V12 / P1 — Vérifié en synthétique : livraison, smoke et rollback.** Dépendance : V11.
  Acceptation : pull sans build, mise à jour contrôlée web/worker, healthchecks et
  HTTPS (auth staging), arrêt explicite du flux si échec ; historique atomique
  des digests précédent/candidat/réussi et du résultat de migration.
  Rollback d'image seulement si compatible avec le schéma et les protections ;
  aucune rétro-migration ni restauration de DB automatisée. Les autres sites
  Caddy et l'autre environnement doivent rester disponibles.
  Validation : refus/échecs migration/readiness/health/HTTPS, interruption et relance,
  état précédent conservé, rollback sans migration compatible et refus sinon.
  Fichiers : scripts CD et tests, `scripts/production_smoke.py` adapté, workflow CD.
  Manuel : décider rollback après revue, vérifier anciennes images conservées,
  sauvegarde et interruption d'écriture si intervention DB distincte nécessaire.

- [x] **V13 / P1 — Vérifié documentairement : runbook et gates opérateur.** Dépendances : V1–V12.
  Acceptation : mettre à jour la documentation existante : Caddy partagé,
  installation sans build VPS, GHCR/GitHub, plan/apply, staging start/stop,
  rollback, backup/restore, supervision et incidents, Brevo et SPF/DKIM/DMARC.
  Distinguer preuves synthétiques, contrôles réels et ouverture publique.
  Validation : `./scripts/check.sh`, CI complète, Compose/Caddy, tests
  synthétiques adaptés sans destruction de volumes, relecture des commandes Debian.
  Fichiers : `README.md`, `ARCHITECTURE.md`, `docs/lot-6-infrastructure.md`, `TASKS.md`, `LAUNCH_CHECKLIST.md`.
  Manuel : OVH/Caddy/DNS/capacité, GitHub/GHCR/SSH, Brevo, backup/alertes,
  informations légales ; toutes les conditions d'ouverture restent dans LAUNCH_CHECKLIST.

**Bilan PR 4 — préparation, pas activation :** branche `feat/cd-manuel`, main `98a5a61`.
Workflow manual/main seulement, plan et apply en deux runs avec run/hash, source
GitHub du plan revérifiée (dernière tentative), provenance V9 et huit fichiers
versionnés, aucun SSH réel pendant les tests. Compte/clé/cibles validés, clé
éphémère/known_hosts strict, permissions GITHUB_TOKEN en lecture seulement.
Un contrôleur hôte séparément revu, configs fixes et modèles privés ; nonce unique,
empreintes du schéma/configuration/secrets, preuves backup/restore et capacité,
verrou commun VPS + verrou environnement, détection de migration encore active.
Plan consommé avant mutation, un seul migrate.sh, journal unknown avant migration,
aucun restore ou retour de schéma, reprise par nouveau plan propre. Up web/worker
sans build ET sans dépendances : ni DB/capture ni Caddy ne sont recréés.
Rollback vers previous après succès, ou current après échec/interruption, avec
schéma identique et instrumentation CD ; images actives comparées au journal.

Preuves locales du 17 novembre : **552 tests réussis** sur la suite complète,
contrôles qualité/Django/migrations/statiques, audit runtime sans vulnérabilité
connue, actionlint, build et exercice staging/CD avec images distinctes ; modules hôte
chargés sous Python 3.13 ; renderer Compose réel/isolation, transport SSH simulé,
refus de preuves/plan/schéma/cible invalides, échecs et rejouage, concurrence.
L'exercice Docker utilise le harness staging existant, readiness/inventaires/HTTPS
réels et journal, identifiants d'images distincts, rollback et reprise ; admission
et provenance y sont simulées. Les migrations en attente sont couvertes en tests
unitaires ; le harness CD n'en applique aucune. Tous les volumes sont conservés.
Le nombre exact de tests, résultats des smokes et CI du commit final figurent dans
la PR ; les preuves historiques ci-dessous sont conservées.

- [ ] **V10–V13 — Activation réelle non satisfaite :** contrôleur et configurations
  privés à installer/revoir sur VPS, compte dédié et accès au démon Docker à
  autoriser (pas de sudo général utilisé), fingerprints SSH/restrictions/reviewers
  GitHub à éprouver. Inventaire/adoption ou bootstrap séparé, image post-lot-4,
  backup externe et exercice de restauration réels, capacité V7, premier plan/
  application/rollback autorisés sur cible. Aucun déploiement pendant cette PR.
- [ ] Retour automatisé vers une image historique dépourvue de release_snapshot :
  non pris en charge ; prévoir procédure opérateur distincte. Les versions
  compatibles CD restent soumises à égalité du schéma et provenance valide.

La publication main GHCR réelle de #35 est réussie (run 44125680324, `98a5a61`) ;
son manifeste a été relu par le publisher. La visibilité/droits et la première
vérification V9 du candidat CD seront contrôlés avant une livraison réelle ;
la case globale de validation opérationnelle GHCR ci-dessus reste ouverte.

**Preuves locales de PR 1 :** `./scripts/check.sh` : 386 tests, Ruff lint/format,
mypy, Django, migrations/statiques réussis ; contrôle `check --deploy`, audit
runtime sans vulnérabilité connue, build Docker et smoke partagé backup/restore
réussis. Les résultats des parcours navigateur et de la CI finale sont consignés
dans la PR. `compose.yaml`, Dockerfile et migrations historiques inchangés.
Les cases V1–V4 attestent l'implémentation et les tests synthétiques, **pas leur
installation sur VPS** ; toutes les actions manuelles ci-dessus restent à faire.
À la livraison de PR 1, V5–V13 restaient ouverts ; les bilans suivants ci-dessus
actualisent leur état. Une CI verte ne lève pas une dépendance d'accord ou de validation réelle. Aucune suppression de volume ni opération de production.

## Correctif UI — espacements des communautés et formulaires

### Corrections de revue — disponibilité, cycle de vie et brouillon

- [x] Garder l'attestation 18+ au niveau du compte sans bloquer les contrôles de
  disponibilité du service ; préserver la clôture des prêts existants.
- [x] Résoudre le modèle CD actif pour start/stop/status du staging, vérifier le
  journal, le chemin privé, le projet et les images ; refuser un retour implicite
  au profil source après livraison et partager les verrous hôte/environnement.
- [x] Restaurer les permissions 0755 des scripts shell avant transfert et les
  préserver avec SCP, notamment pour dump/restore montés dans PostgreSQL.
- [x] Conserver notes/partages en session après « Changer de jeu » pendant les
  recherches GET, la pagination et la navigation vers une proposition manuelle ;
  revalider au dernier POST, effacer après succès ou annulation explicite.

Tests de régression : comptes hérités, cible staging active/explicite/invalide,
concurrence avec CD, permissions du transfert, recherches/brouillon/annulation
et retrait d'appartenance. Le parcours navigateur recherche couvre le brouillon
avec JavaScript et sans JavaScript à 360/1280 px. Commandes de validation :
`./scripts/check.sh`, `docker compose build` et
`uv run --frozen --group browser python scripts/search_browser_smoke.py --browser /usr/bin/google-chrome`.
Tests locaux avec `APP_ENV=test`, `APP_BASE_URL=http://localhost:8000` et PostgreSQL
sur boucle locale ; la configuration Wi-Fi de l'application est conservée.
Bilan exécuté : `scripts/check.sh` réussi, **585 tests PostgreSQL réussis en
190,50 s**, Ruff/format, mypy, Django, absence de migration et collecte des
statiques validés. Build Docker réussi ; parcours navigateur recherche réussi,
y compris conservation du brouillon et annulation avec/sans JavaScript.
Aucune migration ajoutée, aucun déploiement VPS, aucune suppression de données.

Signalement du 18 novembre 2026 sur téléphone et ordinateur, depuis `main`
`27ec280`. [Périmètre et vérification](docs/ui-espacements.md).

- [x] Séparer badge, titre et compteur de communauté avec un rythme explicite,
  conserver la marge intérieure et le lien de carte accessible ; rétablir le
  padding de l’état vide, sans changer les données ni les droits.
- [x] Espacer les actions et liens des panneaux de formulaire, dont la copie
  d’invitation ; réutiliser les variables CSS communes.
- [x] Vérifier les espacements réels à 360 et 1 200 px ; conserver les parcours
  navigateur, contenus longs et repli sans JS aux cinq largeurs existantes.
- [x] Exécuter Ruff/format, mypy, Django/migrations/statiques, les 552 tests
  PostgreSQL et le build Docker ; documenter les preuves et limites.

La livraison sur le staging et la vérification sur Firefox Android physique
restent distinctes de cette correction locale.

### Complément UI — retours du 19 novembre 2026

Même branche/PR #37, depuis la première passe ci-dessus. [Bilan détaillé](docs/ui-retours-staging.md).

- [x] Regrouper les paramètres de communauté et l’invitation dans des fenêtres
  nommées, avec fermeture/Échap, restitution du focus et repli `details` sans JS.
- [x] Masquer les mutations du lien derrière une roue dentée et les actions de
  membre derrière un crayon, en conservant contrôles serveur et confirmations.
- [x] Proposer l’inscription directement dans la page de connexion ; ajouter une
  annulation d’adhésion qui nettoie seulement l’intention du compte/session.
- [x] Séparer choix du jeu et préparation d’exemplaire, conserver le brouillon au
  retour et ne créer les données qu’à la validation finale du parcours.
- [x] Déplacer la gestion/archivage d’un exemplaire sur sa page propriétaire et
  corriger la grille du détail mobile, notamment pour une copie pending privée.
- [x] Ajouter un favicon SVG local aux pages normales et d’erreur.
- [x] Vérifier permissions, CSRF, annulation sans adhésion, préparation sans
  création, revalidation et compatibilité des POST historiques ; 566 tests réussis.
- [x] Vérifier les parcours navigateur produit, recherche, UI et ajout avec/sans JS,
  ainsi que les fenêtres et la copie pending aux cinq largeurs existantes.

Restent à faire après livraison autorisée : relecture sur Firefox Android réel
et validation visuelle du propriétaire. Aucun déploiement effectué, aucune
migration ajoutée ; les portes d’exploitation du lot 6 restent distinctes.

## Vie privée — décisions du 22 novembre 2026

Branche `feat/confidentialite-conservation`, depuis `origin/main` `ee13ea1`.
Les choix du propriétaire remplacent toute hypothèse antérieure : historique clos
trois mois, inactivité douze mois/préavis trente jours, journaux sept jours, support
un mois, preuves six mois, diagnostics trente jours ; autres arbitrages 1/2/3/6/7/10
validés. [Décisions, architecture et runbook](docs/confidentialite-conservation.md).

- [x] Migrations additives de restriction, archivage, preuves, préavis et exceptions ;
  aucun nettoyage à la migration, aucune modification des migrations historiques.
- [x] Commande opérateur de simulation/application, hash d'état et revue humaine,
  restriction puis effacement effectif ; rôle maintenance exigé en production,
  droits runtime inchangés, atomicité et sérialisation avec les prêts.
- [x] Préserver remise/retour et contacts nécessaires aux prêts actifs, interdire les
  nouvelles activités ; transfert consenti ou archivage du dernier administrateur,
  conservation du catalogue et des comptes/collections des autres membres.
- [x] Préavis d'inactivité via l'outbox, sans jeton d'authentification ; trente jours
  comptés seulement après confirmation SMTP, nouvelle connexion invalidant la clôture.
- [x] Nettoyage quotidien des sessions expirées par le worker, sessions valides préservées.
- [x] Rétention manuelle assistée de l'historique trois mois et preuves six mois,
  exceptions justifiées bornées ; ledger signé privé et réconciliation sur restore,
  sans clôture forcée des prêts réapparus. Export exclusivement vers un fichier privé.
- [x] Préparer option de journal systemd isolé, Docker syslog Unix sans cache local,
  monitor compatible, unités de rotation/purge ; aucune configuration globale changée.
- [x] Actualiser SPEC/ARCHITECTURE/DESIGN/README et modèle légal sans identité réelle,
  distinguer préparation et activation réelle, corriger les formulations du staging.
- [ ] Installation/recette hôte : rétention effective de tous les journaux concernés
  et anciennes copies (DB, unités et Caddy partagé inclus) ; jamais validée par
  les seuls tests de transport ou une rotation limitée en volume.
- [ ] Routines opérateur effectives : revue hebdomadaire des demandes/échéances,
  revue mensuelle de l'inactivité, support un mois, diagnostics trente jours,
  preuves/exports six mois ; vérifier sur staging avant interventions réelles.
- [ ] Contrats/garanties des offres effectivement utilisées, adéquation Outlook.com,
  documents privés complets/revus et date de publication ; aucune garantie inventée.
- [ ] Déploiement et migrations autorisés séparément, nouvelle sauvegarde extérieure,
  exercice de suppression/restauration sur données synthétiques et observation réelle.

Les preuves synthétiques exactes et les limites restantes figurent dans la PR.
Aucun effacement, migration ou déploiement de production n'est exécuté par ce lot.

**Preuves locales finales (22 novembre) :** `scripts/check.sh` sur PostgreSQL
synthétique dédié : **625 tests réussis en 132,88 s**, Ruff lint/format, mypy
(131 sources), checks Django, migrations sans dérive et statiques. Audit runtime :
aucune vulnérabilité connue. Build Docker réussi avec CA Cloud montée en secret,
sans nouvelle dépendance. Chromium réel : connexion limitée, profil et prêt accepté
à 360/1280 px sans débordement. Transport Docker syslog réel vers socket Unix avec
cache local désactivé ; syntaxe des deux unités validée hors ligne avec dépendances
de démarrage isolées. La rétention journald en fonctionnement et la recette VPS
restent ouvertes. Une exécution de tests superposée a été écartée ; le résultat
ci-dessus provient d'une exécution unique dans une base synthétique distincte.

## Administration web minimale du catalogue — périmètre validé le 22 novembre 2026

Complément à B.6 (moteur et CLI déjà livrés), sans réimplémenter la modération.

- [x] Amorçage/promotion explicite d’un compte existant vérifié/adulte, accès OS de confiance, audit atomique et garde premier superuser.
- [x] AdminSite dédié, connexion applicative existante, droits staff/superuser actifs/vérifiés/adultes revérifiés ; aucun CRUD générique.
- [x] File paginée, filtres, détail, doublons/similaires et historique ; approbation/rejet/corrections via services métier.
- [x] CSRF, rate limit, formulaire périmé signé, audit/rollback ; préserver exemplaires, partages et prêts.
- [x] Suite complète (611 tests), lint/types/migrations et smoke navigateur local à 360/768/1280 px.
Résultat de la CI de la tête finale : consigné dans la description de PR.
- [x] Runbook premier opérateur et documentation du schéma/retour compatible.
- [ ] Validation sur staging après déploiement explicitement autorisé par l’exploitant ; aucune intervention production dans cette PR.

**Réconciliation avec #40, 23 novembre :** conserver les deux sections de
README/ARCHITECTURE/TASKS et le site opérateur. Suite combinée : **651 tests
réussis** (136,75 s), lint/format, mypy et migrations sans dérive. Les trois
migrations standard `admin` de Django 5.2.19 ont été lues et leurs empreintes
exactes ajoutées à la politique CD ; une base synthétique antérieure à l'admin
et à la conservation vérifie que le plan reconnaît toutes les migrations et
préserve les six états de prêt. Les 68 tests migration/CD concernés passent
après ce complément. Aucune migration de production n'est exécutée.

## Ansible — adoption progressive du VPS (23 novembre 2026)

Branche `feat/ansible-vps`, depuis `origin/main` `51c9995`.
[Périmètre et commandes](infra/ansible/README.md).

- [x] Environnement d'administration indépendant et verrouillé, inventaire d'exemple
  avec un seul hôte physique, SSH strict et compte admin distinct du compte CD.
- [x] Audit sans lecture des contenus privés : métadonnées des répertoires,
  configurations et contrôleur, versions des outils, état des timers existants.
- [x] Adoption des permissions des seuls répertoires existants, non récursive,
  simulation/approbation et refus des liens ou d'une initialisation implicite ;
  installation optionnelle des dépendances manquantes sans upgrade global.
- [x] Exclure inventaire privé et matériel sensible de Git/contexte Docker ;
  ne pas ajouter Ansible aux dépendances applicatives.
- [x] Valider lint/syntaxe et vrais playbooks sur fixtures locales : audit/check sans
  mutation, approbation, idempotence, préservation des secrets/CD/Caddy/unités/volume.
- [ ] Première recette SSH/sudo et adoption réelle sur Debian 13 par l'exploitant.
- [ ] Reprise sous Ansible du contrôleur sous verrou, des unités/alertes, de la
  rétention des journaux et des configurations Caddy/SSH/pare-feu par lots revus.

Ce lot n'est pas un provisionnement complet. Aucun accès VPS, déploiement,
redémarrage, remplacement de secret ou modification de données n'est effectué.

**Preuves locales :** ansible-lint profil production sans avertissement, syntaxe
des deux playbooks et actionlint réussis. Neuf tests Ansible réels réussis en
128,78 s, contrôle Python 3.12/cible 3.13 ; première passe de sept tests également
réussie en cible 3.12. `scripts/check.sh` : **651 tests applicatifs réussis en
196,84 s**, Ruff/format, mypy (134 sources), Django, migrations sans dérive et
statiques. Build Docker réussi ; un conteneur sans réseau confirme l'absence
d'Ansible et du répertoire d'administration dans l'image. Audit des dépendances
d'administration : aucune vulnérabilité connue. L'installation APT effective et
le transport SSH/sudo ne sont pas exercés ; la première adoption réelle reste
ouverte. Le résultat CI du commit final est indiqué dans la PR.

### Complément — promotion ponctuelle d'un compte, accord du 23 novembre

- [x] Playbook dédié, jamais appelé par audit/adopt, environnement/cible/confirmation
  explicites, bootstrap ou acteur existant, simulation par défaut et dans --check,
  double option d'application/approbation, paramètres personnels masqués.
- [x] Appel argv sans shell au socket Docker local et aux noms de conteneurs fixes,
  sous les verrous CD préexistants global/environnement ; refus sans création de
  verrou si absent ou redirigé, arrêt immédiat si une opération est en cours.
- [x] Étendre promote_operator : dry-run sans compte/audit écrit, if-needed sans
  nouvelle écriture mais contrôles conservés, JSON minimal et contexte applicatif
  vérifié avant recherche du compte. Préserver audit atomique et garde bootstrap.
- [x] Valider les tests PostgreSQL de simulation/idempotence/permissions/rollback,
  vrais playbooks locaux avec transport Docker remplacé, lint/types/migrations/build.
- [x] Documenter commande et variables privées, prérequis d'image déployée et limites
  de la simulation ; ne pas placer d'identité réelle dans l'inventaire versionné.
- [ ] Recette sur staging après déploiement autorisé d'une image compatible ; aucune
  habilitation réelle ou intervention VPS réalisée par cette PR.

**Preuves finales du complément :** `scripts/check.sh` réussi, **675 tests
applicatifs en 218,16 s**, dont bootstrap idempotent concurrent (une seule
attribution/trace), Ruff/format, mypy (135 sources), Django, migrations sans
dérive et statiques. **18 tests Ansible réussis en 204,70 s**, contrôle Python
3.12/cible 3.13, dont neuf cas de transport de promotion avec Docker remplacé
explicitement par une fixture. Ansible-lint profil production, syntaxe du
playbook et actionlint réussis. Build Docker réussi ; contrôles sans réseau des
quatre nouvelles options dans l'image et de l'absence d'Ansible/inventaire.
Aucun accès SSH ni aucune promotion réelle sur le VPS n'ont été effectués.

## CD — staging automatique après main (accord du 23 novembre 2026)

Branche `ci/staging-auto-deploy`, depuis `origin/main` `70dc136`.
Cette demande remplace le plan/apply manuel systématique pour staging/deploy ;
production, rollback, restauration et promotion opérateur restent manuels.
[Flux, prérequis GitHub, preuves et reprise](docs/staging-automatique.md).

- [x] Déclencher un workflow distinct après succès complet de la CI push/main,
  publication comprise ; refuser PR/fork/autre dépôt, tentative ou preuve étrangère.
- [x] Reprendre le digest testé et les assets au commit publié ; revérifier la
  provenance avant plan et apply, ignorer les candidats dépassés par main.
- [x] Plan et apply staging dans le même run avec hash/nonce exacts ; réutiliser
  transport SSH strict et contrôleur hôte sans modifier les gates de sauvegarde,
  restauration, capacité, migrations connues, readiness et HTTPS privé.
- [x] Conserver flux manuel/approbations production, verrou partagé staging,
  non-annulation des opérations en cours et échec sans retry/rollback/restore.
- [x] Documenter activation après fusion, règles de l'environnement GitHub staging,
  prérequis hôte, artefacts et reprise ; ne pas automatiser la promotion de comptes.
- [x] Vérifier la suite complète, lint/types/migrations, actionlint, build et
  exercice staging/CD synthétique ; consigner les résultats effectifs dans la PR.
- [ ] Après fusion : attester premier déclenchement automatique, digest livré,
  santé privée et absence d'impact production ; vérifier les règles GitHub staging
  pour ne pas conserver une approbation manuelle involontaire.

Aucun déploiement réel, SSH/VPS, habilitation ou modification de production n'est
effectué pendant cette implémentation. La première recette cible reste distincte.

**Preuves locales :** `scripts/check.sh` réussi, **723 tests PostgreSQL en
113,35 s**, Ruff/format, mypy (136 sources), Django, migrations sans dérive et
statiques ; contrôle production et plan de migrations vide. Build Docker et
actionlint 1.7.12 réussis. Exercice Docker staging/CD réussi : accès privé/capture,
production témoin inchangée, persistance/volumes, cycles de livraison, refus de
doublon, rollback d'image et reprise après échec santé. Les 48 nouveaux tests
couvrent source/provenance/artefact/plan, dépassement de main, transport partagé
et arrêt sans retry. Les métriques capacité restent invalides faute de cgroups
dans ce Docker local ; aucune validation de capacité VPS n'est revendiquée.
La CI du commit final est suivie dans la PR.

## Réconciliation de la recette staging — 23 novembre 2026

[Bilan sourcé et protocole de recette](docs/recette-staging-2026-11-23.md).

- [x] Vérifier les runs de publication, plan/apply et versions effectivement livrées : staging 45153646180 et production 45064624690, tous deux réussis.
- [x] Relier les contrôles du contrôleur aux preuves et réconcilier les cases strictement attestées de LAUNCH_CHECKLIST ; distinguer livraison, recette cible et synthétique.
- [x] Documenter le décalage d’image staging par rapport au complément Ansible et les prérequis d’accès privé, sans demander/utiliser de credentials VPS.
- [ ] Recette sur le staging cible : accès depuis cet environnement bloqué au proxy ; aucun compte créé/promu ni parcours cible effectué dans ce lot.
- [ ] Pièces d’exploitation et validation humaine restantes : ne pas cocher les cases composites sur la seule base de la CI.

Aucun déploiement, changement de configuration distante, accès SSH ou effacement exécuté. Deux cases préexistantes de LAUNCH_CHECKLIST sont cochées sur preuves (digest/provenance/Compose sans build et procédures documentées) ; les autres conservent leurs réserves.
