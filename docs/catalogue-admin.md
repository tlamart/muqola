# Administration minimale du catalogue

Le site `/operator/` est un `AdminSite` Django dédié, avec pages Muqola responsive et accessibles sans JavaScript. Aucun modèle n’est enregistré dans l’admin générique : pas de CRUD, suppression, actions de masse, utilisateurs/groupes, communautés, invitations, exemplaires ou prêts exposés. Les commandes `ops` restent disponibles pour fusion, masquage, comptes et maintenance.

## Accès et revue

Connexion via `/accounts/login/` : mêmes limites de débit et vérification e-mail/attestation 18+ que l’application. Le lien « Modérer le catalogue » apparaît dans le menu du compte superuser/staff. Les droits sont revérifiés en base à chaque requête et dans la transaction avant décision : compte actif, e-mail vérifié, attestation adulte, `is_superuser` **et** `is_staff`. Un admin de communauté ou un compte seulement staff n’a pas accès. Aucune nouvelle connexion admin contournant ces contrôles.

File par défaut : fiches pending et héritées à réviser, 30 par page. Filtres statut/titre/alias, détail générique, explication de proposition, alias, correspondances exactes et suggestions similaires (20 maximum chacune), historique des 30 dernières décisions avec acteur/motif. Aucune note d’exemplaire, adresse e-mail de propriétaire, communauté ou liste de prêts dans la revue.

Le formulaire propose approbation, rejet ou demande de corrections/réexamen, motif obligatoire de 1–500 caractères, justification d’homonymie facultative mais exigée par le service en cas de doublon. Les champs génériques restent validés par `moderation.decide()`/`Game.full_clean()` ; type connu et base validée requis à l’approbation. Les alias saisis s’ajoutent sans suppression des références existantes. Aucun statut/masquage/propriétaire/image ou autre champ système n’est sauvegardé directement.

Chaque POST est protégé par CSRF, limite partagée de 100 soumissions par compte/120 par IP et par heure, et une révision signée valable une heure. Sous `domain_write`, une fiche ou une décision modifiée depuis l’ouverture du formulaire impose une nouvelle revue. Les contrôles exacts de doublon, suggestions et audits `OperatorAction`/`GameDecision` sont ceux de la CLI. Une erreur annule la décision, les changements et l’audit. Pas de mutation sur GET.

Demander des corrections conserve pending et inscrit le motif dans l’historique, consultable par l’auteur dans son parcours existant. Il n’y a pas de nouveau statut ni notification e-mail automatique. Réexaminer une fiche rejetée peut rétablir le prêt selon P1 : le formulaire l’explique. Les fiches déjà approuvées/héritées ne se rejettent pas : utiliser le masquage opérateur existant. Une approbation ne lève jamais `hidden`.

## Premier opérateur en production — procédure à exécuter par l’exploitant uniquement

**Aucune de ces commandes n’a été exécutée sur la production par cette PR.** Vérifier la version d’image et le contexte Compose avant toute intervention. Les rôles PostgreSQL ne sont pas des habilitations Django : ne pas attribuer de droits DB administrateur à l’utilisateur applicatif.

1. Utiliser un compte nominatif existant ou s’inscrire normalement ; confirmer réellement l’adresse e-mail et effectuer personnellement l’attestation adulte. Un mot de passe utilisable est requis. Ne pas fabriquer les horodatages en SQL, ne pas utiliser `create_dev_operator`.
2. Avec l’accès SSH/OS de confiance de l’exploitant, vérifier le profil et la base visés. Promouvoir le compte explicitement (exemple de chemin du runbook, à adapter si nécessaire) :

```sh
docker compose --env-file /etc/muqola/production.env -f compose.prod.yaml exec web \
  python manage.py promote_operator \
  --email personne@domaine.fr --confirm-email personne@domaine.fr \
  --bootstrap --reason 'Habilitation initiale validée par l’exploitant'
```

L’adresse et le motif ne sont pas des secrets ; ne mettre aucun mot de passe dans les arguments. `--bootstrap` refuse **tout** superuser préexistant, même inactif/non vérifié : aucun contournement automatique ni option force. Si un superuser existe sans staff, il peut être l’acteur de sa propre promotion via `--operator` après vérification/attestation, puisque les services CLI n’exigent pas staff. Si aucun opérateur existant n’est utilisable, arrêter et préparer une procédure de récupération distincte revue, sans réactiver aveuglément un compte.

3. Pour les promotions suivantes, remplacer `--bootstrap` par `--operator operateur-existant@domaine.fr`. Ce paramètre identifie l’acteur pour les droits et l’audit ; il **ne constitue pas une authentification** : la commande exige toujours un accès OS de confiance.
4. La commande ne crée pas de compte et ne change ni mot de passe, ni e-mail, ni preuves de vérification/attestation. Elle attribue staff/superuser dans une transaction sérialisée, avec audit obligatoire ; échec d’audit = rollback. La première trace `bootstrap_operator` est attribuée au compte habilité ; documenter séparément l’intervention OS dans le registre de l’exploitant. Les suivantes portent l’acteur existant (`promote_operator`). Un compte déjà pleinement habilité est refusé sans nouvelle écriture.
5. Se connecter normalement, ouvrir `/operator/`, vérifier avec un compte ordinaire le refus d’accès. Toute décision réelle de catalogue reste une opération explicite de l’opérateur.

