# MUQ-06 — Diagnostic JSON et confidentialité

Correction limitée au formateur ; aucun autre MUQ, aucun travail du lot 6.
La stack de l'ADR 0001 est conservée, sans dépendance supplémentaire.

## Reproduction et évolution minimale

Avant correction, deux `LogRecord` avec `exc_info` (respectivement `ValueError`
et `RuntimeError`), message et arguments fictifs sensibles, donnaient exactement :

```json
{"level": "ERROR", "logger": "muqola.core.views", "event": "runtime_event"}
```

Le formateur ignorait la date, le type et la localisation. Le choix de ne pas
rendre le texte libre reste volontaire. Après correction, exemple fictif pour
un enregistrement daté du 12 novembre 2026 à 09:00 UTC :

```json
{"level": "ERROR", "logger": "muqola.core.views", "event": "runtime_event", "timestamp": "2026-11-12T09:00:00.125Z", "exception_type": "ValueError", "module": "muqola.core.views", "function": "health_ready", "line": 42}
```

Une `RuntimeError` devient distinguable par `exception_type`. Les tests figent
cet horodatage et ces métadonnées ; les numéros de ligne réels varient avec le code.

## Contrat : liste fermée des clés

Un objet JSON par ligne, sérialisé avec `json.dumps` (échappement des contrôles).

| Champ | Type | Présence et origine |
| --- | --- | --- |
| `level` | chaîne | Toujours, niveau du LogRecord (comportement existant) |
| `logger` | chaîne | Toujours, nom du logger (comportement existant) |
| `event` | chaîne | Toujours : `database_unavailable`, `notification_retry`, `notification_failed` ou repli `runtime_event` |
| `timestamp` | chaîne | Toujours, `record.created` converti en UTC ISO 8601, millisecondes, suffixe `Z` |
| `exception_type` | chaîne | Seulement si `exc_info` fournit une classe ; nom de classe, jamais son message |
| `module` | chaîne | Module Python sous les répertoires applicatifs `muqola` ou `config` du dépôt |
| `function` | chaîne | Seulement avec module autorisé et nom identifiant valide |
| `line` | entier positif | Seulement avec module autorisé et ligne disponible |

Pour une exception, la dernière frame appartenant au code applicatif est retenue.
Sinon, le site de journalisation est utilisé s'il appartient au code applicatif.
Les chemins absolus, frames tierces, extraits de source et variables locales ne
sont jamais sérialisés. Si aucune localisation applicative n'est disponible,
les champs correspondants sont omis. Les noms de module, fonction et classe
sont limités à des identifiants ASCII de 128 caractères par composant ; un nom
de classe invalide devient `Exception`. Les fonctions synthétiques telles que
`<module>` et `<lambda>` sont omises. Les exceptions chaînées ne sont pas développées.

## Garanties et limites

Le formateur construit explicitement l'objet ; il ne copie pas le dictionnaire
du LogRecord, ni `extra`, ni la requête. Il n'appelle pas `getMessage`,
`formatException`, `formatStack` ou `str(exception)`. `args`, `exc_text` même
prérempli, `stack_info`, URLs/query strings, jetons, secrets, cookies, corps,
en-têtes, contacts et identifiants de requête sont ignorés. Aucun texte de
traceback, local, message ou source de code n'est inclus. La liste des événements
métier reste inchangée. Aucune journalisation exhaustive HTTP n'est activée.

Les noms de logger et métadonnées de code doivent rester définis par le serveur :
ne jamais créer un logger, une classe d'exception, un nom de fonction ou un
chemin de code à partir d'une entrée utilisateur. Ce contrat ne protège pas un
processus compromis capable de fabriquer ses propres métadonnées de code ou
un handler externe utilisant un autre formateur. Les champs diagnostiques
permettent d'identifier le lieu et la famille d'erreur, pas ses valeurs internes.

## Corrélation évaluée

Un UUID aléatoire généré côté serveur serait utile pour relier plusieurs logs
applicatifs d'une même exécution concurrente. Un UUID par ligne n'apporterait
pas cette corrélation. Le bon mécanisme exigerait un contexte par requête/tâche,
initialisé et nettoyé même après exception, avec tests d'isolation et du worker.
Pour garder MUQ-06 minimal, aucun identifiant n'est ajouté à ce stade.
Aucune valeur de `X-Request-ID`, cookie, URL, compte ou autre entrée client n'est
conservée ; même un `extra` nommé `correlation_id` est exclu. Une future extension
devrait générer sa valeur exclusivement côté serveur et ajouter explicitement
ce seul champ à la liste fermée.

## Validation

Tests ciblés :

```sh
uv run --frozen pytest tests/test_logging.py tests/test_foundation.py::test_logs_drop_urls_tokens_and_exceptions
```
Validation complète : `./scripts/check.sh`, avec configuration locale de test
et PostgreSQL réel. Voir la PR pour les résultats exécutés.
