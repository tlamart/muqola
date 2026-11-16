# Catalogue Wikidata et illustrations Commons

## Périmètre et données

Import local volontaire, sans API, téléchargement serveur, synchronisation ou
import au démarrage/migration/déploiement. La commande historique `import_games`
et son CSV neuf colonnes restent inchangés. Le CSV Wikidata est un format séparé.
Aucun exemplaire physique n'est créé pendant l'import.

Le fichier fourni pour la bêta contient **1 539 jeux**, **1 474 titres anglais non
vides** et **298 illustrations `approved_by_owner`**. Les 1 241 autres lignes ne
contiennent pas d'image ; les 57 images écartées ne sont ni recherchées ni rétablies.
Ces nombres sont attendus sur une base sans conflits, pas une obligation de
remplacer des fiches déjà présentes.

Le vrai CSV reste dans `data/import/muqola_wikidata_import_1539.csv`, ignoré par
Git et le contexte Docker. Les noms `*wikidata*.csv` sont aussi ignorés ailleurs.
Aucune donnée réelle n'est dans les migrations, fixtures, tests ou images Docker.
Les tests créent uniquement des données synthétiques en mémoire/répertoire temporaire.

## Commandes locales explicites

Installer les migrations sur la base locale avant la première simulation :

```sh
docker compose exec web python manage.py migrate --noinput
docker compose exec -T web python manage.py import_wikidata_games /dev/stdin --dry-run < data/import/muqola_wikidata_import_1539.csv
docker compose exec -T web python manage.py import_wikidata_games /dev/stdin < data/import/muqola_wikidata_import_1539.csv
```

Hors conteneur, avec la connexion PostgreSQL locale configurée :

```sh
uv run --frozen python manage.py migrate --noinput
uv run --frozen python manage.py import_wikidata_games data/import/muqola_wikidata_import_1539.csv --dry-run
uv run --frozen python manage.py import_wikidata_games data/import/muqola_wikidata_import_1539.csv
```

La simulation n'écrit aucune ligne, aucun compte, alias ou crédit. Les nombres
`created`, `aliases` et `images` y signifient « seraient créés ». La commande réelle
réutilise le compte technique désactivé/non privilégié de `import_games`, après
vérification ; elle ne réactive ni ne transforme un compte humain.

CSV UTF-8/BOM, séparateur virgule, colonnes exactes (ordre libre) :

```text
wikidata_id,title_fr,title_en,bgg_ids,data_source,data_license,image_url,image_commons_file,image_source_url,image_license,image_license_url,image_artist,image_attribution,image_review_status
```

Titre français obligatoire, 120 caractères maximum ; anglais facultatif, même
limite. Identifiant `Q` suivi d'un entier positif, provenance Wikidata, licence
de données `CC0`. Références BGG : entiers positifs séparés par `;`, dédupliqués ;
ce sont uniquement des correspondances provenant de Wikidata, sans métadonnées BGG.
Les champs trop longs ou invalides sont refusés, sans troncature silencieuse.

