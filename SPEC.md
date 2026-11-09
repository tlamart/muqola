# Muqola — Spécifications produit (MVP)

## 1. Vision
Muqola est une application web responsive, mobile-first, gratuite au lancement, permettant à des membres de communautés privées (amis, voisins, collègues) de partager leurs **exemplaires physiques de jeux de société** et de gérer leurs prêts. L'inscription à la plateforme est **ouverte à tous**, y compris pendant la bêta ; les communautés restent privées. Le nom Muqola est provisoire jusqu'à vérification des droits et du domaine.

### Objectif de validation
Deux personnes appartenant à une même communauté peuvent : créer leur compte, vérifier leur adresse e-mail, rejoindre la communauté, publier un jeu, le trouver, demander un prêt avec une date de retour souhaitée, accepter la demande, organiser l'échange par e-mail, confirmer la remise et le retour. Le parcours doit fonctionner sur téléphone.

## 2. Acteurs et autorisations
- **Visiteur** : voit uniquement une page publique de présentation et les pages légales ; ne voit ni jeux, ni membres, ni communautés.
- **Utilisateur inscrit non vérifié** : peut confirmer son e-mail, demander un nouveau lien et se déconnecter ; aucune opération métier sensible avant vérification.
- **Membre vérifié** : peut créer une communauté privée, y rejoindre via une invitation valide, gérer ses propres exemplaires, chercher dans ses communautés et emprunter des exemplaires autorisés.
- **Administrateur de communauté** : gère les paramètres de sa communauté, les invitations et les membres (y compris retrait). Aucun pouvoir d'administration global ni d'accès aux données privées d'autres communautés.
- **Administrateur de plateforme** : accès limité à des fonctions de modération/sécurité et de gestion des comptes (désactivation et retrait d'une fiche abusive). Via un outil opérateur sécurisé documenté si besoin ; pas de tableau de bord d'administration requis. Les actions doivent être tracées, sans consultation générale des données privées. Ne valide pas les inscriptions.

## 3. Comptes et authentification
- Inscription **libre** par e-mail + mot de passe et nom d'affichage ; aucune validation humaine. E-mail unique normalisé, mot de passe robuste haché par une fonction reconnue, sessions sécurisées.
- Vérification obligatoire avant l'accès aux communautés, aux jeux et aux prêts. Lien opaque, aléatoire, stocké sous forme hachée, **à usage unique**, expiration par défaut **24 h** ; nouveau lien possible avec limitation de débit.
- Connexion/déconnexion et réinitialisation du mot de passe par lien opaque, à usage unique, expirant par défaut au bout de **1 h**. Invalider les sessions si nécessaire après réinitialisation.
- Réponses neutres lorsqu'une adresse existe ou non ; protections anti-bruteforce, anti-spam et limites de débit sur inscription, connexion, renvoi de lien et invitations. Ajouter un défi anti-bot uniquement si nécessaire, sans service payant obligatoire.
- Adresse e-mail de contact = **adresse du compte vérifiée**. Pas de changement d'e-mail dans le MVP : ce parcours sensible sera ajouté avec revalidation plus tard.
- Suppression de compte : fournir un moyen effectif de demander la suppression dès le lancement ; prévoir la suppression/anonymisation des données qui peuvent l'être et la résolution des prêts actifs avant clôture définitive, en informant l'utilisateur. Aucune conservation indéfinie par défaut ; détailler la politique réelle dans les documents légaux.
- Pas de connexion sociale, paiement, profil public ni annuaire public au MVP.

## 4. Communautés privées
- Tout utilisateur vérifié peut créer une communauté et en devient administrateur.
- Une communauté comporte au minimum : identifiant, nom, description facultative, créateur, dates de création/modification.
- Invitation par **lien partageable** doté d'un jeton aléatoire non devinable, **multiusage**, révocable et expirant (défaut **7 jours**, configurable). Un compte ne peut adhérer qu'une fois. L'invité voit le nom de la communauté et confirme son adhésion après connexion **et vérification de son e-mail** ; ne jamais adhérer silencieusement.
- Si l'invité n'a pas de compte, conserver le parcours d'invitation durant inscription/vérification/connexion, puis **revérifier** expiration et révocation lors de l'adhésion. Si le lien a expiré entre-temps, expliquer comment demander un nouveau lien, sans contourner l'expiration.
- Les administrateurs peuvent générer, consulter et révoquer les invitations, voir les membres et retirer un membre. Interdire de laisser une communauté sans administrateur (transfert ou suppression explicite).
- Le lien n'accorde l'accès qu'à la communauté ciblée ; contrôle côté serveur, pas seulement dans l'interface.
- Une personne peut appartenir à plusieurs communautés.
- Quand un membre quitte une communauté ou en est retiré, son accès aux exemplaires visibles **uniquement** via cette communauté cesse immédiatement ; il conserve l'accès éventuel via ses autres communautés. Les demandes `REQUESTED` qui ne sont plus autorisées deviennent non acceptables et sont clôturées/annulées avec information des parties. Les prêts déjà `ACCEPTED` ou `HANDED_OVER` restent consultables **par leurs deux parties seulement**, avec possibilité de les clôturer normalement, même si l'appartenance est perdue.
- Si le **propriétaire** quitte une communauté ou en est retiré, retirer automatiquement la visibilité de ses exemplaires dans cette communauté ; ne plus accepter les demandes devenues inéligibles. Conserver uniquement les droits nécessaires aux prêts déjà acceptés.
- La suppression définitive d'une communauté n'est pas requise dans le MVP ; ne pas la simuler par une suppression brutale de prêts ou de données nécessaires.

## 5. Jeux, catalogue interne et exemplaires
### Distinction indispensable
- **Game** : fiche de référence d'un jeu (titre obligatoire ; éditeur, année, nombre de joueurs min/max, durée, description et image facultatifs).
- **OwnedGame** : exemplaire physique appartenant à un utilisateur, lié à un `Game` ; état/commentaire facultatif, disponibilité dérivée des prêts actifs, propriétaire.
- **GameVisibility** : communautés dans lesquelles un exemplaire est visible, choisies explicitement par le propriétaire, parmi ses communautés uniquement.

### Ajout d'un jeu — comportement MVP
1. L'utilisateur recherche par titre dans le **catalogue interne** des fiches `Game` déjà créées sur Muqola (recherche insensible à la casse, aux accents et aux espaces superflus si possible).
2. Il sélectionne une fiche existante et crée son propre `OwnedGame` ; **ou** crée une nouvelle fiche `Game` manuellement si aucun résultat ne convient. Un même utilisateur peut posséder plusieurs exemplaires physiques du même `Game`.
3. Il peut sélectionner **zéro, une ou plusieurs** de ses communautés pour partager l'exemplaire. **Zéro = collection privée invisible aux autres** ; indispensable si l'utilisateur n'a pas encore rejoint de communauté. Aucune visibilité implicite.
4. Il peut modifier les détails de son exemplaire, son partage et son statut « retiré du prêt ». Les exemplaires retirés ne sont plus proposés aux emprunteurs ; les prêts actifs restent clôturables.
5. La suppression physique d'un exemplaire est interdite tant qu'un prêt `ACCEPTED`/`HANDED_OVER` existe. En cas de retrait/masquage ou de perte de toutes les communautés communes, fermer les demandes `REQUESTED` devenues inéligibles ; préserver l'historique minimal des prêts.

### Confidentialité et gouvernance du catalogue
Le catalogue `Game` contient uniquement des **métadonnées génériques sur les jeux** : il peut être recherché par tout membre connecté et vérifié, même sans communauté, mais ne doit jamais révéler les propriétaires, communautés ou quantités d'exemplaires privés. Préciser dans le formulaire que la fiche générique est **visible à tous les comptes vérifiés** ; ne pas y saisir de données personnelles.
- Pour éviter qu'un utilisateur réécrive une fiche adoptée par d'autres : une fiche peut être corrigée par son créateur uniquement tant qu'aucun **autre utilisateur** ne l'a réutilisée ; au-delà, toute correction passe par une intervention de modération/maintenance. Les champs de son propre `OwnedGame` restent modifiables.
- Validation et limites de taille pour tous les champs libres ; pas de HTML arbitraire ni de contenu actif. Prévoir une procédure simple de signalement/correction d'une fiche erronée ou abusive, sans console d'administration complexe.

### Doublons, images et catalogue externe
- Suggérer les fiches existantes avant création ; ne pas imposer l'unicité du titre car des jeux distincts peuvent porter des noms semblables. Contrôler uniquement les IDs externes non nuls quand ils existeront.
- Prévoir `externalSource` et `externalId` facultatifs et une couche d'import indépendante, mais **aucune API externe requise au MVP**.
- **MVP : visuel de remplacement neutre**, sans chargement automatique de couvertures ni dépôt/URL d'image fournie par les utilisateurs. Intégrations externes et illustrations enrichies après vérification des licences, attribution et sécurité.

## 6. Découverte et recherche
- Tableau de bord des jeux accessibles à l'utilisateur via l'union de ses communautés, avec déduplication d'un même exemplaire partagé dans plusieurs communautés.
- Recherche par titre ; filtres disponibilité, communauté, nombre de joueurs (si renseigné).
- Fiche jeu : métadonnées génériques + exemplaires visibles et leur disponibilité ; informations minimales sur le propriétaire (nom d'affichage), sans e-mail avant acceptation d'un prêt.
- Aucun exemplaire invisible ne doit être renvoyé par l'API, les compteurs, les filtres ou les erreurs.

## 7. Cycle de prêt
### États
`REQUESTED` → `ACCEPTED` → `HANDED_OVER` → `RETURNED`.
États terminaux alternatifs : `DECLINED`, `CANCELLED` (avant remise). Prévoir un mécanisme explicite de résolution administrative des prêts bloqués, documenté, sans l'exposer inutilement dans le MVP.

### Règles
- Un emprunteur doit être membre d'au moins une communauté dans laquelle l'exemplaire est partagé **à la demande ET à l'acceptation** ; le propriétaire doit encore pouvoir le prêter. Le propriétaire ne peut jamais emprunter son propre exemplaire.
- Une demande inclut une **date de retour souhaitée obligatoire**, strictement postérieure au jour courant dans le fuseau `Europe/Paris`, et un message facultatif. Même contrôle à l'acceptation : une ancienne demande dont la date est passée ne peut pas être acceptée ; inviter à refaire une demande. Stocker cette échéance comme **date civile** ; stocker les événements horodatés en UTC. Pas de calendrier de réservation au MVP.
- Seul le **propriétaire** accepte ou refuse une demande et confirme la **remise** puis le **retour**. L'emprunteur et le propriétaire peuvent annuler une demande `REQUESTED` ou un prêt `ACCEPTED` avant la remise ; après `HANDED_OVER`, pas d'annulation ordinaire : retour ou résolution documentée.
- **Une seule demande acceptée ou prêt remis actif par exemplaire** : des demandes `REQUESTED` multiples sont possibles, mais un même emprunteur ne peut en avoir qu'une en attente par exemplaire. L'acceptation doit être atomique et protégée par une contrainte en base (par ex. index unique partiel sur `ACCEPTED` et `HANDED_OVER`) **et** transaction. En cas d'acceptation, clore les demandes concurrentes encore en attente avec motif compréhensible et notification.
- Un exemplaire est **disponible** lorsqu'il n'est ni retiré du prêt ni associé à un prêt `ACCEPTED`/`HANDED_OVER` ; une demande `REQUESTED` ne le réserve pas. Ne pas créer de nouvelle demande sur un exemplaire indisponible, et informer clairement les emprunteurs de cette règle.
- En cas de retrait du jeu, perte de visibilité ou changement de communauté **avant l'acceptation**, ne pas accepter une demande devenue non autorisée ; fermer les demandes inéligibles. **Après acceptation**, même si les participants quittent la communauté, le prêt reste visible uniquement aux deux parties et peut être clôturé.
- Après acceptation, afficher l'adresse e-mail vérifiée de contact aux deux participants **tant que le prêt est `ACCEPTED` ou `HANDED_OVER`**. Ne pas l'exposer dans un historique `RETURNED`, `DECLINED` ou `CANCELLED`. Expliquer avant la demande qu'une adresse déjà communiquée ne peut pas être « reprise ».
- Toutes les transitions doivent vérifier, côté serveur, acteur autorisé, état courant et propriétés de la ressource. Historique des prêts accessible uniquement aux participants, jamais aux tiers.
- Muqola facilite la coordination ; il ne détient pas les jeux et ne garantit ni leur état ni leur restitution.

## 8. Notifications
E-mails transactionnels pour : vérification, réinitialisation, demande de prêt, acceptation/refus, annulation, remise et retour. Une notification de rappel avant échéance peut être ajoutée après la bêta.
- Service d'envoi interchangeable ; en développement, capture locale des e-mails sans envoi réel.
- Ne jamais exposer les clés API côté client ; éviter les données sensibles superflues dans les messages.
- Les échecs d'envoi ne doivent pas annuler un prêt déjà validé ni perdre silencieusement la notification : utiliser une **file transactionnelle simple en base** (outbox) et un mécanisme documenté de traitement/reprise, sans Redis ni broker supplémentaire au MVP. Envoi potentiellement répété à gérer aussi proprement que possible.

## 9. Écrans minimum
Accueil public ; inscription ; confirmation e-mail ; connexion ; mot de passe oublié ; tableau de bord (dont état « aucune communauté ») ; liste/création/détail communauté ; gestion des invitations/membres ; catalogue/recherche ; création d'une fiche jeu ; ajout/édition d'un exemplaire ; fiche d'exemplaire ; mes demandes/prêts ; détail d'un prêt ; profil/compte et demande de suppression ; pages légales ; erreurs 403/404/500. Les outils de modération de plateforme peuvent être des **commandes d'administration sécurisées** au MVP, pas un tableau de bord sophistiqué.

## 10. Hors périmètre MVP
Chat, avis/réputation, paiements, dons, abonnements, assurance, événements, objets autres que jeux, carte géographique, catalogue externe obligatoire, application mobile native, notifications push, fonctionnalités sociales publiques, administration sophistiquée, multilingue, système de réservation à créneaux.

## 11. Critères d'acceptation de bout en bout
1. Un inconnu s'inscrit, reçoit un lien, vérifie son e-mail, puis se connecte ; avant vérification, l'accès métier est refusé.
2. Alice crée une communauté, génère un lien ; Bob s'inscrit via ce lien et rejoint après vérification ; un lien révoqué/expiré échoue.
3. Alice crée une fiche `Game` et un exemplaire ; Bob trouve la fiche existante et ajoute son propre exemplaire sans créer de doublon obligatoire.
4. Alice partage son exemplaire uniquement dans la communauté A ; un membre de B ne peut ni le voir ni le demander, même en appelant directement l'API.
5. Bob demande le jeu avec une date ; Alice accepte ; leurs e-mails deviennent visibles l'un à l'autre ; remise et retour clôturent le prêt.
6. Deux demandes simultanées ne peuvent jamais créer deux prêts acceptés sur le même exemplaire.
7. La révocation d'une invitation, le retrait d'un membre et la suppression de visibilité prennent effet immédiatement pour les **nouveaux accès**, tout en préservant la clôture des prêts déjà acceptés.
8. Une personne sans communauté peut créer une fiche et son exemplaire **privé** ; la recherche interne reste possible.
9. Une fiche `Game` réutilisée par Bob ne peut plus être modifiée arbitrairement par Alice ; chacun peut modifier son propre exemplaire.
10. Une demande expirée ou devenue invisible ne peut pas être acceptée ; une demande en attente n'empêche pas les autres d'être déposées.
11. L'application fonctionne sur mobile, avec messages d'erreur et états de chargement accessibles.
