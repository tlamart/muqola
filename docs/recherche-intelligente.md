# Recherche intelligente — PR A

Branche `feat/recherche-intelligente`, créée depuis `origin/main` `fdf9268`, après
fusion de B #29. Aucun import, catalogue réel, upload, fonctionnalité C anticipée,
merge ou déploiement. Les arbitrages B1–B4 et le socle Wikidata/Commons #25 restent
conservés. Les anciennes migrations ne changent pas.

## Deux périmètres et un moteur

`catalogue.matching` centralise la normalisation existante, `title_condition`,
`matching_title` (gardes exactes B) et `ranked`. Les exports historiques restent
compatibles. Aucun service externe, cache partagé ni statistique globale du
catalogue ne participe au score.

- **Ajouter** (`/games/`) : fiches canoniques, approuvées, non masquées, métadonnées
  génériques seulement. Propositions privées et fiches héritées ne sont pas des
  résultats du catalogue validé. Les suggestions du formulaire emploient ce moteur.
- **Emprunter** (`/copies/`) : `borrowable` part des copies non archivées/retirées,
  d'un propriétaire actif et vérifié autre que le lecteur, rattachées à une fiche
  canonique approuvée ou héritée non masquée. Une visibilité doit relier une
  communauté où **lecteur et propriétaire** ont une appartenance active actuelle.
  Les filtres communauté, joueurs et disponibilité précèdent `grouped` et le rang.
  Les `Exists` évitent de multiplier les copies partagées dans plusieurs groupes.
- `grouped` retourne un `Game` par carte et deux agrégats corrélés au même périmètre
  filtré (`copy_count`, `available_count`). Les prêts acceptés/remis rendent une
  copie indisponible mais visible tant qu'elle reste partageable. Sans copie
  autorisée, aucun résultat, même si la fiche existe dans le catalogue global.
- `/copies/games/<uuid>/` exige une copie autorisée et liste au plus 30 copies,
  sans inclure la collection personnelle. Après révocation, ce détail renvoie 404.
  Les détails directs des exemplaires utilisent également le sélecteur strict ;
  le propriétaire conserve son accès à ses copies non archivées dans « Mes jeux ».

Une copie invisible ne change ni rang, ni nombre, ni page. Les noms de communautés
dans les détails sont limités aux appartenances du lecteur. Aucun e-mail n'apparaît
dans la recherche. Les tests comparent le fragment avant/après une copie privée et
un jeu privé, y compris sur la deuxième page.

## Classement et seuils

La clé persistée #25 reste NFKD + casefold, suppression des diacritiques et espaces
normalisés, sur titre principal et alias. Aucun `unaccent` supplémentaire.

1. Exact principal, puis exact alias.
2. Préfixe principal, puis préfixe alias.
3. Contenu principal, puis contenu alias.
4. Similarité trigramme maximale entre principal et chaque alias, décroissante.
5. Dans chaque niveau textuel : titre normalisé, UUID. Les fréquences et quantités
   d'exemplaires n'interviennent jamais. Les alias restent des sous-requêtes, donc
   ne multiplient ni résultats ni pagination.

Une saisie vide restaure la liste initiale ; un caractère ne produit pas de
résultat serveur. Deux caractères : exact/préfixe seulement. Trois : ajout du
contenu. À partir de quatre : fuzzy. Seuil final 0,20 pour quatre caractères,
0,30 au-delà. La connexion fixe `pg_trgm.similarity_threshold=0.2` pour les
candidats indexés `%`, puis le filtre applique le seuil final. Les scores sont
indépendants du corpus ; ils ne sont jamais une décision automatique de fusion.
Les tests couvrent Régicide/regicdie, accents, espaces, alias, Go/Gobelins/Algo,
non-correspondances et homonymes à UUID distincts. Les faux positifs restent des
suggestions à examiner ; un mot isolé mal orthographié dans un titre très long
peut ne pas atteindre le seuil de similarité du titre complet.

`ops catalogue-review` montre les suggestions classées avec le même moteur et,
séparément, les collisions exactes principal/alias de B. Soumission et validation
revérifient les collisions dans `domain_write`, y compris POST direct et courses.
Un homonyme exact peut être justifié et audité ; une proximité fuzzy seule ne
rejette pas un jeu, ne fusionne rien et ne contourne pas les gardes B.

## HTTP, JavaScript et accessibilité

