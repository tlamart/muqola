# Dernière recette de confidentialité — staging synthétique

Cette recette reste à exécuter par l'exploitant : le 26 novembre, il indique que
ces scénarios ne sont pas encore tous testés. Elle ne constitue pas un compte
rendu réussi. Utiliser uniquement des comptes fictifs `@example.test`, un jeu de
test et la base staging. Aucun effacement de production n'est demandé ici.

Le [runbook de conservation](confidentialite-conservation.md) reste la référence
pour les droits, la revue des textes libres, les sauvegardes et le ledger privé.
Les commandes sont à lancer dans la session habituelle de confiance sur le VPS,
par un compte déjà autorisé à lire la configuration staging et utiliser Docker.
Ne pas envoyer d'identifiant, de dump ou de ledger dans le chat ou le dépôt.

## 1. Vérifier le contexte et préparer les comptes

```sh
docker exec muqola-staging-web-1 python manage.py shell --verbosity 0 -c \
  'from django.conf import settings; print(settings.DEPLOYMENT_ENV, settings.APP_BASE_URL, settings.DATABASES["default"]["NAME"])'
```

Attendu : `staging https://staging.muqola.tlam.art muqola_staging`. Si le contexte
diffère, arrêter cette recette. Créer/vérifier normalement Alice et Bob fictifs,
conserver un opérateur fictif distinct et ne jamais traiter le dernier opérateur.
Préparer une sauvegarde staging avant l'effacement, avec la procédure extérieure
déjà vérifiée, et noter son horodatage UTC. Aucune copie de production à utiliser.

Pour retrouver l'identifiant d'un compte fictif connu, répéter cette lecture pour
l'opérateur puis la cible ; elle ne liste pas les autres comptes :

```sh
read -r -p 'Adresse du compte fictif @example.test : ' RECETTE_EMAIL
docker exec --env RECETTE_EMAIL="$RECETTE_EMAIL" muqola-staging-web-1 \
  python manage.py shell --verbosity 0 -c \
  'import os; from muqola.identity.models import User; email=os.environ["RECETTE_EMAIL"].strip().lower(); assert email.endswith("@example.test"), "Compte fictif requis"; print(list(User.objects.filter(email=email).values_list("id", flat=True)))'
```

Depuis Bash, reprendre le modèle CD actif, sans démarrer ses dépendances :

```sh
install -d -m 700 /var/lib/muqola/staging/privacy
privacy_stage() {
  docker compose --project-name muqola-staging \
    --env-file /etc/muqola/staging/staging.env \
    -f /var/lib/muqola/staging/cd/active/compose.json \
    --profile staging-maintenance run --rm --no-deps \
    --user "$(id -u):$(id -g)" \
    --volume /var/lib/muqola/staging/privacy:/privacy \
    migrate python manage.py privacy "$@"
}
read -r -p 'ID numérique de l’opérateur fictif : ' PRIVACY_OPERATOR_ID
read -r -p 'ID numérique du compte fictif à traiter : ' PRIVACY_USER_ID
```

Vérifier les identifiants depuis les comptes de test ; ne pas choisir un ID au
hasard. La commande exige le rôle PostgreSQL de maintenance et un opérateur actif,
vérifié, adulte et non restreint. Le rôle web ne doit pas recevoir de droit DELETE.

## 2. Compte sans prêt actif : simulation puis effacement

Avec le compte fictif ciblé, enregistrer sa demande dans **Mon compte**.
Faire une première simulation :

```sh
privacy_stage account --operator-id "$PRIVACY_OPERATOR_ID" --user-id "$PRIVACY_USER_ID"
```

Attendu : `applied=false`, `outcome=erased` si aucun prêt/exception ne bloque.
Le compte est encore présent ; le bilan ne doit publier ni e-mail ni texte privé.
Examiner les références et textes libres avant de confirmer leur revue.

```sh
read -r -p 'Valeur plan_hash de la simulation relue : ' PRIVACY_PLAN_HASH
privacy_stage account --operator-id "$PRIVACY_OPERATOR_ID" --user-id "$PRIVACY_USER_ID" \
  --approved "$PRIVACY_PLAN_HASH" --review-confirmed
```

Attendu : `applied=true`, `outcome=erased`. Vérifier disparition du compte, sessions,
jetons et collection personnelle, préservation du catalogue et des autres comptes,
exemplaires/partages légitimes et preuve minimale d'effacement. Un plan périmé ou
modifié impose une nouvelle simulation, jamais un hash réutilisé aveuglément.

## 3. Compte avec prêt accepté ou remis

