# Lot 6 — Préparation à la validation sur infrastructure réelle

État du 17 novembre 2026. Base : `main` 0b5e928, après les PR #24
(infrastructure initiale), #25 (Wikidata/Commons), #28 (communautés), #29
(catalogue), #30 (recherche) et #31 (prêt des fiches en attente).
**Aucun achat, déploiement, compte fournisseur ou traitement de données réelles
n'a été effectué. L'ouverture de la bêta reste un no-go.**

## Audit et décisions

| Domaine | Déjà présent | Préparation livrée | Validation humaine restante |
| --- | --- | --- | --- |
| Application | Auth, vérification, CSRF, limites de débit, permissions, prêts concurrents, modération, recherche PostgreSQL | Régressions couvertes ; 18+ explicite et serveur | Deux comptes sur vrai domaine, téléphone réel |
| Production | Gunicorn, WhiteNoise, Caddy de préparation | Compose distinct, secrets fichiers, rôles DB, limites, healthchecks, images figées | VPS, DNS, ACME, charge/mémoire, pare-feu |
| E-mail | Outbox durable, retries, purge, worker | Secrets SMTP, TLS, heartbeat, détection échecs/retards | Fournisseur, SPF/DKIM/DMARC, livraison réelle |
| Sauvegarde | Absente | pg_dump → age → rclone, rétention, statut, restauration isolée | Stockage externe, droits, perte du VPS, exercice réel autorisé |
| Exploitation | Logs JSON sans contenus sensibles | Sonde HTTPS/DB/worker/outbox/disque/backup/erreurs, timers | Canal d'alerte et supervision externe |
| Conformité | Demandes de suppression enregistrées et outils opérateur | Modèles légaux, pages publiques, blocage inscription si incomplets, 18+ | Identité, coordonnées, bases légales, durées, revue juridique et traitement effectif des droits |

Les fichiers préparés ne constituent pas une preuve de fonctionnement sur un
VPS. Les tests synthétiques sont décrits plus bas ; la checklist de lancement
conserve ses validations réelles non cochées.

## Configuration et frontières de confiance

Ne jamais superposer `compose.yaml` (développement, Mailpit) au fichier de
production. Seul Caddy publie 80/443 TCP et 443 UDP. Web et DB n'ont aucun port
publié. Le réseau Docker et son administrateur font partie de la frontière de
confiance : Django accepte le protocole fourni par Caddy, qui écrase les en-têtes
clients. Ne pas connecter de conteneur non fiable à ce réseau.

Le runtime tourne sous UID 10001, en lecture seule et sans capacités Linux ;
`/tmp` est un tmpfs borné. PostgreSQL et les certificats Caddy persistent dans
des volumes distincts. Restart `unless-stopped`, arrêt gracieux et logs Docker
bornés à 3 × 5 Mo par service. Web 512 Mo, worker 192 Mo, DB 768 Mo, Caddy 128 Mo :
cible initiale **2 vCPU / 4 Go RAM**, à mesurer sur le VPS, sans garantie de charge.
Les limites CPU/mémoire Compose s'appliquent sans Swarm. Les erreurs Caddy
filtrent URI, en-têtes et objet requête ; aucun access log n’est activé, pour
protéger aussi les jetons lors d’une panne de Django.

Les versions PostgreSQL, Caddy et Python sont épinglées par digest. Construire
l'image applicative depuis un commit revu, la nommer `muqola:sha-<40 hex>` puis
renseigner de préférence son digest de registre immuable. Ne pas utiliser
`latest`. Revoir régulièrement correctifs et digests en PR, reconstruire,
auditer et tester avant toute mise à jour. Ne pas changer de version majeure
PostgreSQL sans procédure distincte.

Copier le modèle d'environnement **hors dépôt**, par exemple
`/etc/muqola/production.env`, mode 0600. Il ne contient que les paramètres et
chemins ; il ne faut pas injecter tous les secrets par `env_file`.
Dans `/etc/muqola/secrets`, créer séparément `django_key`,
`db_admin_password`, `db_migrate_password`, `db_app_password`, `smtp_password`.
Générer chaque valeur par un générateur cryptographique (au moins 64 caractères
aléatoires pour la clé Django), distincte du développement. Aucune valeur dans
Git, arguments de commande, ticket ou journal. Le répertoire parent doit être
0700, appartenir à l'administrateur ; fichiers lisibles par les UIDs des
conteneurs via ACL ou mode 0444 **à l'intérieur de ce répertoire 0700**. Les
secrets Compose locaux sont des bind mounts : `uid/gid/mode` ne remplace pas les
permissions hôte. Tester la lecture effective sous UID 10001 et sous PostgreSQL,
sans imprimer les valeurs. Ne pas rendre le répertoire traversable au public.