GET classique et `X-Requested-With: live-search` utilisent les mêmes sélecteurs,
paginateurs et templates de résultats HTML autoéchappés. Les fragments exigent
session active et compte vérifié (connexion ou 403), sont `no-store`, et aucune
CORS n'est ouverte. Pas de JSON exposant un autre périmètre. Titres bornés à 120
caractères ; filtres joueurs 1–100 et communauté validée ; 10 fiches/page en ajout,
30 jeux/page en emprunt, 30 copies/page au détail. Pagination invalide bornée par
Django. Chaque GET de recherche utilise une transaction de lecture avec un délai
SQL local de 5 s par instruction ; un dépassement rend une page 503 accessible
avec lien de reprise (`Retry-After: 1`). `jit=off` reste local à cette transaction :
la compilation de centaines d’expressions corrélées dominait le coût mesuré des
petites lectures OLTP ; migrations et écritures gardent leur configuration.
Les URL gardent titre/filtres/page et sont partageables entre comptes,
chacun voyant uniquement ses droits actuels.

`static/search.js` : deux caractères et 250 ms, composition IME suspendue,
`AbortController` et compteur invalidé dès la saisie. Une réponse ancienne est
ignorée même si le transport refuse l'annulation. Vider le titre et changer les
filtres relancent le GET. La pagination reste de vrais liens. Seul le sous-arbre
résultats est remplacé ; choix du jeu, notes et partages restent en place. Le choix
persistant possède une annonce et un bouton d'effacement. Le retour BFCache relance
une lecture des droits actuels. Aucun HTML ni gestionnaire de script inline.

CSP `connect-src 'self'`, sans autoriser les autres origines. `aria-busy`, statut
poli pour chargement/nombre/aide/erreur ; focus de saisie conservé. Une panne garde
les résultats précédents et propose Entrée pour un GET natif ; sans JS, Entrée et
les liens fonctionnent. Le submit HTML caché permet l'activation implicite avec
plusieurs champs (dont le nombre de joueurs). Pas de bouton Rechercher visible.
Les logs JSON existants omettent URL, paramètres et texte recherché.

## Migration et privilèges PostgreSQL 17

`0004_game_game_title_trgm_gamealias_alias_title_trgm` installe `pg_trgm` via
`TrigramExtension`, puis deux GIN `gin_trgm_ops` : `game_title_trgm` et
`alias_title_trgm`. Migration `atomic=False` et `AddIndexConcurrently` : pas de
réécriture des lignes ni verrou bloquant les écritures pendant toute la création
d'index. Aucun prêt, exemplaire, alias, crédit ou identifiant modifié. Les B-tree
existants restent utiles pour exact/préfixe ; PostgreSQL choisit le plan selon
sélectivité. Une petite base peut légitimement préférer un scan séquentiel.

