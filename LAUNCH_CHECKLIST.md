# Muqola — Checklist d'ouverture de la bêta publique

> Préparation technique du lot 6 disponible : [audit, runbooks et interventions humaines](docs/lot-6-infrastructure.md). Les cases ci-dessous concernent la validation réelle, pas uniquement les tests locaux.
>
> **No-go** si une ligne marquée **BLOQUANT** n'est pas satisfaite. Les coordonnées et informations légales doivent être fournies par l'exploitant, et non inventées par Codex. La bêta signifie inscriptions publiques, communautés privées.

## Point de situation — 23 novembre 2026

[Preuves de livraison et protocole de recette](docs/recette-staging-2026-11-23.md).
Le dernier apply staging tracé a réussi : [45153646180](https://github.com/tlamart/muqola/actions/runs/45153646180),
image `4ff9e011…`, commit `51c9995`. La production a une livraison réussie
[45064624690](https://github.com/tlamart/muqola/actions/runs/45064624690) sur `89b58e42…`
(`ee13ea1`). Les digests complets et limites des preuves figurent dans le bilan.

La livraison ne vaut pas recette utilisateur complète. L’accès depuis Codex au
staging est bloqué au proxy sortant ; les parcours sur la cible n’ont pas été
exécutés par cet audit. Les cases composites restent ouvertes si une partie
d’entre elles n’est pas attestée. Les validations historiques ci-dessous gardent
leur portée ; les cases cochées ici sont reliées à une preuve identifiée.

## Parcours réellement opérationnels
- [ ] **BLOQUANT** : inscription sans invitation, vérification e-mail réelle, connexion et réinitialisation du mot de passe.
- [ ] **BLOQUANT** : lien de communauté partageable, permanent par défaut et révocable/régénérable par admin, copiable par tout membre ; vérification e-mail et confirmation explicite, ancien lien invalidé, y compris pendant une inscription.
- [ ] **BLOQUANT** : proposition titre seul, validation administrative avec type/base requis et revue des doublons ; recherche de fiche validée par titre/alias/fautes, ajout d'exemplaire sans communauté, contrôle des visibilités, indicateur pending et absence de fuite vers une communauté non autorisée (aucun upload photo).
- [ ] **BLOQUANT** : demande, acceptation, remise et retour d'un jeu avec date future ; test avec deux comptes distincts.
- [ ] **BLOQUANT** : impossible d'accepter deux prêts simultanés pour un même exemplaire (test PostgreSQL).
- [ ] **BLOQUANT** : aucun accès croisé entre communautés par API/URL ; prêts déjà acceptés clôturables après retrait d'un membre.
- [ ] **BLOQUANT** : migration sur base peuplée et fusion de fiches sans perte de propriétaires/exemplaires/prêts ; catalogue neuf vide, aucun ancien import BGG/Wikidata ni catalogue réel versionné.
- [ ] Mobile : parcourir tous les écrans à 360 px et sur un vrai téléphone ; navigation clavier et contrastes.

## Infrastructure et sécurité
- [ ] **BLOQUANT** : Caddy commun seul exposé, web seul sur `proxy` sous `muqola-web`, DB/worker privés ; IP Caddy stable/exacte, en-têtes et limites vérifiés ; autre site disponible pendant reload, aucun secret dans les logs d'erreur.
- [x] **BLOQUANT** : image GHCR par digest, provenance main validée et disponibilité vérifiées ; contrôle `deploy.check_config` réussi ; aucune image locale/build sur le VPS. **Preuve :** applies staging/production ci-dessus, validation Compose appelée par le contrôleur et pull sans build ; périmètre des versions livrées, voir bilan.
- [ ] **BLOQUANT** : Compose de production séparé du Compose local (Mailpit interdit en production), `APP_ENV=production`, URL HTTPS, proxy de confiance, cookies sécurisés, secrets distincts, services internes non publiés et rôle PostgreSQL à privilèges minimaux.
- [ ] **BLOQUANT** : HTTPS opérationnel, domaine dirigé vers le bon VPS, secrets forts non présents dans Git.
- [ ] **BLOQUANT** : base PostgreSQL persistante (comptes, communautés, prêts, outbox et catalogue, y compris fiches importées) ; migration documentée ; sauvegarde **hors VPS**, chiffrée, avec rétention définie et **restaurée avec succès** sur un environnement de test.
- [ ] **BLOQUANT** : fournisseurs e-mail transactionnels configurés avec DNS SPF/DKIM/DMARC ; envoi réel et vérification des liens testés sur une nouvelle adresse.
- [ ] **BLOQUANT** : protections anti-bruteforce/anti-spam et vérifications d'autorisation activées.
- [x] **BLOQUANT** : procédure de déploiement, retour arrière et gestion des incidents documentée. **Preuve documentaire :** [runbook lot 6](docs/lot-6-infrastructure.md), contrôleur et [limites de retour compatible](docs/recette-staging-2026-11-23.md). L’exercice réel de rollback reste distinct.
- [ ] Suivi du taux d'erreur, de l'espace disque, du worker/outbox et des sauvegardes ; alertes minimales, en réutilisant les logs JSON existants.
- [ ] Tester la déconnexion, les liens historiques expirés, liens révoqués/régénérés, l'absence de fuites de jetons et la suppression de session.

## Catalogue et droits de réutilisation
- [ ] Catalogue neuf vide, sans ancien import BGG/Wikidata ; si données héritées, inventaire et revue des droits avant publication, sans suppression automatique. Aucune commande d'import historique recommandée au lancement.
- [ ] Vérifier absence de seed/import dans démarrage, migrations et déploiement, et exclusion des catalogues réels de Git/images ; les identifiants externes facultatifs ne déclenchent aucune intégration.

## Légal, vie privée et contact
- [ ] **BLOQUANT** : mentions légales complétées avec exploitant, responsable du traitement, hébergeur et contact réels.
- [ ] **BLOQUANT** : politique de confidentialité et durées de conservation réellement applicables, informations sur les e-mails et leur partage lors des prêts ; traitement des droits RGPD.
- [ ] **BLOQUANT** : CGU cohérentes avec un service gratuit de mise en relation, précisant responsabilités et règles de prêt.
- [ ] **BLOQUANT** : procédure effective de **traitement** des demandes de suppression de compte déjà enregistrables, gestion des prêts actifs, délais et conservation ; contact de support fonctionnel.
- [ ] **BLOQUANT** : bêta **18+ exclusivement** (décision définitive), vérifier sur le vrai site la case non précochée, le contrôle serveur, les anciens comptes et la clôture des prêts ; CGU revues cohérentes.
- [ ] Ne pas intégrer de traceurs facultatifs sans traiter les exigences de consentement applicables.
- [ ] Vérifier disponibilité du nom/domaine et risques de conflit de marque.

## Validation finale
- [ ] Contrôles de production (`check --deploy`), CI, tests de permissions/IDOR et de concurrence PostgreSQL, tests navigateur et HTTPS/cookies réels exécutés ; résultats documentés.
- [ ] Plan de migration, sauvegarde préalable, procédure de rollback et d'incident validés ; aucune opération de production sans autorisation humaine explicite.
- [ ] Le propriétaire du projet teste lui-même le parcours complet en production avec deux comptes et un jeu factice.
- [ ] Le projet a une version identifiée/taguée et une méthode de revenir à la précédente.
- [ ] Les fonctionnalités hors MVP n'ont pas retardé les contrôles critiques ci-dessus.

## Informations et actions à fournir par le propriétaire

- [ ] Domaine existant : confirmer droits/contact ACME et DNS staging ; aucun nouvel achat prévu.
- [ ] VPS OVH existant : confirmer SSH/pare-feu/mises à jour, stockage persistant, capacité et accès Docker restreints ; aucune nouvelle location prévue.
- [ ] SMTP : compte transactionnel, domaine/expéditeur vérifiés, identifiants privés, quotas et suivi bounces.
- [ ] DNS : A/AAAA fonctionnels, SPF unique, DKIM et DMARC selon fournisseur ; vérification réelle.
- [ ] Légal : identité/statut/contact de l'exploitant, publication, hébergeur/sous-traitants, bases et durées, droits RGPD/suppression effective, revue compétente des quatre textes.
- [ ] Backup : fournisseur externe/préfixe exclusif, compte restreint, clé privée age hors VPS, rétention, RPO/RTO et exercice de récupération autorisé.
- [ ] Alertes : canal indépendant et sonde extérieure testés avec panne/rétablissement.
- [ ] Autorisation de déploiement distincte après validation et preuves datées de chaque blocage levé.

## Staging avant activation réelle

- [ ] Domaine staging et Caddy commun : toutes les routes protégées, noindex, TLS réel et logs sans credentials/jetons.
- [ ] Projets, bases, volumes, clés, documents et états distincts ; aucune copie de production et seuls comptes fictifs.
- [ ] Capture SMTP interne sans relais ni credentials Brevo, UI non publiée, contrôle staging réussi ; portes 18+/légales conservées.
- [ ] Capacité mesurée sur le VPS sous charge/migration autorisées, marge validée et admission réussie ; staging arrêté hors usage.
- [ ] Plan de migration revu/appliqué explicitement, start/stop/restart et production témoin vérifiés ; aucune suppression de volume.
- [ ] Sonde HTTPS privée et monitoring utilisés lorsque staging actif, sauvegardes/états séparés si conservation nécessaire.

## Publication GHCR — contrôles réels après fusion

**Preuves partielles acquises :** checks/publish du [run 45134687469](https://github.com/tlamart/muqola/actions/runs/45134687469) réussis, provenance revérifiée lors des livraisons et image tirée par digest. Les revues de visibilité/droits et de conservation ci-dessous ne sont pas déduites de ces seuls runs.

- [ ] Premier run main : checks et publish réussis, package lié au dépôt, visibilité et droits revus.
- [ ] Digest/commit/run/tentative et preuve distante vérifiés avec `deploy.image_provenance` ; conservation des preuves et digests de rollback.
- [ ] Architecture VPS compatible avec l'image linux/amd64, accès registre en lecture défini si privé.
- [ ] Environnements staging/production : restrictions main, approbations disponibles et empreintes SSH revues ; droits VPS à préciser au lot CD, aucun ajout requis pour GHCR.

La préparation/test synthétique GHCR ne valide ni capacité VPS, ni déploiement,
ni SMTP réel, ni ouverture publique. Les conditions précédentes restent requises.

## CD manuel — activation réelle distincte

**Preuves partielles acquises :** plan/apply et santé HTTPS réussis sur les deux cibles, dont 401/noindex anonyme puis 200 privé pour la santé staging. La recette des parcours, la mesure sous charge, l’audit du stockage externe et l’exercice réel de rollback restent à consigner.

- [ ] Contrôleur revu installé, compte dédié et accès au démon Docker approuvés, configs/états/secrets privés lisibles par l'opérateur.
- [ ] Références Compose/volumes existants inventoriées, adoption ou bootstrap revu sans reset ; image publiée après ajout du protocole CD.
- [ ] Restrictions main, host keys hors bande et reviewers/fallback de revue testés ; jeton registre éphémère et SSH réel validés dans un créneau autorisé.
- [ ] Sauvegarde externe récente et compte rendu de restauration réelle, capacité 4 Go et alertes validés.
- [ ] Plan lu, hash approuvé, application staging puis promotion du même digest, reprise/rollback autorisés éprouvés sur cible.

Les tests synthétiques du contrôleur et la CI ne cochent pas ces validations.

## Conservation — décisions du 22 novembre 2026, activation encore requise

La recette fonctionnelle de l'image `89b58e42339c8eabf6fc11738d59c3bb0d85e002b528fc27fe7321d5809a7687`
a été confirmée par l'exploitant après la livraison [45064624690](https://github.com/tlamart/muqola/actions/runs/45064624690).
Les trois passages automatiques de supervision des 22 novembre 20:40, 20:46 et
20:51 UTC sont réussis. Cela ne valide pas le code de conservation ajouté ensuite.

- [ ] Déployer la préparation de [conservation](docs/confidentialite-conservation.md)
  après tests, revue/migrations additives et sauvegarde autorisées séparément.
- [ ] Éprouver restriction/effacement et clôture des prêts sur comptes synthétiques,
  y compris exception temporaire, préavis non remis, reconnexion et restauration.
- [ ] Installer/vérifier la rétention hôte sept jours et les anciennes copies, sans
  modifier les autres sites Caddy ni le journal global sans décision distincte.
- [ ] Vérifier les routines manuelles et contrats ; publier les documents privés
  actualisés seulement après revue. Ne pas traiter le modèle comme un document signé.