Web/worker reçoivent seulement clé Django, mot de passe applicatif et SMTP.
La maintenance reçoit le mot de passe migration ; seul PostgreSQL reçoit le
mot de passe administrateur. L'API Docker permet d'accéder aux secrets : limiter
strictement les membres du groupe Docker et l'accès SSH. Les changements de
clé Django invalident sessions et contenus d'outbox chiffrés : ne jamais la
remplacer sans plan de rotation et reprise des messages.

### Rôles et migrations

Sur **volume neuf uniquement**, `10-roles.sh` crée :

- `muqola_admin` : bootstrap, sauvegarde/restauration, jamais utilisé par Django ;
- `muqola_migrate` : propriétaire du schéma/tables, non superuser, droit CREATE
  sur la base pour l'extension de confiance `pg_trgm` ; maintenance ponctuelle ;
- `muqola_app` : connexion, USAGE, SELECT/INSERT/UPDATE et séquences ; pas de DDL,
  rôle, extension ni propriété. DELETE limité aux sessions, jetons, buckets de
  débit, outbox, invitations en attente et visibilités nécessaires au métier.
  Aucun DELETE de prêt, exemplaire, utilisateur ou historique ; aucun accès au
  registre des migrations ni écriture des définitions de permissions Django.

Les migrations historiques sont intactes. La migration adulte ajoute une date
nullable, **sans inventer d'attestation pour les comptes existants**, ni
supprimer de ligne. Son retour arrière est volontairement interdit pour ne pas
perdre les attestations.

Commande de validation structurelle, sans démarrage :

```sh
docker compose --env-file .env.production.example -f compose.prod.yaml config --quiet
```

Commandes **futures**, seulement après configuration et autorisation de
l'opérateur, depuis `/opt/muqola` (aucune exécutée ici sur infrastructure réelle) :

```sh
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml up -d --wait db
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml run --rm migrate python manage.py migrate --plan
# Sauvegarde préalable vérifiée, revue du plan et autorisation avant la suite :
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml run --rm migrate
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml up -d --wait web worker caddy
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml exec -T web python manage.py check --deploy --fail-level WARNING
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml exec -T web python manage.py production_readiness
```

Le service `migrate` n'est jamais lancé automatiquement ; son script applique
les migrations puis réattribue les droits runtime contrôlés. Sur **volume
existant**, l'init PostgreSQL ne tourne pas : arrêter les écritures, inventorier
rôles, propriétaires, extensions et dépendances, sauvegarder et restaurer dans
un environnement isolé, préparer un script d'adoption revu (création des deux
rôles, transfert explicite des objets applicatifs, révocation des droits PUBLIC,
réattribution des seuls droits runtime). Tester ce script sur la copie avant
autorisation de production. **Ne pas effacer un volume pour relancer l'init**, ne
pas lancer de `REASSIGN OWNED` global sans inventaire. Cette adoption n'est pas
une opération automatique fournie pour une base réelle inconnue.

## Sauvegarde et restauration

