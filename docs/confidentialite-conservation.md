# Vie privée et conservation — décisions du 22 novembre 2026

Ces décisions ont été validées par l'exploitant dans la conversation du
22 novembre. Cette PR prépare leur exécution et leur recette synthétique ; elle
n'autorise aucune intervention ni aucun effacement sur le VPS. Les migrations
ajoutent des champs/tables et élargissent un type de jeton ; elles ne nettoient
aucune donnée. Les anciennes migrations restent intactes.

| Domaine | Décision validée |
| --- | --- |
| Demandes de suppression | Traitement manuel assisté, simulation et confirmation ; objectif sept jours, réponse normalement sous un mois à compter de la demande |
| Prêts actifs | Retirer les partages/nouvelles activités, effacer ce qui n'est plus nécessaire ; conserver le minimum pour clôturer les prêts, puis finaliser |
| Historique clos | Seuil de purge de trois mois **calendaires**, effacement anticipé possible sur demande ; exception ciblée et bornée pour litige/obligation |
| Inactivité | Douze mois depuis la dernière connexion, ou création sans connexion ; préavis réellement envoyé puis trente jours, nouvelle connexion annulant l'éligibilité |
| Communautés | Préserver les autres membres et le catalogue ; transfert d'administration consenti ou archivage si dernier administrateur |
| Sessions | Sept jours de validité, nettoyage quotidien des sessions expirées par le worker ; CSRF 364 jours ; jetons verify 24 h/reset 1 h |
| Journaux | Plafond sept jours à mettre en œuvre séparément sur l'hôte, sans modifier le journal global ni les fichiers internes Docker |
| Support | Suppression manuelle un mois après résolution, corbeilles incluses dans la boîte de destination Outlook ; OVH est une redirection, pas une boîte |
| Diagnostics/configurations | Nettoyage manuel trente jours après intervention |
| Preuves de droits | Identifiant technique, type d'opération, date ; six mois, aucune copie du profil ni motif libre |
| Sauvegardes | Sept jours, minimum deux copies ; les deux dernières peuvent dépasser sept jours si les sauvegardes cessent ; réconciliation avant réouverture après restore |

La pseudonymisation n'est pas présentée comme une anonymisation. La commande
d'effacement retire réellement la ligne User et sa collection, les sessions,
jetons, demandes d'adhésion, appartenances et prêts clos associés. Elle conserve
les fiches génériques et les communautés des autres personnes, avec attribution
à **un compte technique commun inactif, sans mot de passe utilisable**. Les
preuves limitées restent des données personnelles protégées pendant six mois.
Les champs libres conservés dans le catalogue ou une communauté partagée exigent
une revue humaine : les informations concernant la personne doivent être
retirées sans détruire les contenus légitimes des autres membres. Le booléen de
confirmation atteste cette revue ; aucun algorithme ne prétend reconnaître tous
les noms, coordonnées ou informations personnelles dans du texte libre.

## Frontières et permissions

La commande `privacy` exige un opérateur actif, vérifié, majeur et superutilisateur,
plus l'accès OS de confiance. Les applications web/worker ne peuvent pas l'appliquer
avec `muqola_app` en production : l'application exige le rôle propriétaire du
schéma (maintenance). Le rôle runtime ne reçoit **aucun nouveau DELETE** sur les
prêts, comptes ou communautés. Pas d'annuaire opérateur public ni d'API d'effacement.

Tous les changements prennent le même verrou PostgreSQL que les prêts et les
partages. Une acceptation concurrente invalide le plan ou impose une restriction,
jamais la destruction d'un prêt accepté. Un prêt remis ne peut pas être annulé
pour contourner la restitution. Les transitions existantes propriétaire/emprunteur
et les autorisations après retrait d'une communauté restent contrôlées.

Un compte restreint peut se reconnecter, demander un reset, consulter son compte
et ses prêts, annuler avant remise et confirmer remise/retour selon son rôle.
Il ne peut plus accepter un prêt, partager, emprunter, créer une communauté ni
modifier le catalogue, même par appel direct aux services. Les sessions
existantes sont révoquées lors de la restriction ; la reconnexion sert à clôturer.
L'adresse vérifiée et l'authentification subsistent tant qu'elles sont nécessaires.
Les motifs de demandes, notes de ses exemplaires, messages non conservés pour
litige et informations privées de proposition sont effacés dès cette première étape.

