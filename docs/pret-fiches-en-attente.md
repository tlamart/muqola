# P1 — prêter un exemplaire avant validation de sa fiche

Décision produit du 16 novembre 2026, remplaçant la restriction initiale de B1.
Branche indépendante `fix/pret-fiches-en-attente`, depuis `main` e57b9b2 : B #29,
A #30 et C #28 fusionnées. La validation d’un Game sert à publier ses métadonnées
au catalogue général ; elle n’est plus un préalable au prêt dans une communauté.

## Droits et parcours

| État de fiche | Catalogue général et suggestions | Exemplaire / prêt |
| --- | --- | --- |
| pending | Exclue, même si déjà partagée | L’auteur crée ses copies et choisit zéro ou plusieurs communautés. Demande/acceptation possibles pour les copies autorisées ; type inconnu permis. |
| approved | Métadonnées validées accessibles aux comptes vérifiés | Règles existantes de propriété, partage et disponibilité. |
| legacy_to_review | Hors catalogue général | Accès existants préservés pendant révision. |
| rejected | Exclue | Copie et partages conservés ; aucune nouvelle demande/acceptation ni nouveau partage. Prêts acceptés/remis clôturables. |

`Game.LENDABLE_STATUSES` aligne la propriété de disponibilité, les filtres SQL
`borrowable`/`available` et l’éligibilité des prêts. Une copie privée peut être
physiquement disponible sans accorder de droit d’emprunt à un tiers. Toujours :
compte actif/vérifié, propriétaire différent de l’emprunteur, appartenance active
**des deux personnes** à une communauté où la copie est partagée, pas de
retrait/archivage/masquage/fusion source, pas de prêt déjà accepté/remis.

Les deux parcours d’ajout fonctionnent sans JS : création de fiche puis copie,
ou ajout rapide titre + copie + partages dans une seule transaction. Les choix de
communautés ne sont plus désactivés sur l’ajout manuel. Aucun partage automatique
à la création, à la validation ou au réexamen. Sans choix, copie privée.

Le catalogue général et ses suggestions restent approved seulement. L’emprunt
cherche/classifie/regroupe/compte les seules copies actuellement autorisées,
pending compris. Le détail Game pending s’ouvre pour son auteur/opérateur ou via
une telle copie ; la lecture ne permet ni réemploi arbitraire ni modification par
un tiers. Le prêt et la copie conservent leurs URLs UUID. La source pending d’une
fusion reste protégée avant redirection : un tiers ne gagne pas accès à une
ancienne proposition seulement parce que la cible est publique.

L’indicateur « Fiche en attente de validation » apparaît dans Explorer, la
collection, les détails de fiche/copie et le prêt. Les explications de proposition
et les motifs de revue restent réservés à l’auteur/opérateur, pas aux emprunteurs.
Noms de communautés limités aux appartenances du lecteur ; aucun e-mail avant
acceptation. Les conditions de partage d’e-mail existantes restent inchangées.

## Modération et conservation

Toutes les écritures restent sérialisées par `domain_write` (transaction et verrou
advisory commun PostgreSQL). Type/base requis pour approved et gardes de doublon
exact principal/alias, homonymie motivée, corrections/fusions opérateur et audit
sont conservés. Fuzzy = suggestion, pas fusion/rejet automatique.

- **Validation** : conserve copies, UUID, propriétaires, partages et tous les prêts.
- **Correction** : garde les références physiques et les prêts, même actifs. Une
  correction de l’auteur sur rejected **conserve rejected**. Elle ne peut donc pas
  contourner le rejet en ramenant automatiquement la fiche à pending. Seul un
  opérateur peut la remettre explicitement en pending (réexamen prêt autorisé),
  l’approuver ou résoudre le doublon par fusion.
- **Fusion** : source conservée, copies déplacées vers la cible canonique ; leurs
  identités, propriétaires, partages et FK de prêts ne changent pas. Les règles
  existantes contre cycles, rétablissement d’un masquage et pertes de références
  restent appliquées. Les demandes annulées ne sont jamais ressuscitées.
- **Rejet** : conserve copie, notes et liens de partage existants. Annule uniquement
  les REQUESTED de cette fiche avec motif explicite, événements et notifications
  transactionnelles. N’altère pas les prêts ACCEPTED/HANDED_OVER ni leur droit de
  remise/retour/annulation autorisée. Aucun nouveau partage pendant le rejet ;
  notes modifiables et partages existants réductibles sans les supprimer d’office.

À la course rejet/acceptation, soit l’acceptation passe d’abord et le prêt accepté
reste clôturable, soit le rejet annule la demande et l’acceptation échoue. Aucune
REQUESTED éligible ne subsiste après rejet. Les contraintes PostgreSQL d’unicité
partielle des prêts actifs et des demandes sont inchangées.

Aucun changement de schéma ni migration de données, aucun backfill d’approbation,
aucune suppression de ligne par les nouvelles décisions de modération. **Les partages pending déjà présents deviennent
éligibles s’ils satisfont tous les droits actuels** ; aucune visibilité n’est
créée automatiquement. Les copies sans partage restent privées. Retrait d’un
membre/propriétaire et masquage gardent leur effet immédiat sur les nouveaux accès,
sans bloquer les prêts acceptés. Aucun import, catalogue réel ou upload.

## Vérification

Tests PostgreSQL dédiés : ajout rapide partagé sans opérateur, titre seul/type
inconnu, alias/accents et fragments, absence du catalogue général, A/B et copies
multicommunautés, notes privées/motifs de revue, IDs directs et tentative de
réemploi/édition par tiers. Matrice privé/retiré/archivé/masqué/propriétaire ou
lecteur retiré/propriétaire inactif ou non vérifié. Fragments avant/après copie
invisible identiques (comptes, ordre et page).

Prêt complet par POST, droits des participants, contacts limités à la phase
active ; snapshots de toutes les copies/visibilités et de tous les états de prêts
lors d’approbation/correction/fusion/rejet. Réexamen opérateur après correction
rejetée, rejet face à demande/acceptation concurrentes, doubles acceptations.
Les budgets SQL existants sont aussi vérifiés pour pending à 1/10/30/65 copies.

Le parcours navigateur produit propose puis partage un jeu pending, vérifie qu’il
reste absent du catalogue et invisible au tiers, demande/accepte le prêt avant
validation, le valide pendant le prêt actif puis vérifie réemploi, retrait de
membre et remise/retour. L’ajout rapide avec/sans JS et les parcours A/C restent
contrôlés par la CI.

Résultats locaux : `scripts/check.sh` complet, **353 tests réussis**, puis les deux
cas supplémentaires de clôture après rejet et perte de communauté dans les
**22 tests P1 réussis** (355 tests distincts dans l’état final). Ruff lint/format,
mypy (102 sources), Django, collecte statique, migration/plan et absence de
migration manquante : succès. Contrôle production et audit runtime réussis ;
build Docker, stack locale, produit/prêt pending et validation pendant prêt,
ajout rapide 6 variantes avec/sans JS, recherche instantanée/transport et repli
sans JS : succès. Le résultat CI du dernier commit est consigné dans la PR.

Le smoke recherche isole aussi ses images Commons synthétiques des téléchargements
externes et attend les événements réseau contrôlés : une autre fixture locale
ne peut plus fausser le comptage des erreurs. Les vraies pannes fetch ne sont pas
ignorées ; l’assertion de classification ERR_ABORTED est conservée.
Validation sur données synthétiques et Chromium, pas de téléphone physique ni
d’audit humain avec un lecteur d’écran dédié. Aucun merge ou déploiement.