`createsuperuser` Django reste techniquement disponible pour créer un nouveau compte avec saisie interactive du mot de passe, mais ne vérifie pas son e-mail, ne recueille pas l’attestation et n’utilise pas cet audit de promotion. Préférer inscription réelle puis `promote_operator` pour cette procédure.

## Promotion ponctuelle avec Ansible

Le [playbook dédié](../infra/ansible/README.md#promotion-ponctuelle-dun-compte-muqola)
appelle la même commande, sous les verrous CD global et environnement. Déployer
d'abord une image compatible avec ses nouvelles options, puis préparer les
paramètres privés sur le poste de confiance et simuler avant toute application.
Aucune promotion n'est exécutée par les playbooks habituels d'audit/adoption.

- `--dry-run` vérifie cible, acteur, motif et bootstrap sous le verrou métier,
  sans modifier de compte ni créer d'audit.
- `--if-needed` autorise une relance sans écriture si le compte est déjà staff et
  superuser ; tous les contrôles restent actifs. Un bootstrap répété n'est permis
  que si aucun autre superuser n'existe. Ce flag ne rétablit aucun compte inactif
  ou restreint et ne force pas la récupération d'un opérateur historique.
- `--deployment-env staging|production` exige `APP_ENV=production` et le contexte
  de déploiement demandé avant même la recherche du compte.
- `--json` expose seulement statut (`would_promote`, `promoted`, `unchanged`),
  simulation et environnement ; aucun e-mail, mot de passe ou motif en sortie.

Les usages manuels existants sans ces options restent compatibles : une promotion
déjà effectuée reste refusée par défaut. Aucun changement de schéma requis.

## Schéma et exploitation

Activation de `django.contrib.admin.apps.SimpleAdminConfig` sans autodécouverte. Les migrations Django standard `admin` ajoutent `django_admin_log` ; aucune migration Muqola ni transformation de données métier. Le journal métier demeure celui des services, pas `LogEntry`. En production, appliquer les migrations avec le service de maintenance et réattribuer les droits runtime par la procédure existante ; le rôle web ne fait pas de DDL. Contrôler `migrate --plan`, sauvegarde et retour compatible avant déploiement autorisé. La table admin additionnelle peut rester en place lors d’un retour à l’image précédente ; ne pas supprimer les traces ni inverser le schéma pour revenir au code antérieur.

HTTPS, cookies, proxy de confiance, CSP, no-store et absence de secrets dans les logs restent ceux du socle. Pas de CDN ni script inline d’admin. Le déploiement en production, les promotions réelles et les décisions réelles ne font pas partie de cette PR. Validation staging à faire avec comptes synthétiques dédiés via le runbook ; ne pas utiliser le smoke local sur une instance distante.

## Vérifications

Tests HTTP : rôles refusés, routes génériques absentes, GET sans effet, CSRF, entrées falsifiées/XSS, types/bases/doublons, audit et rollback, formulaires périmés et droits retirés, limite de débit ; décisions sur copies partagées avec demandes/prêts acceptés/remis, conservation des références et clôture après rejet. Tests PostgreSQL concurrents pour deux premiers opérateurs et deux revues web.

`scripts/admin_browser_smoke.py` crée seulement des données synthétiques sur Compose local, refuse APP_ENV/DEPLOYMENT_ENV non development avant écriture, promeut via la commande auditée, se connecte via le formulaire normal et exécute les trois décisions. Contrôles sans JS à 360/768/1280 px, captures et absence d’erreur JS. Il est intégré à la CI PR ; aucune publication/déploiement déclenché par ce test.

Résultats locaux (22 novembre 2026) : `./scripts/check.sh` réussi — Ruff, formatage, mypy (129 sources), Django, migrations/statiques et **611 tests réussis en 100,23 s** sur PostgreSQL 17. `check --deploy --fail-level WARNING` en configuration synthétique de production : succès. `makemigrations --check --dry-run` : aucune nouvelle migration Muqola ; plan après application vide. Audit runtime : aucune vulnérabilité connue. Image Docker construite avec CA proxy en secret BuildKit, pile Compose locale saine. Smoke opérateur réel réussi sans JavaScript aux trois largeurs, trois décisions via HTTP et promotion via la commande ; capture mobile inspectée. Résultat CI final à consulter dans le bilan de PR. Validation distante staging et matériel réel non effectuée.

Le smoke recherche sa fiche synthétique par titre exact avant de vérifier le filtre de statut : les autres scénarios CI peuvent avoir rempli plusieurs pages de catalogue. Le premier run CI a détecté cette hypothèse incorrecte du script, après réussite des trois décisions ; le comportement paginé de l’application était correct.

Le contrôle responsive historique mesure maintenant les deux rectangles d’espacement dans le même layout et arrondit au millième pour éliminer les résidus flottants ; le seuil de 12 px reste inchangé, sans modification du CSS des communautés. Un second run CI avait échoué sur ce contrôle existant après réussite du parcours de modération et du prêt complet.

Reprise du 23 novembre 2026 : parcours UI complet corrigé réussi à 360/390/768/1200/1280 px, navigation clavier/tactile, filtres, sans JavaScript et contenus longs, sans erreur JS/réseau. Ruff et formatage réussis ; main demeure ee13ea1. Le résultat Actions de la tête finale est suivi dans la PR, sans intervention sur les services distants.
