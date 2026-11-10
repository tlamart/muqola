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
export POSTGRES_PORT=55432
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