Le rôle de **migration** doit posséder les tables et pouvoir créer l'extension
(privilège CREATE sur la base pour cette extension trusted, ou préinstallation
contrôlée par l'administrateur). Le rôle **runtime** n'a besoin que de connexion,
USAGE sur le schéma, DML nécessaire à l'application et usage des fonctions de
l'extension ; pas de CREATE sur la base, pas de rôle superutilisateur. Un test réel
fait fonctionner la recherche sous `NOSUPERUSER NOCREATEDB NOCREATEROLE`, puis
vérifie le refus de création d'une autre extension. Le paramètre pg_trgm de
connexion est réglable sans privilège d'administration.

Préparer les index avant de redémarrer le nouveau binaire. En cas d'interruption
de création concurrente, vérifier `pg_index.indisvalid` : retirer/recréer seulement
l'index invalide concerné, sous procédure opérateur contrôlée, avant de reprendre
la migration. Aucun nettoyage automatique de données. Le reverse de A retire
seulement ses index ; il conserve l'extension partagée entre schémas. B reste
volontairement irréversible, aucun retour destructeur vers les anciens modèles.
Le test de A part de B peuplée et compare toutes les lignes ; les tests historiques
partent aussi de 0001/0002 et conservent tous les états de prêts et références #25.

## Vérification et performances

Mesures exécutées le 16 novembre 2026 sur PostgreSQL 17.12 et Python 3.12.14.
La commande `benchmark_search` refuse toute base non vide, tout environnement
hors test et tout nom ne finissant pas par `_benchmark`. Elle crée 10 000 jeux,
30 000 alias et 40 000 copies synthétiques dans une transaction, puis **annule**
ces insertions. Par jeu : une copie autorisée, une privée, une retirée et une
archivée. Aucun catalogue réel ni dump n'est committé.

Mesure : GET HTML authentifié complet (session, autorisation, SQL de comptage et
résultats, rendu), deux échauffements puis 30 échantillons, un processus, cache
chaud. Huit scénarios : deux caractères, exact, alias et faute, dans les deux
périmètres. Listes GIN en attente vidées explicitement (le corpus reste non committé, donc
l’autovacuum ne peut pas le faire), puis ANALYZE sur toutes les tables concernées,
y compris utilisateurs et appartenances. EXPLAIN ANALYZE/BUFFERS des requêtes
sélective, catalogue et emprunt, plans
conservés dans le rapport JSON local/artefact CI. La CI exécute le même protocole
avec 1 000 jeux et 10 échantillons pour rester dans son budget global.

Les titres synthétiques partagent volontairement beaucoup de trigrammes : cela
stresse aussi les requêtes peu sélectives et le classement d'un grand ensemble.
Le budget déduit est une borne de régression sur cette machine et ce protocole,
pas une promesse de latence sur un VPS non mesuré ou en charge concurrente.


### Résultats locaux (10 000 jeux)

Machine Cloud Linux x86_64, Xeon Platinum 8573C, quota CPU 2 cœurs (3 processeurs
visibles), mémoire disponible dans le conteneur 9,7 Gio. La mesure couvre le GET
Django complet dans le processus, sans réseau navigateur ni debounce.

| Périmètre | Saisie synthétique | p50 ms | p95 ms | Requêtes SQL |
| --- | --- | ---: | ---: | ---: |
| Ajout | Deux caractères | 54.57 | 87.31 | 9 |
| Ajout | Exact principal | 684.87 | 864.89 | 9 |
| Ajout | Alias | 845.58 | 975.21 | 9 |
| Ajout | Faute | 640.05 | 781.41 | 9 |
| Emprunt | Deux caractères | 195.58 | 306.05 | 9 |
| Emprunt | Exact principal | 922.33 | 993.65 | 9 |
| Emprunt | Alias | 1050.35 | 1230.78 | 9 |
| Emprunt | Faute | 889.66 | 1051.93 | 9 |

Le maximum p95 mesuré est **1 230,78 ms**. Budget de régression fixé ensuite à
**3 000 ms p95** pour ce protocole synthétique ; `--p95-budget-ms` le rend explicite
et la commande échoue au dépassement après avoir annulé le corpus et écrit le
rapport. La CI utilise cette même borne sur 1 000 jeux/10 mesures, sans prétendre
mesurer une charge de production. Les lectures HTTP gardent aussi leur limite
SQL de 5 s par instruction et un repli 503, vérifié par `pg_sleep(6)` réel.

EXPLAIN ANALYZE/BUFFERS confirme des Bitmap Index Scan sur **les deux GIN**
pour la requête sélective (0,460 ms d'exécution SQL). Les plans catalogue et
emprunt de stress prennent respectivement 451,333 et 434,189 ms ; ils combinent
scans selon sélectivité, index d'alias et Hash Semi Join du périmètre autorisé.
ANALYZE des appartenances est nécessaire pour des estimations correctes après
un chargement massif synthétique ; l'autovacuum normal reste à surveiller sur
une instance réelle. Aucune option ne force globalement un type de jointure.

L'intersection des candidats titre/alias avec le périmètre autorisé précède le
classement et les comptes. Les branches d'index renvoient seulement des IDs ;
elles ne répètent pas le calcul des droits et ne publient aucun candidat privé.

Validation locale : `scripts/check.sh` complet, **312 tests réussis**, puis test
additionnel des gardes du benchmark (base normale/peuplée refusée), **3 tests de
migration/guard réussis**. Ruff, format, mypy (100 sources), contrôles Django,
`makemigrations --check`, migrations, statiques, check production et audit runtime
réussis. Parcours produit/prêts, ajout rapide 6 variantes avec/sans JS, alias/Commons
avec image synthétique interceptée, responsive 5 largeurs et test de recherche à
horloge/réponses contrôlées exécutés. Le résultat final de CI et les 313 tests
du dernier état sont consignés dans la PR.


### Limites de validation

Chromium Linux et vues mobiles simulées, pas de téléphone physique ni d'audit
humain avec un lecteur d'écran dédié. Les tests vérifient labels, clavier, focus,
statuts et attributs ARIA. Pas de charge concurrente de production, de VPS, de
catalogue réel ni de restauration d'une instance réelle. Ces limites ne sont
pas présentées comme des mesures de production.
