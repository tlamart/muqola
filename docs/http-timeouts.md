# Timeouts HTTP locaux — diagnostic et correction

Incident signalé : cinq `WORKER TIMEOUT` en environ 17 minutes, erreurs HTTP 502
intermittentes, trace `gunicorn/http/unreader.py` → `sock.recv`, puis
`Error handling request (no URI read)`. L'utilisateur confirme un accès direct
à `http://localhost:8000`. Les journaux complets de son poste et les en-têtes
des réponses 502 ne sont pas disponibles ici.

## Cause reproduite

Le Dockerfile utilisait Gunicorn 23.0.0 avec deux workers **sync**, watchdog
30 s, arrêt gracieux 20 s. Un worker sync accepte une connexion, passe la socket
en mode bloquant puis attend une requête HTTP. Si un client ouvre la connexion
TCP mais n'envoie aucun octet, `RequestParser` reste dans `SocketUnreader.chunk()`
sur `sock.recv()`. Django n'a pas encore été appelé, aucune URI n'est disponible.
Ce worker ne rafraîchit plus son heartbeat ; le master le tue et le remplace.
Deux connexions silencieuses suffisent à immobiliser les deux workers.

Reproduction locale sur **le vrai Gunicorn et le vrai Django**, sans écriture
métier, paramètres de durée identiques à ceux du Dockerfile :

| Essai | Résultat observé |
| --- | --- |
| sync, deux sockets silencieuses, 35 s | 13 requêtes échouées sur 28 sondes, deux `WORKER TIMEOUT`, deux `no URI read`, workers remplacés |
| gthread, comparaison initiale au-delà de 30 s | HTTP 200 pendant l'attente, aucun timeout, mêmes deux workers |
| Test automatisé corrigé, douze sockets silencieuses pendant plus de 32 s | Le serveur reste accessible, aucun timeout ni remplacement de worker |

Le contrôle négatif retourne volontairement **1** : ce n'est pas un test réussi
présenté comme tel. Il montre que le scénario détecte le défaut ancien. La trace
reproduite inclut exactement `sock.recv(self.mxchunk)` et `no URI read`.

