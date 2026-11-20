# Muqola

**Lots 1 à 5 — MVP en développement**, sur le socle et la stack validés : Python 3.12,
Django 5.2 LTS, PostgreSQL 17, HTML/CSS serveur, Gunicorn/WhiteNoise.
Lire [l'ADR](docs/adr/0001-stack.md) et [les frontières des modules](docs/modules.md).
Comptes vérifiés, communautés privées, catalogue interne réutilisable, exemplaires
à zéro ou plusieurs visibilités, prêts et notifications capturées sont disponibles.
[Guide de validation sur ordinateur](docs/manual-validation.md) ;
[comptes et sécurité](docs/lot-1-accounts.md). Les lots 1 à 5 et le correctif
Gunicorn sont intégrés dans `main` depuis la fusion de la PR #8. La PR #24 a ajouté
un socle de production distinct, sans déploiement ; les validations opérationnelles
du lot 6 restent à faire ([état exact](docs/lot-6-infrastructure.md)).

## État actuel et préparation de production

Les PR #24 (socle production), #25 (Wikidata/Commons), #28 (communautés),
#29 (catalogue), #30 (recherche), #31 (prêt des fiches en attente) et #32
(préparation production), #33 (Caddy partagé) et #34 (staging privé) et #35 (GHCR) sont fusionnées.
Les communautés restent privées ; les fiches pending sont empruntables seulement
via un exemplaire autorisé, sans publication au catalogue général.

Le lot 6 prépare des secrets montés en fichiers, trois rôles PostgreSQL, HTTPS,
sauvegardes chiffrées/restauration isolée, supervision et SMTP sur l'outbox existante.
**Bêta réservée aux 18+** : case obligatoire à l'inscription, confirmation pour les
anciens comptes, clôture des prêts existants préservée. Les documents légaux
incomplets bloquent l'inscription en production.

[Audit et procédures du lot 6](docs/lot-6-infrastructure.md) : configuration,
commandes futures, sauvegarde/restore, SMTP/DNS, alertes, incidents, droits et
checklist des interventions du propriétaire. [Modèles légaux](docs/legal) à
compléter et faire revoir hors dépôt. [Conditions d'ouverture](LAUNCH_CHECKLIST.md)
restent non validées tant que VPS, domaine, e-mails, stockage externe et conformité
réels ne sont pas vérifiés. **Aucun déploiement réalisé ni autorisé par cette PR.**

Le Compose applicatif utilise maintenant le **Caddy commun de `/opt/caddy`** :
aucun service Caddy ni port publié dans `compose.prod.yaml`. Seul web rejoint
`proxy` sous `muqola-web` ; DB/worker/migration restent privés. Le fragment
`deploy/Caddyfile` doit être intégré et validé par l'exploitant, avec le filtre
global fourni et une IP Caddy stable explicitement approuvée. Le projet/volume
PostgreSQL et les protections #32 sont conservés. Le staging, le flux GHCR et
le CD manuel sont documentés ci-dessous. La première
publication GHCR a réussi après fusion de #35, sans déploiement.
[Configuration, reload sans interruption et précontrôles](docs/lot-6-infrastructure.md#pr-1--caddy-partagé-et-exploitation-compatible).

Contrôle structurel sans démarrage :

```sh
docker compose --env-file .env.production.example -f compose.prod.yaml config --quiet
```

Test local exclusivement synthétique, après build et installation de age/rclone :

```sh
uv run --frozen python scripts/production_smoke.py --image muqola:local
```

Il crée sa propre pile/volumes jetables, utilise une CA locale et ne contacte ni
ACME ni SMTP externe. Voir le guide pour les limites et les preuves de validation.

## Images GHCR et promotion

La CI construit et teste une seule image, puis la conserve par save/load avec
contrôle d'identité et de hash. **Après fusion seulement**, le job publish peut
la publier sur GHCR si tous les contrôles du même push main réussissent ; aucune
publication depuis une PR. Seul ce job possède `packages:write`.

Le résumé du run fournit le digest et la preuve de publication (90 jours).
Les tags SHA/run servent au suivi ; staging et production devront utiliser
**le même digest** `ghcr.io/tlamart/muqola@sha256:…`, sans reconstruction.
Le contrôle `python3 -m deploy.image_provenance --image … --run-id … --attempt …`
vérifie l'API GitHub, les deux jobs réussis, la preuve distante et le manifeste GHCR.
Un label ou un fichier local seul n'autorise aucune promotion.
[Flux, commandes, rétention, accès privé et limites](docs/lot-6-infrastructure.md#pr-3--image-testée-et-publication-ghcr).

Les environnements GitHub staging/production et leurs variables SSH sont déclarés
configurés par l'exploitant. Ils serviront au lot CD manuel ; **aucun droit sudo
ou Docker supplémentaire n'est nécessaire à VPS_USER pour ce lot GHCR**.
Aucun déploiement ni accès SSH depuis cette PR.

## CD manuel : plan puis application

Le workflow `Manual Muqola delivery` est déclenché volontairement sur main.
Choisir staging/production, digest publié, run/tentative de publication et `plan`.
Lire l'artefact `muqola-plan-<environnement>-<tentative>`, puis lancer un **second
run** `apply` avec son run ID et son hash exact après revue. Le nom du run affiche
l'opération et la référence d'approbation. Aucune livraison sur push/PR.

Provenance revérifiée, SSH strict avec les variables/secrets déjà configurés,
verrou hôte, sauvegarde/restauration/capacité obligatoires et migrations connues
seulement. Aucun build VPS, recréation de DB, restore ou suppression de volume.
Un rollback d'image nécessite son propre plan et un schéma compatible.
[Installation opérateur, permissions nécessaires, adoption, reprise et limites](docs/lot-6-infrastructure.md#pr-4--cd-manuel-plan-contrôlé-et-reprise).

Ce flux exige une image publiée après intégration de ce lot et un contrôleur
revu/installé sur le VPS. Les accès Docker du compte SSH seront à préparer par
l'exploitant avant une exécution autorisée ; aucun sudo général n'est utilisé.
Aucun accès au VPS ni déploiement réel effectué pendant cette préparation.

## Staging privé éphémère

`compose.staging.yaml` réutilise `compose.runtime.yaml` avec la production ;
le développement local conserve son Compose. Le staging reste **arrêté par défaut**,
avec projet/base/volumes/secrets propres, alias `muqola-staging-web` et réseau privé
sans sortie pour DB/worker/Mailpit. Aucun port SMTP, interface de capture, Django
ou PostgreSQL n'est publié. Le Caddy commun exige une authentification dédiée
sur toutes les routes et ajoute `noindex` ; son fragment est `deploy/Caddyfile.staging`.

Même image par digest, `APP_ENV=production`, HTTPS/cookies/CSRF, 18+ et porte légale
conservés. Le contexte `DEPLOYMENT_ENV=staging` exige Mailpit interne sans credentials
et restreint les comptes à `@example.test`. Il ne satisfait jamais le contrôle
`production_readiness` ; `staging_readiness` constitue sa porte dédiée.

Le cycle de vie préparé dans `deploy/staging.py` vérifie l'isolation, les valeurs
des secrets, la revue de capacité et la marge réelle mémoire/CPU/disque avant
start ; il ne construit aucune image et n'applique aucune migration. Les opérations
VPS restent à autoriser séparément. [Préparation, plan de migration, start/stop,
mesures et limites](docs/lot-6-infrastructure.md#pr-2--staging-privé-éphémère).

Test uniquement synthétique, sans accès au VPS et avec conservation des volumes :

```sh
uv run --frozen python scripts/staging_smoke.py --image muqola:local
```

## Démarrer localement

Prérequis : Git, Python 3.12 et Docker Engine avec Compose v2 récent (supportant
`--wait` et `service_completed_successfully`). Aucun service externe nécessaire.

```sh
python3 scripts/init_dev.py
# Démarrage : une seule commande après la création du .env local.
docker compose up --build --wait --wait-timeout 120
```

Le script crée `.env` en permission 0600 avec deux secrets **locaux** aléatoires,
sans les afficher ; il conserve tout fichier existant. `.env.example` documente
les variables. Ne pas réutiliser ces secrets pour la production.

- Application : http://localhost:8000
- Capture Mailpit : http://localhost:8025 (aucun relais configuré).
- Vivacité sans base : `/health/live/` ; disponibilité avec `SELECT 1` PostgreSQL :
  `/health/ready/` (503 générique si la base est indisponible).
- Migrations automatiques par un service ponctuel avant démarrage des workers.
- Ports HTTP liés à 127.0.0.1 ; PostgreSQL et SMTP non publiés par défaut.
- La readiness ne vérifie pas la délivrabilité SMTP ni la complétude du produit.

```sh
docker compose exec web python manage.py send_dev_email
# Lire le message synthétique test@example.test dans Mailpit.
docker compose logs --tail=50 web migrate
docker compose stop
# Supprime les conteneurs et le réseau, conserve le volume PostgreSQL :
docker compose down
# Redémarre et conserve les données :
docker compose up --build --wait --wait-timeout 120
```

Ne pas utiliser `down --volumes` sur une base à conserver. Les messages Mailpit
sont éphémères (capture de développement seulement). Les logs applicatifs sont
JSON et ne conservent ni URL/jetons ni données de requête. Pas de logs d'accès
Gunicorn. Les logs d'incidents restent volontairement succincts et sans données de requête.

Le serveur local utilise deux workers Gunicorn `gthread`, quatre threads chacun,
avec une attente keep-alive de 2 s et le watchdog conservé à 30 s. Les préconnexions
TCP silencieuses restent dans le sélecteur, sans bloquer un worker entier.
[Diagnostic des anciens timeouts, reproduction et limites](docs/http-timeouts.md).

## Développement hors conteneur et vérifications

Installer [uv](https://docs.astral.sh/uv/) **0.13.5**, puis :

```sh
uv sync --frozen
set -a
. ./.env
set +a
```

Pour exécuter les outils sur l'hôte, rendre la base disponible **localement**
sans changer le Compose partagé, par exemple créer `work/host.compose.yaml` :

```yaml
services:
  db:
    ports: ['127.0.0.1:55432:5432']
  mailpit:
    ports: ['127.0.0.1:11025:1025']
```

```sh
docker compose -f compose.yaml -f work/host.compose.yaml up -d db mailpit
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 EMAIL_PORT=11025 PYTHONPATH="$PWD"
./scripts/check.sh
```

Le rôle de base local/CI peut créer la base de tests éphémère `test_muqola` ;
ce rôle est réservé au développement, pas à la production.
Les workflows CI, publication GHCR et CD manuel utilisent explicitement
`ubuntu-24.04`, afin de dissocier une migration d’Ubuntu des mises à jour de
`ubuntu-latest`. Leurs actions JavaScript utilisent Node.js 24 et sont fixées
par SHA de commit, avec la version lisible en commentaire. Pour les mettre à
jour, relire les notes de version, vérifier le runtime et les entrées/sorties,
puis valider les deux workflows avec `actionlint` et la CI. Le Node.js des
actions est indépendant du runtime Python de l’application et du VPS.

Les tests Docker de production et de staging demandent un sous-réseau libre à
Docker, puis le déclarent explicitement avant d’y attacher Caddy avec son IP
fixe. Seul le réseau vide créé par le test est recréé ; aucun réseau existant
ni volume n’est modifié. Cette déclaration est nécessaire sur les moteurs
Docker qui refusent les IP fixes avec un pool IPAM alloué implicitement.

`check.sh` exécute réellement : Ruff lint/format, mypy, contrôles Django,
détection de migration manquante, migration, collecte des statiques et pytest
avec PostgreSQL. Il s'arrête à la première erreur. Les tests ne remplacent
**jamais** PostgreSQL par SQLite. Pour une itération :

```sh
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy config muqola tests manage.py
APP_BASE_URL=https://muqola.example.test APP_ENV=production uv run --frozen python manage.py check --deploy --fail-level WARNING
uv run --frozen pip-audit -r requirements.txt --disable-pip --no-deps --progress-spinner off
```

Le contrôle production nécessite une APP_BASE_URL HTTPS et conserve
intentionnellement HSTS sans sous-domaines ni
preload tant que le domaine n'est pas validé : seuls W005/W021 sont désactivés,
avec justification dans settings/ADR. HTTPS réel, proxy de confiance et tests
de cookies réels seront validés au lot 6. Ce contrôle ne vaut pas homologation.

La CI GitHub répète ces contrôles, vérifie le lock runtime généré, audite les
dépendances runtime et démarre un Compose propre (build Docker + migrations +
healthcheck + vraie capture SMTP locale). Aucun déploiement automatique.
Les tests de configuration vérifient qu'en production, l'origine CSRF autorisée
est exactement `APP_BASE_URL`, même en présence de variables Codespaces ; les
cookies sécurisés et la redirection HTTPS restent obligatoires.

## Migrations et dépendances

```sh
# Créer puis relire une migration, sur base de développement uniquement :
uv run --frozen python manage.py makemigrations
uv run --frozen python manage.py migrate --plan
uv run --frozen python manage.py migrate
# Vérifier le schéma livré :
uv run --frozen python manage.py makemigrations --check --dry-run
uv run --frozen python manage.py showmigrations
# Mise à jour volontaire des dépendances, puis revue, audit et CI :
uv lock --upgrade
uv sync --frozen
uv export --frozen --no-dev --no-emit-project --output-file requirements.txt
```

`uv.lock` fixe aussi les outils de développement ; `requirements.txt` est généré
et contient les versions/hachages runtime utilisés par pip dans Docker.
Ne pas l'éditer à la main. L'image fonctionne avec un UID non root (10001),
système de fichiers en lecture seule et `/tmp` éphémère via Compose. Les budgets
mémoire ne constituent pas une mesure de charge sur le VPS cible.

## Variables

| Variable | Usage |
| --- | --- |
| APP_ENV | development/test/production ; Compose local impose development |
| APP_BASE_URL | Origine de confiance des liens, http://localhost:8000 en dev ; HTTPS en production |
| DJANGO_SECRET_KEY / DJANGO_SECRET_KEY_FILE | Secret direct local ou fichier production (exclusifs), ≥50 caractères aléatoires |
| ALLOWED_HOSTS | Hôtes HTTP acceptés, séparés par virgules |
| TRUSTED_PROXY_IPS | IP exactes du Caddy approuvé en production ; jamais tout le subnet partagé |
| MUQOLA_PROJECT / PROXY_NETWORK | Projet production stable et réseau externe Caddy ; ne pas changer le nom d'un volume existant |
| MUQOLA_IMAGE | Référence GHCR par digest immuable en production |
| POSTGRES_DB / USER / PASSWORD | Base et identifiants locaux, aucun défaut pour le mot de passe |
| POSTGRES_HOST / PORT | Connexion directe ; Compose impose db:5432 |
| EMAIL_HOST / PORT | Mailpit:1025 en local ; fournisseur TLS en production |
| EMAIL_FROM | Expéditeur fictif en développement |
| EMAIL_BACKEND | Backend Django remplaçable ; SMTP par défaut |
| EMAIL_HOST_USER / PASSWORD / PASSWORD_FILE | Vides en dev/test ; login et secret fichier en production |
| EMAIL_USE_TLS / SSL | Un seul mode obligatoire pour SMTP de production |
| POSTGRES_PASSWORD_FILE | Secret du rôle DB monté en production, exclusif avec POSTGRES_PASSWORD |
| LEGAL_DOCUMENTS_DIR / LEGAL_REVIEWED | Quatre textes hors dépôt, revue réelle requise avant inscription production |

APP_BASE_URL définit l'origine de confiance des liens de compte et doit être
HTTPS en production ; aucune origine n'est reprise du Host client. Aucune clé de fournisseur,
identifiant VPS ou donnée réelle ne doit entrer dans ce développement.

## Limites et exploitation future

Ce Compose est exclusivement local. Caddy/HTTPS, fournisseur SMTP réel,
URL publique de production, DNS SPF/DKIM/DMARC, rôle PostgreSQL à privilèges réduits,
sauvegardes externes chiffrées/restaurées et supervision sont
préparés dans le lot 6 ; leur configuration réelle doit être validée avant ouverture, selon [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).
L'outbox des comptes/prêts et son worker sont livrés. Les sauvegardes de production
ne sont pas encore opérationnelles. Le développement refuse les identifiants SMTP
et hôtes non locaux pour conserver la capture Mailpit.

Le déploiement futur : image identifiée → sauvegarde vérifiée → revue du plan de
migration → migration ponctuelle → démarrage → smoke tests. Revenir à l'image
précédente uniquement si son schéma reste compatible ; sinon restauration
contrôlée depuis sauvegarde après validation humaine, avec arrêt des écritures
et annonce de la perte potentielle depuis la sauvegarde. Aucune migration
destructive ni opération de production sans accord et stratégie de retour.
La préparation distincte est décrite dans [le document du lot 6](docs/lot-6-infrastructure.md) ;
restauration testée, SMTP réel, supervision et autorisation de lancement restent requis.

Les invariants des lots 2–5 sont testés : invitations privées, fiches réutilisables,
exemplaires à zéro ou plusieurs visibilités, date de retour et contacts uniquement
pendant un prêt accepté/remis. B/A/C et P1 sont fusionnées ; voir [TASKS.md](TASKS.md).
Aucune opération de production automatique.

## Test navigateur du socle

Un navigateur Chromium installé est nécessaire. Lancer Compose puis :

```sh
uv sync --frozen --group browser
uv run --frozen --group browser python scripts/browser_smoke.py --browser /usr/bin/chromium
```

Le script ouvre réellement l'accueil à 360 et 1280 px, vérifie HTTP/CSS, langue,
clavier, absence de débordement et d'échec réseau. Captures locales dans `work/`
(non versionnées). Adapter `--browser` à l'exécutable installé. Les tests métier,
IDOR et concurrence des prêts sont dans pytest et le parcours produit ; ce smoke
se limite au socle. Résultat initial : [docs/lot-0-validation.md](docs/lot-0-validation.md).


## Parcours des comptes (lot 1)

Lancer Compose : le service `worker` traite automatiquement les e-mails en base.
Ouvrir `/accounts/signup/`, créer un compte fictif, puis lire le lien dans Mailpit.
Ouvrir le lien et confirmer par bouton ; connexion ensuite. Un compte non vérifié
reste limité à l'attente/renvoi et ne peut ouvrir `/accounts/dashboard/` (403).
Mot de passe oublié depuis la connexion ; le lien dure 1 h, la vérification 24 h.
Un renvoi invalide le lien précédent. La déconnexion passe par un formulaire POST.

```sh
# Traiter ponctuellement la file (débogage) :
docker compose exec web python manage.py process_outbox --once
# Observer sans afficher les charges ou les liens :
docker compose logs --tail=30 worker
# Sessions expirées (à planifier quotidiennement avant production) :
docker compose exec web python manage.py clearsessions
# Tests du parcours complet avec navigateur installé :
uv sync --frozen --group browser
uv run --frozen --group browser python scripts/accounts_browser_smoke.py --browser /usr/bin/chromium
```

La commande navigateur crée des comptes fictifs @example.test dans la base de
développement ; ne pas la lancer sur une production. Les captures sont dans
`work/`. Les e-mails sont en file chiffrée jusqu'à envoi/reprise ; ne pas remplacer
DJANGO_SECRET_KEY avant d'avoir traité les charges encore chiffrées, y compris
les échecs. Les liens de compte sont hachés, à usage unique.
Voir [le document du lot 1](docs/lot-1-accounts.md) pour contraintes, ON DELETE,
limites de débit, rétention, compromis et limitations des tests.

## Rotation du secret Django

`DJANGO_SECRET_KEY` sert aussi à chiffrer les invitations récupérables. Vider
l'outbox ne suffit donc pas à préparer une rotation. Répéter cette procédure
avec des données fictives avant toute intervention réelle autorisée :

1. Avec l'ancienne clé, faire révoquer les invitations actives à remplacer par
   leurs administrateurs et prévenir les destinataires des liens.
   Conserver les sauvegardes et secrets nécessaires séparément, hors Git et logs.
2. Suspendre les nouvelles écritures (arrêter le service web) et laisser le
   worker traiter les e-mails en attente ou en échec avec l'ancienne clé.
   Vérifier qu'aucune charge chiffrée ne reste à envoyer ; ce correctif ne
   récupère pas une outbox chiffrée avec une clé perdue.
3. Arrêter les processus web/worker, remplacer le secret dans leur environnement,
   puis les redémarrer avec la même nouvelle valeur, sans afficher cette valeur.
4. Se reconnecter : la rotation peut invalider les anciennes sessions. Vérifier
   que les pages de communauté restent utilisables. Une invitation illisible
   affiche un message et conserve son bouton de révocation ; la révoquer puis
   créer et partager un nouveau lien, chiffré avec la nouvelle clé.
5. Vérifier avec un autre compte fictif que le nouveau lien permet l'adhésion
   explicite et que le lien révoqué est refusé.

La rotation seule ne révoque pas les liens déjà partagés : leurs digests restent
valides jusqu'à révocation explicite ou expiration. Un GET ne modifie ni les
invitations ni les appartenances. Aucun ancien secret n'est consulté pour
déchiffrer les invitations ; les liens illisibles sont remplacés explicitement.
Les nouveaux liens sont permanents par défaut : ne pas attendre une échéance
pour les invalider. La régénération admin remplace atomiquement tous les liens
encore valides ; les membres doivent copier et partager le nouveau lien.
[Contrat, migration et vérifications PR C](docs/communautes-refonte.md).

## Tester sur Android avec GitHub Codespaces

Le [guide Android pas à pas](docs/codespaces-android.md) explique la création du
Codespace, l'ouverture des deux URL HTTPS privées, la capture Mailpit, le test
d'inscription/vérification/connexion et l'arrêt. La configuration `.devcontainer`
réutilise Compose avec un profil de développement isolé et vérifie la visibilité
privée des ports avant de démarrer les services. PostgreSQL n'est pas publié.

## Communautés privées (lot 2)

Depuis **Mes communautés**, créer une communauté, générer un lien et le partager
avec un second compte fictif vérifié. L'adhésion doit être confirmée ; les liens
sont actuellement multiusages, expirables et révocables. La cible C prévoit lien
permanent par défaut consultable/copiable par tous les membres, révocation et
régénération réservées aux administrateurs, cartes enrichies et création dédiée.
Ces évolutions attendent validation du plan et implémentation ; les droits privés
sont conservés et la découverte publique reste à préciser. Les liens historiques
à échéance doivent garder leur date, sans réactivation des liens expirés/révoqués.
Transférer l'administration avant le départ du dernier administrateur. Les détails et membres restent privés.
Si la désactivation du seul administrateur bloque la gestion, une
[reprise opérateur explicite et tracée](docs/lot-5-notifications.md#reprise-opérateur)
permet de promouvoir un membre existant ; aucune promotion automatique.
[Schéma, permissions, concurrence et vérifications](docs/lot-2-communities.md).

## Catalogue et collection — PR B

[Statuts, revue opérateur, fusion, migrations et retour](docs/catalogue-refonte.md).
**Mes propositions** permet de suivre les motifs de correction/refus ; les nouveaux
exemplaires peuvent être partagés et prêtés immédiatement dans les communautés choisies,
même si la fiche est encore en attente. Sans partage, ils restent privés.
Aucun upload photo ni saisie d’URL d’image.

**Avec B** : ajout rapide par titre principal ou alias (accents/casse normalisés),
10 résultats/page, priorité au titre exact, sélection et création d'exemplaire
atomiques, parcours sans JS ; zéro communauté = exemplaire privé. Plusieurs
exemplaires d'un jeu sont possibles sans exposer les quantités privées.
La création manuelle propose une fiche hors du catalogue général ; un opérateur
la valide pour le réemploi global. La revue ne bloque pas le prêt entre membres
autorisés. [Décision P1 et gestion du rejet](docs/pret-fiches-en-attente.md). La
case « autre édition » est supprimée ; une homonymie nécessite une justification
et une revue administrative. Les fiches héritées restent à réviser, avec leurs
exemplaires et prêts conservés ; elles ne sont plus réutilisables dans le catalogue validé.
Après masquage, le propriétaire peut encore modifier son exemplaire non archivé,
sans rétablir son prêt ni autoriser une nouvelle copie de la fiche masquée.
[Schéma et invariants historiques](docs/lot-3-catalogue.md).
Depuis la fusion de la [PR #25](https://github.com/tlamart/muqola/pull/25),
`GameAlias`, `GameIllustration`, les crédits/licences et la recherche d'alias
existent déjà ; la migration `0002_wikidata_catalogue` est intégrée. Les
illustrations Commons approuvées sont affichées avec crédits et licence propres
à chaque image, distincts des données Wikidata CC0. Sans illustration valide,
le visuel local reste utilisé ; aucune URL/image n'est saisie par les utilisateurs.
Le [document technique Wikidata/Commons](docs/wikidata-catalogue.md) décrit ce
fonctionnement existant. B réutilise ce socle et préserve ses références,
sans considérer `approved_by_owner` comme une modération des futures photos utilisateur.

**Catalogue B implémenté** : une fiche par jeu (pas par édition), propositions
titre seul puis validation administrative avec type/base si applicable,
gestion modérée des alias existants, corrections et fusions sans perte de références ;
aucun upload photo, illustrations Commons approuvées ou visuel local de remplacement. Une base neuve démarre vide ; aucune
purge d'une instance existante n'est autorisée par cette décision.
**Recherche A implémentée** : recherche instantanée sur titre/alias avec fautes,
regroupement par jeu et contrôles de droits avant compteurs et classement.

### Imports locaux existants (historiques #22 et #25)

Les commandes `import_games` et `import_wikidata_games` sont conservées comme
entrées désactivées. Elles refusaient les doublons par paire source/ID dans
leur ancien parcours manuel ; B interdit désormais toute nouvelle ingestion. Aucun de ces imports n'est exécuté
au démarrage, par les migrations ou par le déploiement. Leur présence ne démontre ni l'existence
de données importées dans une instance ni des droits d'utilisation d'un catalogue.

**Décision actuelle : ne pas importer les anciens CSV BGG ou Wikidata.**
Les anciennes instructions d'import ne constituent plus le parcours recommandé ;
aucun import n'est réalisé par ces trois PR. B définit le comportement
de ces deux commandes : **elles sont maintenant désactivées**, y compris en
simulation et par leur entrée Python. Les métadonnées existantes sont conservées. La PR #25 est désormais intégrée à la base du plan ; sa fusion n'exécute
aucun import et n'autorise ni purge ni nouvel import dans ces trois PR.

Ne jamais versionner un catalogue réel, dump, fixture de catalogue ou photo privée,
ni les embarquer dans l'image Docker. Les fichiers réels éventuels restent hors
Git ; les exclusions `data/` Git/Docker sont déjà présentes. Les tests utilisent
des jeux synthétiques minimaux. Ne jamais utiliser `git add -f` pour ces données.

Si une instance possède des fiches héritées, conserver leurs UUID et références
aux propriétaires, exemplaires, partages et prêts ; inventorier puis réviser
selon le [plan de migration](docs/plan-b-a-c.md#stratégie-de-migration-et-de-retour).
Ne pas supprimer de volume, masquer en masse, effacer des fiches ou changer leurs
références pour « repartir vide ». Toute opération destructive requiert une
autorisation explicite, sauvegarde restaurable et retour arrière.

Vérification **du parcours actuel** sur pile locale avec Mailpit et jeu synthétique
proposé par formulaire puis validé par la console opérateur (script adapté à B) :

```sh
uv run --frozen --group browser python scripts/catalogue_browser_smoke.py --title "Titre déjà présent" --browser /usr/bin/chromium
```

## Prêts (lot 4)

Depuis une copie accessible, **Demander ce jeu** avec date de retour future.
Le propriétaire accepte/refuse ; après acceptation les contacts e-mail deviennent
visibles aux seules parties, puis le propriétaire confirme remise et retour.
Les contacts disparaissent des réponses après clôture. Retrait de communauté ou
de partage ne bloque pas la clôture d'un prêt déjà accepté. **Mes prêts** conserve
l'historique privé. [Invariants et résolution opérateur](docs/lot-4-loans.md).

## Notifications et ergonomie (lot 5)

Le worker traite les événements de compte et de prêt avec reprise persistée,
backoff et diagnostics en échec. Aucun contact de l'autre participant dans les
notifications. Mon compte permet une demande de suppression enregistrée ; son
traitement définitif et les engagements légaux restent à valider avant lancement.
[Outbox, outils de modération et limites](docs/lot-5-notifications.md).

```sh
uv run --frozen --group browser python scripts/product_browser_smoke.py --browser /usr/bin/chromium
```

Le parcours crée trois comptes fictifs et vérifie communautés, catalogue/copies,
prêt complet, accès croisés, notifications Mailpit et UX à 360/768/1280 px.
Utiliser uniquement la pile locale avec son worker. Scénarios à vérifier vous-même :
[guide ordinateur](docs/manual-validation.md).

## Interface responsive du MVP

La [première refonte](docs/ui-redesign.md) et la [passe finale avec captures
avant/après](docs/ui-final-pass.md) couvrent l’accueil connecté, Explorer et la
fiche de jeu. La référence image prime désormais sur les anciennes frames Figma.
L’URL `/` affiche l’accueil public aux visiteurs et redirige les comptes connectés
vers leur tableau de bord (ou la vérification d’e-mail si nécessaire).
Navigation mobile au clavier/tactile, sans framework frontend et avec police Inter
locale ; les formulaires restent utilisables sans JavaScript.
Le [correctif d’espacement](docs/ui-espacements.md) précise les marges des cartes
de communauté, des états vides et des actions de formulaire sur mobile et ordinateur.
Les [retours du staging](docs/ui-retours-staging.md) couvrent aussi les fenêtres
de gestion, l’invitation avec inscription/annulation visibles, l’ajout en deux
écrans, la gestion séparée des exemplaires et le favicon local.

```sh
uv sync --frozen --group browser
uv run --frozen --group browser python scripts/ui_browser_smoke.py --browser /usr/bin/chromium
```

Lancer la pile Compose avec son worker et Mailpit avant ce script. Il crée deux
comptes fictifs et leurs jeux via les vrais formulaires, puis vérifie 360, 390, 768,
1200 et 1280 px, menu, filtres, contenus longs et mode sans JS. Captures dans
`work/ui-redesign/screenshots/` ; les comparaisons avant/après sont versionnées dans la documentation.
Les tests serveur vérifient aussi les limites de visibilité des nouvelles présentations.
Le smoke distingue les fragments de recherche locaux annulés volontairement
(`ERR_ABORTED`) des vraies erreurs réseau ; les annulations sont comptées dans
`result.json`. Le parcours de recherche contrôle cette distinction dans Chrome,
avec une annulation puis une panne réseau forcées.
Cette passe UI historique ne modifiait pas les règles métier ni Gunicorn.
La préparation ultérieure du lot 6 est décrite dans son document dédié.

Le scénario de contenus longs exige désormais, pour les trois formulaires (fiche
jeu, exemplaire, communauté), une réponse POST 302 vers le détail attendu, puis
un rechargement HTTP 200 sans erreur de validation et une relecture exacte des
valeurs enregistrées. Le rendu reste contrôlé aux cinq largeurs, y compris sur
le détail de l'exemplaire.

Test négatif contrôlé, sur la même pile locale uniquement :

```sh
uv run --frozen --group browser python scripts/ui_browser_smoke.py --reject-long-content copy
```

Cette commande doit terminer avec un code non nul et « Soumission refusée » :
elle soumet 501 caractères pour une limite serveur de 500. Elle désactive la
validation HTML pour ce champ uniquement afin d'atteindre la validation serveur,
sans changer les règles de l'application. Les variantes `game` (description de
2001 caractères) et `community` (nom de 101 caractères) sont aussi disponibles.
Le mode normal conserve les données longues valides. Chaque parcours crée deux
nouveaux comptes fictifs ; les limites de débit locales restent applicables.
`work/ui-redesign/result.json` est supprimé au démarrage et écrit uniquement si
tout le parcours réussit ; les captures de référence précèdent les contenus longs.

## Journalisation confidentielle

Le [format JSON MUQ-06](docs/muq-06-safe-logging.md) conserve une liste fermée
avec date UTC, type d'exception et localisation applicative lorsque disponibles.
Messages libres, requêtes, secrets et tracebacks ne sont jamais sérialisés par
le formateur. Le document décrit le contrat, ses limites et le choix de différer
la corrélation plutôt que de reprendre une valeur client.

## Recherche intelligente — PR A

[Classement, périmètres, migration pg_trgm, privilèges, mesures et protocole](docs/recherche-intelligente.md).

`/games/` recherche les seules fiches validées pour ajouter un exemplaire. `/copies/`
cherche les jeux possédant des exemplaires autorisés dans les communautés actuelles,
avec une carte par jeu et un détail dédié `/copies/games/<uuid>/`. La collection
personnelle reste dans `/copies/mine/`. Le moteur normalise titres/alias et tolère
les fautes à partir de quatre caractères. La saisie instantanée (250 ms) conserve
le choix et les champs ; Entrée fonctionne aussi sans JavaScript.

```sh
uv run --frozen --group browser python scripts/search_browser_smoke.py --browser /usr/bin/chromium
```

Ce test ne vise que Compose local et crée des données synthétiques. Le benchmark
requiert une base **vide dédiée** dont le nom finit par `_benchmark`, `APP_ENV=test`
et les migrations appliquées. Ses données sont annulées en fin de transaction :

```sh
POSTGRES_DB=muqola_search_benchmark APP_ENV=test uv run --frozen python manage.py benchmark_search --games 10000 --samples 30
```

## Comptage SQL (MUQ-05)

Explorer, Mes jeux et le détail de fiche réutilisent une annotation de prêt actif.
Le détail affiche au plus 30 exemplaires autorisés par page, avec navigation ;
son badge de disponibilité couvre tous les exemplaires accessibles.
[Mesures avant/après et protocole](docs/muq-05-sql.md).

```sh
uv run --frozen pytest tests/test_inventory_sql.py -q -s
```
