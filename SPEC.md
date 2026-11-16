# Muqola — Spécifications produit (MVP)

> Les PR B et A implémentent le catalogue (section 5) et la recherche (section 6) ; la section 4 reste la cible de C.
> État du code, écarts et arbitrages : [audit](docs/plan-b-a-c.md).
> Arbitrages B1–B4 validés ; [catalogue B](docs/catalogue-refonte.md) et [recherche A : classement, confidentialité et mesures](docs/recherche-intelligente.md).

## 1. Vision
Muqola est une application web responsive, mobile-first, gratuite au lancement, permettant à des membres de communautés privées (amis, voisins, collègues) de partager leurs **exemplaires physiques de jeux de société** et de gérer leurs prêts. L'inscription à la plateforme est **ouverte à tous**, y compris pendant la bêta ; les communautés restent privées. Le nom Muqola est provisoire jusqu'à vérification des droits et du domaine.

### Objectif de validation
Deux personnes appartenant à une même communauté peuvent : créer leur compte, vérifier leur adresse e-mail, rejoindre la communauté, publier un jeu, le trouver, demander un prêt avec une date de retour souhaitée, accepter la demande, organiser l'échange par e-mail, confirmer la remise et le retour. Le parcours doit fonctionner sur téléphone.

## 2. Acteurs et autorisations
- **Visiteur** : voit uniquement une page publique de présentation et les pages légales ; ne voit ni jeux, ni membres, ni communautés.
- **Utilisateur inscrit non vérifié** : peut confirmer son e-mail, demander un nouveau lien et se déconnecter ; aucune opération métier sensible avant vérification.
- **Membre vérifié** : peut créer une communauté privée, y rejoindre via une invitation valide, gérer ses propres exemplaires, chercher dans ses communautés et emprunter des exemplaires autorisés.
- **Administrateur de communauté** : gère les paramètres de sa communauté, les invitations et les membres (y compris retrait). Aucun pouvoir d'administration global ni d'accès aux données privées d'autres communautés.
- **Administrateur de plateforme** : accès limité à des fonctions de modération/sécurité et de gestion des comptes (désactivation, validation des propositions, correction/fusion du catalogue et retrait d'une fiche abusive). Via un outil opérateur sécurisé documenté si besoin ; pas de tableau de bord d'administration requis. Les actions doivent être tracées, sans consultation générale des données privées. Ne valide pas les inscriptions.

## 3. Comptes et authentification
- Inscription **libre** par e-mail + mot de passe et nom d'affichage ; aucune validation humaine. E-mail unique normalisé, mot de passe robuste haché par une fonction reconnue, sessions sécurisées.
- Vérification obligatoire avant l'accès aux communautés, aux jeux et aux prêts. Lien opaque, aléatoire, stocké sous forme hachée, **à usage unique**, expiration par défaut **24 h** ; nouveau lien possible avec limitation de débit.
- Connexion/déconnexion et réinitialisation du mot de passe par lien opaque, à usage unique, expirant par défaut au bout de **1 h**. Invalider les sessions si nécessaire après réinitialisation.
- Réponses neutres lorsqu'une adresse existe ou non ; protections anti-bruteforce, anti-spam et limites de débit sur inscription, connexion, renvoi de lien et invitations. Ajouter un défi anti-bot uniquement si nécessaire, sans service payant obligatoire.
- Adresse e-mail de contact = **adresse du compte vérifiée**. Pas de changement d'e-mail dans le MVP : ce parcours sensible sera ajouté avec revalidation plus tard.
- Suppression de compte : fournir un moyen effectif de demander la suppression dès le lancement ; prévoir la suppression/anonymisation des données qui peuvent l'être et la résolution des prêts actifs avant clôture définitive, en informant l'utilisateur. Aucune conservation indéfinie par défaut ; détailler la politique réelle dans les documents légaux.
- Pas de connexion sociale, paiement, profil public ni annuaire public au MVP.

## 4. Communautés et invitations — cible PR C
- Tout utilisateur actif et vérifié peut créer une communauté et en devient administrateur. Un bouton « Créer une communauté » ouvre une **page dédiée** ; le formulaire n'est plus intégré à la liste.
- Une communauté conserve identifiant, nom, description facultative, créateur et dates. Chaque carte affiche une illustration **prédéfinie locale** choisie par l'administrateur (ou un visuel local par défaut), le nom, le nombre d'appartenances actives de comptes actifs et vérifiés, et le badge « Privée ». Toute la carte ouvre son détail via un lien sémantique accessible au clavier, sans liens/boutons imbriqués.
- **Décision C2 confirmée le 16 novembre 2026 : toutes les communautés restent privées.** Pas de mode public, pas d'annuaire ni de découverte publique, pas d'accès aux membres, exemplaires ou prêts hors des autorisations existantes. Illustrations locales prédéfinies uniquement ; aucun upload ni URL d'image arbitraire. Une éventuelle découverte publique nécessiterait une future décision produit séparée.
- Invitation par **lien partageable**, multiusage, permanent par défaut, aléatoire et difficile à deviner, révocable. L'absence d'expiration doit être explicite ; une expiration facultative peut être conservée. Un compte ne peut adhérer qu'une fois.
- **Tous les membres actifs et vérifiés** peuvent consulter et copier le lien courant de leur communauté. Seuls ses administrateurs peuvent le révoquer et le régénérer. Une régénération révoque **tous les anciens liens encore actifs** de manière atomique ; les membres accèdent ensuite au nouveau. Après révocation seule, l'écran explique l'absence de lien actif. Aucune création/régénération sur GET.
- L'invité voit le nom de la communauté et confirme son adhésion après connexion **et vérification de son e-mail** ; jamais d'adhésion silencieuse. Sans compte, conserver le parcours pendant inscription/vérification/connexion, puis **revérifier** validité, éventuelle expiration et révocation à la confirmation. Un lien périmé doit proposer de demander un nouveau lien aux membres.
- Les anciens liens expirés/révoqués ne sont jamais réactivés par migration. Chaque lien historique conserve son échéance ; le **lien courant** est le plus récent encore valide, et les autres liens historiques restent utilisables jusqu'à leur expiration ou révocation. La rotation admin les révoque tous. Aucun lien n'est créé implicitement sur GET.
- Les administrateurs gèrent paramètres et membres (dont retrait). Interdire de laisser une communauté sans administrateur ; conserver le transfert et la reprise opérateur tracée.
- Le lien n'accorde l'accès qu'à la communauté ciblée ; chaque lecture/écriture contrôle les droits serveur. Un ancien membre ou un membre d'une autre communauté ne peut consulter le lien, même par URL directe.
- Une personne peut appartenir à plusieurs communautés. Son départ/retrait coupe immédiatement les accès obtenus **uniquement** via cette communauté ; l'accès éventuel par d'autres communautés reste possible. Les demandes `REQUESTED` devenues inéligibles sont clôturées/annulées avec information des parties. Les prêts déjà `ACCEPTED`/`HANDED_OVER` restent consultables **par leurs deux parties seulement**, qui peuvent les clôturer normalement.
- Si le **propriétaire** part ou est retiré, enlever la visibilité de ses exemplaires dans cette communauté et fermer les demandes devenues inéligibles ; conserver les droits nécessaires aux prêts déjà acceptés.
- La suppression définitive d'une communauté n'est pas requise ; ne pas supprimer brutalement ses prêts ou historiques.

## 5. Jeux, catalogue interne et exemplaires — cible PR B
### Distinction indispensable
- **Game** : fiche générique d'un **jeu**, indépendante des éditions commerciales et des propriétaires. Plusieurs utilisateurs et plusieurs exemplaires d'un même utilisateur peuvent référencer la même fiche. Une autre boîte, langue, année ou édition commerciale ne justifie pas à elle seule une nouvelle fiche.
- **OwnedGame** : exemplaire physique d'un utilisateur, lié à un `Game`, avec notes/état facultatifs, retrait/archivage et disponibilité dérivée des prêts actifs.
- **GameVisibility** : partages explicites d'un exemplaire vers zéro, une ou plusieurs communautés de son propriétaire. Zéro = collection privée ; aucune visibilité implicite.

### Contenu et types
Une fiche **validée** exige un titre principal, un type de jeu et, si applicable, le jeu de base nécessaire. Distinguer jeu autonome, extension nécessitant une base, extension jouable seule. La relation de base est obligatoire pour l'extension dépendante, sans auto-référence ni cycle. **Une extension dépendante référence un seul jeu de base** ; les cas multibases sont reportés.

Titres alternatifs, illustration et informations de licence, joueurs min/max, durée, année, éditeur, description et identifiants externes restent **facultatifs**. Ne pas rendre l'illustration nécessaire à la validation : un visuel local de remplacement suffit. Conserver les bornes de champs, validations serveur et cohérence min/max. Les identifiants externes ne sont pas une source obligatoire de données.

### Ajout et propositions
1. Un compte actif et vérifié, même sans communauté, recherche une fiche du catalogue, puis la réutilise pour son exemplaire.
2. En l'absence de fiche pertinente, il **propose** une fiche : seul le titre est obligatoire ; le type « Je ne sais pas » est autorisé jusqu'à validation administrative. La proposition n'est pas publiée automatiquement comme fiche validée.
3. Un administrateur **de plateforme**, distinct d'un administrateur de communauté, vérifie les doublons, complète type/base si nécessaire puis valide, demande une correction ou rejette avec motif. Aucune publication par simple réutilisation d'une proposition.
4. **Le même `Game` en attente peut être lié à un exemplaire privé de son auteur** ; aucune visibilité publique, réutilisation par un tiers ni prêt avant validation. Les fiches héritées à réviser conservent les accès de prêt préexistants sans être publiées comme nouvelles fiches approuvées. Les propositions et leurs données privées ne sont visibles que par leur auteur et les opérateurs autorisés.
5. Le propriétaire peut modifier les détails, partages et retrait de son exemplaire. Retrait/masquage/perte de communauté ferme les `REQUESTED` devenues inéligibles, sans bloquer la clôture des prêts acceptés/remis. Aucun effacement physique d'exemplaire avec prêt actif ; conserver l'historique minimal.

### Gouvernance et confidentialité
- Seules les métadonnées génériques **validées** sont recherchables par tous les comptes vérifiés, sans révéler propriétaires, communautés, quantités privées ou adresses e-mail. Le formulaire explique la future visibilité de la fiche, distincte de celle de l'exemplaire.
- La correction du catalogue passe par une proposition de correction ou une opération administrative contrôlée ; un créateur ne peut réécrire directement une fiche validée partagée. Les détails de ses exemplaires restent modifiables. Conserver les signalements et la protection des fiches déjà réutilisées.
- Vérifier les doublons avant validation, **côté serveur aussi**. Un titre semblable ou identique n'est pas une preuve d'identité ; pas d'unicité globale du titre. Une homonymie réelle exige une justification administrative ; une édition différente seule n'est plus un motif suffisant.
- Prévoir correction et **fusion administrative logique sans suppression de la fiche source** (redirection contrôlée), avec trace auteur/motif/source/cible et conservation des références : exemplaires, propriétaires, partages, demandes/prêts, signalements, titres et identifiants externes. Ni suppression en cascade, ni perte d'anciens liens. Ne pas réafficher une fiche masquée par une fusion.
- Valider/borner tous les champs et échapper les contenus ; pas de HTML arbitraire. **Aucun upload photo utilisateur dans la PR B.** Toute future collecte et publication nécessite une décision distincte, le contrôle des droits/licence/attribution, un stockage sûr et une validation explicite. Conserver les illustrations Commons approuvées et le fallback local.

### Socle Wikidata/Commons déjà intégré (#25)
La recherche d'alias et les modèles `GameAlias`/`GameIllustration` existent depuis #25. Les illustrations Commons approuvées par l'exploitant (`approved_by_owner`) sont affichables avec leurs crédits et licence propres ; les données Wikidata CC0 restent distinctes de ces licences. Aucun téléchargement serveur automatique ni saisie d'URL/image par un utilisateur. Conserver ce socle et ses références dans B ; l'approbation de ces illustrations ne valide pas automatiquement de futures photos utilisateur. Les commandes d'import sont présentes, mais la cible ci-dessous ne prévoit aucun import des anciens CSV.

### Catalogue vide et données existantes
- Une **nouvelle base** démarre avec un catalogue vide ; aucun seed, import automatique, ancien CSV BGG ou Wikidata à importer. Ne jamais committer un catalogue réel dans Git ni l'embarquer dans une image Docker ; seuls des jeux de tests synthétiques minimaux sont acceptables.
- « Repartir vide » **n'autorise aucune purge** d'une base existante. Préserver UUID, exemplaires, propriétaires, visibilités, réservations/demandes, prêts et historique lors des migrations. Inventorier les fiches héritées et les faire réviser sans leur inventer un type ou une validation.
- Toute suppression de données ou réinitialisation d'une instance exige une validation explicite distincte, une sauvegarde restaurable et un retour arrière. La PR B ne supprime pas les données historiques ni les anciennes migrations.
- Les commandes historiques `import_games` et `import_wikidata_games` existent dans le code actuel : elles ne sont pas un parcours de la cible. Aucun import BGG/Wikidata dans ces trois PR. Les identifiants externes facultatifs conservés ne constituent pas une intégration externe.

## 6. Découverte et recherche — PR A
- Recherche instantanée **sans bouton « Rechercher »**, résultats actualisés sans rechargement après environ **deux caractères**, debounce d'environ **250 ms**. Les requêtes courtes affichent une aide ou l'état initial ; vider la saisie restaure cet état. Conserver un parcours de repli utilisable sans JavaScript.
- Chercher dans le titre principal et les titres alternatifs, avec casse, accents et espaces normalisés ; tolérer les fautes d'orthographe. Privilégier titre exact, puis préfixe/contenu, puis proximité approximative, avec ordre stable. PostgreSQL et `pg_trgm` si approprié ; ni Meilisearch ni Elasticsearch.
- Deux périmètres explicites : **catalogue validé** pour ajouter un exemplaire (sans informations de possession), **jeux accessibles dans les communautés** pour emprunter. Le mode emprunt ne doit pas suggérer un jeu trouvé uniquement dans le catalogue global ou une collection privée.
- Regrouper les exemplaires d'un même jeu : une fiche par résultat, disponibilité et compteurs calculés **sur les seuls exemplaires autorisés**. Dédupliquer un même exemplaire partagé dans plusieurs communautés ; garder les exemplaires physiques distincts et sélectionner ensuite celui à emprunter.
- Conserver les filtres disponibilité, communauté et nombre de joueurs si renseigné, les bornes de résultats et la pagination. Le filtrage des droits précède recherche, classement, agrégation et pagination, y compris sur endpoints asynchrones et suggestions.
- Proposer des fiches similaires avant soumission d'une proposition et avant validation administrative ; recontrôler côté serveur pour les POST directs et soumissions concurrentes. La recherche JS n'est jamais une garantie d'absence de doublon.
- Interface clavier, labels et focus stables, annonce accessible du chargement/du nombre de résultats/des erreurs. Ne pas remplacer la sélection par une réponse obsolète ; prévoir requêtes annulées, erreur réseau, aucun résultat et reconnexion. Aucune donnée privée dans résultats, compteurs, suggestions, filtres, erreurs ou caches.
- Fiche jeu : métadonnées génériques + exemplaires autorisés et disponibilité ; nom d'affichage du propriétaire uniquement, sans e-mail avant acceptation du prêt.

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
2. Alice crée une communauté par la page dédiée ; Bob rejoint par invitation après vérification. Tout membre peut copier le lien permanent courant ; seuls les administrateurs le révoquent/régénèrent. Un ancien lien révoqué ou à expiration dépassée échoue.
3. Alice propose un titre, un administrateur vérifie les doublons et valide avec type/base requis ; Bob réutilise cette fiche pour son exemplaire. Une édition différente ne crée pas une autre fiche.
4. Alice partage son exemplaire uniquement dans la communauté A ; un membre de B ne peut ni le voir ni le demander, même en appelant directement l'API.
5. Bob demande le jeu avec une date ; Alice accepte ; leurs e-mails deviennent visibles l'un à l'autre ; remise et retour clôturent le prêt.
6. Deux demandes simultanées ne peuvent jamais créer deux prêts acceptés sur le même exemplaire.
7. La révocation d'une invitation, le retrait d'un membre et la suppression de visibilité prennent effet immédiatement pour les **nouveaux accès**, tout en préservant la clôture des prêts déjà acceptés.
8. Une personne sans communauté peut proposer un titre et conserver son exemplaire **privé** ; elle peut rechercher le catalogue validé. Sa proposition ne devient pas publique automatiquement ; aucun upload photo n'est proposé dans B.
9. Alice ne réécrit pas arbitrairement une fiche validée ; chacun peut modifier son exemplaire. Une fusion administrative préserve exemplaires, propriétaires, partages, liens et prêts.
10. Une demande expirée ou devenue invisible ne peut pas être acceptée ; une demande en attente n'empêche pas les autres d'être déposées.
11. L'application fonctionne sur mobile, avec messages d'erreur et états de chargement accessibles.
12. Titres alternatifs, accents et fautes retrouvent le bon jeu ; la saisie actualise les résultats sans bouton ni rechargement ; clavier et mobile fonctionnent.
13. Deux exemplaires autorisés du même jeu sont regroupés ; une copie privée ou une communauté étrangère ne modifie aucun compteur ni résultat.
14. Une base neuve reste vide ; une migration sur base peuplée conserve les références et les prêts de tous états, sans import ni purge.