Bilan JSON : `created`, `existing`, `conflicts`, `invalid`, `aliases`, `images`,
`images_invalid`, `images_ignored`, `dry_run`. Les diagnostics indiquent sur stderr
la ligne physique (fin d'enregistrement multiligne), sans recopier les métadonnées.
Lecture par lots de 250 ; une erreur fatale annule le lot courant, les lots validés
restent acquis. La fiche, son alias et son illustration sont enregistrés atomiquement.
La clé unique en base protège les imports simultanés.

## Idempotence et conflits

Clé stable : `(external_source=wikidata, external_id=Q…)`. Toute fiche déjà
présente est comptée dans `existing` et laissée entièrement intacte : titre,
masquage, alias, provenance et illustration, y compris les modifications humaines.
Une relance ne remplit donc pas une illustration ignorée au premier import ; une
réparation ou un enrichissement ultérieur devra être explicitement conçu/validé.

Un identifiant BGG déjà connu, ou un titre français/anglais identique après
normalisation à une ancienne fiche BGG/manuelle, produit `conflicts` : **aucune
fusion, nouvelle fiche ou modification pour cette ligne**. Les fiches masquées
sont incluses dans cette détection. Des Wikidata distincts restent distincts,
même si leurs titres se ressemblent. La revue des conflits est une décision
humaine ultérieure, pas une suppression ou une réaffectation automatique des
exemplaires existants. Aucune interface d'administration n'est ajoutée.

## Modèle et recherche

Migration additive `catalogue.0002_wikidata_catalogue` :

- `Game.data_source`, `data_license`, `bgg_ids`, vides pour les anciennes fiches.
- `GameAlias` : titre et clé normalisée/indexée, FK `Game` en CASCADE et unicité
  par jeu/clé normalisée. L'anglais est un alias, sans remplacer le français.
- `GameIllustration` : OneToOne/CASCADE vers Game, références Commons et crédits ;
  contrainte de statut approuvé. Les protections existantes des Game/OwnedGame
  et les historiques de prêts restent inchangés.

La recherche française/anglaise ignore casse et accents. Un `Exists` évite de
multiplier les résultats quand plusieurs alias correspondent. Le catalogue et
l'exploration des exemplaires utilisent cette logique, avec leurs contrôles de
visibilité existants. La priorité des correspondances exactes et la pagination
sont conservées. La création manuelle reconnaît aussi les noms anglais pour
proposer le jeu existant avant de confirmer une autre édition.

Les illustrations sont jointes aux lectures en liste pour éviter des requêtes
par carte ; les budgets SQL MUQ-05 restent contrôlés. Aucun propriétaire ou
nombre d'exemplaires privés n'est révélé par les nouvelles métadonnées.

## Images et licences distinctes

`CC0` concerne les **données Wikidata**, pas l'ensemble des images. Une image n'est
retenue que si la ligne porte `approved_by_owner` et si ses références/crédits
passent la validation. Une image invalide ou non approuvée est ignorée sans empêcher
l'import du titre et de l'alias. La validation structurelle n'est pas une expertise
juridique à distance : l'approbation du fichier et sa traçabilité restent importantes.

- URL d'image : HTTPS sur `commons.wikimedia.org/wiki/Special:FilePath/…`.
- Source : HTTPS sur `commons.wikimedia.org/wiki/File:…`, désignant le même fichier
  que `image_commons_file`. Identifiants de connexion, ports, query et fragment refusés.
- Licence : URL HTTPS `creativecommons.org`, chemin cohérent avec le nom CC BY,
  CC BY-SA (versions 1.0/2.0/2.5/3.0/4.0) ou CC0. Les anciens liens HTTP connus sont
  convertis localement en HTTPS, sans les visiter ; cela concerne 37 lignes fournies.
- Auteur ou attribution requis pour BY/BY-SA. Dans le fichier, trois auteurs vides
  ont une attribution utilisée pour les crédits ; une quatrième image est CC0
  sans auteur fourni, affiché comme non renseigné. Aucun auteur n'est inventé.

Le navigateur charge directement Commons (redirection possible vers
`upload.wikimedia.org`). Le serveur ne télécharge ni ne transforme les images.
L'affichage reprend auteur/attribution, source et lien de licence, toujours échappés.
Aucun HTML des métadonnées n'est interprété. Les images indisponibles conservent
le visuel local ; JavaScript masque l'image cassée, sans gestionnaire inline.
Les parcours d'ajout restent utilisables sans JavaScript.

La CSP n'ouvre que `img-src` à ces deux hôtes Wikimedia ; scripts, styles et autres
origines gardent leurs restrictions. `referrerpolicy=no-referrer` et les liens
`noreferrer` évitent de transmettre les URL privées de Muqola. Wikimedia reçoit
néanmoins la requête d'image du navigateur (notamment son IP). Si une fiche est
masquée, aucune illustration distante n'est affichée, même sur l'exemplaire privé
que son propriétaire peut encore consulter.

## Vérifications

```sh
./scripts/check.sh
uv run --frozen pytest tests/test_wikidata_import.py tests/test_catalogue_import.py tests/test_quick_add.py tests/test_inventory_sql.py -q
```

Le workflow CI ajoute une seule ligne synthétique via la nouvelle commande puis
vérifie recherche par alias, titre français, crédits, ajout privé/partagé et
remplacement après erreur avec Chromium, à 360/768/1280 px, avec/sans JS. L'image
de ce scénario est interceptée et remplacée par un pixel synthétique ; aucun
accès réseau Wikimedia ni CSV réel n'est requis pour les tests reproductibles.
Les parcours existants comptes/prêts/notifications/responsive sont conservés.
Dans cet environnement Cloud, le proxy refuse l’accès direct à Commons : la
disponibilité réelle des 298 fichiers distants ne peut donc pas y être confirmée.
Les références du CSV sont toutes validées structurellement ; le navigateur teste
le chargement, les crédits et les erreurs sur une image synthétique interceptée.

Aucune configuration de production du lot 6 ni déploiement n'est réalisé ici.
Avant une migration réelle hors développement, prévoir sauvegarde et validation
opérateur. La migration inverse retirerait les nouvelles métadonnées : elle ne
constitue pas une restauration du catalogue enrichi.
