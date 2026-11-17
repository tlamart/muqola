# Lot 6 — Préparation à la validation sur infrastructure réelle

## PR 4 — CD manuel, plan contrôlé et reprise

Branche `feat/cd-manuel`, base main `98a5a61` après fusion #35. La première
publication GHCR est réussie : [run 44125680324](https://github.com/tlamart/muqola/actions/runs/44125680324),
image `ghcr.io/tlamart/muqola@sha256:a3ee7c80c8c7a51983eb4f71ca9447b56883748182fbdbcd53da44999c4468df`.
Aucun SSH, déploiement ou changement de droits VPS effectué pour ce lot.
Validation locale : **552 tests**, lint/typage/Django/migrations/statiques, contrôle
production, audit runtime et actionlint réussis ; build et scénario staging/CD
avec identifiants d’images distincts réussis. La CI exacte est consignée dans la PR.

### Contrat du workflow

`Manual Muqola delivery` ne possède que `workflow_dispatch`, exécutable sur main
du dépôt attendu. Choisir staging/production, plan/apply, deploy/rollback, digest
GHCR, run et tentative de publication. Concurrence par environnement sans annulation, verrou par environnement et
verrou hôte commun sérialisant les opérations lourdes staging/production. Permissions limitées à contents/actions/packages **read** ; aucun
build, publication, modification du Caddy commun, restore ou suppression de volume.

Le code de contrôle provient du checkout de confiance du workflow sur main. La
provenance GitHub/GHCR est revérifiée avec l'outil V9 à **chaque** plan/application.
Seuls les huit fichiers de `deploy.release.ASSETS` sont lus au commit de l'image
validée et transférés : trois Compose, migrate.sh et quatre scripts SQL/PG existants.
Jamais de .env, clé, dump, catalogue ou document légal dans ce transfert. Leurs
empreintes sont vérifiées sur l'hôte avant utilisation.

SSH utilise VPS_HOST/VPS_USER/SSH_KNOWN_HOSTS des variables de l'environnement et
VPS_SSH_KEY de ses Secrets. Pas de root, ssh-keyscan, désactivation de vérification,
agent forwarding ou commande utilisateur arbitraire. Clé temporaire 0600, known_hosts
fourni/vérifié hors bande ; hôte inconnu ou clé changée bloque la connexion.
Le secret est absent d'argv. Une rupture SSH échoue sans reprise automatique.

Un GITHUB_TOKEN éphémère de lecture est transmis par stdin sur le canal SSH vérifié
pour le pull GHCR privé. Il n'apparaît ni dans les plans, ni dans les arguments/logs.
Le contrôleur épingle le démon Unix vérifié, puis stocke sa configuration Docker
dans un répertoire temporaire privé,
nettoyé en sortie normale ; le jeton expire avec le job en cas d'interruption.
Aucun PAT permanent ou secret SMTP n'est transféré par le workflow.

### Installation préalable par l'exploitant, après revue uniquement

La première image utilisable par le CD devra être publiée **après fusion de ce
lot**, car les images précédentes n'incluent pas `release_snapshot`. La publication
GHCR de #35 reste une preuve du registre, pas un candidat compatible avec ce protocole.

Installer une version revue du contrôleur dans `/opt/muqola-controller/deploy` :
release.py, common.py, check_config.py, image_provenance.py, probe.py, staging.py,
staging_config.py. Garder ce code hors écriture du compte de livraison ordinaire
et ne pas le remplacer depuis le bundle applicatif. Python 3 de Debian 13 et Docker
Compose récent suffisent sur l'hôte ; ni Django, uv, GitHub CLI ni build VPS requis.
Protocole initial 1 ; mettre à jour client/contrôleur ensemble si ce contrat change.

Copier les exemples privés hors dépôt : production `/etc/muqola/release.json`,
staging `/etc/muqola/staging/release.json`, fichiers 0600 appartenant au compte
opérateur. Les statuts backup/restore doivent être lisibles en 0600 par ce même
compte : adapter le User des unités de sauvegarde à la politique opérateur revue
plutôt que rendre leurs fichiers publics pour contourner un refus. Répertoires `/var/lib/muqola/production/cd` et `/var/lib/muqola/staging/cd`
0700. Préparer aussi `/var/lib/muqola/cd.lock`, accessible en écriture aux seuls
comptes de livraison autorisés (même compte, ou groupe dédié si comptes distincts).
Les cibles ne peuvent pas être remplacées par un chemin libre dans le workflow.
Renseigner compose_env, data_path et preuves de chaque environnement. Conserver
`capacity_reviewed=false` avant revue de capacité réelle ; staging exige aussi
synthetic_data_only, accès privé, SMTP capturé et référence production. Production
exige la référence staging pour vérifier les collisions de secrets/volumes/réseaux.
Les références monitor JSON privées doivent cibler les projets et Compose corrects.

Inventorier les volumes/projets existants avant toute installation : le contrôleur
refuse un nom de volume inattendu et ne réinitialise aucune base. DB et capture
staging doivent être initialisées/démarrées dans un créneau distinct autorisé.
**Bootstrap neuf :** inventaire, plan de migrations existant puis initialisation
manuelle revue avec sauvegarde/retour adaptés ; le CD refuse d'appliquer le bootstrap.
Le refus n'est contournable par aucun flag. Refaire un plan après initialisation.

Une application déjà active sans état CD exige une **adoption opérateur revue**.
Créer state.json privé avec current contenant image par digest, commit, publication
V9 validée, compose_file du modèle existant et schema fourni par release_snapshot
dans le contexte migration. Comparer à l'image réellement exécutée ; ne pas fabriquer
un état précédent. Si aucune application n'est active, le premier succès enregistre
current sans précédent ; aucun rollback vers une version inexistante n'est proposé.
Conserver les anciens fichiers/env/volumes et l'inventaire d'adoption hors Git.

Les environnements GitHub sont déclarés déjà créés avec les variables et la clé.
Vérifier restriction à main, droits de déclenchement et reviewer production si
l'offre GitHub le permet, sans auto-approbation. Le compte VPS doit pouvoir lire
sa configuration et utiliser **le même démon Docker que le Caddy commun**. Ce flux
n'utilise pas sudo. Pour son exécution future, un compte dédié avec accès Docker
peut être nécessaire : cet accès peut équivaloir à root et doit être approuvé par
l'exploitant. Ne pas ajouter sudo général, ni changer les droits pendant ces tests.
Un helper root restreint serait une adaptation distincte avant activation si préféré.

### Sauvegarde et exercice de restauration obligatoires

Réutiliser `deploy.backup` et `deploy.restore` de #32 ; aucune seconde filière.
Le contrôleur exige un statut de sauvegarde privé ok, objet renseigné et succès
dans les dernières **24 h** (horodatage futur refusé). Le fichier de restauration
est un compte rendu opérateur 0600 d'un exercice **réel**, isolé et revu, daté de
moins de 30 jours, avec :

```json
{
  "project": "muqola-prod",
  "success": true,
  "isolated": true,
  "reviewed_by": "REMPLACER_APRES_REVUE_REELLE",
  "exercise_id": "REFERENCE_DU_RAPPORT_ET_DES_COMPARAISONS",
  "completed_at": "HORODATAGE_UTC_ISO_APRES_EXERCICE"
}
```

Adapter le projet en staging. Ne pas transformer un essai Cloud ou un simple accès
au stockage en preuve de restauration VPS. Archiver comparaison, objet sauvegardé,
base isolée, RPO/RTO et compte rendu associés à exercise_id. Ce document est une
attestation de l'opérateur de confiance, pas un contrôle indépendant du stockage.
Sans preuve complète, aucune application autorisée ; aucun restore automatique.

### Plan puis application

1. Déclencher **plan** pour le digest publié et son run/tentative. Le contrôleur
   vérifie sauvegarde/restauration, isolation et capacité, pull sans build puis
   inventaire en lecture seule sous rôle migration. Les droits runtime restent
   séparés. Plan expirant après **une heure**, lié au schéma, migrations/fichiers,
   image/provenance, configuration/secrets (empreintes seulement), images réellement
   actives et état précédent. Une image active absente du journal bloque le plan
   jusqu’à une adoption opérateur revue.
   Un nonce unique donne à chaque nouvelle revue son propre hash, même si le
   diagnostic est identique ; les anciennes tentatives consommées restent conservées.
2. Télécharger `muqola-plan-staging-<tentative>` ou `muqola-plan-production-<tentative>` du run réussi.
   Lire plan.json : image, état précédent, opérations de migration et hash.
   Le plan ne contient ni compte utilisateur ni valeurs de secrets. Aucun service
   n'est arrêté et aucune migration n'est appliquée à cette étape.
3. Après revue humaine, déclencher **apply** avec le même digest/publication,
   le run du plan et son hash exact. La source est vérifiée par l'API GitHub :
   workflow manuel sur main réussi, artefact non expiré, environnement/image/kind
   concordants. L'hôte compare son exemplaire du plan au nouveau diagnostic sous
   verrou ; backup/config/schéma/state modifiés ou plan expiré => refaire un plan.
   Si reviewers d'environnement indisponibles, la saisie manuelle du run et hash
   après lecture est la validation explicite liée au plan ; limiter qui déclenche.
4. Marquage durable du plan consommé **avant** arrêt web/worker. Schéma revérifié
   après arrêt ; migrations au plus une fois via migrate.sh puis grants existants.
   `release_snapshot` et politique d'empreintes historiques revues bloquent toute
   migration inconnue/modifiée. Une nouvelle migration exige une PR avec analyse,
   tests et ajout conscient à migration_policy, jamais un flag force générique.
5. Contrôle readiness production/staging (18+, légal, rôles, SMTP), up sans build avec `--no-deps` (DB/capture non recréées),
   santé web/worker et HTTPS avec certificat vérifié ; accès privé staging contrôlé
   avant mutation et après démarrage. Succès : historique, previous/current et
   lien actif mis à jour. Les autres sites Caddy et l'autre environnement ne sont
   pas manipulés. Les volumes et tous les exemplaires/prêts sont conservés.

Pour monitoring/backup actifs, configurer compose_file vers
`/var/lib/muqola/<environment>/cd/active/compose.json` après adoption/premier succès,
avec compose_env et projet explicites. Le JSON résolu reste privé sur VPS (0600),
pas dans les artefacts ; il contient les chemins et paramètres propres à l'hôte.
Ne pas utiliser ce lien avant qu'il existe ; garder la configuration précédente.

### Incident et rollback

Un échec arrête le flux et conserve current/previous ; les services peuvent rester
arrêtés ou la candidate rester démarrée selon la phase. Examiner state.json privé,
les healthchecks et logs expurgés. Pas de restauration ou retour de schéma implicite.
Interruption pendant migration => résultat unknown enregistré avant son lancement ;
si des migrations restent en attente, reprise bloquée jusqu'à réparation/revue
manuelle. Si le schéma est propre et sans migration en attente, produire un nouveau
plan pour poursuivre ; ne jamais réutiliser un hash consommé ni relancer aveuglément.

Rollback : nouveau **plan**, kind=rollback, puis nouvel apply après revue. Après
un succès, choisir le digest/publication de previous ; après un échec ou une
interruption, choisir current, la dernière version réussie conservée au journal. Le schéma actuel doit être **identique** au fingerprint
conservé de cette version et aucune migration ne doit être en attente. C'est une
condition conservatrice : une modification de schéma, même additive, bloque le
rollback automatique d'image. Décider alors séparément une correction en avant
ou une intervention DB avec sauvegarde/arrêt des écritures/autorisation explicite.
Le workflow n'offre aucune rétro-migration ni restauration automatisée.
Le rollback automatique vise uniquement les images capables d'exécuter le
protocole CD : une version antérieure sans release_snapshot exige une procédure
opérateur distincte revue ; le contrôleur ne fabrique pas de compatibilité.

### Vérifications et limites

Tests PostgreSQL de snapshot/politique, Compose réellement rendu et collisions,
refus backup/restauration/périmètre, plans périmés/modifiés, schéma changé, échec
migration/readiness/health, double application, concurrence et rollback incompatible.
Transport SSH simulé, validation d'hôte inconnu et invariants du workflow testés.
Le harness du staging exerce apply avec **vrais cycles de services**, inventaires
SQL, readiness et HTTPS loopback, journal/reprise/rollback entre deux identifiants d’image distincts (même code,
configuration de test dérivée localement et jamais publiée), et production témoin
sondée en continu et inchangée ; admission/provenance y sont des adaptateurs de test. Aucun
flag de bypass n'est livré au contrôleur. Aucune migration n'est en attente dans
cette fixture : l'exécution unique et l'échec de migration sont couverts en tests
unitaires, les migrations historiques/restaurations par les smokes existants.
La capacité réelle, le SSH du VPS, les autorisations GitHub, les sauvegardes et la
première livraison réelle restent à valider séparément. Aucun déploiement de ce lot.

---

## PR 3 — Image testée et publication GHCR

Base : main `3ac1ac3`, après fusion de #34 ; branche `feat/ghcr-publication`.
Couvre V8–V9 ; aucun SSH, déploiement, changement Caddy ou droits du compte VPS.
La première publication GHCR sera déclenchée uniquement après fusion humaine,
par les contrôles du nouveau commit de main. Aucun push registre réel en développement.

### Construire une fois, tester, puis publier

Le job `checks` conserve tous les contrôles existants, sur PR et push main.
Il construit **une seule image linux/amd64**, avec le Dockerfile durci inchangé,
les labels OCI source/révision, puis démarre Compose avec `--no-build`.
Les tests production/staging, TLS/CSRF, rôles, sauvegarde/restauration, navigateurs
et Codespaces utilisent cette image. Aucun secret applicatif n'entre dans le build.

Après succès de tous les contrôles et du nettoyage, `scripts.image_candidate export`
vérifie l'ID Docker, l'UID non root, la plateforme et les labels. Il conserve
l'image par `docker image save` et gzip, avec SHA-256 de l'archive, digest canonique
de configuration OCI extrait des octets sauvegardés et métadonnées
commit/run/tentative dans un artefact immuable de ce run (rétention **3 jours**).
Le job suivant télécharge l'**ID d'artefact** produit par `checks`, jamais un nom
provenant d'une autre branche, d'un autre run ou d'un cache.

Le job `publish` ne s'exécute que pour `push` sur `refs/heads/main` de
`tlamart/muqola`, après `checks=success`. Aucune publication depuis PR, fork,
workflow_dispatch ou pull_request_target. Les permissions globales restent
`contents:read` ; **seul publish** obtient `packages:write`, sans SSH ni droits
sur les environnements staging/production. Le script vérifie aussi ce contexte
avant toute mutation Docker. L'authentification utilise le GITHUB_TOKEN éphémère,
stdin, un DOCKER_CONFIG isolé du runner et un logout final ; aucun PAT de push requis.

Le publisher vérifie archive, ID source attendu, digest de configuration transmis
par checks et contexte. Après chargement il réexporte la configuration pour
vérifier ses octets, contrôle labels/UID/architecture puis publie sans reconstruction
avec `docker image push --platform linux/amd64` (manifeste de cette plateforme) :

- `ghcr.io/tlamart/muqola:<SHA complet>` ;
- `ghcr.io/tlamart/muqola:<SHA complet>-<run>-<tentative>`, pour conserver une
  référence par publication même après une réexécution du même commit.

Aucun tag latest/main. Un tag reste mutable : une réexécution peut modifier le
raccourci SHA. **Seul `ghcr.io/tlamart/muqola@sha256:<64 hex>` est déployable**.
Le manifeste est relu depuis le registre par digest ; son digest de configuration
OCI doit correspondre exactement à la configuration sauvegardée/testée. L'image n'est pas
reconstruite pour la promotion staging → production. Avant usage sur VPS, vérifier
son architecture réelle (`uname -m` doit correspondre à amd64/x86_64) ; aucun
support multiarchitecture non testé n'est prétendu.

### Preuve de publication et vérification avant promotion

Après push et relecture, le publisher conserve `publication.json` dans
`muqola-publication-<SHA>-<tentative>` pendant **90 jours**, et résume digest,
commit et run dans GitHub Actions. La preuve inclut ID d'image, hash de l'archive,
plateforme, digest canonique de configuration et ID d'artefact candidat. Un push partiel ou un workflow ensuite
échoué/annulé ne produit aucune image admissible, même si un tag existe au registre.

Le contrôle en lecture seule `deploy.image_provenance` exige :

1. Référence exacte du dépôt GHCR par digest ; pas de tag, autre dépôt ou argument shell.
2. API GitHub authentifiée : run terminé avec succès, push/main, dépôt et dépôt
   source attendus, workflow CI exact, SHA et tentative courante concordants.
3. Jobs `checks` **et** `publish` terminés avec succès pour ce même commit/run.
4. Preuve unique, non expirée, issue de ce run/tentative ; ZIP borné lu en mémoire,
   fichier publication.json seulement, aucun fichier extrait sur disque.
5. Concordance de toutes les métadonnées ; manifeste disponible dans GHCR et
   digest de configuration identique aux octets de la configuration testée.

Un fichier local, un label OCI, un tag SHA ou le succès d'une ancienne CI de PR ne
suffisent jamais. Preuve expirée/absente, API inaccessible, permissions manquantes,
manifest absent ou réexécution non réussie : **refus**, sans option de contournement.
Une réexécution remplace la tentative courante : ne pas utiliser une preuve d'une
ancienne tentative. Pour reprendre une publication échouée/expirée, utiliser
**Re-run all jobs** : relancer seulement les jobs échoués conserve un candidat
d'une ancienne tentative, volontairement refusé. Le futur lot CD utilisera ce
contrôle avant toute livraison.

Exemple **après publication réelle**, sur runner CI ou poste opérateur équipé de
Python 3, GitHub CLI et Docker avec buildx ; aucun démarrage de conteneur :

```sh
# Remplacer par les valeurs du run main ayant publié l'image.
RELEASE_IMAGE='ghcr.io/tlamart/muqola@sha256:REMPLACER_64_HEX'
RELEASE_RUN_ID=REMPLACER_RUN
RELEASE_ATTEMPT=1
python3 -m deploy.image_provenance --image "$RELEASE_IMAGE" \
  --run-id "$RELEASE_RUN_ID" --attempt "$RELEASE_ATTEMPT" \
  --output work/evidence/validated-image.json
```

GitHub CLI utilise sa connexion privée ou GH_TOKEN hors argv/logs ; le contrôle
requiert lecture des métadonnées/artefacts Actions du dépôt. Docker/buildx utilise
ses accès registre en lecture. Aucun jeton de publication n'est transmis au VPS.
Le contrôle ne modifie pas Compose/env et ne déploie rien. Conserver run, preuve
et versions GHCR nécessaires au rollback ; pas de purge automatique. Au-delà de
la rétention, sans preuve distante disponible, nouvelle publication validée requise.

### Configuration GitHub et interventions restantes

Conserver la visibilité privée par défaut d'un nouveau package ; ce lot ne
rend aucun package public. L'exploitant vérifiera après fusion les droits Actions
et l'association du package au dépôt (label OCI source), le succès du job publish,
le digest et la preuve. Si un package existe déjà, accorder à ce dépôt les droits
d'écriture nécessaires plutôt que d'ajouter un PAT large au workflow. Si le quota
Actions/Packages est atteint, publication bloquée : aucun achat automatique.
Un accès privé en lecture pour le futur VPS sera à définir au lot CD ; décider
séparément d'une visibilité publique éventuelle. Ne jamais transmettre les clés ici.

**Déclaré par l'exploitant le 17 novembre :** environnements GitHub `staging` et
`production` déjà créés, chacun avec variables `SSH_KNOWN_HOSTS`, `VPS_HOST`,
`VPS_USER` et secret `VPS_SSH_KEY`. Le futur CD utilisera les variables par `vars`
et la clé par `secrets`. Valeurs non consultées, aucune clé utilisée par ce lot.
Les restrictions à main, approbations production si disponibles et empreintes SSH
vérifiées hors bande restent à contrôler au lot 4.

`VPS_USER` n'a actuellement ni sudo ni accès Docker : **aucun ajout nécessaire
pour GHCR**, garder ces droits en l'état. Le lot CD précisera le mécanisme de
commandes autorisées sur le VPS avant tout besoin de modification ; ne pas accorder
sudo général par anticipation. L'accès libre au socket Docker équivaut à des
privilèges administrateur ; il ne constitue pas une restriction de clé SSH.

### Preuves synthétiques et limites

Tests de la politique du workflow et des refus PR/fork/échec, altération archive,
image/commit/run/tentative incorrects, preuves absentes/expirées/étrangères,
manifest/config incohérents ; promotion du même digest vérifiée sans distinction
de l'environnement cible. PyYAML ajouté **uniquement aux dépendances dev** pour
parser réellement le workflow ; aucune nouvelle dépendance runtime.

`python -m scripts.image_delivery_smoke` effectue réellement save/load/push et
relecture du manifeste sur un **registre loopback synthétique**, avec vérification
de l'identité conservée. Aucun GHCR réel ; son volume reste conservé/inventorié.
La CI conserve son JSON avec les captures. Les smokes production/staging et tous
les parcours existants restent dans le job checks. Résultats exacts dans TASKS/PR.
Validation locale du 17 novembre : **483 tests réussis**, lint/format/typage,
Django/migrations/statiques, check production, audit runtime sans vulnérabilité
connue, actionlint 1.7.12, chargement des outils sous Python 3.13.5, build et smokes
registre/production/staging réussis. Correctif de régression staging : lecture du
champ officiel Docker `CpuCfsQuota`, avec échec reproduit avant correction puis
test positif/négatif. Sans cela les quotas CPU étaient toujours réputés absents,
y compris sur une machine compatible. Le contrôleur et l'échantillonneur sont
corrigés ; le daemon local reste réellement sans cgroups. La CI de la PR consigne
le résultat du commit final ; ses métriques éventuelles ne valent pas mesure VPS.
La CI a également révélé que l'ID moteur Docker peut être un digest de manifeste
avec containerd. Le digest canonique est donc lu dans l'archive save, transmis
par sortie du job checks et revérifié après load puis au registre. Les changements
de handle entre moteurs sont acceptés uniquement avec la même configuration ;
Docker et OCI sont testés par relecture réelle sur registre loopback.
La première publication GHCR réelle et sa vérification distante restent à faire
après fusion ; aucune mesure de capacité VPS ni ouverture publique validée ici.

---

## PR 2 — Staging privé éphémère

Base : main `67df970`, après fusion de #33 ; branche `feat/staging-ephemere`.
Ce lot prépare V5–V7. Aucun accès SSH, déploiement, publication GHCR, création
de compte fournisseur ou changement de données réelles. GHCR/CD restent les PR 3–4.

### Isolation et garanties

Les services communs sont définis dans `compose.runtime.yaml`, puis étendus
par les deux profils complets : `compose.prod.yaml` et `compose.staging.yaml`.
Le fichier commun seul ne constitue pas un déploiement (ressources/secrets non
résolus). Les rôles, grants, scripts PostgreSQL, images applicatives et garanties
production de #32/#33 sont réutilisés ; le Compose local reste inchangé.

Le staging utilise **muqola-staging**, DB **muqola_staging**, volume
**muqola-staging_postgres_data**, alias **muqola-staging-web** ; seuls ses web
rejoignent également `proxy`. Son réseau privé est `internal: true` : worker,
DB et Mailpit n'ont aucune sortie vers un SMTP ou une base extérieure. Aucun
port n'est publié ; aucun nouveau média utilisateur ni copie de production.
Les profils sont explicites (`staging`, `staging-maintenance`) et les services
ne redémarrent pas automatiquement après reboot. Aucun script ne détruit de volume.

Les secrets stage sont quatre fichiers indépendants sous `/etc/muqola/staging/secrets`,
avec les permissions décrites au lot précédent. **Aucun secret SMTP/Brevo** n'est
monté. Les vérifications refusent collisions de projets, volumes, réseaux privés,
chemins de clés et documents légaux ; elles comparent aussi les empreintes des
valeurs des clés avec la configuration production privée de référence, sans les
journaliser. Préparer cette référence et ses fichiers hors dépôt avant l'admission.
Le staging n'interroge pas la base production pour ces contrôles.

Le contexte `DEPLOYMENT_ENV=staging` conserve `APP_ENV=production` et ses drapeaux
HTTPS/CSRF/cookies. Au chargement Django, toute DB autre que `muqola_staging` sur
`db`, tout SMTP autre que Mailpit:1025, credential SMTP ou backend différent est
refusé. Les formulaires et l'inscription serveur n'acceptent que `@example.test` ;
`staging_readiness` rejette également des comptes étrangers à ce domaine.
Une bannière identifie l'environnement et rappelle les données fictives/capture.
Cela ne prouve pas que du texte libre est fictif : l'exploitant ne doit jamais
copier/anonymiser un dump production pour le staging ni y saisir de données réelles.

La restriction 18+ et la porte légale restent actives. `LEGAL_REVIEWED=false`
laisse les inscriptions fermées, même derrière l'authentification du proxy.
Ne pas activer cet indicateur pour contourner une revue manquante. Les fichiers
fictifs marqués comme tels utilisés par les tests isolés ne constituent pas des
mentions validées pour l'exploitation. Le contrôle production conserve les
exigences SMTP réel/TLS et refuse le contexte staging ; aucune option de bypass.

### Accès privé et non-indexation

Importer `deploy/Caddyfile.staging` dans le Caddy commun, sans toucher aux autres
sites et en conservant le filtre global des erreurs de #33. Le domaine est littéral
`staging.muqola.tlam.art` ; l'authentification s'applique aussi à santé, inscription,
pages légales, erreurs et ressources. `X-Robots-Tag: noindex, nofollow, noarchive`
et `Cache-Control: no-store` sont présents ; l'application ajoute aussi noindex.
Noindex complète le contrôle d'accès, ce n'est pas une protection de confidentialité.
Le header Authorization de l'accès Caddy est supprimé avant transmission à Django.

Le fragment importe `/etc/caddy/private/muqola-staging-users` : une ou plusieurs
lignes **identifiant + hash bcrypt** générées par l'exploitant. Exemple de commande
interactive future (pas de mot de passe dans argv, Git, logs ou chat) :

```sh
cd /opt/caddy
docker compose exec -it caddy caddy hash-password
```

Placer le résultat dans le fichier privé appartenant au compte qui exécute Caddy,
permissions adaptées (par exemple root:root 0600 si Caddy tourne root), répertoire
0700 ; vérifier les UID/montages effectifs. Ne pas réutiliser un mot de passe de
production. Suivre la procédure validate/reload du lot 1, avec surveillance d'un
autre site. Ajouter `muqola-staging-web` aux exclusions NO_PROXY/no_proxy du Caddy
si un proxy HTTP sortant y est configuré, en conservant les exclusions existantes.

La sonde privée lit un JSON 0600 hors dépôt, par exemple
`/etc/muqola/staging/probe.json`, contenant `username` et `password` : mêmes accès
staging que ceux autorisés par Caddy, jamais credentials SMTP ; mot de passe
distinct d'au moins 16 caractères. Le helper TLS
vérifie le certificat, ignore les proxys d'environnement et refuse **toutes** les
redirections pour ne pas transférer Authorization à une autre destination.
Il exige d'abord **401 + noindex sans identifiants**, puis 200 avec les accès
privés. Un accès devenu public est donc détecté même si la requête authentifiée
réussit ; aucun credential n'est envoyé dans ce cas.
Aucun credential dans l'URL ou la ligne de commande. Adapter
`deploy/monitor.staging.example.json`, conserver ses états et sauvegardes dans
`/var/lib/muqola/staging` et surveiller le staging uniquement lorsqu'il est actif ;
ne pas activer son timer permanent sans gérer explicitement les périodes d'arrêt.

### Installation préparatoire et migrations, par l'exploitant uniquement

Prévoir Docker Compose **2.24.4 ou supérieur** (extends et !override), le réseau
Caddy existant, les DNS staging, les répertoires/permissions et les quatre secrets
indépendants. Copier `.env.staging.example` hors Git sous
`/etc/muqola/staging/staging.env` (0600), renseigner IP Caddy stable, **même digest
GHCR que le candidat à tester**, et documents légaux stage indépendants.
Les sources runtime/profils doivent correspondre à la version de l'image.
Aucune construction sur le VPS ; la publication automatisée sera préparée en PR 3.

Copier `deploy/staging.example.json` vers `/etc/muqola/staging/operator.json` (0600).
Renseigner `production_config`, référence privée de production avec project/env/
fichier Compose et secrets, ainsi que le fichier de sonde et le chemin réel des
données Docker (`docker info --format '{{.DockerRootDir}}'`). Le fichier d'état doit
être `state.json` dans un répertoire staging ; les chemins de production sont refusés.
`synthetic_data_only` et `capacity_reviewed` sont volontairement **false** dans
l'exemple : les passer à true seulement après revue effective et mesures autorisées.

Depuis `/opt/muqola`, commandes futures après autorisation distincte :

```sh
python3 -m deploy.check_config --config /etc/muqola/staging/operator.json
python3 -m deploy.staging check --config /etc/muqola/staging/operator.json
python3 -m deploy.staging status --config /etc/muqola/staging/operator.json
```

L'admission valide le rendu des deux profils, leur isolation, les valeurs des
secrets, la confirmation données fictives, la revue et les mesures de capacité.
Le start vérifie aussi le refus HTTPS anonyme avant de démarrer un service.
Il peut initialiser uniquement l'infrastructure staging (DB et Mailpit) après
ces contrôles, puis **refuse les migrations en attente** et n'ouvre pas web/worker.
Il ne les applique jamais automatiquement. Pour une base staging neuve, après
admission réussie et dans un créneau explicitement autorisé, examiner le plan :

```sh
docker compose --project-name muqola-staging --env-file /etc/muqola/staging/staging.env -f compose.staging.yaml --profile staging up -d --no-build --wait db mailpit
docker compose --project-name muqola-staging --env-file /etc/muqola/staging/staging.env -f compose.staging.yaml --profile staging run --rm migrate python manage.py migrate --plan
# Uniquement après revue et autorisation des migrations additives du staging :
docker compose --project-name muqola-staging --env-file /etc/muqola/staging/staging.env -f compose.staging.yaml --profile staging run --rm migrate
```

Ne pas exécuter de migration destructive, restaurer un dump réel ou intervenir
en parallèle d'un start/stop. Pour une base stage existante à conserver, prévoir
une sauvegarde propre et un exercice de restauration isolé avant évolution.
`deploy/backup.staging.example.json` réutilise les outils age/rclone existants avec
répertoire, préfixe, destinataire et état séparés ; aucune configuration distante
n'est créée par ce lot. La preuve d'un test synthétique n'est pas un exercice de
récupération du VPS après sinistre.

### Démarrage, arrêt et capacité

```sh
python3 -m deploy.staging start --config /etc/muqola/staging/operator.json
python3 -m deploy.monitor --config /etc/muqola/staging/monitor.json
# Arrêt explicite du staging seulement ; pas de down --volumes :
python3 -m deploy.staging stop --config /etc/muqola/staging/operator.json
```

Start vérifie les migrations déjà appliquées puis `staging_readiness` (notamment
les droits runtime, adultes, comptes fictifs et documents légaux), démarre web/
worker sans build et exige un smoke HTTPS authentifié. Un échec est enregistré ;
il n'y a ni rollback de schéma ni restauration automatique. DB/Mailpit ou des
services déjà démarrés peuvent rester actifs après un échec : diagnostiquer puis
stopper explicitement le staging. Un verrou interdit deux opérations concurrentes
via l'outil. Stop reste utilisable sans nouvelle revue de capacité et ne touche
que web/worker/Mailpit/DB du projet staging. Les volumes et données fictives
persistent après stop ; Mailpit est une capture éphémère, pas un stockage durable.
Le prochain start est volontaire et repasse ses contrôles.

Budgets préparés : web **256 Mio** (1 worker/2 threads), worker **128 Mio**, DB
**384 Mio** (64 Mio shared_buffers/20 connexions), Mailpit **64 Mio** : **832 Mio**
en exécution. Migration **384 Mio**, marge d'admission **512 Mio** par défaut :
start exige au moins **1 728 Mio de MemAvailable**, espace libre ≥2 Gio et charge
moyenne par cœur ≤0,75. La marge ne peut pas être réduite sous 256 Mio. Le rapport
check affiche les mesures présentes et les raisons de refus, sans secrets.
Il exige Docker local et le support effectif des limites mémoire/CPU : un daemon
sans cgroups est refusé, même si les plafonds apparaissent dans le Compose.
Ce sont des plafonds/contrôles prudents, **pas une garantie de capacité** : la
revue humaine reste obligatoire pour les pics production, autres applications,
cache système et migrations, et la situation peut évoluer après le contrôle.
Sur le VPS réel, dans un créneau autorisé, mesurer avant/pendant/après une charge
fictive et une migration, avec `docker stats --no-stream`, `free -m`, `df -h`,
journaux OOM et disponibilité du site production. Faire la première mesure
contrôlée sans présumer que les deux piles tiennent ensemble. Tant que cette
preuve n'existe pas, conserver capacity_reviewed=false et staging arrêté.

### Preuves et limites de ce lot

La suite automatisée et `scripts/staging_smoke.py` utilisent deux piles
**synthétiques** et un seul Caddy local, CA interne et résolution HTTPS loopback
explicite, sans ACME ni SMTP externe. Elles vérifient accès privé/noindex,
conservation des portes légale/18+, outbox et capture, absence de connexion aux
réseaux privés étrangers, stop/restart sans perte et production témoin inchangée.
Le test échantillonne mémoire/CPU et écrit `work/staging-smoke.json` : maximum
**observé par échantillonnage**, pas mesure de pic absolu ni validation OVH.
Les métriques Docker sont marquées invalides si les cgroups ne sont pas actifs :
elles ne doivent jamais être assimilées à l'empreinte du staging. C'est le cas
du daemon rootless de cet environnement local ; la preuve de capacité OVH reste
non satisfaite et le démarrage contrôlé y est refusé. Les mesures du runner CI,
si son support cgroups est actif, restent elles aussi distinctes d'une mesure VPS.
Tous les volumes sont conservés avec inventaire dans work/. Validation locale
du 17 novembre : `scripts/check.sh` réussi (**415 tests**, lint/format/typage,
Django/migrations/statiques), contrôle Django production et audit runtime sans
vulnérabilité connue ; build Docker puis smokes production et staging réussis.
La CI ajoutée exécute aussi le smoke staging et conserve le rapport JSON.
Les résultats navigateur/CI et toute limite non satisfaite sont consignés dans
TASKS et la PR. Aucune validation OVH/DNS/ACME ni capacité VPS revendiquée.

---


## PR 1 — Caddy partagé et exploitation compatible

Accord d'implémentation reçu après l'audit ci-dessous. Branche
`feat/caddy-partage`, issue de main `ff9e0c2`. Cette PR couvre V1–V4 ; les PR
staging, publication GHCR et CD manuel restent des lots suivants, après intégration
de leurs prérequis. Aucun accès SSH ni déploiement effectué par l'agent.

### Configuration applicative livrée

`compose.prod.yaml` ne démarre plus Caddy et ne publie **aucun port**.
Seul web rejoint le réseau externe `proxy` (alias `muqola-web`) et le réseau
`private`. DB, worker et migration ne rejoignent que `private`, avec sortie
nécessaire vers le SMTP production ; ce réseau privé n'est pas un annuaire public.
Seules des applications administrées et fiables doivent rejoindre `proxy`.
La clé Django, les trois rôles PostgreSQL, la distribution de secrets, les
healthchecks et budgets de #32 sont conservés ; `compose.yaml` n'est pas modifié.
Le projet reste `muqola-prod`, donc le volume reste
`muqola-prod_postgres_data`. Ne jamais changer ce nom pour une mise à jour.
Les anciens volumes Caddy ne sont pas supprimés ; le Caddy commun existant
conserve ses propres données/certificats dans `/opt/caddy`.

Renseigner dans le fichier privé d'environnement : domaine `muqola.tlam.art`,
`MUQOLA_PROJECT=muqola-prod`, `PROXY_NETWORK=proxy`, image
`ghcr.io/tlamart/muqola@sha256:<64 hex>` et **IP exacte et stable du Caddy**
dans `TRUSTED_PROXY_IPS` (liste séparée par virgules si IPv4 et IPv6).
Aucun CIDR, joker ou nom DNS n'est accepté comme source de confiance.
Le modèle contient des marqueurs à remplacer, pas des identifiants utilisables.
La publication/provenance et disponibilité GHCR seront vérifiées par les PR 3–4 ;
cette PR fournit un contrôle local de la forme et de l'isolation :

```sh
# Configuration JSON privée contenant project, compose_env et compose_file :
python3 -m deploy.check_config --config /etc/muqola/monitor.json
```

Exit non nul si image mutable/autre dépôt, ports/build, réseaux inattendus,
service ajouté ou projet incohérent. Ce précontrôle ne lance aucun service,
ne prouve pas la provenance de l'image et n'autorise aucun déploiement.
Les commandes futures de production doivent passer par cette vérification,
la sauvegarde et la revue du plan décrites plus bas.

### Configuration Caddy commune : actions futures de l'exploitant

Confirmer la version réelle de Caddy et le nom de son service Compose. Le test
utilise Caddy 2.11.9 épinglé de #32 ; il ne met pas à jour le Caddy du VPS.
Ne pas remplacer le Caddyfile global ni installer une seconde instance.
Les deux fichiers fournis ont des rôles différents :

- `deploy/Caddyfile` est **uniquement un site à importer** : domaine cible,
  `reverse_proxy muqola-web:8000`, taille de corps 64 Ko, compression et en-têtes
  réécrits, dont `X-Real-IP`/`X-Forwarded-For` depuis `{remote_host}`. Le domaine
  est littéral : une variable globale APP_DOMAIN d'une autre application ne doit
  pas détourner ce site. Si le Caddy commun hérite d'un proxy HTTP sortant,
  ajouter `muqola-web` à ses NO_PROXY/no_proxy avant le routage interne ; ne pas
  remplacer les exclusions nécessaires aux autres applications.
- `deploy/caddy-global-options.example` contient le filtre JSON à fusionner
  dans le bloc global existant : supprimer les objets requête/URI/en-têtes
  lors des erreurs. Ne pas activer d'access log contenant les liens sensibles.
  Préserver les options et journaux des autres applications et vérifier leurs
  éventuels loggers spécifiques. Ne pas recopier l'ancien `admin off` :
  l'API de reload doit écouter **uniquement localhost dans le conteneur**,
  jamais une interface réseau publiée.

Après autorisation d'exploitation distincte, sur Debian 13, depuis `/opt/caddy`
(et en adaptant le nom du service si ce n'est pas `caddy`) :

```sh
# Lecture seule : vérifier réseau et montages avant de préparer les changements.
docker network inspect proxy
docker compose config --quiet
```

Si `proxy` n'existe pas, le créer une seule fois après revue de l'adressage,
puis connecter Caddy via **son** Compose existant. Si l'IP Caddy n'est pas stable,
préparer une réservation IPv4/IPv6 dans cet adressage, hors collisions ; aucune
adresse réelle n'est inventée par le dépôt. Renseigner la même adresse exacte
côté Django. Ne pas approuver tout le subnet : les autres applications partagent
le réseau. Un changement d'IP Caddy nécessite la mise à jour contrôlée de cette
configuration applicative.

Préparer une copie complète du Caddyfile conservant tous les sites, y importer
le fragment Muqola et fusionner le filtre global. L'import peut par exemple
viser `/etc/caddy/sites/muqola.caddy` si **le répertoire** correspondant est monté
et déclaré dans la configuration commune. Vérifier la copie avec le même
conteneur/version et les mêmes imports/certificats avant installation.
Si seul un fichier est bind-monté, un remplacement par renommage change son
inode et peut laisser le conteneur sur l'ancien contenu : contrôler le montage
et les fichiers effectivement visibles dans le conteneur. Privilégier un montage
de répertoire pour des mises à jour atomiques ; toute modification du montage
existant exige une opération distincte revue avec l'exploitant.

Une fois les fichiers approuvés installés et visibles dans le conteneur :

```sh
docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# Seulement après validation, sans arrêt/restart des autres sites :
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

Surveiller un autre site avant/pendant/après le reload et vérifier Muqola,
HTTPS, cookies et absence de jeton/Authorization dans les erreurs. Ne jamais
publier 2019, 8000 ou 5432. Les ports UFW TCP existants suffisent pour HTTPS ;
HTTP/3 est facultatif et n'impose pas d'ouvrir UDP pour cette intégration.

### Identité cliente et protection du protocole

Le middleware de confiance est exécuté **avant** SecurityMiddleware. Hors
production il n'altère pas le développement/Codespaces ; les limites continuent
à ignorer les en-têtes clients directs. En production, les en-têtes de forwarding
sont supprimés si l'adresse du pair n'est pas une IP Caddy approuvée. Seuls les
healthchecks internes loopback sur leurs deux routes publiques gardent le
protocole de leur sonde ; cette exception ne s'applique pas aux routes métier.
Le calcul des limites prend `X-Real-IP` uniquement depuis un Caddy approuvé,
une seule adresse valide, sinon l'adresse du pair. Une liste/valeur malformée
ne crée pas de nouveaux buckets arbitraires. Les limites par adresse e-mail
restent communes aux IP. `production_readiness` refuse une confiance proxy vide.

### Sauvegarde, supervision et Debian 13

Chaque JSON d'exploitation doit désormais inclure `"project": "muqola-prod"`,
en plus de ses chemins `compose_file` et `compose_env`. Les outils passent
explicitement `--project-name` et refusent une configuration sans projet ;
mettre à jour les JSON **avant** de remplacer l'outillage. Garder les chemins et
statuts historiques de production ; les futurs statuts staging seront distincts.
Les outils pg_dump/age/rclone, chiffrement, rétention et restauration sont réutilisés.

Le monitoring contrôle web/worker/DB dans le projet applicatif et la disponibilité
HTTPS via le Caddy commun, sans attendre un service Caddy local. La supervision
propre du Caddy partagé reste sous la responsabilité de `/opt/caddy` ; la sonde
externe indépendante reste nécessaire pour détecter une panne du VPS.

Les modules hôte de `deploy/` n'utilisent que la bibliothèque standard ; les
units systemd utilisent `/usr/bin/python3`. Sur Debian 13, vérifier `python3 --version`,
installer au besoin `python3`, `age`, `rclone`, `ca-certificates` via apt après
revue des versions ; Docker/Compose sont déjà présents. Ne pas installer le
projet Django/uv ni reconstruire son image sur le VPS. Django reste sous
Python 3.12 dans l'image ; la contrainte `<3.13` du projet ne s'applique pas
à l'import autonome des modules hôte. Exécuter depuis `/opt/muqola`, conserver
configs 0600 et clés de récupération hors VPS.

### Validation et limites

Le smoke utilise un **projet Caddy séparé**, un réseau externe synthétique, un
site témoin et l'application isolée. Il vérifie la continuité du témoin pendant
reload, les en-têtes/CSRF/limites/logs, les rôles SQL et le cycle backup/restore.
Il retire seulement ses conteneurs et réseaux ; **tous les volumes sont conservés**,
avec inventaire sous `work/muqola-lot6-synthetic-*-retained-volumes.json`.
Ni purge globale ni suppression de volume n'est autorisée par cet outillage.
Les fixtures restent synthétiques et aucun SMTP réel/ACME/VPS n'est contacté.
Résultats locaux : `scripts/check.sh` réussit avec **386 tests**, lint/format,
typage, Django, migrations et statiques ; contrôle Django production et audit
runtime sans vulnérabilité connue. Le smoke partagé a réussi reload/HTTPS/CSRF,
expurgation des erreurs et backup/restore ; les six états de prêts sont conservés.
Les modules hôte s'importent sous **Python 3.13.18**, sans installation de Django
(test autonome, pas qualification du VPS). Les parcours navigateur et la CI
sur le commit final sont consignés dans la PR ; les validations serveur restent
strictement des actions manuelles à réaliser après autorisation distincte.

---


## Audit Caddy partagé, staging et CI/CD — 17 novembre 2026

**Audit préalable conservé comme historique ; découpage approuvé ensuite par l’exploitant.**
Branche locale `docs/lot-6-cicd-audit`, issue de `origin/main` synchronisé à
`ff9e0c208be067b993f22b5f4b3b5751d5a8579d`. La [PR #32](https://github.com/tlamart/muqola/pull/32)
est **fusionnée depuis le 17 novembre à 13 h 57, heure de Paris** ; son commit
`7945797` et toute sa préparation font désormais partie de main. Il n'y a donc
ni reprise de branche ouverte ni implémentation parallèle à entreprendre.
La preuve historique de [CI #89 verte](https://github.com/tlamart/muqola/actions/runs/44045607508)
porte sur ce commit de PR. La [CI du merge 44088074202](https://github.com/tlamart/muqola/actions/runs/44088074202)
est également **terminée avec succès** sur `ff9e0c2`, vérification API du présent audit.

### Infrastructure et périmètre vérifié

Selon les informations de l'exploitant : OVH VPS-1, 2 vCores/4 Go, Debian 13,
Docker/Compose installés, UFW 22/80/443 TCP, SSH par clé sans root, Caddy commun
dans `/opt/caddy`, HTTPS disponible sur `muqola.tlam.art`. Le réseau externe
`proxy` est **prévu**, sa présence et son adressage restent à vérifier par
l'exploitant. Staging cible : `staging.muqola.tlam.art`, arrêté par défaut.
Ces informations ne constituent pas une inspection serveur : aucun SSH ni
changement du VPS, aucune vérification du service applicatif public effectuée.
L'ouverture publique reste régie par `LAUNCH_CHECKLIST.md`.

### Écarts et risques concrets

| Point | Constat dans main | Adaptation proposée avant livraison |
| --- | --- | --- |
| Caddy/ports | `compose.prod.yaml` démarre Caddy et publie 80/443 TCP + 443 UDP | Retirer ce service et ses ports ; laisser les anciens volumes intacts ; Caddy commun seul maître des ports |
| Réseaux | Tous les services sur `default`, sans réseau externe ni alias propre | web sur privé + `proxy`, alias `muqola-web` ; staging `muqola-staging-web` ; db/worker/migrate privés ; aucune route vers l'alias ambigu `web` |
| Confiance réseau | Django fait confiance au protocole fourni par le proxy | N'admettre sur `proxy` que des applications administrées et fiables ; le réseau partagé ne garantit pas l'isolation entre les web des applications ; DB et secrets restent privés |
| Rechargement Caddy | Le fichier fourni contient `admin off` | Ne pas recopier ce bloc dans le Caddy commun : conserver son endpoint admin interne permettant `caddy reload`, sans l'exposer ; préserver les autres sites/options/certificats |
| Journaux et en-têtes | Filtrage des requêtes/URI/en-têtes et réécriture du protocole déjà présents | Reprendre ces protections dans un extrait à fusionner ; ajouter un test d'erreur avec Authorization/cookie/jeton et un second site témoin pendant reload |
| Limites par IP | `identity/ratelimit.py` utilise `REMOTE_ADDR` : derrière Caddy, budget partagé entre clients | Déduire l'IP uniquement depuis le Caddy explicitement approuvé et son en-tête réécrit ; tester l'usurpation, ne pas approuver tout `proxy` |
| Image | Pas de build dans le Compose production, mais référence libre ; exemple de tag local | Exiger `ghcr.io/tlamart/muqola@sha256:…` et sa provenance ; garder le tag SHA complet comme trace, jamais comme garantie d'immuabilité |
| CI/GHCR | Un workflow de contrôles PR/main, aucun publisher ni CD | Ajouter publication du candidat testé après contrôles du même main, puis workflow manuel ; aucune publication depuis PR, aucun `pull_request_target` exécutant du code non fiable |
| Staging | Aucun Compose, secret, volume ou protection d'accès dédié | Projet/base/volumes/chemins/clés propres ; accès Caddy protégé, noindex et capture SMTP privée, sans copie de production |
| SMTP staging | `APP_ENV` ne connaît pas staging ; flags de sécurité activés seulement par production ; `production_readiness` refuse capture et absence de TLS SMTP | Garder `APP_ENV=production` en staging ; contrôle staging distinct exigeant Mailpit interne sans relais/egress SMTP et conservant les autres protections ; ne pas assouplir le contrôle production ni les portes 18+/légales |
| Monitoring | `deploy/monitor.py` attend un service `caddy` dans le projet app | Séparer état du Caddy commun et état de l'app ; sonde HTTPS adaptée à l'auth staging ; credentials de sonde privés et absents des logs |
| Backup/restore | Outils #32 opérationnels sur synthétique, configuration un seul projet/fichier Compose | Réutiliser pg_dump/age/rclone ; configurations/env/états/préfixes indépendants et sélection explicite de projet ; ne jamais confondre état de backup staging et production |
| Migrations | `deploy/migrate.sh` applique explicitement migrate + grants, sans protocole CD | Plan puis application autorisée, backup frais et preuve de restauration ; contrôle du schéma et du plan, verrou ; opération destructive/inconnue bloquée, aucune restauration automatique |
| Rollback | Procédure documentaire sans registre de release | Enregistrer ancien/candidat/réussi avec digest et schéma ; rollback d'image seulement si compatible, arrêt avec diagnostic après migration incertaine |
| Test existant | `production_smoke.py` possède son Caddy et termine par `down --volumes` | Adapter au proxy partagé et retirer la destruction de volumes ; ne pas exécuter ce script inchangé sous les contraintes de cette mission |
| Debian 13 | Image Python 3.12 ; projet limité à Python <3.13 ; units hôte pointant sur `.venv` | Vérifier Python hôte Debian (normalement 3.13) et tester les outils `deploy/` en stdlib sous l'interpréteur Debian ; ne pas imposer uv sync du projet ni construire Python/Django sur le VPS |

**Budget :** le rendu Compose donne 512 Mio web + 192 Mio worker + 768 Mio DB,
soit 1 472 Mio par pile ; deux piles plafonnent à 2 944 Mio, hors Caddy commun,
SMTP capturé, système, Docker et autres applications. Deux migrations
simultanées ajoutent 1 024 Mio : plus de marge raisonnable sur 4 Go.
Ce calcul porte sur les **limites**, pas sur la consommation. Mesurer RSS/CPU,
pointes de migration, MemAvailable et disque ; sérialiser les opérations lourdes,
refuser un démarrage sans marge et garder le staging arrêté hors usage.
Les limites CPU des services ne constituent pas une réservation de capacité.

### Modifications prévues, fichier par fichier

Cette liste est un plan, pas une liste de changements déjà réalisés.

| Fichier existant ou prévu | Intervention après accord |
| --- | --- |
| `compose.prod.yaml` | Caddy retiré, réseaux/alias, durcissement conservé, projet/volumes stables, image GHCR par digest |
| `.env.production.example` | Domaine réel cible sans secret, image immuable, chemins et identité explicite du projet/proxy |
| `compose.staging.yaml`, `.env.staging.example` (nouveaux) | Paramètres isolés, domaine/alias propres, capture SMTP sans relais, ressources et arrêt à la demande ; réemploi de la configuration commune sans hériter des secrets production |
| `deploy/Caddyfile` | Extrait pour Caddy commun, routes/auth staging/noindex ; consignes de fusion du bloc de logs et de l'admin local, sans écrasement des autres sites |
| `config/settings.py`, `muqola/core/proxy.py` (prévu), `muqola/identity/ratelimit.py` | Paramètres des proxys approuvés, résolution d'IP bornée/testée ; préserver tous les flags de sécurité et le fonctionnement local |
| `config/gunicorn.py` | Conserver les réglages éprouvés ; clarifier le commentaire qui les décrit encore comme réservés au développement ; tuning seulement après mesures |
| `deploy/common.py` | Choix explicite de projet/configuration par environnement, compatible avec les backups existants |
| `deploy/monitor.py`, `deploy/monitor.example.json` | Caddy externe, app/HTTPS/outbox/backup propres à l'environnement, auth staging privée |
| `deploy/backup.example.json`, `deploy/systemd/*` | Chemins, statuts, unités et interpréteur hôte Debian compatibles, sans réécrire le chiffrement/restore |
| `deploy/backup.py`, `deploy/restore.py`, `deploy/postgres/*`, `deploy/migrate.sh` | Réemploi ; seulement les adaptations indispensables, aucun changement de rôles ou garantie de restauration affaiblie |
| `muqola/operations/management/commands/production_readiness.py` | Garder les exigences production ; mutualiser uniquement les contrôles sûrs si un contrôle staging dédié est ajouté |
| `.github/workflows/ci.yml` | Conserver tous les contrôles ; job publication main seulement après succès, candidat testé conservé, packages:write limité au publisher ; SHA et digest archivés |
| `.github/workflows/deploy.yml` (nouveau) | workflow_dispatch staging/production, modes plan/apply, validation de provenance, environnements GitHub, approbation, concurrence et SSH strict |
| `deploy/release.py` et `deploy/image_provenance.py` (prévus) | Orchestration limitée : liste de fichiers versionnés, vérifications digest/plan/backup, verrou, pull/migrate/health/smoke, état de release et rollback compatible |
| `scripts/production_smoke.py` | Proxy partagé synthétique, deux sites/environnements, pas de destruction de volumes ; conserver TLS/CSRF/logs/SQL/backup/restore |
| `tests/test_deploy_configuration.py`, `tests/test_release.py` (prévus) | Isolation/ports/alias, source d'image approuvée, permissions workflows, échecs/interruptions/rollback et plans périmés |
| `tests/test_deploy_monitor.py`, `tests/test_deploy_backup.py`, `tests/test_production_readiness.py`, tests comptes | Adapter Caddy/staging, prouver conservation des protections et refus de l'usurpation |
| `.gitignore`, `.dockerignore` | Autoriser seulement les nouveaux exemples et continuer à exclure secrets, données et fichiers d'environnement réels |
| `README.md`, `ARCHITECTURE.md`, présent document, `TASKS.md`, `LAUNCH_CHECKLIST.md` | Runbooks Debian 13 et preuves ; conserver les historiques et validations d'ouverture non satisfaites |
| `Dockerfile`, `compose.yaml`, migrations historiques, règles métier | Réutilisation sans refonte ; développement local inchangé, aucun média utilisateur |

### Quatre PR proposées après accord

1. **Caddy partagé et exploitation compatible** : V1–V4. Réseaux, logs/en-têtes,
   IP de confiance, monitoring/backup et smoke adapté. Aucun besoin de GHCR pour
   tester localement ; un contournement de test accepte uniquement une image
   synthétique locale dans le harness, jamais dans le chemin de déploiement.
2. **Staging privé éphémère** : V5–V7, après PR 1 intégrée. Isolation/capture,
   authentification, non-indexation et contrôles de capacité. Usage réel suspendu
   aux mesures et à la configuration de l'exploitant.
3. **Publication GHCR après main validé** : V8–V9. Préserver exactement l'image
   candidate testée, tag SHA complet, digest et enregistrement de publication de
   confiance ; pas de secret GHCR dans les PR ni de publication depuis PR.
4. **CD manuel et exploitation documentée** : V10–V13, après PR 1–3 intégrées.
   Deux modes manuels `plan` puis `apply` pour que le reviewer puisse examiner
   le plan produit **avant** l'application ; apply référence un plan récent,
   un digest et un état de schéma revérifiés. La simple approbation d'un job avant
   calcul du plan ne suffit pas. Rollback contrôlé, sans opération DB automatique.

Chaque PR est créée depuis la dernière main, après intégration de ses
prérequis, avec preuves propres et aucun merge automatique. Les textes existants
sont mis à jour dans chacune ; aucun second système de sauvegarde ni manuel
redondant. Aucun déploiement réel ne sera exécuté pour ces implémentations.

### Actions manuelles à préparer

- **GitHub/GHCR :** choisir package public ou privé ; configurer droits Actions
  et environnements `staging`/`production`, branches autorisées, reviewer production
  si disponible pour le compte ; empêcher l'auto-approbation si possible.
  Prévoir secret SSH dédié par environnement, host key vérifiée hors bande et,
  si nécessaire, accès GHCR VPS limité à la lecture. Ne pas fournir les clés privées
  dans le chat. Sans reviewers disponibles : plan puis validation manuelle explicite
  liée au run/digest, avec accès workflow restreint ; documenter la limite.
- **OVH/VPS/Caddy :** confirmer version/conteneur Caddy, mode de montage du
  Caddyfile (attention au remplacement atomique d'un fichier bind-monté), service
  Compose réel et admin local ; réseau `proxy` et identité stable du Caddy,
  répertoires séparés, permissions, espace/mémoire/CPU et autres apps.
  Les comptes autorisés à Docker disposent de privilèges comparables à root :
  les limiter, ne pas prétendre qu'une clé SSH est limitée si elle accède librement
  au socket Docker. Ne pas ouvrir 8000/5432 ; aucun changement UFW nécessaire
  pour ajouter le staging HTTPS. HTTP/3 reste facultatif avec 443 UDP actuellement fermé.
- **DNS/Brevo :** confirmer l'enregistrement staging A/AAAA (IPv6 seulement si
  opérationnel), créer/vérifier le compte SMTP et expéditeur Brevo, copier les
  valeurs SPF/DKIM/DMARC fournies et cohérentes avec les autres expéditeurs.
  Credentials SMTP uniquement en production ; staging capture interne sans relais.
  Tests de délivrabilité ultérieurs sur adresses contrôlées et suivi des rejets/quotas.
- **Sauvegarde et conformité :** stockage extérieur, destinataire age public,
  clé privée séparée, politique de rétention, restauration isolée et RPO/RTO ;
  alerte indépendante du VPS. Fournir les informations légales, revue et procédure
  effective de suppression ; ne pas activer un indicateur de revue fictif.

### Preuves de cet audit et arrêt demandé

Références synchronisées, état de fusion lu par API, fichiers obligatoires et
outils existants examinés ; rendu Compose production valide avec/sans profil
maintenance, limites calculées depuis ce rendu. Aucun test de nouvelle CI/CD
n'est présenté comme réussi : elle n'est pas encore implémentée. Les 373 tests
et le smoke de #32 restent des preuves historiques ; pas de relance du smoke
qui détruit ses volumes sous sa forme actuelle. Aucun accès SSH, déploiement,
push GHCR, modification de Caddy réel, création de secret ou suppression de volume.
Seuls cet audit et la section V0–V13 de TASKS.md ont été préparés localement.

**Accord reçu ; voir l’état de PR 1 ci-dessus et les tâches de suivi.**

---

Les sections suivantes actualisent le runbook de #32 pour le Caddy partagé ;
les résultats datés de #32 restent des preuves historiques.


État du 17 novembre 2026. Base : `main` 0b5e928, après les PR #24
(infrastructure initiale), #25 (Wikidata/Commons), #28 (communautés), #29
(catalogue), #30 (recherche) et #31 (prêt des fiches en attente).
**Aucun achat, déploiement, compte fournisseur ou traitement de données réelles
n'a été effectué. L'ouverture de la bêta reste un no-go.**

## Audit et décisions

| Domaine | Déjà présent | Préparation livrée | Validation humaine restante |
| --- | --- | --- | --- |
| Application | Auth, vérification, CSRF, limites de débit, permissions, prêts concurrents, modération, recherche PostgreSQL | Régressions couvertes ; 18+ explicite et serveur | Deux comptes sur vrai domaine, téléphone réel |
| Production | Gunicorn, WhiteNoise, Caddy de préparation | Compose distinct, secrets fichiers, rôles DB, limites, healthchecks, images figées | VPS, DNS, ACME, charge/mémoire, pare-feu |
| E-mail | Outbox durable, retries, purge, worker | Secrets SMTP, TLS, heartbeat, détection échecs/retards | Fournisseur, SPF/DKIM/DMARC, livraison réelle |
| Sauvegarde | Absente | pg_dump → age → rclone, rétention, statut, restauration isolée | Stockage externe, droits, perte du VPS, exercice réel autorisé |
| Exploitation | Logs JSON sans contenus sensibles | Sonde HTTPS/DB/worker/outbox/disque/backup/erreurs, timers | Canal d'alerte et supervision externe |
| Conformité | Demandes de suppression enregistrées et outils opérateur | Modèles légaux, pages publiques, blocage inscription si incomplets, 18+ | Identité, coordonnées, bases légales, durées, revue juridique et traitement effectif des droits |

Les fichiers préparés ne constituent pas une preuve de fonctionnement sur un
VPS. Les tests synthétiques sont décrits plus bas ; la checklist de lancement
conserve ses validations réelles non cochées.

## Configuration et frontières de confiance

Ne jamais superposer `compose.yaml` (développement, Mailpit) au fichier de
production. Seul le **Caddy commun externe** publie les ports HTTP/HTTPS. Le Compose
applicatif ne publie aucun port ; UDP/HTTP3 reste facultatif. Le réseau Docker et son administrateur font partie de la frontière de
confiance : Django accepte le protocole fourni par Caddy, qui écrase les en-têtes
clients. Ne pas connecter de conteneur non fiable à ce réseau.

Le runtime tourne sous UID 10001, en lecture seule et sans capacités Linux ;
`/tmp` est un tmpfs borné. PostgreSQL persiste dans le projet applicatif ; les certificats Caddy restent
dans les volumes du projet `/opt/caddy`, sans transfert ni suppression. Restart `unless-stopped`, arrêt gracieux et logs Docker
bornés à 3 × 5 Mo par service. Web 512 Mio, worker 192 Mio, DB 768 Mio ; le budget du Caddy commun
est à vérifier séparément :
cible initiale **2 vCPU / 4 Go RAM**, à mesurer sur le VPS, sans garantie de charge.
Les limites CPU/mémoire Compose s'appliquent sans Swarm. Les erreurs Caddy
filtrent URI, en-têtes et objet requête ; aucun access log n’est activé, pour
protéger aussi les jetons lors d’une panne de Django.

Les images PostgreSQL et Python sont épinglées par digest ; la version du
Caddy commun est gérée indépendamment. L'image applicative doit être construite
sur runner et référencée sous `ghcr.io/tlamart/muqola@sha256:…`, sans build VPS.
La publication automatisée avec trace du SHA complet relève de la PR 3 à venir ;
ni tag local ni `latest` ne passent le précontrôle de production. Revoir régulièrement correctifs et digests en PR, reconstruire,
auditer et tester avant toute mise à jour. Ne pas changer de version majeure
PostgreSQL sans procédure distincte.

Copier le modèle d'environnement **hors dépôt**, par exemple
`/etc/muqola/production.env`, mode 0600. Il ne contient que les paramètres et
chemins ; il ne faut pas injecter tous les secrets par `env_file`.
Dans `/etc/muqola/secrets`, créer séparément `django_key`,
`db_admin_password`, `db_migrate_password`, `db_app_password`, `smtp_password`.
Générer chaque valeur par un générateur cryptographique (au moins 64 caractères
aléatoires pour la clé Django), distincte du développement. Aucune valeur dans
Git, arguments de commande, ticket ou journal. Le répertoire parent doit être
0700, appartenir à l'administrateur ; fichiers lisibles par les UIDs des
conteneurs via ACL ou mode 0444 **à l'intérieur de ce répertoire 0700**. Les
secrets Compose locaux sont des bind mounts : `uid/gid/mode` ne remplace pas les
permissions hôte. Tester la lecture effective sous UID 10001 et sous PostgreSQL,
sans imprimer les valeurs. Ne pas rendre le répertoire traversable au public.

Web/worker reçoivent seulement clé Django, mot de passe applicatif et SMTP.
La maintenance reçoit le mot de passe migration ; seul PostgreSQL reçoit le
mot de passe administrateur. L'API Docker permet d'accéder aux secrets : limiter
strictement les membres du groupe Docker et l'accès SSH. Les changements de
clé Django invalident sessions et contenus d'outbox chiffrés : ne jamais la
remplacer sans plan de rotation et reprise des messages.

### Rôles et migrations

Sur **volume neuf uniquement**, `10-roles.sh` crée :

- `muqola_admin` : bootstrap, sauvegarde/restauration, jamais utilisé par Django ;
- `muqola_migrate` : propriétaire du schéma/tables, non superuser, droit CREATE
  sur la base pour l'extension de confiance `pg_trgm` ; maintenance ponctuelle ;
- `muqola_app` : connexion, USAGE, SELECT/INSERT/UPDATE et séquences ; pas de DDL,
  rôle, extension ni propriété. DELETE limité aux sessions, jetons, buckets de
  débit, outbox, invitations en attente et visibilités nécessaires au métier.
  Aucun DELETE de prêt, exemplaire, utilisateur ou historique ; aucun accès au
  registre des migrations ni écriture des définitions de permissions Django.

Les migrations historiques sont intactes. La migration adulte ajoute une date
nullable, **sans inventer d'attestation pour les comptes existants**, ni
supprimer de ligne. Son retour arrière est volontairement interdit pour ne pas
perdre les attestations.

Commande de validation structurelle, sans démarrage :

```sh
docker compose --env-file .env.production.example -f compose.prod.yaml config --quiet
```

Commandes **futures**, seulement après configuration et autorisation de
l'opérateur, depuis `/opt/muqola` (aucune exécutée ici sur infrastructure réelle) :

```sh
python3 -m deploy.check_config --config /etc/muqola/monitor.json
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml up -d --wait db
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml run --rm migrate python manage.py migrate --plan
# Sauvegarde préalable vérifiée, revue du plan et autorisation avant la suite :
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml run --rm migrate
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml up -d --wait web worker
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml exec -T web python manage.py check --deploy --fail-level WARNING
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml exec -T web python manage.py production_readiness
```

Le service `migrate` n'est jamais lancé automatiquement ; son script applique
les migrations puis réattribue les droits runtime contrôlés. Sur **volume
existant**, l'init PostgreSQL ne tourne pas : arrêter les écritures, inventorier
rôles, propriétaires, extensions et dépendances, sauvegarder et restaurer dans
un environnement isolé, préparer un script d'adoption revu (création des deux
rôles, transfert explicite des objets applicatifs, révocation des droits PUBLIC,
réattribution des seuls droits runtime). Tester ce script sur la copie avant
autorisation de production. **Ne pas effacer un volume pour relancer l'init**, ne
pas lancer de `REASSIGN OWNED` global sans inventaire. Cette adoption n'est pas
une opération automatique fournie pour une base réelle inconnue.

## Sauvegarde et restauration

Outils hôte : Python 3 Debian (stdlib uniquement), Docker Compose, **age 1.3.2** et rclone (version
maintenue à fixer dans l'inventaire VPS). La clé privée age est générée et
conservée **hors VPS**, avec copie de secours chiffrée accessible à l'opérateur.
Le VPS n'a besoin que du destinataire public `age1…`. La perte de la clé privée
rend les sauvegardes irrécupérables. La récupération inclut, par canal distinct,
la clé Django correspondante et les paramètres applicatifs ; le dump ne
contient pas les rôles/mots de passe PostgreSQL.

Adapter `deploy/backup.example.json` dans `/etc/muqola/backup.json` (0600), avec
un préfixe de stockage **exclusivement dédié**. Configurer rclone dans un fichier
0600 : compte à droits minimaux limité au préfixe, TLS vérifié, SFTP avec fichier
`known_hosts` vérifié par canal indépendant. Backends préparés : S3, B2, SFTP,
Azure Blob ou WebDAV HTTPS. Le backend local est refusé sauf indicateur explicite
`synthetic: true`, réservé au test. Éviter toute configuration désactivant TLS.
Ne jamais mettre les clés de stockage dans le JSON, l'environnement ou argv.

```sh
python -m deploy.backup --config /etc/muqola/backup.json
```

Flux réel : `pg_dump --format=custom --no-owner --no-acl` → chiffrement age →
`rclone rcat`. Aucun dump clair sur disque lors de la sauvegarde. Le fichier
`.partial` n'est promu qu'après succès des trois processus et taille non nulle.
Une sauvegarde cohérente PostgreSQL inclut comptes, catalogue/alias/crédits
Commons, communautés, exemplaires, prêts et outbox. Rétention par défaut 30 jours,
minimum 7 sauvegardes, configurables ; seuls les noms horodatés générés par cet
outil sont éligibles. Les fichiers étrangers et `.partial` ne sont jamais
supprimés automatiquement : surveiller leur accumulation après échecs.

Le statut 0600 conserve dernière tentative, succès et nom d'objet ; un échec ne
remplace pas la date du dernier succès. Exit non nul et événement JSON générique,
sans credentials ni contenu de dump. Verrou local pour empêcher deux sauvegardes
simultanées. Le compte distant doit permettre liste/écriture/renommage/suppression
sur ce seul préfixe. Tester réellement chaque fournisseur ; les droits et les
renommages peuvent varier. Les copies immuables/versionnées avec identité de
suppression séparée constituent une protection supplémentaire contre une
compromission du VPS, à configurer chez le fournisseur.

### Exercice de restauration futur

1. Choisir un environnement de récupération isolé, jamais la base active ;
   installer les mêmes versions, rôles et clé Django via canaux privés.
2. Y créer une base **vide**, nommée `muqola_restore_<identifiant>`, appartenant
   à `muqola_migrate`. Ne pas lancer les migrations avant d'importer le dump.
3. Fournir temporairement la clé age privée dans un fichier 0600 sur un poste
   de récupération de confiance, avec espace libre suffisant (borne par défaut
   2 Gio + marge). La retirer ensuite selon la politique de ce poste.
4. Exécuter depuis ce poste, avec une configuration pointant sur la pile isolée :

```sh
python -m deploy.restore --config /etc/muqola/restore.json \
  --object HORODATAGE-IDENTIFIANT.dump.age \
  --database muqola_restore_exercice --identity /chemin/prive/identity.txt
```

5. Vérifier les comptes, références, états de tous les prêts, nombres de lignes,
   alias/crédits, accès privés et contrôle d'intégrité ; consigner date, durée,
   taille, résultat, RPO/RTO mesurés. Ne pas envoyer l'ancienne outbox vers les
   vrais destinataires pendant l'exercice (worker arrêté/transport isolé).
6. Une restauration de service ou un basculement reste une opération distincte,
   explicitement autorisée avec sauvegarde et plan de retour.

La restauration refuse le nom actif et les cibles non `muqola_restore_*`, ainsi
que les bases contenant des tables applicatives. Le flux est intégralement
authentifié par age avant d'appeler PostgreSQL ; dump clair temporaire 0600 dans
un répertoire 0700, supprimé en fin de traitement, taille bornée. Utiliser un
disque hôte chiffré pour protéger les blocs temporaires. `pg_restore` fonctionne
en transaction unique, sans `--clean`, `DROP` ou `TRUNCATE`. Les droits runtime
sont réappliqués ensuite ; si cette dernière étape échoue, diagnostiquer/rejouer
les droits sur la copie, ne pas réimporter dans une base désormais peuplée.

## SMTP, DNS et délivrabilité

Réutilisation exclusive de `EmailOutbox` et `process_outbox`. `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD_FILE`, `EMAIL_FROM` sont
configurables. STARTTLS : 587/TLS=true/SSL=false ; TLS implicite :
465/TLS=false/SSL=true. Certificats vérifiés par Python ; ne jamais activer les
deux modes. Délai réseau borné par les paramètres existants. Mailpit demeure
strictement local. `production_readiness` refuse le transport local/factice ou
sans TLS, les identifiants modèles, les droits DB excessifs et les textes
juridiques incomplets ; ce contrôle ne prouve pas l'envoi réel.

Le fournisseur doit autoriser l'expéditeur et le domaine. Reprendre **ses**
valeurs DNS : un seul SPF cohérent (incluant les autres expéditeurs autorisés),
DKIM avec son sélecteur et sa clé publique, DMARC avec alignement du domaine
From/SPF ou DKIM. Démarrer la politique DMARC selon la revue de vos flux et
traiter les rapports dans une boîte réellement surveillée ; aucune adresse ni
valeur SPF/DKIM fictive ne doit être publiée.

Après configuration et autorisation, utiliser deux adresses de test contrôlées
sur des fournisseurs distincts : inscription/vérification, reset, invitation et
prêt complet. Contrôler inbox/spam, en-têtes Authentication-Results
SPF/DKIM/DMARC, bon domaine HTTPS, expiration et usage unique des liens, absence
de jetons dans les logs. Simuler un échec SMTP sur **la pile de test** et vérifier
retry après reprise sans fuite ni perte de demande. L'outbox applique backoff,
20 tentatives max, échec après 7 jours ; l'état SMTP accepté ne garantit pas la
livraison finale. Consulter les bounces chez le fournisseur, sans ajouter de
webhook non demandé. Une reprise après interruption peut produire un doublon
(effet externe SMTP hors transaction) ; contrôler avant tout retry opérateur.

## Supervision, alertes et incidents

`python -m deploy.monitor --config /etc/muqola/monitor.json` : HTTPS avec
certificat vérifié, état/health web/worker/DB, HTTPS via le Caddy commun, SELECT 1, outbox en échec
ou en retard >15 minutes, disque (<1 Gio libre ou >90 %), sauvegarde absente,
échouée ou âgée de >36 h, erreurs JSON web/worker des 10 dernières minutes.
Ne publie que des codes, jamais les logs bruts ou identités. Heartbeat worker
actualisé après une boucle réussie, périmé après 120 s. `/health/ready/` reste
minimal/public ; les métriques d'exploitation restent privées.

Adapter les modèles systemd `deploy/systemd/` : backup quotidien, sonde toutes
les 5 minutes. Utiliser `/usr/bin/python3` sans installer Django sur l’hôte, protéger
configs 0600 et répertoires 0700. Créer et tester **avant activation**
`/etc/muqola/notify-operator` et `muqola-alert@.service` à partir du modèle,
via canal indépendant du SMTP applicatif. `OnFailure` transmet uniquement le
nom du service. Test volontaire d'échec puis de rétablissement, suivi journal
systemd et accusé opérateur. Aucun canal réel n'est livré/configuré. Une sonde
externe indépendante doit détecter panne du VPS lui-même et expiration TLS ;
la sonde locale seule ne peut pas le faire. Les logs bornés sont une alerte
légère, pas une garantie de détecter toutes les erreurs à très haut débit.

Incident : limiter l'accès si confidentialité en jeu, préserver les journaux
sans les publier, identifier version et dernière sauvegarde, vérifier DB,
worker, disque puis SMTP, appliquer correction revue. Ne pas purger l'outbox ni
relancer des migrations à l'aveugle. Compromission : révoquer/rotater les secrets
par canal privé et examiner l'impact RGPD avec le responsable désigné.
Rollback : une ancienne image ne doit être utilisée qu'après vérification de
compatibilité avec le schéma courant et des protections 18+/confidentialité. Pas de downgrade de migration irréversible.
Tester le retour sur copie restaurée ; restaurer/basculer en production exige
une autorisation distincte et l'évaluation des écritures postérieures au backup.

## Adultes, légal et suppression de compte

Bêta **18 ans et plus**, décision définitive. Case obligatoire non précochée,
validation serveur et date d'attestation, sans date de naissance ni document
identitaire. Les anciens comptes doivent attester avant toute nouvelle activité.
Les prêts existants restent consultables et clôturables (annuler/refuser/remettre/
rendre), sans accepter de nouveau prêt. Le profil et les demandes de suppression restent
accessibles sans attestation. Ce mécanisme est une attestation, pas
une vérification d'identité ; faire valider la formulation juridique.

Compléter les quatre modèles `docs/legal/*.txt.example` hors dépôt, monter
`mentions.txt`, `terms.txt`, `privacy.txt`, `support.txt` en lecture seule dans
`LEGAL_DOCUMENTS_DIR`. Renseigner identité/statut de l'exploitant, directeur de
publication si applicable, contact, responsable du traitement, hébergeur et
sous-traitants/lieux/transferts, bases légales, durées effectives, procédure de
droits, délais et juridiction après revue compétente. Aucun texte modèle n'est
une consultation juridique. `LEGAL_REVIEWED=true` signifie **revue réellement
faite**, pas simple copie du modèle. Sinon pages 503 et inscription production
fermée ; les marqueurs de remplacement ne sont jamais affichés comme mentions
validées. Les pages échappent le texte (pas de HTML arbitraire).

Procédure de droits à finaliser avec l'exploitant :

1. Surveiller quotidiennement `ops` (demandes existantes) et le contact renseigné ;
   consigner réception, vérification proportionnée d'identité et échéance légale.
2. Vérifier prêts actifs et obligations de conservation, informer la personne du
   périmètre, des motifs et des délais réellement applicables. Ne pas empêcher
   la clôture d'un prêt ou effacer les références historiques à l'aveugle.
3. Le verrouillage/désactivation opérateur existant empêche la nouvelle activité ;
   **ce n'est pas un effacement RGPD**. Préparer sur une copie synthétique une
   opération ciblée de suppression/anonymisation conforme à la politique validée,
   incluant profil, champs libres, jetons/outbox, invitations, signalements et
   liens historiques. Faire revoir et autoriser son application réelle. Aucun
   effacement automatique global n'est livré par ce lot, car les bases légales et
   durées de l'exploitant sont inconnues.
4. Répondre, enregistrer l'exécution et ne clôturer la demande dans l'outil qu'après
   traitement effectif ; prévoir les exceptions justifiées et une voie de recours.
   Les backups expirent selon rétention ; rejouer les décisions d'effacement
   après toute restauration avant réouverture, sans réintroduire de comptes.

**Bloquant public :** opérateur responsable, procédure effective éprouvée et
politique de conservation juridiquement validée. Le simple stockage d'une
requête de suppression ne satisfait pas cette exigence.

## Preuves reproductibles sur données synthétiques

```sh
./scripts/check.sh
APP_ENV=production APP_BASE_URL=https://muqola.example.test \
  uv run --frozen python manage.py check --deploy --fail-level WARNING
uv run --frozen pip-audit -r requirements.txt --disable-pip --no-deps
# Après build local, avec age/age-keygen et rclone installés :
uv run --frozen python scripts/production_smoke.py --image muqola:local
```

Résultats locaux du 17 novembre : `scripts/check.sh` (lint, format, typage,
Django, migrations, statiques et **373 tests réussis**), contrôle Django de
production et structure Compose valides, audit runtime sans vulnérabilité connue.
Les six scripts navigateur (socle, comptes, recherche, produit, catalogue et UI)
réussissent, avec et sans JavaScript selon les parcours, de 360 à 1280 px.
Le smoke production avec vrais outils a réussi le chiffrement/restauration,
la rétention, les rôles, TLS/CSRF et les refus de clé/base invalides ; la PR et sa
CI conservent la preuve de la version finale. Aucune validation distante réelle.

Le smoke crée un projet applicatif `muqola-lot6-synthetic-<aléatoire>` et un
projet Caddy séparé, avec volumes neufs, sans ports DB/web publiés. HTTPS loopback avec CA Caddy interne
(pas d'ACME), cookies/CSRF et en-têtes vérifiés, interdictions SQL testées,
pg_dump/age/rclone réels, rétention, restauration dans une base distincte, refus
clé erronée/base peuplée, comparaison de toutes les lignes et des six états de
prêts. La source reste identique. Ses conteneurs/réseaux sont retirés et ses
volumes sont **conservés**, avec inventaire dans work/. Ce test n'atteste ni stockage distant réel, ni SMTP réel, ni certificat
public. Résultats exacts et CI sont consignés dans la PR.

## Interventions du propriétaire et ordre des validations

1. **Domaine existant :** confirmer nom/droits, contact ACME surveillé et DNS
   nécessaires ; aucun achat prévu.
2. **VPS OVH existant :** vérifier intégration Caddy, SSH/pare-feu, mises à jour,
   accès Docker restreint, capacité, disque et volumes ; aucune nouvelle location.
3. **SMTP :** créer compte transactionnel, vérifier domaine/expéditeur, quotas,
   contact bounces ; déposer credentials privés, choisir TLS correct.
4. **DNS :** A/AAAA exacts (ne pas publier IPv6 non fonctionnel), SPF/DKIM/DMARC
   du fournisseur ; vérifier résolution, ACME et renouvellement.
5. **Légal :** fournir les informations ci-dessus, faire revoir les textes et
   éprouver la procédure de suppression ; monter seulement les versions validées.
6. **Backup externe :** créer stockage et identité restreinte, garder clé age
   privée hors VPS, définir rétention/RPO/RTO et tester restauration autorisée.
7. **Exploitation :** versions figées, secrets et accès, canal d'alerte indépendant,
   sonde externe, tests panne/reprise, puis validation des parcours réels.
8. **Ouverture :** toutes les cases BLOQUANT satisfaites, preuves datées et
   autorisation humaine explicite distincte. Ne pas déployer depuis cette PR.