Si une autre administration active/vérifiée existe, retirer seulement le membre.
Sinon l'opérateur fait d'abord organiser un transfert consenti, ou le traitement
archive la communauté, désactive ses appartenances/partages et révoque ses liens.
Aucune nomination silencieuse d'un autre membre. L'archivage conserve les autres
comptes, exemplaires et prêts ; leurs parties peuvent clôturer les prêts acceptés.
Une reprise d'administration existante ne doit pas réouvrir une communauté archivée.

## Commandes et simulation

Les exemples suivants sont des procédures **futures**, à exécuter seulement après
fusion, publication, revue du plan CD, sauvegarde et déploiement autorisé. Ne pas
les exécuter contre une version ancienne. Aucun exemple ne donne un hash universel
ou ne transforme automatiquement une simulation en approbation.

Depuis le compte opérateur du VPS, dans un dossier lisible :

```sh
cd /opt/muqola-controller
# Fonction de commodité locale ; aucune clé ou adresse personnelle dans l'historique.
install -d -m 700 /var/lib/muqola/production/privacy
privacy() {
  docker compose --project-name muqola-prod \
    --env-file /etc/muqola/production.env \
    -f /var/lib/muqola/production/cd/active/compose.json \
    --profile maintenance run --rm --no-deps \
    --user "$(id -u):$(id -g)" \
    --volume /var/lib/muqola/production/privacy:/privacy \
    migrate python manage.py privacy "$@"
}
# Choisir les identifiants techniques sur l'instance concernée.
privacy account --operator-id "$PRIVACY_OPERATOR_ID" --user-id "$PRIVACY_USER_ID"
```

La réponse contient un hash et un bilan sans nom, e-mail, mot de passe, jeton ni
texte privé. Examiner les prêts actifs/exceptions et les identifiants de contenus
à revoir. Le hash lie le jour UTC et l'état des tables métier, dont les exceptions.
Il est volontairement conservateur : une modification concurrente peut nécessiter
une nouvelle simulation. Le calcul est diffusé par lots de 200 lignes, sans dump
sur disque ni chargement de toute la base en mémoire.

Après vérification de l'identité et de la demande, réponse à la personne, examen
des textes libres, sauvegarde extérieure récente et autorisation de l'intervention :

```sh
privacy account --operator-id "$PRIVACY_OPERATOR_ID" --user-id "$PRIVACY_USER_ID" \
  --approved "$PRIVACY_PLAN_HASH" --review-confirmed
```

La demande doit déjà être enregistrée dans Mon compte (ou provenir du préavis
arrivé à échéance). Ne jamais créer une fausse demande pour contourner cette
condition. Pour une demande reçue par support, aider la personne à utiliser Mon
compte ; si elle ne peut pas s'authentifier, vérifier son identité et enregistrer
sa demande via un accès OS de maintenance tracé, avant toute simulation.

Si le résultat est `restricted`, informer la personne des éléments encore
nécessaires, du motif et de la suite prévue ; suivre la clôture des prêts et refaire
une simulation pour finaliser. Ne pas attendre la fin d'un prêt pour répondre à la
demande. Le délai habituel d'un mois n'est pas une période d'attente obligatoire.
Aucune suppression d'un opérateur actif : transférer/démissionner ses fonctions
avant de traiter son compte, sans retirer le dernier accès opérateur de l'instance.

## Inactivité : revue mensuelle, préavis par l'outbox existante

```sh
privacy inactivity --operator-id "$PRIVACY_OPERATOR_ID"
privacy notice --operator-id "$PRIVACY_OPERATOR_ID" --user-id "$PRIVACY_USER_ID"
# Après examen du plan uniquement :
privacy notice --operator-id "$PRIVACY_OPERATOR_ID" --user-id "$PRIVACY_USER_ID" \
  --approved "$PRIVACY_PLAN_HASH" --review-confirmed
```

La liste est limitée à 100 comptes ; utiliser `--after-id` avec le dernier ID
pour continuer sans ignorer les comptes suivants.

Le dernier appel **met en file**, il ne prétend pas que le message est livré.
Aucun contact manuel par identifiant deviné ; le destinataire provient du compte.
Le worker envoie le préavis par le transport habituel (Mailpit en synthétique,
Brevo seulement sur production configurée). Le préavis ne porte aucun jeton de
connexion et ne fournit qu'un lien vers le formulaire de connexion de l'origine
configurée. Une fois le transport confirmé, `InactivityNotice.sent_at` est enregistré.
En cas d'échec SMTP, le délai de trente jours **ne commence pas**. La livraison
confirmée par SMTP ne prouve pas la lecture ; surveiller bounces et quotas Brevo.
Une nouvelle connexion avant envoi annule le message, et après envoi annule
l'éligibilité à la clôture pour cette période d'inactivité. Après trente jours,
utiliser `privacy account` avec une nouvelle simulation et une confirmation humaine.
Aucune clôture automatique de comptes par le worker.

