# Muqola — Contraintes et décisions d'architecture

## Liberté encadrée
**Codex choisit et justifie la stack exacte** (framework web, langage, ORM, bibliothèque UI, tests). Avant l'implémentation, produire un court ADR (`docs/adr/0001-stack.md`) comparant au moins deux options, avec arguments de rapidité, maintenabilité, sécurité, disponibilité des bibliothèques et simplicité d'exploitation. Favoriser un écosystème mature, bien documenté et adapté au développement assisté par IA ; ne pas choisir une technologie seulement parce qu'elle est tendance.

## Contraintes non négociables
- Monolithe modulaire, pas de microservices, Kubernetes ou architecture événementielle distribuée.
- Base relationnelle **PostgreSQL** avec migrations versionnées.
- Application web responsive ; pas de client mobile natif.
- Déploiement sur **petit VPS Linux indépendant** (cible 2 vCPU / 4 Go RAM / ~40 Go SSD), Docker Compose, reverse proxy Caddy et HTTPS ; ne pas dépendre d'un fournisseur VPS précis.
- Services logiques : identité, communautés, catalogue, exemplaires/visibilité, prêts, notifications, administration.
- API et contrôles d'accès côté serveur, requêtes paramétrées, protection CSRF si sessions cookies, cookies Secure/HttpOnly/SameSite adaptés, validation serveur, gestion sûre des secrets.
- Modèle de données et migrations pensés pour éviter les prêts concurrents ; **contrainte d'unicité partielle PostgreSQL** pour un `Loan` actif (`ACCEPTED`/`HANDED_OVER`) par exemplaire, plus vérification transactionnelle ; tests de concurrence avec vrai PostgreSQL.
- Intégration e-mail remplaçable (SMTP ou API) ; environnement de développement avec boîte de capture locale. **Outbox en PostgreSQL** et worker léger reprenant après redémarrage (pas de broker dédié).
- Fichiers de configuration d'exemple sans secrets ; aucun secret ni données réelles dans Git.

## Modèle logique minimal
- `User` : id, email normalisé unique, hash mot de passe, date vérification, nom d'affichage, dates.
- `EmailVerificationToken`, `PasswordResetToken` : valeur hachée, expiration, consommation.
- `Community`, `Membership` (rôle, statut), `CommunityInvite` (token haché, expiration, révocation, créateur).
- `Game` : métadonnées génériques, `createdBy`, source externe/id optionnels. Fiche partagée ; modification par créateur seulement si non réutilisée par autrui, sinon modération.
- `OwnedGame` : gameId, ownerId, détails d'exemplaire, indicateur « retiré du prêt » ; zéro ou plusieurs communautés de visibilité.
- `GameVisibility` : ownedGameId, communityId ; unicité de la paire ; vérifier l'appartenance du propriétaire et l'absence de partage implicite.
- `Loan` : ownedGameId, borrowerId, ownerId, état, `dueDate` (DATE), dates de transition horodatées, message facultatif ; protéger l'exclusivité des prêts actifs par index partiel. Interdire les `REQUESTED` en double pour un même couple (exemplaire, emprunteur).
- `EmailOutbox` : type, destinataire, référence d'événement, statut/essais, prochaine tentative, dates ; ne pas conserver de jetons en clair dans les logs.
- Journal minimal des événements sensibles sans stockage inutile de données personnelles.

Documenter précisément clés étrangères, règles `ON DELETE`, contraintes d'unicité/index, politiques d'anonymisation et invariants des transitions. Indexer les recherches par titre, les appartenances/visibilités et les prêts par participant. **Les autorisations ne doivent pas reposer sur les seuls IDs fournis par le navigateur.**

## Fiabilité et exploitation
- Healthcheck, logs structurés sans secrets, politique de redémarrage, volumes persistants, migrations au déploiement **avec sauvegarde et procédure de retour arrière**, arrêt gracieux. Définir des limites mémoire raisonnables pour un VPS 4 Go. Pas d'images de production générées à partir de secrets.
- CI : format/lint, vérification de types si disponible, tests unitaires et intégration avec PostgreSQL ; build Docker.
- Sauvegardes quotidiennes **hors VPS**, rétention définie, chiffrement et procédure de restauration testée avant ouverture ; ne pas se contenter d'un volume Docker ou d'un snapshot non testé.
- Processus de déploiement reproductible et rollback documenté. Pas de déploiement automatique en production sans validation explicite.
- Dépendances maintenues, vérification de vulnérabilités, limitation de débit et protection anti-spam sur les endpoints publics.
- Politique de confidentialité, mentions légales, CGU adaptées au service, cookies (aucun traceur non nécessaire sans conformité), droits RGPD, durée de conservation et point de contact avant ouverture. Renseigner les coordonnées de l'exploitant et de l'hébergeur avec les **vraies** informations : ne jamais inventer de mentions légales. Prévoir une procédure de gestion des incidents de données.

## Hébergement et e-mails
Variables d'environnement pour URL publique, base PostgreSQL, secrets de session, fournisseur d'e-mails, adresse expéditrice, domaine. Documenter DNS A/AAAA, MX si réception nécessaire, SPF/DKIM/DMARC pour l'envoi, HTTPS. L'envoi d'e-mails de vérification doit être opérationnel avant ouverture des inscriptions.

## Sécurité particulière
- Vérifier l'appartenance et la visibilité pour **chaque** lecture et écriture ; tests IDOR entre communautés. Gérer explicitement l'accès des deux participants à un prêt déjà accepté après leur retrait d'une communauté, sans restaurer leur accès au catalogue.
- Éviter d'exposer des e-mails de membres, sauf aux deux parties d'un prêt accepté.
- Ne pas révéler l'existence d'une communauté privée par les réponses publiques.
- Les invitations sont des secrets : token fort, stockage haché, expiration, révocation, aucune journalisation du token brut. Protéger le token dans les URL contre les fuites par `Referer`, analytics ou logs ; éviter le contenu tiers sur l'écran d'invitation.
- Protéger les entrées libres contre XSS et les sorties contre injection ; ne pas rendre de HTML utilisateur, de fichiers ou d'images distantes arbitraires au MVP. Mettre en place une politique CSP proportionnée, et limiter la taille des requêtes.
- Prévoir une suppression de compte sûre, y compris en présence de prêts en cours, avec procédure documentée. Prévoir une méthode opérateur minimale pour désactiver un compte ou retirer une fiche abusive, sans interface d'administration complète.
