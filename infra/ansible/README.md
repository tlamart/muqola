# Administration du VPS avec Ansible

Premier lot : **audit, adoption des permissions existantes et promotion ponctuelle**.
Ce dépôt décrit la configuration ; l'exploitant lance Ansible depuis son poste
de confiance. Aucun identifiant VPS n'est fourni à Codex Cloud ni à la CI.

Une seule machine physique héberge staging et production. Elle figure **une fois**
dans l'inventaire. Les environnements conservent leurs chemins, secrets, volumes
et états CD distincts.

## Périmètre de ce lot

| Ansible fait | Ce qui reste dans les procédures existantes |
| --- | --- |
| Auditer la présence et les métadonnées des configurations, du contrôleur et des modèles CD | Lire/revoir les configurations privées et les preuves de sauvegarde/restauration |
| Auditer les versions des outils de sauvegarde et l'état des timers connus | Tester les alertes et superviser réellement le service |
| Fixer propriétaire/groupe et mode `0700` de neuf répertoires privés existants, sans récursion | Créer une nouvelle installation, des comptes ou des secrets |
| Sur option explicite, installer les paquets de sauvegarde manquants | Installer/mettre à jour Docker, SSH, le pare-feu ou redémarrer le serveur |
| Via un playbook ponctuel distinct, simuler/appliquer une promotion de compte auditée | Déployer d'abord l'image applicative compatible et vérifier réellement le compte |

Le rôle **n'installe ni ne remplace le contrôleur**, les fichiers de configuration,
les unités systemd ou leurs scripts d'alerte. Leur reprise demandera des lots
suivants revus, notamment une coordination avec le verrou CD pour le contrôleur.
Les unités locales personnalisées et leur canal Brevo sont préservés.

Le déploiement applicatif reste dans GitHub Actions : `plan → revue → apply`.
Les playbooks d'audit/adoption ne lancent pas Docker et ne modifient aucun fichier
applicatif. Le playbook de promotion utilise seulement `docker exec` sous les
verrous CD existants pour contrôler ou accorder les droits du compte choisi.
Aucun de ces playbooks ne change d'image, ne migre/restaure/efface de base, ne
modifie volumes, états/liens CD ou Caddy. La présence d'un fichier ne prouve pas
que son contenu est valide.

## Préparer le poste de confiance

Prérequis : Linux/macOS ou WSL, Git, **Python 3.12**, uv et SSH. Ansible n'est pas
ajouté à l'environnement Django ni à l'image applicative. `uv.lock` fixe les
versions testées ; `ansible-core` reste sur la série 2.21 compatible avec ce Python
de contrôle et le Python 3.13 du VPS Debian 13. Ne pas passer à 2.22 sans adapter
l'interpréteur de contrôle et retester.

Depuis une copie revue du dépôt :

```sh
cd infra/ansible
uv sync --frozen
cp inventory.example.yml inventory.local.yml
chmod 600 inventory.local.yml
```

