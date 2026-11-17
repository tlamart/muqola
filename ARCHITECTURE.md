# Muqola — Contraintes et décisions d'architecture

## Stack et portée
La stack est **déjà validée** dans [ADR 0001](docs/adr/0001-stack.md) : Python 3.12, Django 5.2 LTS, PostgreSQL 17, templates HTML/CSS/JS locaux, Gunicorn/WhiteNoise et Docker Compose. La conserver ; ne pas réinitialiser le projet ni relancer un choix de framework pour les PR B/A/C.

L'[audit du code et des écarts](docs/plan-b-a-c.md) conserve la photographie de `main` à `e0fa4ca`, après fusion de la PR #25, et détaille les décisions validées. [SPEC](SPEC.md) fixe le comportement ; [TASKS](TASKS.md) détaille les trois PR et leurs validations. B (#29), A (#30), C (#28) et P1 (#31) sont fusionnées dans `main`. Voir le [schéma et les migrations B](docs/catalogue-refonte.md), la [recherche intelligente A](docs/recherche-intelligente.md) et les [communautés/invitations C](docs/communautes-refonte.md). Le socle de préproduction séparé/Caddy existe depuis #24 ; il n'autorise aucun déploiement.

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
- `User` : id, email normalisé unique, hash mot de passe, date vérification, nom d'affichage, attestation 18+ horodatée nullable pour les comptes hérités, dates.
- `AccountToken` : jetons de vérification et de réinitialisation distingués par type, digest unique, expiration et consommation ; `RateBucket` pour les limites de débit.
- `Community`, `Membership` (rôle, actif/inactif), `CommunityInvite` (digest unique, copie chiffrée récupérable, expiration, révocation, créateur) et `PendingJoin`. **Cible C :** expiration nullable pour lien permanent par défaut, lien courant lisible par membres, mutations admin transactionnelles ; préserver les échéances/révocations existantes. Communautés strictement privées, sans découverte publique (décision C2 validée).
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

## Lot 6 — frontières de production préparées

Compose distinct, Caddy seul exposé, secrets montés par service, images de base
épinglées et trois rôles PostgreSQL : bootstrap/admin, propriétaire migration,
runtime DML sans DDL ni effacement d'historique. Migration explicite suivie de
réattribution contrôlée des droits. Le runtime ne modifie pas le registre des
migrations ni les définitions de permissions Django. Sauvegarde en flux
pg_dump/age/rclone, restauration authentifiée uniquement dans une base séparée
vide ; sonde hôte légère et heartbeat worker. Aucune infrastructure réelle créée.

Attestation 18+ obligatoire côté serveur pour les nouvelles activités ; les
prêts existants et l'exercice des droits restent accessibles sans attestation.
Documents légaux complets/revus hors image requis pour ouvrir les inscriptions
en production. [Audit, tests, procédures et validations humaines restantes](docs/lot-6-infrastructure.md).

## Caddy commun et sources de confiance

Le Compose applicatif conserve web/worker/migrate/DB et un réseau privé, sans
port publié. Seul web rejoint également le réseau externe `proxy`, sous l'alias
`muqola-web`. Le Caddy indépendant de `/opt/caddy` reste maître des ports et des
certificats, avec admin local pour reload ; les anciens volumes Caddy sont conservés.
Le filtrage JSON global et la réécriture des en-têtes sont fournis comme fragments
à fusionner sans écraser les autres applications.

Le middleware de proxy précède SecurityMiddleware : en production, forwarding
accepté depuis des IP Caddy exactes uniquement ; `X-Real-IP` validé alimente les
limites de débit tout en conservant les limites par compte. Aucune confiance
implicite au réseau partagé, aux en-têtes publics ou à un nom DNS. Le développement
local/Codespaces garde sa configuration. Les outils d'exploitation ciblent un
projet explicite, et le monitoring vérifie HTTPS via le Caddy commun sans attendre
un service edge dans le projet applicatif. [Procédure et limites](docs/lot-6-infrastructure.md#pr-1--caddy-partagé-et-exploitation-compatible).

## Staging éphémère

Production et staging étendent un socle de services `compose.runtime.yaml` ;
aucun changement du Compose de développement. Staging a projet, DB, volumes,
clés, documents et états distincts. Worker/DB/Mailpit restent sur un réseau privé
interne sans sortie ; seul web rejoint aussi le proxy partagé. Le Caddy commun
protège toutes les routes par authentification, supprime Authorization avant
l'upstream et ajoute noindex. Les flags Django production/18+/légal restent actifs.

Un contexte staging explicite exige la capture SMTP et les comptes fictifs,
sans assouplir la porte de production. Admission locale : isolation et valeurs
des secrets, revue de capacité et mesures de marge ; aucune migration appliquée
par le start, arrêt limité au staging et volumes conservés. Mesures réelles VPS
requises avant activation ; le smoke à deux piles n'en tient pas lieu.

## Image candidate et preuve GHCR

La CI construit une image linux/amd64 puis la teste sans rebuild ; archive
save/load, hash et digest canonique de configuration lient les jobs checks/publish
du même run. Ce digest est lu dans l’archive et revérifié après chargement ;
les handles moteur Docker/containerd peuvent différer sans altérer ce contenu.
Publication limitée aux push main réussis, packages:write au seul publisher.
Tags SHA complet et run/tentative pour la traçabilité ; digest comme seule entrée
de promotion. Le Dockerfile et les profils applicatifs restent inchangés.

Le validateur indépendant interroge GitHub pour le succès du run main et des deux
jobs, télécharge la preuve bornée liée au commit/tentative, puis relit le manifeste
GHCR par digest et compare sa configuration à l'image testée. Ni tag/label ni
record local ne vaut provenance. Échec fermé si preuve expirée ou registre/API
indisponible ; aucune reconstruction, installation VPS ou livraison dans ce lot.

## Livraison manuelle avec état durable

Workflow dispatch de confiance sur main, lectures seules GitHub/GHCR, provenance
revérifiée et transfert par liste de fichiers au commit publié. SSH identités
explicites/known_hosts vérifié, sans forwarding ; contrôleur hôte revu installé
séparément. Environnements isolés et opérations lourdes sérialisées par verrou
commun, en plus de la concurrence par environnement.

Plan avec nonce/hash, schéma, fichiers, configuration, état et preuves privées ;
application séparée après revue, diagnostic revérifié sous verrou. Empreintes
finies des migrations historiques revues ; bootstrap et migrations inconnues
refusés. Snapshot lit colonnes/précisions, index, contraintes, fonctions, triggers,
relations et droits sans données utilisateurs. Arrêt web/worker, marqueur durable
avant migration unique, readiness et HTTPS, historique puis pointeur actif.
Pas de recréation DB/capture, build, restore ou downgrade implicite. Une tentative
interrompue impose inspection/nouveau plan, les migrations encore actives bloquent
la reprise. Rollback limité aux versions CD avec schéma identique, sans migration.
