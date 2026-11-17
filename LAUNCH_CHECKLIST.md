# Muqola — Checklist d'ouverture de la bêta publique

> Préparation technique du lot 6 disponible : [audit, runbooks et interventions humaines](docs/lot-6-infrastructure.md). Les cases ci-dessous concernent la validation réelle, pas uniquement les tests locaux.
>
> **No-go** si une ligne marquée **BLOQUANT** n'est pas satisfaite. Les coordonnées et informations légales doivent être fournies par l'exploitant, et non inventées par Codex. La bêta signifie inscriptions publiques, communautés privées.

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
- [ ] **BLOQUANT** : Compose de production séparé du Compose local (Mailpit interdit en production), `APP_ENV=production`, URL HTTPS, proxy de confiance, cookies sécurisés, secrets distincts, services internes non publiés et rôle PostgreSQL à privilèges minimaux.
- [ ] **BLOQUANT** : HTTPS opérationnel, domaine dirigé vers le bon VPS, secrets forts non présents dans Git.
- [ ] **BLOQUANT** : base PostgreSQL persistante (comptes, communautés, prêts, outbox et catalogue, y compris fiches importées) ; migration documentée ; sauvegarde **hors VPS**, chiffrée, avec rétention définie et **restaurée avec succès** sur un environnement de test.
- [ ] **BLOQUANT** : fournisseurs e-mail transactionnels configurés avec DNS SPF/DKIM/DMARC ; envoi réel et vérification des liens testés sur une nouvelle adresse.
- [ ] **BLOQUANT** : protections anti-bruteforce/anti-spam et vérifications d'autorisation activées.
- [ ] **BLOQUANT** : procédure de déploiement, retour arrière et gestion des incidents documentée.
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

- [ ] Domaine : nom/droits/budget, achat et contact ACME surveillé.
- [ ] VPS : fournisseur/région/budget, location, SSH/pare-feu/mises à jour, stockage persistant et accès Docker restreints.
- [ ] SMTP : compte transactionnel, domaine/expéditeur vérifiés, identifiants privés, quotas et suivi bounces.
- [ ] DNS : A/AAAA fonctionnels, SPF unique, DKIM et DMARC selon fournisseur ; vérification réelle.
- [ ] Légal : identité/statut/contact de l'exploitant, publication, hébergeur/sous-traitants, bases et durées, droits RGPD/suppression effective, revue compétente des quatre textes.
- [ ] Backup : fournisseur externe/préfixe exclusif, compte restreint, clé privée age hors VPS, rétention, RPO/RTO et exercice de récupération autorisé.
- [ ] Alertes : canal indépendant et sonde extérieure testés avec panne/rétablissement.
- [ ] Autorisation de déploiement distincte après validation et preuves datées de chaque blocage levé.
