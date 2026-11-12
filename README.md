# Muqola

**Lots 1 à 5 — MVP en développement**, sur le socle et la stack validés : Python 3.12,
Django 5.2 LTS, PostgreSQL 17, HTML/CSS serveur, Gunicorn/WhiteNoise.
Lire [l'ADR](docs/adr/0001-stack.md) et [les frontières des modules](docs/modules.md).
Comptes vérifiés, communautés privées, catalogue interne réutilisable, exemplaires
à zéro ou plusieurs visibilités, prêts et notifications capturées sont disponibles.
[Guide de validation sur ordinateur](docs/manual-validation.md) ;
[comptes et sécurité](docs/lot-1-accounts.md). Les lots 1 à 5 et le correctif
Gunicorn sont intégrés dans `main` depuis la fusion de la PR #8. Lot 6 non entrepris.

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
| DJANGO_SECRET_KEY | Obligatoire, au moins 50 caractères aléatoires, serveur uniquement |
| ALLOWED_HOSTS | Hôtes HTTP acceptés, séparés par virgules |
| POSTGRES_DB / USER / PASSWORD | Base et identifiants locaux, aucun défaut pour le mot de passe |
| POSTGRES_HOST / PORT | Connexion directe ; Compose impose db:5432 |
| EMAIL_HOST / PORT | Capture SMTP seulement ; Compose impose mailpit:1025 |
| EMAIL_FROM | Expéditeur fictif en développement |
| EMAIL_BACKEND | Backend Django remplaçable ; SMTP par défaut |
| EMAIL_HOST_USER / PASSWORD | Vides en dev/test, configuration réelle au lot 6 |
| EMAIL_USE_TLS / SSL | Choisir un seul mode pour un futur transport réel |

APP_BASE_URL définit l'origine de confiance des liens de compte et doit être
HTTPS en production ; aucune origine n'est reprise du Host client. Aucune clé de fournisseur,
identifiant VPS ou donnée réelle ne doit entrer dans ce développement.

## Limites et exploitation future

Ce Compose est exclusivement local. Caddy/HTTPS, fournisseur SMTP réel,
URL publique de production, DNS SPF/DKIM/DMARC, rôle PostgreSQL à privilèges réduits,
sauvegardes externes chiffrées/restaurées et supervision sont
à livrer/valider avant ouverture, selon [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).
L'outbox des comptes/prêts et son worker sont livrés. Les sauvegardes de production
ne sont pas encore opérationnelles. Le développement refuse les identifiants SMTP
et hôtes non locaux pour conserver la capture Mailpit.

Le déploiement futur : image identifiée → sauvegarde vérifiée → revue du plan de
migration → migration ponctuelle → démarrage → smoke tests. Revenir à l'image
précédente uniquement si son schéma reste compatible ; sinon restauration
contrôlée depuis sauvegarde après validation humaine, avec arrêt des écritures
et annonce de la perte potentielle depuis la sauvegarde. Aucune migration
destructive ni opération de production sans accord et stratégie de retour.
Procédure exacte de production, restauration testée et incident au lot 6.

Les invariants des lots 2–5 sont testés : invitations privées, fiches réutilisables,
exemplaires à zéro ou plusieurs visibilités, date de retour et contacts uniquement
pendant un prêt accepté/remis. Voir [TASKS.md](TASKS.md). Arrêt après le lot 5 pour
validation humaine ; aucune fusion ni opération de production automatique.

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

## Tester sur Android avec GitHub Codespaces

Le [guide Android pas à pas](docs/codespaces-android.md) explique la création du
Codespace, l'ouverture des deux URL HTTPS privées, la capture Mailpit, le test
d'inscription/vérification/connexion et l'arrêt. La configuration `.devcontainer`
réutilise Compose avec un profil de développement isolé et vérifie la visibilité
privée des ports avant de démarrer les services. PostgreSQL n'est pas publié.

## Communautés privées (lot 2)

Depuis **Mes communautés**, créer une communauté, générer un lien et le partager
avec un second compte fictif vérifié. L'adhésion doit être confirmée ; les liens
sont multiusages, expirables et révocables. Transférer l'administration avant le
départ du dernier administrateur. Les détails et membres restent privés.
Si la désactivation du seul administrateur bloque la gestion, une
[reprise opérateur explicite et tracée](docs/lot-5-notifications.md#reprise-opérateur)
permet de promouvoir un membre existant ; aucune promotion automatique.
[Schéma, permissions, concurrence et vérifications](docs/lot-2-communities.md).

## Catalogue et collection (lot 3)

**Ajouter un jeu** commence par la recherche d'une fiche existante ; sinon créer
une fiche générique manuellement. **Ajouter mon exemplaire** sélectionne ensuite
zéro ou plusieurs communautés : sans sélection, il reste privé. Un second compte
réutilise la même fiche pour sa propre copie. **Ma collection** permet l'édition
et le retrait du prêt. Une fiche déjà réutilisée passe par le signalement pour
correction. [Schéma et confidentialité](docs/lot-3-catalogue.md).
Après masquage d'une fiche par modération, le propriétaire peut encore modifier
son exemplaire non archivé. La fiche reste masquée et l'exemplaire retiré du prêt ;
aucun nouvel exemplaire de cette fiche ne peut être créé.

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

```sh
uv sync --frozen --group browser
uv run --frozen --group browser python scripts/ui_browser_smoke.py --browser /usr/bin/chromium
```

Lancer la pile Compose avec son worker et Mailpit avant ce script. Il crée deux
comptes fictifs et leurs jeux via les vrais formulaires, puis vérifie 360, 390, 768,
1200 et 1280 px, menu, filtres, contenus longs et mode sans JS. Captures dans
`work/ui-redesign/screenshots/` ; les comparaisons avant/après sont versionnées dans la documentation.
Les tests serveur vérifient aussi les limites de visibilité des nouvelles présentations.
Aucun changement des règles métier, de Gunicorn, ni démarrage du lot 6.

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

## Comptage SQL (MUQ-05)

Explorer, Mes jeux et le détail de fiche réutilisent une annotation de prêt actif.
Le détail affiche au plus 30 exemplaires autorisés par page, avec navigation ;
son badge de disponibilité couvre tous les exemplaires accessibles.
[Mesures avant/après et protocole](docs/muq-05-sql.md).

```sh
uv run --frozen pytest tests/test_inventory_sql.py -q -s
```
