# Lot 6 / PR #24 — Infrastructure de production (préparation uniquement)

## Périmètre
Configuration **distincte** du Compose local : Caddy, Gunicorn/Django, worker
d'outbox existant, PostgreSQL 17 et volumes persistants. Pas de Mailpit, pas de
port PostgreSQL exposé, pas de publication directe du port web. Seuls 80/443
sont publiés pour Caddy. Aucun VPS ni domaine n'a été créé ou configuré.

La configuration `compose.prod.yaml` est une **base de préparation**, pas une
autorisation de mise en ligne. Les PR suivantes doivent finaliser les sauvegardes
externes chiffrées et la restauration testée, le SMTP réel, la supervision, les
informations légales, la restriction aux adultes et la sécurité opérationnelle.

## Préparation (ne pas lancer sur un VPS réel avant validation)
1. Acheter et vérifier un domaine, choisir un VPS Linux dédié (cible 2 vCPU /
   4 Go RAM), contrôler le budget, configurer le DNS A/AAAA et ouvrir uniquement
   les ports nécessaires. Caddy demande l'accès public à 80/443 pour HTTPS.
2. Copier `.env.production.example` en `.env.production` **sans le committer**,
   renseigner les vraies valeurs via un canal privé et `chmod 600 .env.production`.
   Utiliser un secret Django et un mot de passe PostgreSQL différents du local.
   Le domaine doit être identique dans APP_DOMAIN, ALLOWED_HOSTS et APP_BASE_URL
   (APP_BASE_URL commence par https://).
3. Sur un poste de travail, valider la structure **sans démarrer de service** :
   `docker compose --env-file .env.production.example -f compose.prod.yaml config --quiet`.
   Ne pas utiliser le fichier d'exemple pour déployer : ses secrets et son SMTP
   sont volontairement non fonctionnels.
4. Une fois les prérequis des PR suivantes satisfaits et l'autorisation humaine
   obtenue : sauvegarder avant migration, examiner le plan Django, exécuter
   explicitement la migration ponctuelle, puis démarrer les services et effectuer
   les tests de fumée HTTPS, cookies et parcours avec deux comptes.

## Règles de sécurité et d'exploitation
- `compose.yaml` reste réservé au développement ; ne pas le superposer au
  fichier de production.
- Le proxy Caddy termine TLS et fournit X-Forwarded-Proto. Django ne lui fait
  confiance que lorsque APP_ENV=production. **Ne jamais exposer directement
  Gunicorn** ou le réseau interne à des clients non fiables.
- Les migrations ne s'exécutent **pas automatiquement** au démarrage en
  production. Elles nécessitent sauvegarde préalable, plan de migration,
  approbation et procédure de retour arrière.
- Le conteneur applicatif conserve un UID non root, un système de fichiers en
  lecture seule, les limites de mémoire et des logs JSON bornés.
- La base est initialisée par l'image PostgreSQL officielle. **Avant ouverture,
  séparer et réduire les privilèges du rôle utilisé par l'application** : le
  compte initial POSTGRES_USER peut disposer de privilèges trop étendus.
  Cette étape n'est pas livrée par la PR #24.
- Aucun import BGG n'est lancé automatiquement. Le catalogue public ne doit
  contenir que des données dont les droits sont vérifiés.
- Prévoir l'identification des versions d'images par digest, les sauvegardes
  chiffrées hors VPS, un test de restauration, des alertes et un rollback
  documenté avant ouverture. Ne jamais revenir à une ancienne image si le
  schéma migré est incompatible sans restauration contrôlée.
- Les secrets ne doivent apparaître ni dans Git, ni dans les logs, ni dans une
  sortie de commande publiée. Ne pas coller une sortie `docker compose config`
  contenant des variables réelles dans une PR.

## Vérifications restantes avant fusion et lancement
- CI Django et tests existants ; contrôle de syntaxe Compose.
- Validation réelle de Caddy/TLS/proxy/cookies **ultérieure**, avec domaine et
  VPS disponibles ; aucune preuve de fonctionnement HTTPS réel à ce stade.
- Contrôle des versions/digests et de la politique de mise à jour.
- PR #25 : SMTP, sauvegardes, restauration et supervision.
- PR #26 : conformité, suppression de compte, conditions 18+.
- Validation humaine explicite avant toute dépense ou opération de production.
