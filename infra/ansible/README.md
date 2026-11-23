# Administration du VPS avec Ansible

Premier lot : **audit en lecture seule et adoption des permissions existantes**.
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

Le rôle **n'installe ni ne remplace le contrôleur**, les fichiers de configuration,
les unités systemd ou leurs scripts d'alerte. Leur reprise demandera des lots
suivants revus, notamment une coordination avec le verrou CD pour le contrôleur.
Les unités locales personnalisées et leur canal Brevo sont préservés.

Le déploiement applicatif reste dans GitHub Actions : `plan → revue → apply`.
Ansible ne lance pas Docker, ne change pas d'image, ne migre/restaure/efface aucune
base, ne touche pas aux volumes, au verrou, aux états et liens actifs CD, ni au
Caddy partagé. La présence d'un fichier ne prouve pas que son contenu est valide.

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

## Vérification locale et CI

Sans inventaire privé ni connexion VPS :

```sh
uv run --frozen ansible-lint --offline
uv run --frozen ansible-playbook -i inventory.example.yml playbooks/audit.yml --syntax-check
uv run --frozen ansible-playbook -i inventory.example.yml playbooks/adopt.yml --syntax-check
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

Validation locale du 23 novembre 2026 : neuf tests réussis avec cible Python 3.13,
lint production/syntaxe/actionlint réussis ; 651 tests applicatifs et build Docker
réussis. Un conteneur sans réseau vérifie l'absence d'Ansible et des inventaires
dans l'image. Ces résultats ne valent pas recette sur le VPS.

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
