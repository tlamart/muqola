# Muqola — Contraintes et décisions d'architecture

## Stack et portée
La stack est **déjà validée** dans [ADR 0001](docs/adr/0001-stack.md) : Python 3.12, Django 5.2 LTS, PostgreSQL 17, templates HTML/CSS/JS locaux, Gunicorn/WhiteNoise et Docker Compose. La conserver ; ne pas réinitialiser le projet ni relancer un choix de framework pour les PR B/A/C.

L'[audit du code et des écarts](docs/plan-b-a-c.md) conserve la photographie de `main` à `e0fa4ca`, après fusion de la PR #25, et détaille les décisions validées. [SPEC](SPEC.md) fixe le comportement ; [TASKS](TASKS.md) détaille les trois PR et leurs validations. B (#29) et A (#30) sont intégrées dans `main` ; C (#28) est mise à jour sur cette base. Voir le [schéma et les migrations B](docs/catalogue-refonte.md), la [recherche intelligente A](docs/recherche-intelligente.md) et les [communautés/invitations C](docs/communautes-refonte.md). Le socle de préproduction séparé/Caddy existe depuis #24 ; il n'autorise aucun déploiement.

## Contraintes non négociables
- Monolithe modulaire, pas de microservices, Kubernetes ou architecture événementielle distribuée.
- Base relationnelle **PostgreSQL** avec migrations versionnées.
- Application web responsive ; pas de client mobile natif.
- Déploiement sur **petit VPS Linux indépendant** (cible 2 vCPU / 4 Go RAM / ~40 Go SSD), Docker Compose, reverse proxy Caddy et HTTPS ; ne pas dépendre d'un fournisseur VPS précis.
- Services logiques : identité, communautés, catalogue, exemplaires/visibilité, prêts, notifications, administration.
- API et contrôles d'accès côté serveur, requêtes paramétrées, protection CSRF si sessions cookies, cookies Secure/HttpOnly/SameSite adaptés, validation serveur, gestion sûre des secrets.
- Modèle de données et migrations pensés pour éviter les prêts concurrents ; **contrainte d'unicité partielle PostgreSQL** pour un `Loan` actif (`ACCEPTED`/`HANDED_OVER`) par exemplaire, plus vérification transactionnelle ; tests de concurrence avec vrai PostgreSQL.
- Intégration e-mail remplaçable (SMTP ou API) ; environnement de développement avec boîte de capture locale. **Outbox en PostgreSQL** et worker léger reprenant après redémarrage (pas de broker dédié).
- Fichiers de configuration d'exemple sans secrets ; aucun secret ni données réelles dans Git.

## Modèle logique et cible des évolutions
- `User` : id, email normalisé unique, hash mot de passe, date vérification, nom d'affichage, dates.
- `AccountToken` : jetons de vérification et de réinitialisation distingués par type, digest unique, expiration et consommation ; `RateBucket` pour les limites de débit.
- `Community`, `Membership` (rôle, actif/inactif), `CommunityInvite` (digest unique, copie chiffrée récupérable, expiration, révocation, créateur) et `PendingJoin`. **Cible C :** expiration nullable pour lien permanent par défaut, lien courant lisible par membres, mutations admin transactionnelles ; préserver les échéances/révocations existantes. Visibilité privée par défaut, découverte publique à préciser avant implémentation.
- `Game` : fiche générique UUID distincte des exemplaires, métadonnées et paire externe optionnelle, créateur protégé, `hidden` et `ever_reused`. `GameAlias` et `GameIllustration` (crédits/licence Commons) existent depuis #25 et sa migration `0002_wikidata_catalogue`. **B :** une fiche par jeu, type/base et gestion modérée des alias existants, propositions et validation distincte de masquage, correction/fusion opérateur auditée ; identifiants multiples à conserver sans perte. Migration additive sans inventer un type aux lignes héritées ; voir les arbitrages de l'audit. Aucune copie ni prêt supprimé lors d'une fusion.
- `OwnedGame` : gameId, ownerId, détails d'exemplaire, indicateur « retiré du prêt » ; zéro ou plusieurs communautés de visibilité.
- `GameVisibility` : ownedGameId, communityId ; unicité de la paire ; vérifier l'appartenance du propriétaire et l'absence de partage implicite.
- `Loan` : ownedGameId, borrowerId, ownerId, état, `dueDate` (DATE), dates de transition horodatées, message facultatif ; protéger l'exclusivité des prêts actifs par index partiel. Interdire les `REQUESTED` en double pour un même couple (exemplaire, emprunteur).
- `EmailOutbox` : type, destinataire, référence d'événement, statut/essais, prochaine tentative, dates ; ne pas conserver de jetons en clair dans les logs.
- Journal minimal des événements sensibles sans stockage inutile de données personnelles.

Documenter précisément clés étrangères, règles `ON DELETE`, contraintes d'unicité/index, politiques d'anonymisation et invariants des transitions. Indexer les recherches par titre, les appartenances/visibilités et les prêts par participant. **Les autorisations ne doivent pas reposer sur les seuls IDs fournis par le navigateur.**

