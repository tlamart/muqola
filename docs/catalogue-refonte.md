# PR B — Catalogue modéré et fusions conservatrices

Implémentation sur `feat/catalogue-refonte`, depuis `origin/main` à `46362f1` (arbitrages B1–B4 validés). Django/PostgreSQL, recherche synchrone et communautés privées conservés. Aucune fonction des PR A/C, aucun upload, aucun seed ou import externe.

> Le correctif [P1](pret-fiches-en-attente.md) amende B1 : le prêt pending ne nécessite plus de validation administrative. Les preuves de livraison B ci-dessous restent historiques.

## Modèle et droits

`Game` conserve son UUID, ses métadonnées et les modèles Commons de #25. Le statut est distinct de `hidden` :

| Statut | Catalogue global / réemploi | Collection / prêt |
| --- | --- | --- |
| `pending` | Hors catalogue général ; auteur/opérateur ou accès actuel à une copie partagée | Auteur : copies privées ou explicitement partagées/prêtables (P1) |
| `rejected` | Hors catalogue général ; motif réservé à l’auteur/opérateur | Copies/partages conservés ; pas de nouvelle demande/acceptation. Prêts acceptés clôturables ; correction auteur sans lever le rejet |
| `approved` | Réemploi par tous les comptes actifs/vérifiés si non masqué | Partages explicitement choisis par chaque propriétaire |
| `legacy_to_review` | Hors du catalogue validé, pas de nouvel exemplaire par URL directe | Accès des exemplaires déjà autorisés et prêts maintenus jusqu'à révision |

Un titre seul suffit à proposer (ancien formulaire ou ajout rapide). Le type `unknown` est permis en attente. L'approbation exige un type connu : `standalone`, `expansion` (une base validée obligatoire), `standalone_expansion` (jouable seule). Auto-références/cycles sont refusés. Les autres métadonnées restent optionnelles.

Les titres alternatifs utilisent les clés normalisées de #25. Suggestions utilisateur : fiches **validées** uniquement, sans propriétaires ni propositions tierces. Les écritures de création/édition/validation passent par les services et le verrou transactionnel commun. La case « autre édition » est supprimée : une édition commerciale ne suffit pas à créer une fiche distincte. Un homonyme peut être proposé avec une explication privée ; l'opérateur doit ensuite fournir sa propre justification pour approuver malgré une correspondance titre/alias.

Les exemplaires d’une proposition peuvent rester privés ou être partagés/prêtés immédiatement (P1). Aucune communauté n’est ajoutée lors de l’approbation ; les partages explicites existants sont conservés. Notes, UUID et propriétaires des exemplaires ne changent pas. Un créateur ne modifie plus directement une fiche approuvée : signalement, puis correction par la console opérateur. « Mes propositions » permet de suivre les décisions.

Les deux anciennes commandes CSV et leurs fonctions Python refusent l'import, y compris en simulation, avant lecture de fichier ou écriture. Les validations de format/Commons utiles et les commandes demeurent identifiables ; leurs anciens corps d'ingestion ont été retirés. Aucun catalogue réel n'est versionné. Les données déjà présentes, licences et illustrations #25 restent intactes.

> Une [interface web de revue restreinte](catalogue-admin.md) complète désormais
> cette console ; les descriptions et preuves historiques ci-dessous restent valables.

## Console opérateur

La console existante exige accès OS de confiance **et** compte plateforme actif, vérifié et superutilisateur ; un administrateur de communauté n'obtient aucun droit de modération global. Le compte fictif `create_dev_operator` reste réservé au développement, sans mot de passe utilisable. Aucun compte opérateur créé automatiquement par migration/démarrage.

Commandes sur une pile **locale de validation**, avec un opérateur fictif créé explicitement :

```sh
docker compose exec web python manage.py create_dev_operator --email operateur@example.test
docker compose exec web python manage.py ops catalogue-inventory --operator operateur@example.test
docker compose exec web python manage.py ops catalogue-review --operator operateur@example.test
docker compose exec web python manage.py ops catalogue-review --operator operateur@example.test --game-id UUID
```

L'inventaire retourne agrégats (statuts, types inconnus, homonymes, prêts par état, alias/images/IDs) et schéma des FK vers Game/OwnedGame ; aucun titre, note, nom ou e-mail dans cet inventaire. La file de revue affiche les métadonnées des propositions, leur explication et les fiches similaires, jamais une liste de possessions privées.

Pour approuver/corriger, fournir un fichier JSON **hors Git** contenant uniquement les métadonnées autorisées. Exemple synthétique :

```json
{"kind":"standalone","aliases":["Titre alternatif synthétique"],"external_ids":[{"source":"synthetic","identifier":"demo-1"}]}
```

