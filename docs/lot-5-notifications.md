# Lot 5 — Notifications et parcours

## File transactionnelle

Chaque événement de prêt (demande, acceptation, refus, annulation, remise,
retour, y compris clôture automatique des demandes concurrentes/inéligibles)
crée deux entrées d'outbox dans la même transaction PostgreSQL. Aucun appel
SMTP dans la transaction métier. Les deux participants actifs et vérifiés
reçoivent un message donnant l'événement et un lien vers leur espace privé.
Ni adresse de l'autre participant, ni message libre de la demande dans le corps.
Vérification et récupération des comptes conservent leur file existante.

`EmailOutbox` possède soit un jeton de compte (OneToOne/CASCADE), soit un
événement de prêt (FK/CASCADE) et son destinataire (User/PROTECT). Une contrainte
vérifie cette alternative ; une clé unique événement/destinataire évite de
réinsérer un même message. L'index statut/prochaine tentative sert au worker.
`LoanEvent.notifications_queued` permet de reprendre les événements antérieurs
au lot 5 et les événements non encore mis en file, sans recréer les envois purgés.
Les données de compte et les historiques métier restent protégés par leurs FK.

Le worker utilise `SELECT FOR UPDATE SKIP LOCKED` : plusieurs workers peuvent
traiter la file sans traiter simultanément une ligne. Une transaction de livraison
reste ouverte pendant le SMTP (timeout 5 secondes), indépendamment des écritures
métier. Un succès doit être confirmé par le backend. Un échec conserve la charge
chiffrée et programme une tentative après 60 secondes, puis délai exponentiel
plafonné à une heure. À 20 échecs, statut `failed` visible dans les diagnostics,
sans annuler le prêt. `Message-ID` stable par ligne ; livraison **au moins une fois** :
un arrêt après acceptation SMTP mais avant commit peut encore produire un doublon.
Le message décrit un événement daté et renvoie vers l'état actuel du prêt.

SIGTERM/SIGINT arrête le worker après le message courant ; Compose accorde
30 secondes. Les verrous sont libérés après arrêt brutal, la file est persistante.
La clé Django chiffre les charges : sa rotation nécessite de vider ou migrer
la file, sinon les charges anciennes ne sont plus lisibles.

Le worker purge chaque heure : charges envoyées/invalidées effacées aussitôt,
charges en échec effacées après 7 jours ; attente supérieure à 7 jours convertie
en échec explicite ; diagnostics terminaux supprimés après 30 jours. Les événements
de prêt ne sont pas supprimés par cette purge. Un message de prêt en échec peut
être régénéré depuis l'événement ; pour un lien de compte expiré, demander un
nouveau lien. Jetons d'invitation expirés effacés, intention d'adhésion supprimée
après 30 jours. Les rétentions des jetons de compte du lot 1 restent applicables.
La politique complète des historiques/droits RGPD est à finaliser avant ouverture
au lot 6, avec l'exploitant ; aucun compte réel ici.

## Transport et diagnostic privés

SMTP Django est interchangeable via `EMAIL_BACKEND`, `EMAIL_HOST/PORT`,
`EMAIL_FROM`, `EMAIL_HOST_USER/PASSWORD`, `EMAIL_USE_TLS` ou `EMAIL_USE_SSL`.
TLS et SSL simultanés sont refusés. En développement/test : hôte local/Mailpit
et aucun identifiant SMTP autorisés. Compose impose Mailpit ; aucun fournisseur
réel configuré, aucune délivrabilité réelle prétendue.

```sh
docker compose logs --tail=30 worker
docker compose exec web python manage.py process_outbox --once
# Uniquement en développement, crée un opérateur fictif sans mot de passe :
docker compose exec web python manage.py create_dev_operator --email operateur@example.test
docker compose exec web python manage.py ops outbox-status --operator operateur@example.test
docker compose exec web python manage.py ops retry-failed --operator operateur@example.test
```

