"""Serveur du Compose de développement ; aucun réglage de production livré ici."""

bind = "0.0.0.0:8000"
workers = 2
# sync bloque tout le processus en attendant le premier octet d'une préconnexion.
# gthread attend la lisibilité des sockets dans son sélecteur, hors du pool HTTP.
worker_class = "gthread"
threads = 4
worker_connections = 64
keepalive = 2
timeout = 30
graceful_timeout = 20
# Compose monte /tmp en tmpfs ; le heartbeat ne dépend pas du disque Docker.
worker_tmp_dir = "/tmp"  # noqa: S108 — fichiers mkstemp privés de Gunicorn, tmpfs Compose.
accesslog = None
errorlog = "-"
loglevel = "warning"