## Fiabilité et exploitation
- Healthcheck, logs structurés sans secrets, politique de redémarrage, volumes persistants, migrations au déploiement **avec sauvegarde et procédure de retour arrière**, arrêt gracieux. Définir des limites mémoire raisonnables pour un VPS 4 Go. Pas d'images de production générées à partir de secrets.
- CI : format/lint, vérification de types si disponible, tests unitaires et intégration avec PostgreSQL ; build Docker.
- Sauvegardes quotidiennes **hors VPS**, rétention définie, chiffrement et procédure de restauration testée avant ouverture ; ne pas se contenter d'un volume Docker ou d'un snapshot non testé.
- Processus de déploiement reproductible et rollback documenté. Pas de déploiement automatique en production sans validation explicite.
- Dépendances maintenues, vérification de vulnérabilités, limitation de débit et protection anti-spam sur les endpoints publics.
- Politique de confidentialité, mentions légales, CGU adaptées au service, cookies (aucun traceur non nécessaire sans conformité), droits RGPD, durée de conservation et point de contact avant ouverture. Renseigner les coordonnées de l'exploitant et de l'hébergeur avec les **vraies** informations : ne jamais inventer de mentions légales. Prévoir une procédure de gestion des incidents de données.

## Hébergement et e-mails
Variables d'environnement pour URL publique, base PostgreSQL, secrets de session, fournisseur d'e-mails, adresse expéditrice, domaine. Documenter DNS A/AAAA, MX si réception nécessaire, SPF/DKIM/DMARC pour l'envoi, HTTPS. L'envoi d'e-mails de vérification doit être opérationnel avant ouverture des inscriptions.

## Sécurité particulière
- Vérifier l'appartenance et la visibilité pour **chaque** lecture et écriture ; tests IDOR entre communautés. Gérer explicitement l'accès des deux participants à un prêt déjà accepté après leur retrait d'une communauté, sans restaurer leur accès au catalogue.
- Éviter d'exposer des e-mails de membres, sauf aux deux parties d'un prêt accepté.
- Ne pas révéler l'existence d'une communauté privée par les réponses publiques.
- Les invitations sont des secrets : token fort, digest haché et copie chiffrée récupérable, éventuelle expiration, révocation, aucune journalisation du token brut. En C, contrôler l'appartenance active/vérifiée avant déchiffrement ; la permanence n'affaiblit pas la révocation. Protéger le token dans les URL contre les fuites par `Referer`, analytics ou logs ; éviter le contenu tiers sur l'écran d'invitation.
- Protéger les entrées libres contre XSS et les sorties contre injection ; ne pas rendre de HTML utilisateur, de fichiers ou d'images distantes arbitraires au MVP ; conserver la liste fermée d'origines Commons et les validations d'illustration introduites par #25. Mettre en place une politique CSP proportionnée, et limiter la taille des requêtes.
- Prévoir une suppression de compte sûre, y compris en présence de prêts en cours, avec procédure documentée. Prévoir une méthode opérateur minimale pour désactiver un compte ou retirer une fiche abusive, sans interface d'administration complète.


## Évolutions prévues B/A/C
- **B :** réutiliser les services `catalogue`/`inventory` et la console `operations`, pas de back-office générique. Autorisations propositions/illustrations privées distinctes du catalogue validé. Fusion logique source→cible sans changer `OwnedGame.id`, propriétaire ou `Loan.owned_game` ; contrôler collisions d'alias/IDs/signalements et cycles de base.
- **A :** normalisation persistée NFKD/casefold, `pg_trgm` et GIN sur titre et alias, migration additive concurrente `0004` et tests PostgreSQL réels. Filtrer les droits avant classement, regroupement par jeu, compteurs et pagination. GET classique/fragments HTML utilisent le même moteur et les mêmes templates ; JS natif avec debounce/annulation/génération, CSP `connect-src 'self'`. Le sélecteur `borrowable` exige les appartenances actuelles du lecteur et du propriétaire, puis `grouped` agrège sans jointure multiplicatrice. Aucun Meilisearch/Elasticsearch.
- **C :** mutations invitation sérialisées avec adhésion, pas de génération sur GET ; rotation invalide tous les anciens liens actifs, consultation réservée aux membres, droits privés maintenus. Pas de dépendance de schéma à B ; A dépend de B. Résoudre conflits CSS/JS/scripts/docs au rebase.
- Pas d'import BGG/Wikidata ni de catalogue réel dans Git/image. Une base neuve reste vide ; sur base existante, aucune purge, reset, réactivation ou suppression de références automatique. Sauvegarde/retour à tester avant toute migration réelle autorisée.
- Pas d'upload/URL d'image arbitraire ; photo utilisateur privée par défaut. Une collecte éventuelle exige stockage privé, validation de fichier/droits et approbation de publication, sinon conserver le visuel local. Les nouvelles règles ne valent pas autorisation d'ouvrir un service externe.


## Décision P1 — partage et prêt sans approbation préalable

`Game.LENDABLE_STATUSES` centralise pending/approved/legacy pour la propriété
`lendable` et les sélecteurs SQL `borrowable`/`available`. Le catalogue général
garde son filtre approved. `readable` n’ouvre pending qu’à l’auteur/opérateur ou
par un exemplaire actuellement visible ; aucun accès trans-communauté par UUID.
Les décisions et explications de revue ne sont pas rendues aux emprunteurs.

Le rejet et les demandes/acceptations utilisent le même `domain_write`. Le rejet
clôt les seules REQUESTED de la fiche et écrit leurs événements/outbox ; aucun
DELETE, aucune modification des prêts ACCEPTED/HANDED_OVER. Correction auteur
sans changement du statut rejeté. Fusions et validations gardent les références
physiques et permissions existantes. Aucun changement de schéma ni migration de
données requis. [Détail et vérification](docs/pret-fiches-en-attente.md).
