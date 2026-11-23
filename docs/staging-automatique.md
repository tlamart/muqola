# Livraison automatique du staging

Demande du propriétaire du 23 novembre 2026 : après fusion sur `main`, livrer
automatiquement l'image validée au staging. Cette décision remplace la revue
manuelle systématique du plan **pour staging/deploy seulement**. La production,
les rollbacks, restaurations et habilitations de comptes restent manuels.

## Flux

1. Le push main lance `Muqola checks` : tests et contrôles, construction unique,
   exercices synthétiques, puis publication du candidat testé sur GHCR.
2. La fin réussie du workflow complet déclenche `Automatic staging delivery`.
   Échec/annulation de CI, PR, fork, autre dépôt/branche/workflow : aucune livraison.
3. Le runner exécute le code du main de confiance, pas celui d'un artefact.
   Il lit seulement la preuve de publication bornée et revérifie via API les jobs
   `checks`/`publish`, tentative courante, commit, image et manifeste GHCR.
4. Le candidat doit toujours correspondre à main, avant accès hôte et avant apply.
   Un candidat dépassé termine avec `phase=skipped`, `reason=superseded_main`.
5. Le transport existant transfère les seuls assets autorisés au commit publié,
   puis demande un plan au contrôleur staging installé sur le VPS.
6. Le hash et les cibles staging/deploy/image/commit du plan sont vérifiés. La
   provenance est revérifiée ; le hash exact est transmis immédiatement à apply.
   Le contrôleur revalide plan, nonce, état et prérequis sous ses verrous existants.
7. Les migrations déjà reconnues par la politique hôte sont appliquées, puis
   readiness, santé et HTTPS privé sont contrôlés avant `phase=succeeded`.

Il n'y a ni build VPS, copie de base production, recréation de DB/Mailpit, purge,
effacement de compte, promotion opérateur, modification de Caddy ni restauration
automatique. Une migration inconnue/non revue reste bloquée : mettre à jour le
contrôleur/politique hôte par une intervention séparée revue, sans option force.

## Prérequis et activation

- Fusionner le workflow dans main active le flux pour les CI main terminant ensuite.
  Aucun déclenchement SSH réel n'est effectué par les tests ou l'ouverture de PR.
- L'environnement GitHub **staging** doit conserver `VPS_HOST`, `VPS_USER`,
  `SSH_KNOWN_HOSTS`, `VPS_SSH_KEY` et les restrictions à main. Pour zéro clic, aucun
  reviewer obligatoire ou autre règle nécessitant une action ne doit y être imposé.
  Les protections de **production** doivent être conservées. Le code ne change
  aucune de ces configurations GitHub ; l'exploitant les vérifie dans les réglages.
- Le compte SSH et le contrôleur installé sont ceux du flux manuel existant ; aucun
  nouveau privilège/sudo ni mise à jour du contrôleur hôte requis par ce transport.
- Sauvegarde staging récente, preuve de restauration isolée revue, capacité réelle,
  contexte synthétique, secrets isolés et barrière HTTPS privée restent nécessaires.
  Un prérequis périmé/inaccessible fait échouer la livraison au lieu de le contourner.
- Le staging doit être initialisé selon le runbook existant. Le flux ne bootstrappe
  pas une base neuve et ne démarre pas implicitement sa DB/capture si elles sont arrêtées.

La sérialisation GitHub utilise `delivery-staging`, comme le workflow manuel.
Une livraison en cours n'est jamais annulée pour un nouveau merge ; une nouvelle
version sera traitée après elle. GitHub peut remplacer un run encore en attente
par un autre : les versions dépassées ne sont pas toutes livrées. Une avance de
main après le dernier contrôle ne coupe pas une migration déjà engagée.
Le verrou hôte commun protège aussi la coexistence avec une livraison production.

## Preuves et reprise

Le run `Automatic staging delivery` conserve trois jours un artefact
`muqola-auto-staging-<run>-<tentative>` contenant `plan.json` s'il a été produit et
`staging-result.json`. Ce dernier contient le résultat, commit, publication_run et
hash du plan en cas de succès, ou un code d'erreur expurgé en cas d'échec.
Le journal durable hôte conserve les références de version et l'issue de migration.
Les preuves de publication conservent leur rétention de 90 jours.

Un plan automatique n'est pas un `plan_run` manuel et ne peut pas être réutilisé
dans le workflow manuel. En cas d'échec, consulter le code/journal et l'état du
staging avant toute reprise. Aucun retry ni retour d'image automatique n'est lancé.
Le flux manuel reste disponible avec **son nouveau plan**, après correction de la
cause ; les protections de reprise et de schéma du contrôleur restent applicables.
Réexécuter le workflow automatique revalide la provenance et produit un nouveau
plan ; un candidat qui n'est plus main est ignoré. Ne pas annuler volontairement
un run pendant une migration ; une interruption impose l'inspection du journal.

L'exercice réel après fusion reste à attester : CI main + publication réussies,
workflow staging déclenché sans clic, digest attendu livré, santé privée validée,
production inchangée. Ensuite seulement reprendre la recette et le playbook de
promotion d'un compte synthétique. Aucun de ces résultats cibles n'est déduit
des seuls tests locaux ou de la CI de PR.

## Vérifications locales du 23 novembre

`scripts/check.sh` : 723 tests PostgreSQL réussis en 113,35 s, Ruff/format, mypy,
Django, absence de dérive de migrations et collecte des statiques. Contrôle de
configuration production et plan sans migration restante réussis. Actionlint
1.7.12 valide tous les workflows ; image Docker construite sans nouvelle dépendance.

`staging_smoke.py --exercise-release` réussi : vrai HTTPS privé/noindex, capture
SMTP et persistance, pile production témoin inchangée, cycles de service, refus
de double application, retour d'image compatible et reprise après échec santé.
Les preuves `work/staging-smoke.json` et `work/release-smoke.json` sont synthétiques ;
la provenance et l'admission y sont simulées. Aucun scénario avec migration en
attente dans ce harness ; refus et migrations sont couverts par la suite PostgreSQL.
Les cgroups du Docker local ne permettent pas une mesure fiable : valeurs de
capacité nulles, jamais assimilées à une mesure du VPS.
