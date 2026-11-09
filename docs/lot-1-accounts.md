# Lot 1 — comptes

Branche `feat/lot-1-accounts`, créée depuis `origin/main` après fusion de la PR 1.
Périmètre : comptes uniquement. Communautés, invitations, catalogue, exemplaires
et prêts restent aux lots suivants. ADR 0001 validé par le propriétaire.

## Comportements

- Inscription libre : e-mail trim/minuscules unique, nom d'affichage 1–80 caractères,
  mot de passe 12–128 caractères avec validateurs Django. PBKDF2-SHA256 maintenu
  par Django ; jamais de mot de passe dans une réponse, une session ou un log.
- Réponse publique identique pour une inscription nouvelle ou déjà existante ;
  aucun remplacement de compte et aucun e-mail répété sur doublon d'inscription.
  Même calcul de hachage sur les deux chemins.
- Vérification : lien opaque 256 bits, durée 24 h, digest SHA-256 unique en base,
  consommation transactionnelle à usage unique. Aucun compte connecté nécessaire.
  GET prépare une confirmation ; POST avec CSRF consomme le lien. Un scanner
  d'e-mail ne vérifie donc pas silencieusement une adresse.
- Connexion autorisée au compte non vérifié pour voir l'attente, demander un
  nouveau lien et se déconnecter. Les routes métier sont refusées côté serveur.
  Tableau de bord minimal uniquement après vérification, sans communauté simulée.
- Réinitialisation : même réponse pour une adresse éligible ou inconnue, lien
  valable 1 h, nouveau mot de passe validé côté serveur, usage unique. Le nouveau
  hash rend toutes les anciennes sessions inutilisables ; pas de reconnexion
  automatique. Le reset ne vérifie pas implicitement un compte non vérifié.
- Un renvoi remplace tous les liens précédents de même nature. Un reset réussi
  invalide tous les jetons de compte encore actifs. Aucun changement d'e-mail.
- Déconnexion exclusivement POST avec CSRF. Rotation d'identifiant de session
  à la connexion, HttpOnly/SameSite=Lax, durée maximale 7 jours, Secure en production.
  Les anciennes lignes de session sont invalides même avant leur purge standard.

## Autorisation, liens et confidentialité

`VerifiedAccountMiddleware` protège par défaut chaque vue résolue, sauf une liste
fermée d'écrans publics nommés. Le futur code métier ne doit pas ajouter ses vues
à cette liste. Aucun passe-droit pour un superutilisateur non vérifié. Les
modules métier devront toujours ajouter leurs contrôles de ressource/acteur.

L'origine des liens vient seulement de `APP_BASE_URL`, jamais du Host client.
Origine sans chemin, identifiants ni paramètres ; HTTPS obligatoire en production.
Les URL à jeton redirigent immédiatement vers une URL propre avec
`Referrer-Policy: no-referrer`, et seul leur digest est conservé dans la session.
Les autres pages utilisent `same-origin` : pas de référent vers un site tiers,
mais un Origin utilisable par la protection CSRF du navigateur. Une politique
`no-referrer` globale produisait effectivement `Origin: null` sous Chromium.
Le correctif conserve le rejet des origines nulles ; il ne désactive pas CSRF.
Toutes les réponses dynamiques portent `Cache-Control: no-store`. Aucun contenu
ou script tiers ; aucun jeton brut dans les logs ou les formulaires affichés.

## Limitation de débit PostgreSQL

Fenêtres fixes, budget par IP **et** par e-mail normalisé ; pas de cache mémoire
isolé par worker. Clés HMAC-SHA256 avec secret serveur, sans IP/e-mail en clair.
Verrous transactionnels IP puis adresse ; une IP épuisée ne crée plus de nouvelle
entrée d'adresse. Réponse 429 neutre, Retry-After jusqu'à la fin de fenêtre.

| Action | Fenêtre | Par IP | Par adresse |
| --- | --- | --- | --- |
| Inscription | 1 h | 10 | 3 |
| Connexion | 15 min | 30 | 10 |
| Renvoi de vérification | 1 h | 10 | 3 |
| Demande de reset | 1 h | 10 | 3 |
| Ouverture/confirmation de lien | 15 min | 60 | — |

Le client est identifié par REMOTE_ADDR ; X-Forwarded-For n'est pas accepté
aveuglément. Au lot 6 il faudra valider la chaîne de confiance Caddy et les
limites adaptées aux réseaux partagés. Les fenêtres peuvent autoriser une rafale
à leur frontière ; pas de promesse d'anti-DDoS réseau ni de CAPTCHA requis.

## Schéma et migrations

- `User.updated_at` ajouté ; `email` reste unique. CHECK non vide et
  CHECK email = lower(trim(email)) empêchent même une écriture SQL non normalisée.
  `save` normalise ; les formulaires valident format et longueur. Aucun rôle
  opérateur ni statut vérifié n'est accepté depuis l'inscription.
- `AccountToken` unifie vérification et reset, séparés par `purpose` contraint.
  UUID primaire, digest unique, expiration indexée et strictement après création,
  date de consommation nullable. FK User ON DELETE CASCADE : ces autorisations
  temporaires ne doivent pas survivre au compte.
- `RateBucket` : clé HMAC primaire, compteur positif, expiration indexée.
- `EmailOutbox` : UUID, OneToOne AccountToken ON DELETE CASCADE, charge chiffrée,
  statut contraint, essais, prochaine tentative, dates. Index (statut, échéance).
  Une entrée par jeton ; la suppression du jeton purge son e-mail temporaire.
