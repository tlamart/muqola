# Muqola — Checklist d'ouverture de la bêta publique

> **No-go** si une ligne marquée **BLOQUANT** n'est pas satisfaite. Les coordonnées et informations légales doivent être fournies par l'exploitant, et non inventées par Codex. La bêta signifie inscriptions publiques, communautés privées.

## Parcours réellement opérationnels
- [ ] **BLOQUANT** : inscription sans invitation, vérification e-mail réelle, connexion et réinitialisation du mot de passe.
- [ ] **BLOQUANT** : lien de communauté partageable, expirant/révocable, y compris pour une personne sans compte.
- [ ] **BLOQUANT** : création manuelle et recherche d'une fiche `Game` existante, ajout d'exemplaire sans communauté, contrôle des visibilités.
- [ ] **BLOQUANT** : demande, acceptation, remise et retour d'un jeu avec date future ; test avec deux comptes distincts.
- [ ] **BLOQUANT** : impossible d'accepter deux prêts simultanés pour un même exemplaire (test PostgreSQL).
- [ ] **BLOQUANT** : aucun accès croisé entre communautés par API/URL ; prêts déjà acceptés clôturables après retrait d'un membre.
- [ ] Mobile : parcourir tous les écrans à 360 px et sur un vrai téléphone ; navigation clavier et contrastes.

## Infrastructure et sécurité
- [ ] **BLOQUANT** : Compose de production séparé du Compose local (Mailpit interdit en production), `APP_ENV=production`, URL HTTPS, proxy de confiance, cookies sécurisés, secrets distincts, services internes non publiés et rôle PostgreSQL à privilèges minimaux.
- [ ] **BLOQUANT** : HTTPS opérationnel, domaine dirigé vers le bon VPS, secrets forts non présents dans Git.
- [ ] **BLOQUANT** : base PostgreSQL persistante (comptes, communautés, prêts, outbox et catalogue, y compris fiches importées) ; migration documentée ; sauvegarde **hors VPS**, chiffrée, avec rétention définie et **restaurée avec succès** sur un environnement de test.
- [ ] **BLOQUANT** : fournisseurs e-mail transactionnels configurés avec DNS SPF/DKIM/DMARC ; envoi réel et vérification des liens testés sur une nouvelle adresse.
- [ ] **BLOQUANT** : protections anti-bruteforce/anti-spam et vérifications d'autorisation activées.
- [ ] **BLOQUANT** : procédure de déploiement, retour arrière et gestion des incidents documentée.
- [ ] Suivi du taux d'erreur, de l'espace disque, du worker/outbox et des sauvegardes ; alertes minimales, en réutilisant les logs JSON existants.
- [ ] Tester la déconnexion, les liens expirés/révoqués, l'absence de fuites de jetons et la suppression de session.

## Catalogue et droits de réutilisation
- [ ] **BLOQUANT POUR L'IMPORT BGG PUBLIC** : droits de stockage et d'affichage permanents des données BGG vérifiés et documentés avant tout import sur l'instance publique. Ce point **ne bloque pas** une bêta avec catalogue manuel ou données autorisées.
- [ ] Import CSV uniquement sur décision explicite, jamais au démarrage, pendant les migrations ou le déploiement ; CSV réels absents de Git et des images Docker. Vérifier simulation, provenance et bilan de l'import.

## Légal, vie privée et contact
- [ ] **BLOQUANT** : mentions légales complétées avec exploitant, responsable du traitement, hébergeur et contact réels.
- [ ] **BLOQUANT** : politique de confidentialité et durées de conservation réellement applicables, informations sur les e-mails et leur partage lors des prêts ; traitement des droits RGPD.
- [ ] **BLOQUANT** : CGU cohérentes avec un service gratuit de mise en relation, précisant responsabilités et règles de prêt.
- [ ] **BLOQUANT** : procédure effective de **traitement** des demandes de suppression de compte déjà enregistrables, gestion des prêts actifs, délais et conservation ; contact de support fonctionnel.
- [ ] Vérifier les conditions de participation de mineurs ; décider explicitement si la bêta est réservée aux adultes avant ouverture et adapter CGU/UX.
- [ ] Ne pas intégrer de traceurs facultatifs sans traiter les exigences de consentement applicables.
- [ ] Vérifier disponibilité du nom/domaine et risques de conflit de marque.

## Validation finale
- [ ] Contrôles de production (`check --deploy`), CI, tests de permissions/IDOR et de concurrence PostgreSQL, tests navigateur et HTTPS/cookies réels exécutés ; résultats documentés.
- [ ] Plan de migration, sauvegarde préalable, procédure de rollback et d'incident validés ; aucune opération de production sans autorisation humaine explicite.
- [ ] Le propriétaire du projet teste lui-même le parcours complet en production avec deux comptes et un jeu factice.
- [ ] Le projet a une version identifiée/taguée et une méthode de revenir à la précédente.
- [ ] Les fonctionnalités hors MVP n'ont pas retardé les contrôles critiques ci-dessus.