Pour une extension dépendante : `kind="expansion"`, `base_game_id="UUID_DE_LA_BASE_VALIDEE"`. Une liste d'alias/IDs est **ajoutée**, jamais utilisée pour supprimer les références existantes. Le statut, le propriétaire, `hidden` et les images ne sont pas modifiables par ce fichier.

```sh
docker compose exec web python manage.py ops approve-game --operator operateur@example.test --game-id UUID --metadata-file /chemin/prive/metadata.json --reason 'Revue du jeu et des doublons'
# En cas d'homonymie réelle, ajouter --homonym-reason 'Justification distincte des editions'
docker compose exec web python manage.py ops request-game-changes --operator operateur@example.test --game-id UUID --reason 'Precision du titre necessaire'
docker compose exec web python manage.py ops reject-game --operator operateur@example.test --game-id UUID --reason 'Proposition a corriger'
docker compose exec web python manage.py ops correct-game --operator operateur@example.test --game-id UUID --metadata-file /chemin/prive/metadata.json --reason 'Correction verifiee'
```

Le fichier doit être accessible dans le processus Django ; pour un fichier de l'hôte, utiliser `docker compose exec -T ... --metadata-file /dev/stdin < work/metadata.json`. Chaque décision conserve acteur, motif, statut et justification d'homonymie. Une approbation ne démasque jamais une fiche. Pour retirer une fiche déjà approuvée/héritée, conserver `ops hide-game` : retrait des copies du prêt, clôture des demandes inéligibles et conservation des prêts actifs, comme auparavant.

## Fusion logique

```sh
# Simulation par défaut : aucune écriture, même d'audit.
docker compose exec web python manage.py ops merge-games --operator operateur@example.test --game-id UUID_SOURCE --target-game-id UUID_CIBLE --reason 'Meme jeu verifie' --dry-run
# Source/cible explicites et application distincte après lecture du bilan.
docker compose exec web python manage.py ops merge-games --operator operateur@example.test --game-id UUID_SOURCE --target-game-id UUID_CIBLE --reason 'Meme jeu verifie' --apply
```

La cible doit être une fiche canonique approuvée. Des masquages différents ou un cycle de bases interdisent la fusion. La transaction prend le même verrou que les ajouts, décisions et prêts ; toute erreur annule l'ensemble, audit compris.

- `Game` source conservé, `merged_into` vers cible ; anciennes sources déjà fusionnées aplaties vers la nouvelle cible. Ancienne URL : autorisation sur la source **avant** redirection vers une cible elle-même autorisée. Une proposition privée ne devient pas une URL consultable par un tiers.
- `OwnedGame.game` change, mais ni UUID d'exemplaire, propriétaire, notes, visibilité, retrait/archivage, ni `Loan.owned_game`/participants/état ne changent. Les copies physiques ne sont jamais fusionnées ; les prêts restent clôturables.
- Alias non conflictuels déplacés et titre source ajouté à la cible. Si une même clé d'alias existe déjà sur la cible, la ligne source reste conservée, et le même titre reste recherchable sur la cible ; aucun alias supprimé.
- IDs multiples dans `GameExternalIdentifier`, paire source/identifiant unique. Anciennes colonnes de provenance/IDs conservées sur la source ; les références normalisées rejoignent la cible.
- Signalements déplacés avec `original_game` immuable. L'unicité d'un signalement ouvert par auteur porte sur cette origine : deux dossiers du même auteur issus des deux fiches gardent leurs IDs, motifs et états, sans clôture artificielle.
- Illustration source déplacée si la cible n'en a pas ; si les deux en ont une, les deux lignes/licences/crédits restent présentes, la page canonique montre aussi l'illustration conservée de la source. Le contrôle Commons et la CSP ne sont pas élargis.
- Historique `GameMerge` avec source/cible, acteur, motif et UUID/IDs des références déplacées ; journal opérateur conservé. `ever_reused` est conservé/propagé ; aucune remise en visibilité implicite.

## Migration, inventaire et retour

`0001` et `0002_wikidata_catalogue` sont inchangées. `0003` ajoute statuts/types/bases/fusion, journal de décisions/fusions et identifiants multiples ; renseigne `original_game` pour chaque signalement et classe **toutes** les fiches préexistantes en `legacy_to_review`, sans type ni validation inventés. La base neuve reste vide ; aucun compte technique ni jeu créé par migration.

