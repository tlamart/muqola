# Muqola

Socle technique **lot 0**, stack proposée en attente de validation : Python 3.12,
Django 5.2 LTS, PostgreSQL 17, HTML/CSS serveur, Gunicorn/WhiteNoise.
Lire [l'ADR](docs/adr/0001-stack.md) et [les frontières des modules](docs/modules.md).
Aucun compte public, communauté, exemplaire ou prêt n'est encore implémenté.

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
Gunicorn. Les logs d'incidents restent volontairement succincts au lot 0.

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
export POSTGRES_PORT=55432 EMAIL_PORT=11025
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
APP_ENV=production uv run --frozen python manage.py check --deploy --fail-level WARNING
uv run --frozen pip-audit -r requirements.txt --disable-pip --no-deps --progress-spinner off
```

Le contrôle production conserve intentionnellement HSTS sans sous-domaines ni
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
| DJANGO_SECRET_KEY | Obligatoire, au moins 50 caractères aléatoires, serveur uniquement |
| ALLOWED_HOSTS | Hôtes HTTP acceptés, séparés par virgules |
| POSTGRES_DB / USER / PASSWORD | Base et identifiants locaux, aucun défaut pour le mot de passe |
| POSTGRES_HOST / PORT | Connexion directe ; Compose impose db:5432 |
| EMAIL_HOST / PORT | Capture SMTP seulement ; Compose impose mailpit:1025 |

Pas d'URL publique requise au lot 0 : les liens d'identité/invitation et leur
origine de confiance seront configurés au lot 1. Aucune clé de fournisseur,
identifiant VPS ou donnée réelle ne doit entrer dans ce développement.

## Limites et exploitation future

Ce Compose est exclusivement local. Caddy/HTTPS, fournisseur SMTP réel,
URL publique, DNS SPF/DKIM/DMARC, rôle PostgreSQL à privilèges réduits,
worker d'outbox, sauvegardes externes chiffrées/restaurées et supervision sont
à livrer/valider avant ouverture, selon [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).
Ni outbox ni sauvegarde opérationnelle ne sont simulées comme livrées.

Le déploiement futur : image identifiée → sauvegarde vérifiée → revue du plan de
migration → migration ponctuelle → démarrage → smoke tests. Revenir à l'image
précédente uniquement si son schéma reste compatible ; sinon restauration
contrôlée depuis sauvegarde après validation humaine, avec arrêt des écritures
et annonce de la perte potentielle depuis la sauvegarde. Aucune migration
destructive ni opération de production sans accord et stratégie de retour.
Procédure exacte de production, restauration testée et incident au lot 6.

Les inscriptions ouvertes, invitations privées, fiches réutilisables, exemplaires
à zéro ou plusieurs visibilités, date de retour et confidentialité des e-mails
restent les invariants des lots 1–5. Voir [TASKS.md](TASKS.md).
Attendre la validation explicite de l'ADR **et** du lot 0 avant le lot 1.

## Test navigateur du socle

Un navigateur Chromium installé est nécessaire. Lancer Compose puis :

```sh
uv sync --frozen --group browser
uv run --frozen --group browser python scripts/browser_smoke.py --browser /usr/bin/chromium
```

Le script ouvre réellement l'accueil à 360 et 1280 px, vérifie HTTP/CSS, langue,
clavier, absence de débordement et d'échec réseau. Captures locales dans `work/`
(non versionnées). Adapter `--browser` à l'exécutable installé. Les tests métier,
IDOR et concurrence des prêts seront ajoutés avec leurs lots ; ce smoke ne les
couvre pas. Le résultat de la livraison est dans [docs/lot-0-validation.md](docs/lot-0-validation.md).
