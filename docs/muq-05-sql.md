# MUQ-05 — Disponibilité et requêtes SQL

Base mesurée : `main` au commit `bced0a87ec0b2c77daadb7057a05707424704b1d`.
Mesures réelles avec Django 5.2.19, Python 3.12.14 et PostgreSQL 17
(conteneur local isolé). Comptage de la requête HTTP complète avec le client
Django et `CaptureQueriesContext`, rendu des templates compris ; création des
fixtures et connexion hors comptage. Chaque jeu de données comporte une fiche,
un propriétaire, un lecteur, une communauté commune et N exemplaires partagés,
sans prêt actif. « Mes jeux » est consulté par le propriétaire.

| Vue | Exemplaires en base | Avant | Après | Affichés après |
| --- | ---: | ---: | ---: | ---: |
| Explorer | 1 | 7 | 6 | 1 |
| Explorer | 10 | 16 | 6 | 10 |
| Explorer | 30 | 36 | 6 | 30 |
| Explorer | 65 | 36 | 6 | 30 |
| Mes jeux | 1 | 5 | 4 | 1 |
| Mes jeux | 10 | 14 | 4 | 10 |
| Mes jeux | 30 | 34 | 4 | 30 |
| Mes jeux | 65 | 34 | 4 | 30 |
| Détail de fiche | 1 | 8 | 9 | 1 |
| Détail de fiche | 10 | 17 | 9 | 10 |
| Détail de fiche | 30 | 37 | 9 | 30 |
| Détail de fiche | 65 | 72 | 9 | 30 |

Avant la correction, Explorer et Mes jeux étaient déjà paginés à 30 : leur coût
plafonnait donc après 30, mais augmentait avec chaque exemplaire affiché.
Le détail chargeait tous les exemplaires. Les mesures historiques de l'audit
sont confirmées sur cette base, sans être utilisées comme assertions initiales.

## Correction

`with_availability()` annote chaque exemplaire avec un `Exists` corrélé par
`OuterRef` sur les prêts `ACCEPTED`/`HANDED_OVER`. `OwnedGame.available` réutilise
cette annotation dans les vues de lecture et leurs templates ; une instance non
annotée conserve sa vérification directe. Retrait, archivage et fiche masquée
restent indisponibles. Le filtre de disponibilité utilise le même sous-select.
Les transactions de prêt conservent leurs lectures et contrôles existants.

Le détail utilise le paginateur Django à 30 exemplaires avec navigation et ordre
stable existant. Les visibilités ne sont chargées que pour la page courante et
les communautés actives du lecteur, puis regroupées en mémoire. Le badge global
interroge la disponibilité de tous les exemplaires autorisés, y compris hors
page ; c'est une requête supplémentaire constante. Un exemplaire privé ou
visible uniquement ailleurs n'entre ni dans ce badge ni dans le compteur.

Aucune migration, dépendance, cache ou infrastructure supplémentaire.

## Reproduire et vérifier

Configurer PostgreSQL et les variables de test comme dans le README / la CI,
installer le verrou avec `uv sync --frozen`, puis :

```sh
uv run --frozen python manage.py collectstatic --noinput
uv run --frozen pytest tests/test_inventory_sql.py -q -s
uv run --frozen pytest tests/test_inventory.py tests/test_communities.py tests/test_loans.py tests/test_ui.py -q
./scripts/check.sh
```

Pour reproduire l'avant, utiliser un checkout isolé du commit de base, y copier
le test `test_page_query_count` avec ses imports et retirer ses deux assertions
finales (budget constant et taille bornée). Les mesures ci-dessus ont été faites
avec ce test avant toute optimisation puis avec la correction, sur le même
PostgreSQL et le même verrou de dépendances.

Les tests SQL couvrent 1/10/30/65 exemplaires, le filtre « disponibles », tous les
états de prêt croisés avec retrait/archivage/masquage, l'absence de requête lors de
lectures répétées de l'annotation, trois pages sans doublon, les pages invalides,
la disponibilité hors page, les exemplaires privés, le masquage des communautés
étrangères et la révocation d'appartenance. Les tests métier existants vérifient
notamment les permissions et les transitions de prêt.

## Résultats de validation

- Tests SQL : **45 réussis**.
- SQL + inventaire + communautés + prêts + interface : **92 réussis**.
- `./scripts/check.sh` : lint, format, mypy, contrôles Django, absence de
  migrations nouvelles, migration locale, collecte statique et **206 tests réussis**.
- Construction de `muqola:muq05` réussie ; `python manage.py check` dans l'image
  sans dépendances de développement : aucun problème détecté.