- Deux migrations additives versionnées. Aucun effacement de compte ni migration
  destructive. Les données du socle étaient des comptes fictifs normalisés ;
  sur une autre base, vérifier les e-mails existants avant d'appliquer les CHECK.

Émission du jeton et écriture de l'outbox dans la même transaction que le compte.
Émission/consommation verrouillent l'utilisateur puis le jeton, afin de sérialiser
renvois et consommations. Deux consommations concurrentes ne réussissent pas.

## E-mails de compte persistés

Le lot 1 implémente seulement la partie nécessaire aux comptes de l'outbox prévue
par l'ADR ; les notifications de prêt et leurs scénarios restent au lot 5.
Fernet de `cryptography` chiffre le destinataire, le sujet et le corps, y compris
le lien brut requis pour l'envoi. Clé dérivée de DJANGO_SECRET_KEY par HMAC-SHA256
avec contexte distinct. Le jeton d'autorisation lui-même reste haché.

Ne pas remplacer DJANGO_SECRET_KEY avec des messages encore en attente : vider
la file ou définir une rotation des clés avant cette opération. La sauvegarde de
la base seule ne suffit pas à déchiffrer la file, et les secrets doivent être
sauvegardés séparément avant production. Aucun secret de production ici.

`process_outbox` tourne dans le même code (service Compose `worker`), toutes les
5 secondes. Verrouillage SKIP LOCKED pour plusieurs workers possibles ; SMTP
avec timeout 5 s, retry exponentiel de 60 s à 1 h, Message-ID stable. Les erreurs
ne suppriment pas le compte ni le message. Les messages expirés/révoqués ou pour
un compte désactivé sont abandonnés explicitement. Après envoi/abandon, la charge
chiffrée est immédiatement effacée. Envoi au moins une fois : un crash après
SMTP et avant commit peut produire un doublon, jamais une garantie « exactement
une fois ». Aucun relais Mailpit configuré, fournisseur réel toujours au lot 6.

Purge automatique à chaque démarrage du worker puis environ toutes les heures :
budgets expirés, jetons consommés depuis plus de 24 h ou expirés depuis plus de
24 h, avec cascade des lignes outbox. Les comptes ne sont pas supprimés par ce
nettoyage. `clearsessions` doit être planifié au déploiement. Politique complète
de conservation, demandes de suppression et résolution des prêts au lot 6 avant
ouverture ; aucune procédure légale/opérationnelle n'est déclarée déjà prête.

## Vérifications

Voir README et `scripts/check.sh` : Ruff, mypy, migrations, pytest PostgreSQL.
Tests des validations, neutralité des réponses, CSRF, restrictions non vérifié,
permissions serveur par défaut, expiration, renvoi, usage unique, sessions et
reprise SMTP. Tests concurrents PostgreSQL réels pour consommation d'un jeton,
inscriptions simultanées et budget partagé ; connexions de threads fermées.

`scripts/accounts_browser_smoke.py` utilise vraiment Chromium, les formulaires
et leur CSRF, SMTP Mailpit et la base. Il couvre à 360 et 1280 px : inscription,
connexion non vérifiée et refus 403 métier, vérification dans un nouveau contexte
sans connexion, connexion vérifiée, reset, invalidation de l'ancienne session,
nouvelle connexion et déconnexion. Adresses uniquement fictives @example.test.
La CI exécute aussi ces parcours après un démarrage Compose propre.

Limites : pas de téléphone physique, SMTP public/DNS/HTTPS, tests de charge ni
mesure des limites mémoire du petit VPS. Dans ce Cloud, le pilote Docker `vfs`
et le disque de 7,9 Go ne permettent pas de garder tous les conteneurs applicatifs
simultanément : build réel effectué, tests navigateur locaux via Gunicorn et
worker sur l'hôte avec PostgreSQL/Mailpit Docker. Le Compose complet est vérifié
par la CI sur un runner propre. Aucun service externe métier, achat, secret ou
identifiant de production. Lot 2 en attente de validation du lot 1.

Exécutions locales réelles du lot (9 novembre 2026) :

- `./scripts/check.sh` avec `.env` local, `POSTGRES_PORT=55432` et cache uv sous
  `work/` : Ruff, format, mypy, contrôles Django, migrations/statiques réussis ;
  **56 tests réussis** avec vrai PostgreSQL, sans avertissement de connexion restante.
- `APP_BASE_URL=https://muqola.example.test APP_ENV=production ... manage.py check
  --deploy --fail-level WARNING` : réussi, W005/W021 seuls désactivés conformément
  à l'ADR validé ; aucun service HTTPS public testé.
- `pip-audit -r requirements.txt --disable-pip --no-deps --cache-dir work/audit-cache` :
  aucune vulnérabilité connue après passage à cryptography 50.0.2. L'audit avait
  détecté des avis sur la version 48 initialement sélectionnée ; aucune exception
  d'audit ajoutée pour les masquer.
- `python scripts/accounts_browser_smoke.py` et `python scripts/browser_smoke.py` :
  deux résolutions réussies chacune, e-mails réellement capturés et formulaires
  effectivement soumis par le navigateur, y compris CSRF.
- Build Docker réel réussi ; démarrage simultané interrompu par saturation du
  disque Cloud `vfs`. Les anciens conteneurs/images/caches de ce lot ont été
  retirés, sans suppression du volume PostgreSQL. Aucun résultat local de Compose
  complet n'est inventé ; la CI de PR doit confirmer ce démarrage et les parcours
  navigateur sur le commit final avant validation.