Les paires externes existantes et références BGG informatives sont recopiées dans la table dédiée si non conflictuelles et compatibles avec la borne de 120 caractères par identifiant. En cas de référence trop longue ou de correspondance croisée déjà attribuée, aucune réaffectation arbitraire : les anciennes colonnes (dont `bgg_ids`) restent intégralement conservées pour révision opérateur. Les champs historiques ne sont pas retirés. Les règles FK nouvelles sont `PROTECT` ; pas de suppression en cascade de la fiche source lors d'une fusion.

Avant migration réelle : arrêt/maîtrise des écritures, inventaire et comparaison du nombre/UUID des fiches, exemplaires, partages et prêts par état ; sauvegarde restaurable de la base précédente et version d'image identifiée. **Aucune opération réelle ni de production effectuée par cette PR.** Exemple de sauvegarde et essai isolé à adapter/revoir par l'exploitant :

```sh
# Le chemin de sauvegarde est privé, hors du dépôt et des logs.
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /chemin/prive/avant-catalogue-b.dump
# Restaurer uniquement dans une nouvelle base de validation dédiée, jamais par-dessus l'existante.
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" muqola_restore_test'
docker compose exec -T db sh -c 'pg_restore --no-owner --no-acl -U "$POSTGRES_USER" -d muqola_restore_test' < /chemin/prive/avant-catalogue-b.dump
# Revue du plan sur cette copie synthétique/restaurée configurée séparément :
uv run --frozen python manage.py migrate --plan
uv run --frozen python manage.py makemigrations --check --dry-run
```

La migration est **volontairement irréversible** par `migrate` : un retour arrière de schéma ne doit pas enlever colonnes, journaux ou références écrites depuis B. Un échec pendant sa transaction PostgreSQL annule la migration ; on peut corriger puis reprendre. Après succès, privilégier un correctif forward compatible. L'ancienne application n'est pas un rollback sûr (écritures omettant de nouveaux champs et risque d'exposer les propositions privées) : ne pas la redémarrer sur la base B. Un retour vers une sauvegarde précédente exige arrêt des écritures, autorisation explicite et analyse de toute donnée postérieure ; aucune suppression/restauration automatique.

## Vérification

Tests de migration dans des schémas **synthétiques isolés** depuis `0001` et `0002`, conservation des champs/UUID/FK et de tous les états de prêts, absence de seed et refus d'un reverse destructeur. Tests de propositions/permissions/contraintes, alias/homonymes, fusions avec conflits et rollback, courses PostgreSQL de propositions/approbations et fusion face à correction/approbation/ajout/prêt.

Les parcours navigateur locaux/CI créent des propositions par les vrais formulaires, vérifient leur confidentialité puis les approuvent par la console opérateur avant partage et prêt. La fixture Commons est exclusivement synthétique, sans import CSV ni téléchargement externe ; le test intercepte l'image. Aucun téléphone physique ni donnée réelle utilisés. Résultats exacts : bilan de PR et cases B de TASKS ; les tâches A/C restent ouvertes.


### Résultats locaux

- `./scripts/check.sh` sur PostgreSQL 17 isolé : Ruff lint/format, mypy (95 sources), contrôles Django, absence de migration manquante, migrations, statiques et suite pytest complète exécutée en série sans avertissement, complétée par le contrôle des libellés et droits du formulaire de base. Nombre final de tests et résultat CI consignés dans la PR.
- `check --deploy --fail-level WARNING` : succès (les deux avertissements volontairement neutralisés du socle sont conservés). Audit des dépendances runtime : aucune vulnérabilité connue détectée.
- Build Docker et pile locale avec migration/worker/Mailpit : succès. Le certificat public du proxy Cloud a été fourni par le secret BuildKit `proxy_ca` déjà prévu au Dockerfile, sans le conserver dans l'image ; aucune désactivation TLS.
- Parcours produit avec modération réelle, prêts et retrait de membre ; ajout avec/sans JS à 360/768/1280 px ; responsive/clavier/tactile, filtres, contenus longs et sans JS à 360/390/768/1200/1280 px : succès. Inspection visuelle du rendu 360 px effectuée.
- Des fixtures synthétiques remplacent les imports dans la CI. Les données préexistantes et les migrations #25 restent préservées. Les anciens scénarios d'import ne sont plus des fonctionnalités à livrer ; les tests attestent leur refus sans lecture ni écriture.
- Aucun critère fonctionnel B volontairement reporté. Limites : pas de données de production, pas de téléphone physique, pas de restauration sur une instance réelle ; migration de schéma irréversible et ancien binaire non utilisable comme rollback sûr, conformément à la stratégie décrite ci-dessus. Aucun déploiement ni merge automatique.


Le bilan B ci-dessus reste historique. Après fusion de #29, la PR A ajoute la
[recherche intelligente](recherche-intelligente.md), sans changer les règles B
ni les migrations 0001–0003. C reste hors de ce lot.