Renseigner dans `inventory.local.yml` l'hôte et le **compte d'administration** SSH
qui dispose de sudo (`debian` sur l'installation existante). Garder
`muqola_host_deploy_user: muqola-deploy` : ce dernier reste le compte de CD, sans
ajout de sudo. La clé d'administration reste dans le gestionnaire SSH du poste ;
ne pas réutiliser/transmettre le secret GitHub. Si nécessaire, préciser un chemin
de clé **local** avec `--private-key`, sans la copier dans le dépôt.

Vérifier l'empreinte de l'hôte par un canal indépendant (console fournisseur par
exemple), puis enregistrer sa clé dans `~/.ssh/known_hosts`. La vérification SSH
reste obligatoire ; un `ssh-keyscan` seul ne prouve pas l'identité du serveur.
Ne pas utiliser `StrictHostKeyChecking=no` pour contourner une erreur.

L'inventaire local, `private/` et les fichiers de mot de passe Vault sont ignorés
par Git. **Tout `infra/ansible/` est exclu du contexte Docker**. Cela ne dispense
pas de relire `git diff --cached` : ne jamais y mettre les clés, mots de passe,
exports, dumps ou documents légaux réels. Les secrets déjà sur le VPS restent
sur place ; aucun Vault ni service de secrets supplémentaire n'est nécessaire
pour ce lot. Si Vault est ajouté ultérieurement, il ne chiffrera qu'au repos et
ne remplacera pas `no_log`/`diff: false` pour les tâches manipulant des secrets.

## 1. Audit sans changement

```sh
uv run --frozen ansible-playbook -i inventory.local.yml playbooks/audit.yml --ask-become-pass
```

Omettre `--ask-become-pass` si sudo fonctionne déjà sans mot de passe pour le compte
d'administration. Le compte de déploiement doit déjà exister et les neuf
répertoires privés doivent être de vrais répertoires. Le rôle refuse les parents
redirigés par des liens symboliques ; une installation incomplète exige une
inspection manuelle, elle n'est pas initialisée implicitement.

Résultat attendu : `changed=0`, puis revue des propriétaires/modes, fichiers absents,
versions et timers. Un timer absent n'est pas installé ni activé par cet audit.
L'audit ne lit pas les contenus privés, ne fait aucun `docker inspect`, ne collecte
pas l'environnement du serveur et ne publie pas les champs personnels du compte.
Les sorties contiennent tout de même des métadonnées d'exploitation : les garder
privées. Ne pas ajouter de journal Ansible public ni de cache persistant de facts.

## 2. Prévisualiser l'adoption

```sh
uv run --frozen ansible-playbook -i inventory.local.yml playbooks/adopt.yml --check --diff --ask-become-pass
```

Les changements attendus concernent uniquement propriétaire/groupe et mode `0700`
des répertoires de `roles/muqola_host/vars/main.yml`. Les fichiers de secrets restent
à `0444` dans leurs répertoires privés : aucune récursion ne les transforme en
fichiers illisibles pour les conteneurs. Les fichiers `.env`/JSON restent inchangés.

Par défaut **aucun paquet n'est géré**. Si l'audit signale une dépendance manquante,
prévisualiser l'option séparément :

```sh
uv run --frozen ansible-playbook -i inventory.local.yml playbooks/adopt.yml --check --diff --ask-become-pass \
  -e '{"muqola_host_manage_packages": true}'
```

La liste est fermée (`python3`, `age`, `rclone`, `util-linux`, `ca-certificates`),
`state: present`, sans upgrade global, rafraîchissement APT ou démarrage de service.
Si le cache APT est trop ancien, l'opérateur le traite séparément. Ce lot ne gère
ni dépôts APT ni politique de mises à jour de sécurité.

`--check` est une prévisualisation, pas une transaction ni une preuve complète
d'exécution future. Les seules commandes forcées en lecture pendant `--check`
sont `dpkg-query --show` et `systemctl show`. Toutes les mutations restent dans
des modules natifs compatibles avec ce mode.

## 3. Appliquer après revue

Pour la production, faire valider les changements proposés avant cette commande.
Ce lot n'exige aucun arrêt de l'application ; choisir toutefois une fenêtre sans
intervention d'administration concurrente. Conserver les modes/propriétaires
précédents depuis l'audit pour pouvoir les rétablir précisément si nécessaire.

```sh
uv run --frozen ansible-playbook -i inventory.local.yml playbooks/adopt.yml --ask-become-pass \
  -e '{"muqola_host_approved": true}'
```

Si les paquets ont aussi été revus, fournir les deux booléens dans **le même JSON** :
`-e '{"muqola_host_approved": true, "muqola_host_manage_packages": true}'`.
Sans approbation booléenne explicite, l'application échoue avant toute modification.
Cette garde n'est pas un contrôle d'accès : une personne ayant sudo peut toujours
modifier les playbooks. Elle évite un lancement accidentel.

Relancer l'audit et la même adoption : la seconde adoption doit rendre `changed=0`.
Vérifier le site, les timers et la CD avec les procédures existantes. Le rôle
ne masque pas un échec partiel : corriger sa cause, relire `--check`, puis reprendre.
Il ne restaure/désinstalle rien automatiquement.

## Promotion ponctuelle d'un compte Muqola

Ce playbook est indépendant d'`audit.yml` et `adopt.yml` ; une adoption normale
ne promeut aucun compte. Il accorde les droits opérateur **dans Muqola** et ne
change aucun droit Linux. La commande reste protégée par l'accès SSH/OS de
confiance ; l'adresse d'acteur sert aux permissions métier et à l'audit, pas à
authentifier la session SSH.

Prérequis : déployer d'abord par la CD une image contenant les options
`--dry-run`, `--if-needed`, `--json` et `--deployment-env` de `promote_operator`.
Une ancienne image refuse les options ; aucun contournement SQL n'est prévu.
Les migrations de la version doivent avoir été appliquées par le déploiement.
Le compte cible doit déjà exister, être actif, non restreint, avoir confirmé son
adresse et son attestation adulte, et posséder un mot de passe utilisable.
L'automatisation ne crée pas de compte et ne fabrique aucune confirmation.

Depuis `infra/ansible`, préparer les paramètres **sur le poste de confiance** :

```sh
umask 077
mkdir -p private
chmod 700 private
cp operator.example.yml private/promotion.yml
chmod 600 private/promotion.yml
```

Adapter le fichier privé : environnement explicite (`staging` ou `production`),
adresse et confirmation identiques, motif non sensible de 1–500 caractères.
L'exemple vise uniquement un compte fictif en staging. Les adresses de test du
staging restent en `@example.test`. Pour le **tout premier** opérateur, garder
`muqola_operator_bootstrap: true` sans acteur. Pour les suivants, mettre bootstrap
à `false` et renseigner `muqola_operator_actor` avec l'adresse d'un opérateur
existant, actif, vérifié, adulte et non restreint.

Prévisualiser avec les mêmes contrôles transactionnels que l'application :

```sh
uv run --frozen ansible-playbook -i inventory.local.yml playbooks/promote-operator.yml \
  -e @private/promotion.yml --check --ask-become-pass
```

Même sans `--check`, le comportement par défaut est une **simulation**. Le bilan
affiche seulement l'environnement et `would_promote` ou `unchanged` ; aucune
écriture de compte/audit. Les adresses, motifs et sorties privées sont masqués
dans les tâches, y compris en cas d'erreur. Ne pas ajouter ces données à des noms
de tâches ou des commandes de journalisation.

Après revue du compte et de l'environnement, application explicitement autorisée :

```sh
uv run --frozen ansible-playbook -i inventory.local.yml playbooks/promote-operator.yml \
  -e @private/promotion.yml --ask-become-pass \
  -e '{"muqola_operator_apply": true, "muqola_operator_approved": true}'
```

Une application réussie rend `promoted` et crée l'audit métier dans la même
transaction que les droits. Une relance rend `unchanged` sans nouvelle écriture
ni audit, après recontrôle des permissions. Le bootstrap reste refusé si **un
autre** superuser existe, même inactif : après l'amorçage, utiliser le mode acteur.
Un premier opérateur historique sans `is_staff` suit la procédure manuelle
documentée dans [le guide catalogue](../../docs/catalogue-admin.md), sans bootstrap
forcé. Une erreur d'audit annule la promotion.

Le playbook utilise les noms de conteneur existants `muqola-staging-web-1` et
`muqola-prod-web-1`, le socket Docker local explicitement fixé, et vérifie le
contexte applicatif **dans** le conteneur avant de rechercher le compte. Il ne
démarre/recrée aucun service. Les verrous préexistants global puis environnement
sont pris dans l'ordre de la CD, sans attente : code 75 si occupés ; attendre la
fin de l'opération en cours, puis refaire la simulation. Un verrou manquant ou
redirigé est refusé, aucun nouveau verrou n'est initialisé par le playbook.

### Verrou refusé en mode 0664

Le verrou global `/var/lib/muqola/cd.lock` sérialise les opérations CD entre
environnements ; `production/cd/release.lock` ou `staging/cd/release.lock` protège
l'environnement ciblé. `flock` réserve le fichier pendant l'opération et libère
la réservation à la fermeture du descripteur ; le fichier reste normalement
présent. Sa présence seule ne signifie pas qu'une opération est en cours.

Un échec sur `not item.stat.wgrp` signifie que le fichier est modifiable par le
groupe. Le rôle refuse ces permissions **avant toute promotion** et ne les corrige
pas implicitement, même en simulation. Le contrôleur historique pouvait créer ses
verrous en `0664` avec un umask `0002` ; les nouveaux verrous sont désormais créés
avec un mode maximal `0600`, comme ceux du cycle staging. Les fichiers existants
gardent leur mode, leur propriétaire, leur contenu et leur inode.

Pour le cas identifié par l'audit Ansible (fichier régulier, non symbolique,
propriétaire `muqola-deploy`, mode `0664`), l'exploitant peut corriger **ce fichier**
sur le VPS après revue du chemin et des métadonnées :