Sources vérifiées dans la version installée/verrouillée :
[SyncWorker.accept/handle](https://github.com/benoitc/gunicorn/blob/23.0.0/gunicorn/workers/sync.py),
[SocketUnreader.chunk](https://github.com/benoitc/gunicorn/blob/23.0.0/gunicorn/http/unreader.py),
[ThreadWorker.accept/on_client_socket_readable](https://github.com/benoitc/gunicorn/blob/23.0.0/gunicorn/workers/gthread.py).

## Correction ciblée

Le Dockerfile charge désormais `config/gunicorn.py`, source unique des réglages
locaux : **gthread**, deux processus, quatre threads chacun, au plus 64 connexions
par worker, keep-alive 2 s. Le watchdog reste à **30 s**, l'arrêt gracieux à **20 s**.
Gunicorn reste à 23.0.0 ; aucune nouvelle dépendance ni modification métier.

Dans ce worker, une connexion sans données attend dans le sélecteur de sockets ;
elle n'occupe ni le pool de traitement HTTP ni tout un processus. Les tests
ouvrent **plus de sockets silencieuses que de threads disponibles** pour vérifier
qu'il ne s'agit pas simplement de repousser la saturation en ajoutant des threads.
Le keep-alive est pris en charge puis expire normalement. Le worker sync ne
prend pas en charge les connexions persistantes : modifier son keep-alive ou
augmenter son watchdog aurait laissé le blocage initial.

Le watchdog gthread surveille la vie du processus, **pas la durée maximale d'une
requête**. Il ne constitue pas une nouvelle garantie de délai applicatif. Le
nombre potentiel de connexions PostgreSQL du web passe à huit (une par thread
actif), à prendre en compte dans le budget du futur hébergement. Les contraintes
et tests PostgreSQL d'intégrité métier restent inchangés.

## Docker et healthchecks examinés

- Le `CMD` Docker est un tableau exec, sans shell intermédiaire ; aucun problème
  de propagation des signaux confirmé. Compose conserve `init: true`, un arrêt
  gracieux conteneur de 30 s, le mode non root, les limites mémoire et le rootfs
  en lecture seule. `/tmp` est un tmpfs ; `worker_tmp_dir` le désigne explicitement.
  L'hypothèse d'un heartbeat bloqué par les écritures disque n'explique pas la
  trace `recv` reproduite et n'est pas confirmée.
- Le healthcheck est une **vraie requête HTTP GET**, pas une connexion TCP muette.
  Son timeout réseau reste à 4 s et celui de Docker à 5 s, intervalle 10 s,
  cinq échecs avant unhealthy, délai initial 10 s. Sa réponse est désormais lue
  et fermée explicitement avec un context manager. L'ancien petit processus
  se terminait après chaque contrôle et `urllib` demandait déjà la fermeture :
  aucune fuite persistante du healthcheck n'a été établie. Ce changement explicite
  la gestion de ressource ; le correctif principal est le mode de worker.
- `/health/live/` n'accède pas à PostgreSQL ; `/health/ready/` exécute `SELECT 1`.
  Le délai de connexion PostgreSQL est de 3 s. Une indisponibilité SQL peut rendre
  la readiness négative, mais produirait une trace SQL après parsing HTTP. Elle
  n'explique pas la trace pré-URI fournie. Aucun changement SQL n'est apporté.
- SMTP est exécuté par le worker outbox séparé ; il ne s'exécute pas dans le
  traitement d'une page web. Aucune intégration externe ne fait partie de cet essai.

## Hypothèses non vérifiées et portée

Une préconnexion spéculative du navigateur, un autre client ouvrant la socket
avant sa requête, ou une interruption réseau peuvent déclencher ce mécanisme.
**L'origine exacte des connexions pendant les cinq incidents signalés n'est pas
prouvée** : aucune capture réseau ni corrélation des événements du poste utilisateur.

Le watchdog reproduit l'indisponibilité et les traces, mais pas un statut HTTP
502 exact. Le Compose local ne déclare aucun proxy HTTP et la publication de port
est TCP. L'émetteur des 502 vus sur localhost reste à identifier (en-têtes, corps,
proxy local éventuel). Ne pas attribuer ce statut à Codespaces : l'utilisateur
confirme localhost. Une réponse 502 seule ne prouve ni une erreur Django ni SQL.

CPU saturé, OOM, mise en veille et stockage Docker Desktop lent restent des causes
possibles d'autres indisponibilités ; aucune n'est confirmée par les éléments
fournis. Un message Gunicorn « SIGKILL! Perhaps out of memory? » après son watchdog
ne prouve pas à lui seul un OOM : le master peut aussi tuer son worker bloqué.

Ce correctif traite les préconnexions sans octet. Avec Gunicorn 23 gthread, les
sockets initiales silencieuses restent ouvertes jusqu'à fermeture par le client,
dans la limite configurée ; une requête **partiellement transmise** peut encore
immobiliser un thread. Un client volontairement lent sur toutes les connexions
peut donc saturer le serveur. Le test de fragmentation vérifie une reprise normale,
pas une défense Slowloris complète. Ce serveur local/private preview ne doit pas
être exposé directement sur Internet. Le proxy de production et ses limites seront
validés au lot 6 ; aucune configuration ni installation de production ici.

## Vérifications reproductibles

Avec PostgreSQL disponible localement selon le README et uniquement des données
fictives (ne pas exécuter sur production) :

```sh
set -a
. ./.env
set +a
# Si la base est publiée pour les outils hôte selon README :
docker compose -f compose.yaml -f work/host.compose.yaml up -d --no-deps db
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 PYTHONPATH="$PWD"
# Le script lance Gunicorn sur l'hôte : il ne charge pas .env, ne publie pas
# PostgreSQL et ne collecte pas les statiques à la place de l'opérateur.
uv run --frozen python manage.py collectstatic --noinput
./scripts/check.sh
# Contrôle négatif : retour 1 attendu, logs dans work/http-sync/.
uv run --frozen python -m scripts.http_stability --baseline-sync --idle-connections 2 --duration 35 --output work/http-sync
# Essai long corrigé, retour 0 attendu ; lance son propre serveur sur un port local libre.
uv run --frozen python -m scripts.http_stability --duration 1200 --output work/http-stability
```

Le script maintient douze connexions sans octet et en ouvre/ferme deux autres à
chaque cycle ; il interroge l'accueil, la connexion, live et ready. Le rapport
`result.json` indique nombre d'échecs, latence maximale, timeouts et PIDs des workers
avant/après ; `gunicorn.log` contient les événements du serveur sans journal d'accès.
Le script retourne 1 si une sonde échoue, si un worker est remplacé ou si le
watchdog intervient. Le bilan de l'essai long est consigné dans la PR de correction.

`./scripts/check.sh` exécuté : **123 tests réussis**, Ruff/mypy, contrôles Django,
absence de nouvelles migrations, migrations PostgreSQL et statiques. Les trois
nouveaux tests sur sockets réelles vérifient préconnexions, keep-alive et requêtes
fragmentées/abandonnées ; ils ne simulent pas les réponses du serveur.

La CI ajoute le même stress au-delà du watchdog **sur l'image Docker construite**,
avec les healthchecks live/ready, puis vérifie l'absence de timeout dans les logs.
Elle répète aussi les parcours des comptes/produit et le profil HTTPS Codespaces.
Le build complet local n'est pas relancé : environnement Docker `vfs` avec environ
1,7 Go libres, limite déjà rencontrée lors des lots précédents. Les essais locaux
emploient l'application sur l'hôte et PostgreSQL/Mailpit en conteneurs ; le build
et l'exécution de l'image complète sont vérifiés par la CI.

## Diagnostic Linux Mint du 9 novembre 2026

Cette section consigne les essais réalisés lors du diagnostic initial. Les
rapports cités sont des artefacts locaux dans `work/`, ignorés par Git ; ils ne
sont pas fournis par un clone du dépôt. Ces résultats historiques ne constituent
pas une nouvelle exécution des essais à chaque mise à jour de cette documentation.

Le rapport trouvé sur le poste après `collectstatic` diffère du premier essai
signalé (468 sondes, 351 échecs) : **480 sondes, 120 échecs**, exclusivement
des 503 sur ready ; aucune erreur sur les pages HTML, aucun timeout, mêmes PIDs
260647/260648. Copie conservée dans `work/http-stability-before-local-fix/`.

Deux prérequis locaux distincts expliquent les erreurs :

- **500 HTML** : `templates/base.html` appelle `{% static 'app.js' %}` et
  `{% static 'app.css' %}`. Avec `DEBUG=False`, le stockage WhiteNoise exige
  leur présence dans le manifeste. La chaîne est `storage.url()` → `_url()` →
  `stored_name()` (`django/contrib/staticfiles/storage.py:518` dans Django
  5.2.19), qui lève `ValueError: Missing staticfiles manifest entry for 'app.js'`.
  Le mécanisme a été reproduit avec un stockage au manifeste vide **en mémoire**,
  sans altérer les statiques. Les traces HTTP 500 initiales ne sont plus dans le
  journal disponible ; celui-ci correspond au test après collecte. Le manifeste
  actuel contient les deux fichiers, et les pages répondent 200. Relancer
  `collectstatic --noinput` avant Gunicorn sur l'hôte ; l'image Docker le fait
  déjà à la construction. Ne pas désactiver la vérification du manifeste.
- **503 ready** : `.env` cible `127.0.0.1:5432`, mais Compose ne publiait aucun
  port PostgreSQL sur l'hôte. Connexion directe confirmée en échec :
  `OperationalError: connection failed ... 127.0.0.1, port 5432 ... Connection refused`.
  Trace : `connection.cursor()` → `_cursor()` → `ensure_connection()` →
  `connect()` → `postgresql/base.py:get_new_connection()` →
  `psycopg/connection.py:126:connect()`. `health_ready()` intercepte correctement
  cette erreur et renvoie 503. Le journal affiche `database_unavailable` ;
  `SafeJsonFormatter` masque volontairement messages d'exception et requêtes.
  Le port a été publié via `work/host.compose.yaml` sur **127.0.0.1:55432**,
  avec le volume existant ; `POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432`
  sont exportés après chargement de `.env`. `SELECT 1` depuis Django sur l'hôte
  retourne ensuite `(1,)`. Aucun changement de mot de passe ou de données.

Le script ne présente pas de faux succès : il retournait bien 1 pour les 503.
Il hérite des variables du shell, contrairement aux services applicatifs Compose
qui imposent `db:5432`. Aucun défaut métier ni modification du worker n'a été
nécessaire ; seule la procédure hôte est précisée. `.env` reste inchangé.

Validations sur l'hôte (Python 3.12.3, Django 5.2.19, Gunicorn 23.0.0) :

| Durée demandée | Durée mesurée | Sondes | Échecs | Latence max |
| --- | --- | --- | --- | --- |
| 10 s | 11,06 s | 40 | 0 | 60,2 ms |
| 120 s | 121,93 s | 476 | 0 | 34 ms |
| 1 200 s | 1 201,97 s | 4 760 | 0 | 25,4 ms |

Ces trois essais maintiennent 12 sockets silencieuses, sans `WORKER TIMEOUT`,
sans `no URI read`, sans remplacement de worker, retour 0. Rapports séparés :
`work/http-stability-short/`, `work/http-stability-120s/` et
`work/http-stability-20min/`. L'essai de 20 minutes conserve les PIDs
268472/268473 ; son journal final ne contient ni erreur ni avertissement,
seulement démarrage, signal TERM demandé par le script et arrêt normal.
Commandes exécutées après chargement de `.env` et exports hôte ci-dessus :

```sh
uv run --frozen --no-sync python -m scripts.http_stability --duration 10 --output work/http-stability-short
uv run --frozen --no-sync python -m scripts.http_stability --duration 120 --output work/http-stability-120s
uv run --frozen --no-sync python -m scripts.http_stability --duration 1200 --output work/http-stability-20min
```

`--no-sync` réutilise l'environnement uv déjà installé. Pour ces commandes,
`UV_CACHE_DIR=/tmp/muqola-uv-cache` a également été exporté (contrainte sandbox).
`./scripts/check.sh` retourne 0 : Ruff (118 fichiers formatés), mypy (76 fichiers),
contrôles Django, aucune migration manquante ou à appliquer, collecte des
statiques et **123 tests réussis en 74,94 s**, dont les tests sur sockets réelles
et les tests concurrents PostgreSQL. Aucune image Docker reconstruite pour cette
correction de documentation/configuration hôte.

Contrôle négatif rejoué avec la même configuration hôte corrigée :
`uv run --frozen --no-sync python -m scripts.http_stability --baseline-sync
--idle-connections 2 --duration 35 --output work/http-sync-local`.
Retour **1 attendu** : 28 sondes, 14 échecs, 35,89 s mesurées, deux
`WORKER TIMEOUT`, deux `no URI read`, workers 277048/277055 remplacés par
277566/277567. Le scénario détecte donc toujours le défaut ancien.

L'accueil et ready répondent aussi 200 sur `http://localhost:8000` (Compose).
Le test valide le correctif du blocage Gunicorn sur préconnexion silencieuse ;
il n'identifie toujours pas l'émetteur des 502 historiques, qui n'ont pas été
reproduits comme réponses HTTP pendant cette investigation.

## Si un incident persiste sur le poste local

Conserver l'heure et les informations suivantes, sans copier cookies, jetons,
fichiers `.env` ou sortie complète de `docker inspect` :

```sh
curl -sS -D - -o /dev/null --max-time 5 http://localhost:8000/health/live/
curl -sS -D - -o /dev/null --max-time 5 http://localhost:8000/health/ready/
docker compose ps
docker compose logs --since=20m --tail=100 web
docker inspect --format '{{.State.Status}} OOM={{.State.OOMKilled}} restarts={{.RestartCount}}' "$(docker compose ps -q web)"
```

Relever en particulier le statut réel et un éventuel en-tête `Server` du 502,
les timeouts, redémarrages et événements mémoire. Ces éléments permettent de
distinguer une réapparition du défaut de socket d'une autre panne locale.