Cette console exige **un accès OS de confiance** et un opérateur de plateforme
actif, vérifié, superuser ; connaître son adresse ne donne aucun accès HTTP.
Aucun opérateur automatique ni admin web. Un administrateur de communauté n'a
aucun droit global. La console ne propose pas de consultation générale des prêts.
Elle liste au plus 100 signalements/demandes de suppression à la fois.

```sh
docker compose exec web python manage.py ops reports --operator operateur@example.test
docker compose exec web python manage.py ops deletion-requests --operator operateur@example.test
# Remplacer les identifiants par ceux des données fictives à traiter :
docker compose exec web python manage.py ops hide-game --operator operateur@example.test --game-id UUID --reason 'Fiche abusive'
docker compose exec web python manage.py ops disable-user --operator operateur@example.test --user-id ID --reason 'Compte abusif'
```

`correct-game --metadata-file chemin.json --game-id UUID --reason …` accepte
seulement les métadonnées génériques validées ; le fichier doit être accessible
dans le conteneur. La correction/masquage clôt les signalements. Désactiver un
compte ou masquer une fiche retire les exemplaires et clôt les demandes devenues
inéligibles, sans effacer les prêts actifs. Une désactivation peut nécessiter la
[résolution opérateur du lot 4](lot-4-loans.md). Les mutations de modération sont
tracées (ainsi que la reprise manuelle de la file) dans `OperatorAction` (opérateur PROTECT, cible, motif limité, date UTC).
Ne jamais mettre de secret ou d'adresse de contact dans un motif.

## UX et suppression

Tableau de bord sans communauté avec accès à la collection privée, confirmations
après écritures, états de prêt/historique français, pagination des listes principales,
pages 400/403/404/500 indépendantes de la base. Formulaires HTML natifs avec labels,
erreurs et focus ; JavaScript local limité à l'état d'envoi et au message hors ligne.
Les validations serveur restent déterminantes, y compris sans JavaScript.
En cas de coupure après un POST, consulter Mes prêts avant de répéter l'action.

Mon espace → Mon compte propose une demande de suppression confirmée et persistée,
visible seulement par le titulaire et la console de confiance. Un prêt actif est
signalé ; la demande n'efface ni ne désactive immédiatement le compte. Le traitement
définitif, l'anonymisation et les délais/support réels sont à valider au lot 6 avant
lancement. `DeletionRequest.user` est OneToOne/PROTECT pour ne pas perdre une demande.

## Vérifications et limites

`./scripts/check.sh` : Ruff, mypy, Django, absence de migrations manquantes,
migrations réelles PostgreSQL, statiques et **120 tests réussis**. Tests d'intégration
de chaque événement, rollback, chiffrement/confidentialité, reprise après panne,
échec terminal/purge/reprise manuelle, workers concurrents avec PostgreSQL,
permissions opérateur, conservation des prêts actifs et demande de suppression.
Les erreurs de transport sont injectées dans ces tests ; aucun SMTP réel externe.

`scripts/product_browser_smoke.py` teste avec Chromium et Mailpit réels locaux :
inscription/vérification, invitation, réemploi/privé, accès croisés, prêt complet
malgré retrait, notifications reçues sans contacts, demande de suppression,
message hors ligne, formulaire sans JavaScript et captures 360/768/1280 px.
L'événement hors ligne est simulé dans le navigateur, pas une coupure du réseau mobile.
Les scénarios complets et commandes sont dans [le guide manuel](manual-validation.md).

Le build Compose complet ne tient pas dans le stockage Docker `vfs` de cet
environnement Cloud ; ici PostgreSQL/Mailpit en conteneurs et application sur
l'hôte. La CI vérifie une pile Compose propre et le profil HTTPS Codespaces simulé.
Pas de mesure de charge VPS, test matériel Android/tablette, audit d'accessibilité
exhaustif, vrai Codespace authentifié ni test de délivrabilité. Ces validations et
les tâches de préproduction restent à faire ; le lot 6 n'est pas commencé.