```sh
sudo stat -c '%a %U:%G %n' -- /var/lib/muqola/production/cd/release.lock
sudo chmod 0600 -- /var/lib/muqola/production/cd/release.lock
sudo stat -c '%a %U:%G %n' -- /var/lib/muqola/production/cd/release.lock
```

Le propriétaire/groupe restent identiques ; seul le mode devient `600`.
Pour staging ou le verrou global, utiliser le chemin **effectivement refusé**,
sans opération récursive ni changement de propriétaire. Un fichier absent ou
redirigé exige une inspection de l'installation, pas un `touch` de contournement.

Ne jamais supprimer, renommer ou recréer un verrou pour débloquer une opération :
deux processus pourraient alors réserver des inodes différents. `chmod` sur le
fichier existant conserve le verrou détenu ; si la CD est active, la promotion
reste refusée avec le code 75. Attendre sa fin, puis reprendre la simulation avec
`--check` avant l'application approuvée.

La correction du contrôleur doit être installée séparément sur l'hôte selon le
runbook CD ; publier une image applicative ne remplace pas `/opt/muqola-controller`.
Elle ne répare pas les anciens fichiers. Leur correction explicite reste durable
avec l'ancien contrôleur tant que les fichiers sont conservés. Aucun accès VPS,
changement de permissions réelles ou promotion n'est effectué par ce correctif.

