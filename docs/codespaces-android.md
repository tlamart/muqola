# Tester Muqola depuis Android avec un Codespace privé

Ce profil utilise le lot 1 et les mêmes Django/PostgreSQL/Mailpit/worker que
`compose.yaml`. C'est une prévisualisation de développement, avec des données
fictives et sans VPS, fournisseur d'e-mails réel ni déploiement de production.
L'authentification GitHub protège l'accès au Codespace ; les comptes Muqola à
l'intérieur gardent leur propre inscription/vérification/connexion.

## 1. Créer le Codespace depuis Chrome Android

1. Connectez-vous à GitHub dans Chrome. Dans le menu ⋮ de Chrome, activez
   **Version pour ordinateur**. Le mode paysage facilite l'éditeur web.
2. Vérifiez votre quota gratuit Codespaces et désactivez toute dépense au-delà
   de ce quota. La configuration ne provisionne aucun service payant ; ne
   souscrivez pas d'offre payante si GitHub indique que le quota est épuisé.
3. Ouvrez [la création du Codespace sur la branche de prévisualisation](https://github.com/codespaces/new?repo=1451197982&ref=feat%2Fcodespaces-preview).
   Vérifiez dépôt `tlamart/muqola`, branche **feat/codespaces-preview**, puis
   sélectionnez la machine **2 cœurs** et créez le Codespace.
4. Attendez la construction du conteneur. Elle installe Python 3.12, Docker
   Compose v2 dans un Docker de développement isolé, et GitHub CLI. Les données
   et images de ce Docker ne sont pas celles d'un VPS ou d'une production.
5. Dans l'éditeur web, ouvrez **Terminal** si nécessaire. Le démarrage est lancé
   automatiquement à l'ouverture de l'éditeur. Attendez le message
   **Muqola prête — accès privé avec votre compte GitHub** et les deux URL.
   Le premier build et les migrations peuvent prendre plusieurs minutes.

Il n'est pas nécessaire de fusionner la PR de prévisualisation pour créer ce
Codespace sur sa branche. Cette branche contient le lot 1 sans modifier sa PR 2.
La PR de configuration cible temporairement la branche du lot 1 pour afficher
uniquement son propre diff ; la recibler vers main après fusion de la PR 2,
sans la fusionner dans la branche du lot 1.

## 2. Si GitHub CLI demande une autorisation

Le démarrage refuse de lancer les services s'il ne peut pas fixer **et vérifier**
les deux ports privés. Une autorisation CLI peut être nécessaire même si Chrome
est déjà connecté à GitHub. Les jetons fournis automatiquement au Codespace
n'ont pas toujours la portée nécessaire.

Dans le terminal du Codespace, collez :

```sh
env -u GH_TOKEN -u GITHUB_TOKEN gh auth login --hostname github.com --git-protocol https --web --scopes codespace
```

Suivez le lien d'authentification affiché dans un nouvel onglet Chrome et saisissez
le code à usage court, avec **le même compte GitHub que le propriétaire du
Codespace**. Cette autorisation sert à gérer/vérifier les ports de vos Codespaces.
Ne copiez aucun jeton dans le dépôt, le chat ou un formulaire Muqola.
Revenez au terminal et relancez :

```sh
bash .devcontainer/start.sh
```

Si l'erreur concerne des ports absents, ouvrez l'onglet **Ports**, ajoutez **8000**
et **8025**, choisissez **Private**, puis relancez la même commande. Si d'autres
ports y figurent, supprimez leurs transferts avant de relancer. Le profil ne
transfère jamais PostgreSQL ou SMTP.

## 3. Ouvrir l'application et les e-mails

Dans l'onglet **Ports**, seuls ces deux ports doivent être présents :

| Port | Service | Visibilité GitHub | URL extérieure |
| --- | --- | --- | --- |
| 8000 | Muqola | **Private** | `https://<nom-du-codespace>-8000.app.github.dev` |
| 8025 | Mailpit | **Private** | `https://<nom-du-codespace>-8025.app.github.dev` |

Utilisez les liens réellement affichés par le terminal/onglet Ports ; ne recopiez
pas les exemples avec chevrons. Ouvrez-les dans deux onglets Chrome normaux.
GitHub peut vous demander de vous reconnecter ou d'autoriser la page transférée.

Le protocole **interne** du port reste **HTTP**, tel que défini dans devcontainer.
L'URL **externe** est bien HTTPS : GitHub termine TLS. Ne basculez pas le
protocole interne sur HTTPS, Django/Mailpit n'y servent pas de certificat TLS.
Ne choisissez jamais `Public` ou `Private to organization` : `Private` réserve
l'accès au propriétaire connecté à GitHub.

Contrôle manuel indispensable au premier essai : ouvrez chaque URL dans un
onglet de navigation privée **non connecté à GitHub**. Vous devez obtenir une
barrière/connexion GitHub ou un refus, jamais Muqola ni la boîte Mailpit. Refermez
ensuite cet onglet privé et poursuivez dans vos onglets normaux. Le propriétaire
peut toujours changer manuellement les réglages GitHub ; ne le faites pas. Le
script réapplique et vérifie Private à chaque démarrage/réouverture d'éditeur.

## 4. Tester l'inscription, la vérification et la connexion

1. Dans Muqola, touchez **S'inscrire**. Utilisez un nom fictif, par exemple
   **Camille**, une adresse **camille@example.test** et un mot de passe de test
   unique d'au moins 12 caractères. N'utilisez ni vraie adresse ni mot de passe
   déjà utilisé ailleurs.
2. Après inscription, connectez-vous avec ce compte : l'écran doit demander de
   **vérifier votre adresse e-mail**, et l'espace doit rester inaccessible.
3. Dans l'onglet **Mailpit privé**, attendez quelques secondes, actualisez et
   ouvrez **Confirmez votre adresse e-mail** destiné à camille@example.test.
   Aucun e-mail n'est envoyé à une messagerie extérieure.
4. Touchez le lien HTTPS du message. Il doit revenir sur **le port 8000 du même
   Codespace**, puis touchez **Confirmer mon e-mail**. Un compte Muqola déjà
   connecté n'est pas requis ; l'accès GitHub au port privé reste requis.
5. Connectez-vous à Muqola : vous devez voir **Bienvenue, Camille**. Vous pouvez
   alors vous déconnecter puis vous reconnecter. Les communautés et prêts ne
   sont pas encore disponibles.
6. Facultatif : testez **Mot de passe oublié**. Lisez le nouveau message dans
   Mailpit, choisissez un autre mot de passe fictif puis reconnectez-vous.

Les liens de vérification expirent après 24 h, ceux de reset après 1 h. Ils sont
à usage unique ; un renvoi remplace le lien précédent. Si vous avez déjà inscrit
la même adresse, utilisez la connexion/renvoi, ou une autre adresse fictive telle
que camille2@example.test. Le worker réessaie les envois après erreur.

## 5. Arrêter et reprendre sans frais inutiles

Fermer Chrome ne garantit pas l'arrêt immédiat du Codespace. Dans
[Vos Codespaces](https://github.com/codespaces), utilisez **Stop codespace**
après votre essai et configurez un délai d'inactivité court dans GitHub.
L'arrêt conserve l'espace et le volume PostgreSQL ; le stockage reste soumis au
quota de votre compte. Supprimez le Codespace pour supprimer aussi cet espace de
test lorsque vous n'en avez plus besoin.

Pour reprendre, rouvrez le Codespace : le démarrage est relancé. Au besoin :

```sh
bash .devcontainer/start.sh
```

Cette commande conserve `.env` et le volume, ne crée pas de nouveaux secrets à
chaque ouverture et ne réinitialise pas les comptes. La réouverture de l'éditeur
ne coupe pas un Mailpit déjà sain. Les messages Mailpit restent éphémères :
un arrêt réel du service peut les effacer ; demandez alors un nouveau lien.
Ne changez pas le secret serveur avec une file d'e-mails encore en attente.

## Dépannage dans le terminal du Codespace

```sh
# Statut du profil uniquement :
docker compose --project-name muqola-codespaces -f compose.yaml -f .devcontainer/compose.codespaces.yaml ps
# Derniers événements, sans afficher les secrets d'environnement :
docker compose --project-name muqola-codespaces -f compose.yaml -f .devcontainer/compose.codespaces.yaml logs --tail=40 web worker migrate
```

- **403 de formulaire** : utilisez l'URL HTTPS actuelle du port 8000 ; rechargez
  le formulaire pour renouveler le jeton CSRF. N'utilisez pas l'URL du port 8025
  pour Django, ni l'URL d'un autre Codespace.
- **400 hôte refusé** : même vérification ; le profil autorise seulement le nom
  exact calculé depuis les variables GitHub et les hôtes locaux de healthcheck.
- **Pas d'e-mail** : vérifier worker/Mailpit, actualiser la capture et demander
  un nouveau lien. L'expéditeur reste fictif `notifications@example.test`.
- **Démarrage refusé** : contrôler l'autorisation CLI et la visibilité Private.
  Ne contournez pas le contrôle en lançant manuellement les services exposés.
- **Quota ou politique d'organisation** : arrêter le Codespace et régler le
  problème dans GitHub sans activer une option payante par défaut.

## Isolation et validation technique

Les réglages spécifiques sont dans `config.codespaces`, sélectionné seulement
par le complément Compose `.devcontainer/compose.codespaces.yaml`. Le profil
refuse APP_ENV=production/test et une exécution hors Codespaces. Il calcule une
origine exacte, sans wildcard ALLOWED_HOSTS/CSRF et sans faire confiance aux
en-têtes X-Forwarded-Proto. Cookies Secure/HttpOnly/SameSite et hôtes de cookie
limités au domaine de l'application. Aucun changement de config/settings.py ni
désactivation CSRF en production.

Le projet Compose **muqola-codespaces**, l'image **muqola:codespaces**, son volume
et le Docker de développement sont distincts des services locaux/production.
PostgreSQL et SMTP ne publient aucun port hôte ; les ports HTTP sont liés à
127.0.0.1, puis transférés de façon privée par GitHub. La découverte automatique
des autres ports et leur restauration sont désactivées. Les services n'ont pas
de redémarrage automatique avant le contrôle de visibilité GitHub.

Vérifications automatisées : Ruff/mypy, tests PostgreSQL, refus des origines
étrangères et des hôtes arbitraires, cookies Secure, refus d'utiliser le profil
en production, refus de démarrer sur visibilité publique/inconnue, validation
Dev Containers CLI et fusion Compose. Le smoke du profil soumet réellement les
formulaires au backend avec Host/Origin HTTPS tels que transmis par le proxy,
reçoit le lien HTTPS dans Mailpit et confirme vérification/connexion.

Limite explicite : la CI vérifie ce backend et le Compose, pas le service
GitHub d'authentification/forwarding ni un téléphone Android physique. Le premier
Codespace réel et le contrôle en navigation privée ci-dessus restent à tester
par son propriétaire. Aucun Codespace ni ressource payante n'est créé par la CI.

Références : [ports GitHub Codespaces](https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace),
[GitHub CLI — visibilité](https://cli.github.com/manual/gh_codespace_ports_visibility).