## Historique, exceptions et preuves

```sh
privacy retention --operator-id "$PRIVACY_OPERATOR_ID"
# Après vérification des exceptions et approbation du bilan :
privacy retention --operator-id "$PRIVACY_OPERATOR_ID" --approved "$PRIVACY_PLAN_HASH"
```

Le lot maximal est de 100 prêts clos ; recommencer la simulation si le lot est
plein. Les événements et outbox associés sont retirés avant les prêts, sans
suppression des exemplaires, fiches ni comptes des autres personnes. Un état
REQUESTED/ACCEPTED/HANDED_OVER est exclu, même si une date de clôture incohérente
est présente. Les preuves de plus de six mois sont retirées par la même procédure.
Cette rétention historique est **opérée manuellement**, pas activée par une
migration ou au démarrage. Organiser une revue hebdomadaire et traiter les
échéances sans ajouter une durée de conservation implicite ; si le volume
empêche de tenir les engagements, automatiser ce lot après décision distincte.

Avant toute purge ou traitement impliquant un litige identifié :

```sh
privacy hold --operator-id "$PRIVACY_OPERATOR_ID" --loan-id "$PRIVACY_LOAN_ID" \
  --until "$PRIVACY_HOLD_UNTIL" --code dispute
# Reprendre les mêmes paramètres et le hash examiné pour appliquer.
```

`--code` vaut `dispute` ou `legal`. Horodatage avec fuseau, date future d'au plus
366 jours avant réexamen ; pas de conservation indéfinie. Documenter hors des
journaux techniques la justification, les seules données nécessaires et le suivi.
Le traitement ne purge pas les prêts couverts et ne termine pas l'effacement du
compte concerné. Une exception n'autorise pas à conserver toutes ses autres données.

## Sauvegardes et réconciliation après restauration

Après chaque intervention, produire une sauvegarde chiffrée hors VPS et exporter
les preuves dans un fichier privé ; conserver cet export **chiffré** hors VPS,
avec une rétention de six mois. Utiliser un nom technique unique pour chaque export ;
la commande refuse d’écraser un fichier existant. Elle écrit dans le bind privé
(`/var/lib/muqola/production/privacy` sur l’hôte), jamais le ledger sur stdout
ni dans les journaux Docker. L'export est signé mais **pas chiffré** : ne pas
le mettre dans Git, un artefact Actions, un ticket ou des journaux publics.

```sh
umask 077
privacy receipts --operator-id "$PRIVACY_OPERATOR_ID" --ledger-file /privacy/ledger-export.json
# Chiffrer avec age vers la clé publique de sauvegarde puis transférer par rclone,
# dans le stockage privé prévu, avant de clore administrativement l'intervention.
```

Le ledger signé est limité à l'origine configurée ; il ne porte que les IDs,
actions, date d'export et exceptions actives. La clé Django doit être conservée
pour valider la signature ; une rotation exige une procédure distincte. Le compte
opérateur et la clé age de secours ne doivent pas dépendre du seul VPS perdu.
Les effacements intervenus après la dernière copie extérieure sont dans le RPO :
ne jamais prétendre garantir un rejeu sans une preuve disponible et suffisamment récente.

Avant remise en service d'une restauration autorisée, fermer les accès utilisateurs,
utiliser une copie isolée et un ledger récent indépendant du dump ancien :

```sh
# Base isolée préalablement restaurée, schéma mis à niveau sur cette copie seulement.
# PRIVACY_RESTORE_DB doit être un nom muqola_restore_* ; la commande refuse la base principale.
docker compose --project-name muqola-prod \
  --env-file /etc/muqola/production.env \
  -f /var/lib/muqola/production/cd/active/compose.json \
  --profile maintenance run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  --volume /var/lib/muqola/production/privacy:/privacy:ro \
  --env POSTGRES_DB="$PRIVACY_RESTORE_DB" \
  migrate python manage.py privacy replay --operator-id "$PRIVACY_OPERATOR_ID" \
  --ledger-file /privacy/ledger-export.json --backup-at "$PRIVACY_BACKUP_AT"
# Après examen du plan, répéter avec --approved et --review-confirmed.
```

