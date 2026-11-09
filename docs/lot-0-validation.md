# Lot 0 — preuves et limites

Date : 9 novembre 2026. Branche : `feat/lot-0-foundation`.
ADR proposé : [0001-stack.md](adr/0001-stack.md). Validation humaine encore requise.
Les six documents du kit ont été lus entièrement avant modification.

## Livré

Accueil français responsive, modules séparés, utilisateur technique personnalisé
sans routes de compte, migration initiale et migrations Django, PostgreSQL seul,
Compose local avec service migration préalable, SMTP Mailpit sans relais,
Gunicorn non root, statiques WhiteNoise, headers de sécurité, healthchecks,
secrets locaux générés sans affichage, logs JSON sans URL/jeton, outils verrouillés,
README, CI et tests. Aucun modèle ni endpoint de communauté/catalogue/prêt.

## Exécutions réelles dans Codex Cloud

- `uv lock`, `uv sync --frozen`, `uv export --frozen --no-dev --no-emit-project
  --output-file requirements.txt` : réussis ; dépendances runtime hachées.
- `./scripts/check.sh` après chargement du `.env` **local**, avec
  `POSTGRES_PORT=55432` et `UV_CACHE_DIR` dans `work/` : Ruff lint/format OK,
  mypy OK, contrôles Django OK, aucune migration manquante, migrations PostgreSQL
  appliquées, statiques collectées, **16 tests réussis**. Aucune base simulée.
- `APP_ENV=production uv run --frozen python manage.py check --deploy
  --fail-level WARNING` : OK ; W005/W021 seuls désactivés explicitement
  (HSTS sous-domaines/preload différés jusqu'au choix du domaine).
- `uv run --frozen pip-audit -r requirements.txt --disable-pip --no-deps
  --progress-spinner off --cache-dir work/audit-cache` : aucune vulnérabilité
  connue dans les dépendances runtime au moment du contrôle.
- Build Docker réel puis `docker compose -f compose.yaml -f work/cloud.compose.yaml
  up --no-build --wait --wait-timeout 120` : code 0, PostgreSQL/Mailpit/web sains,
  service `migrate` terminé avec code 0.
- `curl --fail http://127.0.0.1:8000/health/ready/` : HTTP 200, `{"status":"ok"}`.
- `docker compose exec -T web python manage.py send_dev_email` : succès ; API
  Mailpit `/api/v1/messages` confirme la capture d'un message synthétique.
- `python scripts/browser_smoke.py` avec Playwright 1.62.0 et Chromium installé :
  succès à 360 et 1280 px, HTML/CSS réellement servis par l'image Docker,
  français, lien d'évitement clavier, aucun débordement/échec réseau.

La CI versionnée répète contrôles, audit et démarrage Compose propre. Son statut
GitHub doit être vert avant fusion ; ce document ne substitue pas les résultats
locaux à une exécution CI distante.

## Incidents résolus et limites de l'environnement

- Le cache uv/pip-audit par défaut pointait vers un répertoire non inscriptible :
  caches déplacés sous `work/`, sans changement des permissions système.
- Premier démarrage Docker : fichiers copiés avec droits trop restrictifs pour
  l'UID 10001. Dockerfile corrigé pour donner les droits de lecture/traversée,
  sans rendre le code modifiable par le processus applicatif.
- Le pilote Docker Cloud `vfs` a rempli le disque de 7,9 Go lors des builds :
  caches et anciens conteneurs/images de ce lot supprimés, volume PostgreSQL
  conservé ; image corrigée démarrée et testée ensuite avec succès.
- L'override `work/cloud.compose.yaml` fournit uniquement le certificat CA public
  du proxy via un secret BuildKit éphémère et les ports locaux de test
  PostgreSQL/SMTP. Aucun certificat de session n'entre dans Git ni dans l'image.
  Le build standard local/CI utilise le Dockerfile sans cet override.
- La première CI distante a passé tous les contrôles Python mais révélé une
  incohérence de priorité entre mot de passe du shell et `env_file` Compose.
  Configuration corrigée pour partager explicitement les mêmes variables
  PostgreSQL entre application et base ; diagnostic sans affichage des valeurs.
- Le runtime Docker Cloud signale l'absence de cgroups : les limites mémoire
  déclarées ne sont donc pas validées ici. Pas de test de charge du VPS cible.
- Aucun test sur téléphone physique, aucun HTTPS public, SMTP réel, sauvegarde
  externe/restauration, test IDOR/concurrence métier ou parcours d'inscription.
  Ces éléments appartiennent aux lots suivants et à LAUNCH_CHECKLIST.md.

## Décisions attendues

Valider ensemble l'ADR et le lot 0 avant le lot 1. Aucun service métier externe,
secret de production, achat, déploiement ou lancement public n'a été engagé.
Le propriétaire validera plus tard les coûts, fournisseurs, domaine, cadre légal
et mise en production. Le lot 1 n'a pas été entrepris.
