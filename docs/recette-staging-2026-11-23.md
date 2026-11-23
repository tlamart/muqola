# Recette et preuves de livraison — 23 novembre 2026

## Portée

Réconciliation de la checklist à partir des runs GitHub et du contrat du contrôleur versionné, depuis `main` `70dc136bf3f22bc71d42225485975029962563b0`. Aucun nouveau déploiement, aucune promotion, aucun effacement, aucune connexion SSH au VPS ni aucune modification de production n’est effectué par ce bilan.

Un run réussi de livraison prouve les vérifications obligatoires de son contrôleur ; il ne prouve pas une recette utilisateur complète. Les constats ci-dessous sont datés, pas une garantie de l’état actuel si une intervention ultérieure a eu lieu. Aucun secret ni contenu d’un fichier privé n’a été consulté.

## Versions et preuves

| Cible | Preuve observée | Version livrée |
| --- | --- | --- |
| Production | [Apply 45064624690](https://github.com/tlamart/muqola/actions/runs/45064624690), lancé le 22 novembre à 21:07 (Paris), terminé avec succès, réponse `phase=succeeded` | Commit `ee13ea10456458d45b4b48b4a5e466db5f14c1ea` ; digest `89b58e42339c8eabf6fc11738d59c3bb0d85e002b528fc27fe7321d5809a7687` |
| Staging | [Plan 45150212876](https://github.com/tlamart/muqola/actions/runs/45150212876) puis [apply 45153646180](https://github.com/tlamart/muqola/actions/runs/45153646180), lancé le 23 novembre à 11:10 (Paris), terminé avec succès, réponse `phase=succeeded` | Commit `51c999550abe5b7372009fa43ed8b2907abb4d5b` ; digest `4ff9e011a9af5d7b582448a419c951c2dcdd9e91a4d74801f4bafe8a81db096d` |
| Publication staging | [Muqola checks 45134687469](https://github.com/tlamart/muqola/actions/runs/45134687469), jobs `checks` et `publish` réussis ; tentative 1 | Même commit/digest que la livraison staging |
| Publication production | [Muqola checks 44704300981](https://github.com/tlamart/muqola/actions/runs/44704300981), référence acceptée par la provenance du plan/apply production ; tentative 1 | Même commit/digest que la livraison production |
| Dernier code source | `main` `70dc136` : Ansible et options supplémentaires de promotion ; [Ansible checks 45190681441](https://github.com/tlamart/muqola/actions/runs/45190681441) réussi | Ce commit n’est pas la version livrée au staging par le run ci-dessus. Suivre séparément la [CI applicative 45190681696](https://github.com/tlamart/muqola/actions/runs/45190681696) et sa publication |

Les digests complets sont des références `ghcr.io/tlamart/muqola@sha256:…` et non des tags flottants.

### Référence exacte du plan staging appliqué

- `publication_run=45134687469`, `publication_attempt=1`
- `plan_run=45150212876`
- `plan_hash=f2cb93933643a401d7379a17f8e940ab7802985ef4c8952a5ed3048c6c4ff1f4`
- Environnement `staging`, opération `deploy`.

Le [premier apply 45151434935](https://github.com/tlamart/muqola/actions/runs/45151434935) a échoué avant SSH : `explicit_plan_hash_required`. La valeur saisie était le hash de l’archive uploadée, préfixé `sha256:`, au lieu de la propriété `hash` de `plan.json`. L’apply suivant réussi utilise le bon hash. Le plan appliqué est consommé : ces références sont une preuve historique, **pas une instruction de rejouage** ; toute nouvelle application exige son propre plan revu.

## Contrôles techniques établis par ces livraisons

Le workflow [deploy.yml au commit livré](https://github.com/tlamart/muqola/blob/51c999550abe5b7372009fa43ed8b2907abb4d5b/.github/workflows/deploy.yml) et [deploy/release.py](https://github.com/tlamart/muqola/blob/51c999550abe5b7372009fa43ed8b2907abb4d5b/deploy/release.py) imposent, avant `phase=succeeded` :

- provenance GitHub/GHCR revérifiée et image référencée par digest, pull sans build ; seules les ressources versionnées autorisées sont transférées ;
- rendu Compose contrôlé par `deploy.check_config.validate` (pas de build/ports publiés sur les services applicatifs, rôles runtime/migration distincts, réseaux privés/proxy, origine et volume identifiés) ;
- plan et nonce revérifiés, sérialisation et prérequis de capacité/backup/restore acceptés ;
- migrations prévues exécutées, puis snapshot sans migration restante et contrôle `staging_readiness` ou `production_readiness` réussi ;
- services web/worker démarrés avec healthchecks ;
- sonde `/health/ready/` en HTTPS avec certificat vérifié et redirections refusées. En staging, `deploy.probe` exige d’abord **401 et noindex sans accès privé**, puis **200 avec accès privé** ;
- journal de succès et références de version conservés par le contrôleur.

Limites : l’acceptation d’un enregistrement backup/restore ne constitue pas une nouvelle inspection indépendante du stockage distant ni une mesure RPO/RTO. La sonde santé n’est pas une recette de toutes les routes, des cookies dans un navigateur ou de la délivrabilité réelle. La disponibilité d’un autre site lors d’un reload Caddy, la rétention effective des journaux, les droits/visibilité du package et les pièces de revue juridique ne sont pas déduits du succès de l’apply.

## Recette fonctionnelle restante sur le staging

URL prévue et contrôlée par le contrôleur : `https://staging.muqola.tlam.art/`.

Le 23 novembre, la tentative HTTPS depuis l’environnement Codex s’est arrêtée au proxy sortant (`CONNECT tunnel failed, response 403`, aucun code HTTP reçu du site). Ce résultat **ne constitue ni un 403 de Muqola ni un échec de son contrôle d’accès**. Aucun accès privé au staging n’est configuré dans cet environnement ; aucun compte n’a été créé/promu et aucune modification de données du staging n’a été effectuée pour cette recette.

Pour reprendre les tests depuis cet environnement : autoriser ce domaine dans les réglages réseau lorsque proposés, configurer l’accès privé dans les réglages de secrets ou utiliser une session de navigateur accessible aux outils. Ne pas mettre de mot de passe/jeton dans le chat, un argument de commande, une URL ou le dépôt. Aucun identifiant VPS n’est requis ni demandé ici. Si ces capacités ne sont pas disponibles, l’exploitant exécute la recette dans son navigateur et fournit les résultats expurgés.

### Ordre et critères à consigner

Utiliser seulement des comptes fictifs **`@example.test`**, des jeux synthétiques et des profils de navigateur séparés. Conserver les limites de débit et portes légales/18+ ; ne pas désactiver la protection privée. Relever pour chaque cas la date, l’image observée, le résultat attendu/obtenu et une preuve sans secret.

1. **Accès privé et comptes.** Vérifier le refus anonyme sur accueil, connexion, ressources, santé et erreurs ; accès autorisé sans redirection externe, noindex/no-store et TLS. Tester inscription 18+ non précochée, refus avant vérification, confirmation et reset via la capture SMTP privée. Ne pas exposer Mailpit pour accéder aux messages ; organiser son accès privé selon le runbook existant.
2. **Premier opérateur.** Créer/vérifier normalement un compte fictif, attester la majorité puis faire exécuter par l’exploitant la [promotion auditée](catalogue-admin.md) sur le conteneur staging. La commande classique de #40 est dans l’image `51c9995`. Les options récentes `--dry-run`/`--if-needed`/JSON/contexte utilisées par le playbook Ansible sont ajoutées après ce commit : ne pas les appeler sur cette image. Pour recetter le playbook, attendre la publication d’une image compatible puis son propre plan/apply explicitement autorisé. Aucun opérateur de production n’est requis pour le test.
3. **Permissions et modération.** Tester compte ordinaire, administrateur de communauté et opérateur dans trois sessions. Seul l’opérateur entre dans `/operator/` ; demande de corrections, rejet et approbation produisent une trace motivée. Type/base/doublon invalides refusés, justification d’homonymie explicite, masquage conservé ; aucun accès à une collection privée depuis l’admin.
4. **Communautés et prêt.** Alice et Bob rejoignent explicitement une communauté via le lien permanent ; tester copie membre et rotation admin. Créer une copie privée et une copie partagée pending, rechercher puis demander/accepter/remettre/rendre ; vérifier l’exclusion d’un tiers. Retirer un membre après acceptation : clôture toujours possible. Rejet d’une autre fiche pending avec demande en attente : annulation attendue, exemplaires/partages conservés. Les courses PostgreSQL restent couvertes par les tests automatisés, pas par un simple double clic manuel.
5. **Vie privée.** L’exploitant suit le [runbook de conservation](confidentialite-conservation.md) sur des comptes explicitement synthétiques, en commençant par les simulations et revues des champs libres ; toute application d’effacement reste une opération séparée revue, aucune commande générique n’est lancée ici. Tester restriction avec prêt accepté/remis, reconnexion et clôture, finalisation, exception temporaire et préavis réellement capturé. Ces fonctions ne sont pas recettées par le simple contrôle readiness.
6. **Ergonomie.** Parcours à 360/768/1280 px, clavier, sans JavaScript et téléphone réel ; dialogues/focus, formulaires longs et erreurs. Les captures CI restent des preuves synthétiques, pas des captures du staging cible.

### Portes encore ouvertes

- [ ] Accès direct au staging depuis les outils de recette, ou compte rendu de l’exploitant.
- [ ] Recette comptes/opérateur/modération/permissions réellement exécutée sur le staging cible.
- [ ] Recette des communautés, prêts et confidentialité avec comptes synthétiques sur la cible.
- [ ] Validation téléphone réel et lecteur d’écran si disponible.
- [ ] Pièces d’exploitation : DNS/SMTP, sauvegarde extérieure/restauration, capacité sous charge, alertes, journaux et revue juridique.
- [ ] Validation d’une image compatible avant recette du nouveau playbook Ansible de promotion.

Aucune de ces cases n’est cochée par ce bilan. Le passage du staging en production n’est pas autorisé par ce document.