Le CLI exige un fichier privé non symbolique ≤1 Mio, une signature valide, la même
origine, un export de moins d'un jour et une sauvegarde d'au plus six mois. Une
preuve trop ancienne/incomplète n'autorise pas à rouvrir le service. Les restrictions
sont réappliquées ; les prêts actifs ou exceptions réapparus empêchent l'effacement
et sont signalés, jamais clôturés de force. Une restriction seule dans le ledger
ne vaut pas autorisation d'effacement final. Ne rouvrir que si le résultat et la
revue humaine permettent la réconciliation complète, y compris les états des prêts.

## Journaux : activation hôte séparée et optionnelle

Les fichiers JSON Docker actuels sont bornés en volume ; ils ne garantissent pas
sept jours. **Cette PR ne prétend pas avoir déjà changé la rétention du VPS.**
L'option proposée réutilise systemd-journald, sans nouveau service externe :

1. Installer `deploy/systemd/journald-muqola.conf.example` comme
   `/etc/systemd/journald@muqola-production.conf`, root:root 644. Activer la socket
   syslog du namespace `muqola-production`, vérifier le chemin réel
   `/run/systemd/journal.muqola-production/dev-log` et la réception locale.
2. Installer les deux unités `muqola-journal-retention@.*`, root:root 644,
   `daemon-reload`, tester le service puis activer le timer instance `production`.
   Le journal est isolé, borné à 64 Mio, rotation horaire et purge à six jours
   (marge avant le plafond public de sept jours). Contrôler le plus ancien message
   et les passages automatiques. Aucune modification du journal global, des
   journaux SSH ni des fichiers internes `/var/lib/docker/containers`.
3. Installer les versions revues de `deploy/journal.py`, `release.py`, `monitor.py`
   dans le contrôleur root-owned. Ajouter `journal_namespace: muqola-production`
   aux configurations privées CD **et** monitoring ; ces modifications invalident
   tout plan CD antérieur. Le nouveau plan refuse une socket absente.
4. Les nouveaux modèles CD utilisent Docker `syslog` vers cette socket Unix,
   avec cache local Docker **désactivé**, tags propres au projet/service. Le monitor
   lit alors le namespace par `journalctl`, jamais `docker compose logs`. Préparer
   ses droits de lecture dédiés (ou son unité root, code/configs de confiance et
   accès Docker déjà équivalent root), tester sans accorder lecture des autres
   journaux au compte applicatif.
5. La CD ne recrée que web/worker. La bascule DB exige une intervention séparée
   autorisée avec interruption planifiée et **volume conservé** ; retirer l'ancien
   conteneur sans toucher son volume pour éliminer son ancien journal. La même
   vérification vaut pour les anciens conteneurs de maintenance. Le Caddy partagé
   reste hors de ce modèle : vérifier ses logs Muqola filtrés séparément, sans
   modifier la conservation des autres sites sans décision distincte.
6. Le journal des unités de sauvegarde/supervision peut rejoindre ce namespace
   par des drop-ins `LogNamespace=muqola-production` après revue des alertes.
   Vérifier les deux environnements séparément ; ne pas mélanger les identités.

Tant que tous les journaux concernés et les anciennes copies ne sont pas traités,
ne pas annoncer que le plafond de sept jours est effectif. Les exemples n'installent
rien automatiquement et ne modifient pas la CD des installations sans cette option.

## Documents et contrôles restant réels

Mettre à jour les quatre documents privés, dater la politique et refaire la revue.
Le modèle `docs/legal/privacy.txt.example` conserve des marqueurs bloquants : aucune
identité/garantie contractuelle ne doit être inventée ni publiée par cette PR.
Vérifier les garanties des offres réellement souscrites (y compris Outlook.com),
liens DPA/confidentialité et transferts internationaux ; conserver les références
et dates hors dépôt. La localisation UE seule ne suffit pas. Références :
[CNIL — information](https://www.cnil.fr/fr/conformite-rgpd-information-des-personnes-et-transparence),
[RGPD — droits](https://www.cnil.fr/fr/reglement-europeen-protection-donnees/chapitre3).

Tests synthétiques et résultats exacts figurent dans TASKS.md et la PR. Resteront
une publication/image, l'installation du contrôleur hôte, une migration additive
revue, une recette staging avec faux comptes, la rétention réelle des journaux,
les routines manuelles et la revue juridique/contractuelle. Aucune case de mise
en production ne doit être cochée uniquement sur la foi de ces tests.