Avec un autre compte fictif, préparer un prêt accepté ; refaire ensuite le cas
avec un prêt remis. Enregistrer la demande et répéter simulation/revue/application.

Attendu : `outcome=restricted`, compte conservé, sessions révoquées, nouvelles
activités/partages/acceptations bloqués. Le compte peut se reconnecter et consulter
ses prêts ; les deux parties conservent leurs droits de clôture. Le propriétaire
confirme remise/retour selon l'état réel. Les demandes devenues inéligibles sont
closes ; aucune annulation forcée d'un prêt remis.

Après clôture, refaire une simulation et sa revue : l'effacement final doit devenir
possible sans perdre les données des autres membres. Une exception temporaire
justifiée doit continuer de bloquer ce qui doit être conservé ; ne pas créer de
litige fictif sur un compte réel et ne pas avancer l'horloge du VPS.

## 4. Restauration : rejouer les preuves sur une copie isolée

Après l'effacement du compte sans prêt actif, exporter les preuves vers un nom
privé nouveau (la commande refuse l'écrasement) :

```sh
privacy_stage receipts --operator-id "$PRIVACY_OPERATOR_ID" \
  --ledger-file /privacy/ledger-recette-2026-11-26.json
```

Le ledger est signé, **non chiffré** : le chiffrer et le conserver hors VPS suivant
le runbook, sans le publier dans un artefact Actions. Restaurer la sauvegarde
staging antérieure dans une base vide distincte `muqola_restore_*`, avec le schéma
compatible, le même opérateur, la même clé de signature et l'origine du staging.
Ne jamais restaurer dans `muqola_staging` ou la base de production.

Pour le rejeu, utiliser le modèle staging, mais un contexte maintenance de copie
isolée. `DEPLOYMENT_ENV=staging` impose la base principale `muqola_staging` et
refuserait la copie : l'override ci-dessous ne concerne que le conteneur ponctuel,
sur la base restaurée. Il ne change aucun service ou fichier de configuration.
`APP_ENV=production` et le contrôle CLI `muqola_restore_*` restent actifs ; SMTP,
clé et origine du modèle staging sont conservés, aucun worker n'est démarré.

```sh
read -r -p 'Nom de la copie isolée muqola_restore_* : ' PRIVACY_RESTORE_DB
read -r -p 'Horodatage UTC de la sauvegarde (ISO 8601 avec fuseau) : ' PRIVACY_BACKUP_AT
privacy_replay_stage() {
  case "$PRIVACY_RESTORE_DB" in
    muqola_restore_?*) ;;
    *) echo 'Une base de restauration isolée est obligatoire.' >&2; return 1 ;;
  esac
  docker compose --project-name muqola-staging \
    --env-file /etc/muqola/staging/staging.env \
    -f /var/lib/muqola/staging/cd/active/compose.json \
    --profile staging-maintenance run --rm --no-deps \
    --user "$(id -u):$(id -g)" \
    --volume /var/lib/muqola/staging/privacy:/privacy:ro \
    --env DEPLOYMENT_ENV=production --env POSTGRES_DB="$PRIVACY_RESTORE_DB" \
    migrate python manage.py privacy replay --operator-id "$PRIVACY_OPERATOR_ID" \
    --ledger-file /privacy/ledger-recette-2026-11-26.json \
    --backup-at "$PRIVACY_BACKUP_AT" "$@"
}
privacy_replay_stage
```

Examiner le bilan. Après revue, appliquer sur **cette copie seulement** :

```sh
read -r -p 'Valeur plan_hash du rejeu relu : ' PRIVACY_PLAN_HASH
privacy_replay_stage --approved "$PRIVACY_PLAN_HASH" --review-confirmed
```

Attendu pour le cas sans prêt actif : le compte effacé ne réapparaît pas et
`reopening_allowed=true`. Si un prêt actif/une exception est retrouvé, la reprise
doit être refusée (`reopening_allowed=false`), sans clôture forcée. Ne pas ouvrir
la copie aux utilisateurs tant que sa réconciliation n'est pas complète.

## Résultat à conserver

Relever date, image, identifiants techniques fictifs, résultats attendus/obtenus
et référence privée de la restauration, sans publier le ledger ni les contenus
personnels. Fournir seulement les statuts : simulation sans écriture, effacement
sans prêt, restriction/clôture/finalisation, préservation des autres comptes,
rejeu isolé et refus d'un prêt actif retrouvé. Jusqu'à ce compte rendu, la réserve
de recette reste ouverte dans [la checklist](../LAUNCH_CHECKLIST.md).
