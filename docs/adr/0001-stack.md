# ADR 0001 — Stack du MVP Muqola

- Date : 9 novembre 2026
- Statut : **acceptée par le propriétaire après validation du lot 0 et fusion de la PR 1**
- Sources lues entièrement : SPEC.md, DESIGN.md, ARCHITECTURE.md, AGENTS.md,
  TASKS.md et LAUNCH_CHECKLIST.md.

## Comparaison

| Critère | Python 3.12 / Django 5.2 LTS | PHP 8.4 / Laravel 12 |
| --- | --- | --- |
| Rapidité | ORM, migrations, formulaires, sessions et CSRF intégrés | Très bon socle intégré, conventions productives |
| Maintenance | LTS jusqu'en avril 2028, documentation mature, typage progressif | Écosystème mature, mises à niveau majeures plus fréquentes |
| Sécurité | Auto-échappement, permissions à expliciter, validateurs de mots de passe | Protections comparables, permissions à expliciter également |
| Bibliothèques | psycopg, pytest, SMTP standard ; peu de dépendances | Eloquent, PHPUnit/Pest, SMTP ; outillage PHP requis |
| Petit VPS | Gunicorn + PostgreSQL ; ni Node ni broker à exploiter | PHP-FPM + serveur HTTP + PostgreSQL ; très viable également |

Les deux conviennent. Django est retenu pour ses migrations et contraintes
conditionnelles PostgreSQL, ses transactions/verrous et son socle de tests.
Un frontend React/API séparé ajouterait des contrats et du JavaScript à maintenir
sans besoin MVP démontré. Le HTML serveur suffira ; amélioration progressive
possible sans changer d'architecture.

## Décision précise

- Python **3.12**, Django **5.2 LTS**, correctifs exacts dans `uv.lock`.
- PostgreSQL **17**, psycopg 3 ; **aucune substitution SQLite**, même en tests.
- Templates Django, HTML sémantique, CSS local avec variables ; pas de CDN.
- Gunicorn WSGI, deux workers pour commencer ; WhiteNoise pour les statiques.
- Docker Compose v2 ; image Python slim, processus applicatif non root.
- Mailpit local pour SMTP et interface de capture, sans relais réel.
- Sessions serveur PostgreSQL, cookies HttpOnly/SameSite et Secure hors dev,
  CSRF Django, CSP restrictive, Referrer-Policy sans référent.
- Ruff format/lint, mypy + django-stubs, pytest/pytest-django, pip-audit ;
  GitHub Actions avec vrai PostgreSQL et build/smoke Docker.
- Caddy 2 pour HTTPS **au lot 6** ; ni hébergeur ni domaine imposé.
- SMTP interchangeable via le backend Django ; outbox PostgreSQL et worker
  du même code, sans Redis/Celery, au lot 5. Les liens des comptes au lot 1
  devront déjà être persistés transactionnellement pour éviter leur perte.

Les images utilisent des versions majeures/mineures explicites ; les correctifs
Python sont verrouillés et hachés dans le fichier généré `requirements.txt`.
Avant production, figer aussi les digests d'images et organiser leurs mises à jour.

## Frontières du monolithe

`identity` possède l'utilisateur technique et, au lot 1, les comptes/jetons.
`communities` possédera communautés/appartenances/invitations ; `catalogue` les
fiches génériques ; `inventory` les exemplaires et visibilités ; `loans` les
transitions ; `notifications` l'outbox et ses transports ; `operations` les
commandes opérateur ; `core` uniquement les pages et mécanismes transversaux.
Une base et un déploiement ; pas de endpoints métier dans le lot 0. Les futures
écritures passent par les services du module propriétaire ; lectures filtrées
par acteur côté serveur et transactions explicites pour les invariants.