Outils hôte : Python 3.12, Docker Compose, **age 1.3.2** et rclone (version
maintenue à fixer dans l'inventaire VPS). La clé privée age est générée et
conservée **hors VPS**, avec copie de secours chiffrée accessible à l'opérateur.
Le VPS n'a besoin que du destinataire public `age1…`. La perte de la clé privée
rend les sauvegardes irrécupérables. La récupération inclut, par canal distinct,
la clé Django correspondante et les paramètres applicatifs ; le dump ne
contient pas les rôles/mots de passe PostgreSQL.

Adapter `deploy/backup.example.json` dans `/etc/muqola/backup.json` (0600), avec
un préfixe de stockage **exclusivement dédié**. Configurer rclone dans un fichier
0600 : compte à droits minimaux limité au préfixe, TLS vérifié, SFTP avec fichier
`known_hosts` vérifié par canal indépendant. Backends préparés : S3, B2, SFTP,
Azure Blob ou WebDAV HTTPS. Le backend local est refusé sauf indicateur explicite
`synthetic: true`, réservé au test. Éviter toute configuration désactivant TLS.
Ne jamais mettre les clés de stockage dans le JSON, l'environnement ou argv.

```sh
python -m deploy.backup --config /etc/muqola/backup.json
```

Flux réel : `pg_dump --format=custom --no-owner --no-acl` → chiffrement age →
`rclone rcat`. Aucun dump clair sur disque lors de la sauvegarde. Le fichier
`.partial` n'est promu qu'après succès des trois processus et taille non nulle.
Une sauvegarde cohérente PostgreSQL inclut comptes, catalogue/alias/crédits
Commons, communautés, exemplaires, prêts et outbox. Rétention par défaut 30 jours,
minimum 7 sauvegardes, configurables ; seuls les noms horodatés générés par cet
outil sont éligibles. Les fichiers étrangers et `.partial` ne sont jamais
supprimés automatiquement : surveiller leur accumulation après échecs.

Le statut 0600 conserve dernière tentative, succès et nom d'objet ; un échec ne
remplace pas la date du dernier succès. Exit non nul et événement JSON générique,
sans credentials ni contenu de dump. Verrou local pour empêcher deux sauvegardes
simultanées. Le compte distant doit permettre liste/écriture/renommage/suppression
sur ce seul préfixe. Tester réellement chaque fournisseur ; les droits et les
renommages peuvent varier. Les copies immuables/versionnées avec identité de
suppression séparée constituent une protection supplémentaire contre une
compromission du VPS, à configurer chez le fournisseur.

### Exercice de restauration futur

1. Choisir un environnement de récupération isolé, jamais la base active ;
   installer les mêmes versions, rôles et clé Django via canaux privés.
2. Y créer une base **vide**, nommée `muqola_restore_<identifiant>`, appartenant
   à `muqola_migrate`. Ne pas lancer les migrations avant d'importer le dump.
3. Fournir temporairement la clé age privée dans un fichier 0600 sur un poste
   de récupération de confiance, avec espace libre suffisant (borne par défaut
   2 Gio + marge). La retirer ensuite selon la politique de ce poste.
4. Exécuter depuis ce poste, avec une configuration pointant sur la pile isolée :

```sh
python -m deploy.restore --config /etc/muqola/restore.json \
  --object HORODATAGE-IDENTIFIANT.dump.age \
  --database muqola_restore_exercice --identity /chemin/prive/identity.txt
```

5. Vérifier les comptes, références, états de tous les prêts, nombres de lignes,
   alias/crédits, accès privés et contrôle d'intégrité ; consigner date, durée,
   taille, résultat, RPO/RTO mesurés. Ne pas envoyer l'ancienne outbox vers les
   vrais destinataires pendant l'exercice (worker arrêté/transport isolé).
6. Une restauration de service ou un basculement reste une opération distincte,
   explicitement autorisée avec sauvegarde et plan de retour.

La restauration refuse le nom actif et les cibles non `muqola_restore_*`, ainsi
que les bases contenant des tables applicatives. Le flux est intégralement
authentifié par age avant d'appeler PostgreSQL ; dump clair temporaire 0600 dans
un répertoire 0700, supprimé en fin de traitement, taille bornée. Utiliser un
disque hôte chiffré pour protéger les blocs temporaires. `pg_restore` fonctionne
en transaction unique, sans `--clean`, `DROP` ou `TRUNCATE`. Les droits runtime
sont réappliqués ensuite ; si cette dernière étape échoue, diagnostiquer/rejouer
les droits sur la copie, ne pas réimporter dans une base désormais peuplée.

## SMTP, DNS et délivrabilité

Réutilisation exclusive de `EmailOutbox` et `process_outbox`. `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD_FILE`, `EMAIL_FROM` sont
configurables. STARTTLS : 587/TLS=true/SSL=false ; TLS implicite :
465/TLS=false/SSL=true. Certificats vérifiés par Python ; ne jamais activer les
deux modes. Délai réseau borné par les paramètres existants. Mailpit demeure
strictement local. `production_readiness` refuse le transport local/factice ou
sans TLS, les identifiants modèles, les droits DB excessifs et les textes
juridiques incomplets ; ce contrôle ne prouve pas l'envoi réel.

Le fournisseur doit autoriser l'expéditeur et le domaine. Reprendre **ses**
valeurs DNS : un seul SPF cohérent (incluant les autres expéditeurs autorisés),
DKIM avec son sélecteur et sa clé publique, DMARC avec alignement du domaine
From/SPF ou DKIM. Démarrer la politique DMARC selon la revue de vos flux et
traiter les rapports dans une boîte réellement surveillée ; aucune adresse ni
valeur SPF/DKIM fictive ne doit être publiée.

Après configuration et autorisation, utiliser deux adresses de test contrôlées
sur des fournisseurs distincts : inscription/vérification, reset, invitation et
prêt complet. Contrôler inbox/spam, en-têtes Authentication-Results
SPF/DKIM/DMARC, bon domaine HTTPS, expiration et usage unique des liens, absence
de jetons dans les logs. Simuler un échec SMTP sur **la pile de test** et vérifier
retry après reprise sans fuite ni perte de demande. L'outbox applique backoff,
20 tentatives max, échec après 7 jours ; l'état SMTP accepté ne garantit pas la
livraison finale. Consulter les bounces chez le fournisseur, sans ajouter de
webhook non demandé. Une reprise après interruption peut produire un doublon
(effet externe SMTP hors transaction) ; contrôler avant tout retry opérateur.

## Supervision, alertes et incidents

`python -m deploy.monitor --config /etc/muqola/monitor.json` : HTTPS avec
certificat vérifié, état/health web/worker/DB/Caddy, SELECT 1, outbox en échec
ou en retard >15 minutes, disque (<1 Gio libre ou >90 %), sauvegarde absente,
échouée ou âgée de >36 h, erreurs JSON web/worker des 10 dernières minutes.
Ne publie que des codes, jamais les logs bruts ou identités. Heartbeat worker
actualisé après une boucle réussie, périmé après 120 s. `/health/ready/` reste
minimal/public ; les métriques d'exploitation restent privées.

Adapter les modèles systemd `deploy/systemd/` : backup quotidien, sonde toutes
les 5 minutes. Installer l'environnement Python hôte depuis le lock, protéger
configs 0600 et répertoires 0700. Créer et tester **avant activation**
`/etc/muqola/notify-operator` et `muqola-alert@.service` à partir du modèle,
via canal indépendant du SMTP applicatif. `OnFailure` transmet uniquement le
nom du service. Test volontaire d'échec puis de rétablissement, suivi journal
systemd et accusé opérateur. Aucun canal réel n'est livré/configuré. Une sonde
externe indépendante doit détecter panne du VPS lui-même et expiration TLS ;
la sonde locale seule ne peut pas le faire. Les logs bornés sont une alerte
légère, pas une garantie de détecter toutes les erreurs à très haut débit.

Incident : limiter l'accès si confidentialité en jeu, préserver les journaux
sans les publier, identifier version et dernière sauvegarde, vérifier DB,
worker, disque puis SMTP, appliquer correction revue. Ne pas purger l'outbox ni
relancer des migrations à l'aveugle. Compromission : révoquer/rotater les secrets
par canal privé et examiner l'impact RGPD avec le responsable désigné.
Rollback : une ancienne image ne doit être utilisée qu'après vérification de
compatibilité avec le schéma courant et des protections 18+/confidentialité. Pas de downgrade de migration irréversible.
Tester le retour sur copie restaurée ; restaurer/basculer en production exige
une autorisation distincte et l'évaluation des écritures postérieures au backup.

## Adultes, légal et suppression de compte

Bêta **18 ans et plus**, décision définitive. Case obligatoire non précochée,
validation serveur et date d'attestation, sans date de naissance ni document
identitaire. Les anciens comptes doivent attester avant toute nouvelle activité.
Les prêts existants restent consultables et clôturables (annuler/refuser/remettre/
rendre), sans accepter de nouveau prêt. Le profil et les demandes de suppression restent
accessibles sans attestation. Ce mécanisme est une attestation, pas
une vérification d'identité ; faire valider la formulation juridique.

Compléter les quatre modèles `docs/legal/*.txt.example` hors dépôt, monter
`mentions.txt`, `terms.txt`, `privacy.txt`, `support.txt` en lecture seule dans
`LEGAL_DOCUMENTS_DIR`. Renseigner identité/statut de l'exploitant, directeur de
publication si applicable, contact, responsable du traitement, hébergeur et
sous-traitants/lieux/transferts, bases légales, durées effectives, procédure de
droits, délais et juridiction après revue compétente. Aucun texte modèle n'est
une consultation juridique. `LEGAL_REVIEWED=true` signifie **revue réellement
faite**, pas simple copie du modèle. Sinon pages 503 et inscription production
fermée ; les marqueurs de remplacement ne sont jamais affichés comme mentions
validées. Les pages échappent le texte (pas de HTML arbitraire).

Procédure de droits à finaliser avec l'exploitant :

1. Surveiller quotidiennement `ops` (demandes existantes) et le contact renseigné ;
   consigner réception, vérification proportionnée d'identité et échéance légale.
2. Vérifier prêts actifs et obligations de conservation, informer la personne du
   périmètre, des motifs et des délais réellement applicables. Ne pas empêcher
   la clôture d'un prêt ou effacer les références historiques à l'aveugle.
3. Le verrouillage/désactivation opérateur existant empêche la nouvelle activité ;
   **ce n'est pas un effacement RGPD**. Préparer sur une copie synthétique une
   opération ciblée de suppression/anonymisation conforme à la politique validée,
   incluant profil, champs libres, jetons/outbox, invitations, signalements et
   liens historiques. Faire revoir et autoriser son application réelle. Aucun
   effacement automatique global n'est livré par ce lot, car les bases légales et
   durées de l'exploitant sont inconnues.
4. Répondre, enregistrer l'exécution et ne clôturer la demande dans l'outil qu'après
   traitement effectif ; prévoir les exceptions justifiées et une voie de recours.
   Les backups expirent selon rétention ; rejouer les décisions d'effacement
   après toute restauration avant réouverture, sans réintroduire de comptes.

**Bloquant public :** opérateur responsable, procédure effective éprouvée et
politique de conservation juridiquement validée. Le simple stockage d'une
requête de suppression ne satisfait pas cette exigence.

## Preuves reproductibles sur données synthétiques

```sh
./scripts/check.sh
APP_ENV=production APP_BASE_URL=https://muqola.example.test \
  uv run --frozen python manage.py check --deploy --fail-level WARNING
uv run --frozen pip-audit -r requirements.txt --disable-pip --no-deps
# Après build local, avec age/age-keygen et rclone installés :
uv run --frozen python scripts/production_smoke.py --image muqola:local
```

Résultats locaux du 17 novembre : `scripts/check.sh` (lint, format, typage,
Django, migrations, statiques et **373 tests réussis**), contrôle Django de
production et structure Compose valides, audit runtime sans vulnérabilité connue.
Les six scripts navigateur (socle, comptes, recherche, produit, catalogue et UI)
réussissent, avec et sans JavaScript selon les parcours, de 360 à 1280 px.
Le smoke production avec vrais outils a réussi le chiffrement/restauration,
la rétention, les rôles, TLS/CSRF et les refus de clé/base invalides ; la PR et sa
CI conservent la preuve de la version finale. Aucune validation distante réelle.

Le smoke crée un projet `muqola-lot6-synthetic-<aléatoire>` distinct et des
volumes neufs, sans ports DB/web publiés. HTTPS loopback avec CA Caddy interne
(pas d'ACME), cookies/CSRF et en-têtes vérifiés, interdictions SQL testées,
pg_dump/age/rclone réels, rétention, restauration dans une base distincte, refus
clé erronée/base peuplée, comparaison de toutes les lignes et des six états de
prêts. La source reste identique. Seuls ses propres volumes synthétiques sont
retirés. Ce test n'atteste ni stockage distant réel, ni SMTP réel, ni certificat
public. Résultats exacts et CI sont consignés dans la PR.

## Interventions du propriétaire et ordre des validations

1. **Domaine :** vérifier nom/marque, budget et titulaire ; achat seulement sur
   votre initiative. Fournir domaine et contact ACME surveillé.
2. **VPS :** choisir fournisseur/région/budget, louer et durcir SSH/pare-feu,
   mises à jour, accès Docker restreint, disque chiffré si nécessaire et volumes.
3. **SMTP :** créer compte transactionnel, vérifier domaine/expéditeur, quotas,
   contact bounces ; déposer credentials privés, choisir TLS correct.
4. **DNS :** A/AAAA exacts (ne pas publier IPv6 non fonctionnel), SPF/DKIM/DMARC
   du fournisseur ; vérifier résolution, ACME et renouvellement.
5. **Légal :** fournir les informations ci-dessus, faire revoir les textes et
   éprouver la procédure de suppression ; monter seulement les versions validées.
6. **Backup externe :** créer stockage et identité restreinte, garder clé age
   privée hors VPS, définir rétention/RPO/RTO et tester restauration autorisée.
7. **Exploitation :** versions figées, secrets et accès, canal d'alerte indépendant,
   sonde externe, tests panne/reprise, puis validation des parcours réels.
8. **Ouverture :** toutes les cases BLOQUANT satisfaites, preuves datées et
   autorisation humaine explicite distincte. Ne pas déployer depuis cette PR.
