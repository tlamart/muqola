# PR C — Communautés privées et invitations

Branche indépendante `feat/communautes-refonte`, depuis `main` 46362f1. C1 et C2 appliqués ; aucun changement catalogue B/A, aucun déploiement.

## Parcours et droits

La liste GET `/communities/` contient un lien vers `/communities/new/` (GET/POST), des cartes entièrement cliquables au clavier, trois illustrations SVG originales locales et le badge Privée. Le compte exclut les appartenances retirées et les comptes inactifs/non vérifiés. La requête agrège les comptes en SQL, sans requête par communauté. L’illustration est une valeur de liste fermée ; fallback local `table`, aucune URL ou collecte d’image.

Tous les membres actifs/vérifiés lisent le lien courant sur le détail privé. L’adhésion exige toujours une confirmation explicite et la vérification du compte. Consultation, retrait, adhésion et mutations sont sérialisés par le verrou `domain_write` existant ; les droits sont revérifiés avant déchiffrement. Le lien est affiché dans un champ sélectionnable sans JS. Le bouton de copie annonce succès ou échec et sélectionne le texte si Clipboard est refusé.

Seul un admin peut générer/régénérer ou révoquer par POST avec CSRF et limites de débit. La confirmation indique la portée de l’action. La régénération révoque **tous** les liens encore valides avant création du nouveau dans la même transaction ; erreur de génération = rollback intégral. Aucun lien créé sur GET. L’audit `InvitationEvent` conserve acteur, communauté, action, date et motif borné `admin_request`, jamais jeton/digest/ciphertext. Pas de journalisation des secrets. Pages communautés `no-store` et `no-referrer`, liens construits avec `APP_BASE_URL`.

## Permanence et compatibilité

Un nouveau lien est permanent par défaut (`expires_at=NULL`), avec durée facultative 1–30 jours. Un lien est valide si non révoqué et sans échéance ou avec échéance strictement future. La contrainte SQL autorise NULL ou une date postérieure à la création ; elle ne compare pas à l’heure courante et accepte les liens historiquement expirés.

La migration 0002 est additive : illustration par défaut locale, expiration nullable, audit séparé. Elle ne crée aucun lien, ne réactive rien, ne modifie aucune date, aucun UUID, prêt ou partage et ne dépend d’aucune migration B. Le lien courant est le plus récent valide (date puis UUID pour départager), sans désignation persistante ni écriture GET. Les autres liens historiques restent utilisables jusqu’à échéance/révocation. Révoquer seulement le courant peut donc révéler un autre lien historique encore valide ; régénérer les invalide tous.

Une clé Fernet perdue rend le lien illisible mais pas invalide : les destinataires peuvent toujours adhérer par son digest. L’admin peut le remplacer explicitement. Un membre retiré perd la consultation, mais on ne peut reprendre un secret déjà copié : révoquer/régénérer si nécessaire. La politique de réadhésion par invitation n’est pas modifiée. Les prêts acceptés/remis gardent leurs droits de clôture existants.

## Migration et retour compatible

`manage.py migrate --plan` et les tests MigrationExecutor couvrent le passage depuis 0001 peuplée (liens expirés/révoqués/multiples, dates et ciphertext conservés). Une base de tests neuve migre également. Avant une migration réelle : sauvegarde restaurable et procédure opérateur autorisée distincte. Après création de liens permanents, **ne pas inverser** 0002 vers l’ancienne contrainte NOT NULL ni revenir au code qui compare directement une date nullable. Retour compatible : conserver le schéma étendu et le lecteur compatible NULL ; correctif forward ou restauration contrôlée après arrêt des écritures. Aucune purge ni rollback de production exécuté.

## Vérification

Tests dédiés `test_community_redesign.py` : permissions/CSRF/GET, compte/budget SQL, illustrations bornées, rollback sur erreur, bornes temporelles/contrainte, migration historique, concurrence PostgreSQL (double rotation, adhésion contre rotation/révocation, retrait contre lecture), rotation pendant inscription. Les tests communautés existants couvrent clé illisible, transfert du dernier admin et parcours d’inscription ; les suites inventory/loans conservent retraits, annulation des demandes et clôture après départ.

Le smoke UI vérifie carte clavier, lien permanent membre, Clipboard refusé, solution sans JS et géométrie 360/768/1280 ; les scénarios existants conservent cinq largeurs et contenus longs. Les trois scripts créateurs utilisent la page dédiée.

L’intégration après A reste une porte de validation : rebaser et rejouer toute la CI si main évolue. Validation téléphone physique/lecteur d’écran hors environnement Cloud ; contrôles navigateur automatisés seulement.

Résultats locaux : `./scripts/check.sh` — Ruff, formatage, mypy (94 sources), contrôles Django/migrations/statiques et **309 tests réussis en 58,40 s** sur PostgreSQL 17. `check --deploy --fail-level WARNING` en configuration production synthétique : succès. Image Docker construite avec CA proxy montée comme secret BuildKit ; pile Compose locale saine. Résultats navigateur et CI à consulter dans le bilan de PR.