Le modèle utilisateur personnalisé est créé dès la première migration pour
éviter un remplacement risqué de `AUTH_USER_MODEL` après la création des FK.
Il n'expose **aucun** parcours de compte. Aucun modèle de prêt anticipé.
Les FK, ON DELETE et anonymisations métier seront documentés avec leurs lots.

## Invariants réservés aux lots suivants

Inscription libre, e-mail vérifié, invitations multiusages révocables et expirables.
Catalogue interne générique réutilisable, création manuelle de secours, aucun
catalogue externe obligatoire. Exemplaires distincts avec zéro à plusieurs
communautés choisies, sans partage implicite. Date civile de retour future dans
Europe/Paris, événements UTC. Deux index uniques partiels pour prêts actifs et
demandes en attente, transactions et tests concurrents réels au lot 4.
E-mails de contact accessibles aux seules parties pendant ACCEPTED/HANDED_OVER.
La perte d'appartenance ferme les demandes inéligibles mais préserve la clôture
des prêts acceptés. Pas de paiement, d'image distante ou d'upload au MVP.

## Risques et arbitrages

- Django ne garantit pas l'isolation métier : tests IDOR et filtrage systématique
  requis aux lots 2–4. Aucun admin web général exposé.
- Le compte email utilise une normalisation simple trim/minuscules ; les jetons
  hachés/expirables/consommables, anti-abus et invalidation des sessions restent
  au lot 1. Les fonctions Django seules ne satisfont pas toute la SPEC.
- La concurrence requiert PostgreSQL réel : pas de promesse fondée sur des mocks.
- SMTP est au moins une fois : l'outbox devra gérer reprise, doublons et rétention
  des données sensibles ; pas de garantie d'envoi exactement une fois.
- Un VPS unique est un point de panne. Limites mémoire proposées : application
  512 Mio, base 768 Mio, Mailpit 128 Mio (dev uniquement) ; ce sont des budgets
  initiaux, pas un résultat de test de charge. Réserver de la marge OS/Caddy/worker.
- Sauvegardes hors VPS chiffrées et restauration testée, HTTPS, SMTP délivrable,
  protection anti-abus et informations légales sont des blocages de lancement.
- Le Compose du lot 0 est **local seulement** ; aucune conformité production
  ou fonctionnalité MVP n'est déclarée sur la seule base de la CI.

## Validations du propriétaire

1. Valider cette stack et le socle du lot 0 avant toute ouverture du lot 1.
2. Au lot 6 : valider fournisseur/région VPS et budget récurrent, domaine/marque,
   SMTP, stockage externe des sauvegardes et coûts, avant engagement.
3. Avant ouverture : fournir coordonnées légales/contact, valider conservation,
   politique de suppression et participation des mineurs, puis autoriser le
   déploiement et exécuter le parcours complet avec deux comptes.

Lot 0 : logiciels sans licence payante nécessaire, aucun achat, aucun service
métier réel connecté, aucune ressource provisionnée ni secret de production.
Les téléchargements de dépendances et la CI/PR GitHub sont l'outillage de dev.
Aucun coût d'exploitation n'est engagé ; prix fournisseurs à vérifier au lot 6.

HSTS sera d'abord court (1 heure), sans `includeSubDomains` ni `preload` :
ces engagements concernent un domaine encore inconnu. W005/W021 sont les seuls
avertissements Django explicitement désactivés pour cette raison ; tous les
autres avertissements de sécurité font échouer le contrôle CI.


Précision au lot 1 : la politique de référent est `no-referrer` sur la redirection
qui porte le jeton, puis `same-origin` sur les pages propres. Chromium produisait
`Origin: null` avec `no-referrer` global sur les POST de formulaires ; ce découpage
préserve la protection du secret et permet CSRF, sans accepter d'origine nulle.
L'outbox minimale des comptes est désormais persistée et traitée ; sa charge est
chiffrée par Fernet (`cryptography`, version corrigée verrouillée), avec une clé
dérivée du secret serveur. Notifications métier complètes toujours au lot 5.