## Vérification locale et CI

Sans inventaire privé ni connexion VPS :

```sh
uv run --frozen ansible-lint --offline
uv run --frozen ansible-playbook -i inventory.example.yml playbooks/audit.yml --syntax-check
uv run --frozen ansible-playbook -i inventory.example.yml playbooks/adopt.yml --syntax-check
uv run --frozen ansible-playbook -i inventory.example.yml playbooks/promote-operator.yml --syntax-check
uv run --frozen python -m unittest discover -s tests -v
```

Les tests exécutent les vrais playbooks en connexion locale, sans sudo, dans
`/tmp/muqola-ansible-test-*`, avec des fichiers **synthétiques**. Ils vérifient
audit/check sans mutation, approbation, idempotence, refus des liens/chemins
invalides et préservation des secrets, états/liens CD, Caddy, unités et volume
factices. Une valeur témoin ne doit jamais apparaître dans la sortie Ansible.
Le préfixe de fixture est refusé hors de cette connexion locale confinée ; ne
jamais le renseigner dans l'inventaire VPS. Ne pas exécuter les tests avec sudo.

Le workflow `Ansible checks` ne reçoit aucun secret SSH ni environnement GitHub de
déploiement. Il utilise Python 3.12 pour le contrôle et Python 3.13 pour exécuter
les modules sur les fixtures, comme sur le VPS. En local, `MUQOLA_TEST_PYTHON`
permet de choisir cet interpréteur cible ; sinon celui du contrôle est utilisé.
Les tests ne couvrent pas une installation APT réelle ou le transport
SSH/sudo : ces vérifications et la première adoption sur Debian 13 restent à faire
par l'exploitant après revue. La CI applicative existante reste indépendante.

Les tests de promotion Ansible remplacent **uniquement Docker** par un exécutable
local qui enregistre les arguments et retourne des réponses préparées ; il ne
simule pas la base ni les droits. Ils vérifient sélection staging/production,
simulation par défaut et dans `--check`, approbation, verrou occupé, absence
d'interprétation shell et confidentialité des erreurs. Les tests PostgreSQL
`tests/test_operator_promotion.py` et `tests/test_catalogue_admin.py` exécutent la
vraie commande et vérifient permissions, idempotence, absence d'écriture en
simulation, audit et rollback. Aucun compte réel n'est utilisé par ces tests.

Validation locale initiale du 23 novembre 2026 : neuf tests réussis avec cible Python 3.13,
lint production/syntaxe/actionlint réussis ; 651 tests applicatifs et build Docker
réussis. Un conteneur sans réseau vérifie l'absence d'Ansible et des inventaires
dans l'image. Ces résultats ne valent pas recette sur le VPS.

Complément promotion du même jour : **18 tests Ansible réussis**, dont neuf pour
le transport ponctuel, et **675 tests applicatifs réussis** sur PostgreSQL.
Lint/types/migrations/build réussis ; les quatre nouvelles options sont présentes
dans l'image construite, Ansible et ses inventaires en restent absents. Aucun
compte réel n'est promu ; première recette sur staging toujours à effectuer.

## Lots suivants proposés

1. Reprendre les scripts du contrôleur avec une activation sous verrou, sans
   concurrence avec les plans, applications ou sauvegardes existants.
2. Reprendre les unités backup/monitor et leurs alertes, après inventaire privé
   complet pour conserver leurs horaires et leurs paramètres.
3. Installer puis éprouver la rétention des journaux déjà préparée dans
   [le runbook de conservation](../../docs/confidentialite-conservation.md).
4. Étudier séparément comptes/SSH/pare-feu/Caddy partagé ; validation de configuration
   et reprise d'accès obligatoires avant toute modification sensible.

Ces lots ne sont pas implémentés ni activés par cette PR.
