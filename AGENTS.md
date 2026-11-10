# Instructions permanentes à Codex — Muqola

## Mission
Construire un MVP exploitable de Muqola, application web de prêt gratuit de jeux de société entre membres de communautés privées. Lire **SPEC.md**, **DESIGN.md**, **ARCHITECTURE.md** et **TASKS.md** avant toute modification. Les décisions produit de ces documents prévalent sur les préférences de framework.

## Mode de travail
1. Conserver la stack Django validée dans `docs/adr/0001-stack.md` ; signaler les arbitrages majeurs. Ne réexaminer ce choix que si la tâche le demande explicitement.
2. Travailler par lots petits, testables et indépendamment vérifiables selon TASKS.md. **Dans Codex Cloud, préférer une branche et une pull request par lot**, sans pousser directement sur `main`.
3. Pour chaque lot : expliquer brièvement le plan, implémenter, écrire/adapter les tests, exécuter lint/tests/build, puis résumer fichiers modifiés, commandes exécutées, résultats et points restant à traiter.
4. Ne pas annoncer une fonctionnalité terminée sans preuve de test. Ne jamais inventer une exécution ou un résultat. Si l'environnement Codex Cloud ne permet pas Docker ou un test navigateur, le signaler et fournir des commandes exactes à lancer localement avant validation.
5. Ne pas ajouter de fonctionnalités hors MVP sans accord. En cas d'ambiguïté non bloquante, prendre la solution la plus simple, la documenter et poursuivre. Demander une décision uniquement si elle change les règles métier, la confidentialité, le coût ou le risque.
6. Priorité : sécurité des autorisations, intégrité des prêts, simplicité du déploiement, ergonomie mobile, puis esthétique.
7. Garder un `README.md` à jour : installation locale, commandes, tests, migrations, variables d'environnement et déploiement.
8. Ne pas utiliser de services payants ni provisionner de ressources cloud sans approbation explicite. Ne jamais afficher de secrets ni les committer. Ne pas demander ni utiliser les identifiants du VPS en développement local ou Cloud.
9. Avant toute migration destructive ou opération de production : demander confirmation et fournir une stratégie de sauvegarde/retour arrière.

## Qualité attendue
- Architecture monolithique modulaire avec frontières de modules claires.
- Validations et autorisations **sur le serveur** ; tests d'accès croisé et de concurrence.
- Dépendances minimales et maintenues ; pas de complexité prématurée.
- Interface française, responsive, accessible et utilisable avec données vides.
- Erreurs compréhensibles et journalisation utile sans divulgation de données sensibles.
- Aucune dépendance à un catalogue externe pour le parcours d'ajout de jeux. Favoriser le réemploi des fiches internes et autoriser les exemplaires privés sans communauté.
- Respecter les règles exactes de transition des prêts et les cas où une appartenance ou une visibilité est retirée. En cas de contradiction apparente, la confidentialité et l'intégrité des prêts priment ; signaler le conflit dans la PR.
- Ne pas implémenter de fausses intégrations (API e-mail, sauvegardes) présentées comme opérationnelles : distinguer clairement les simulateurs de développement et la production.

## Définition de « terminé »
Une tâche est terminée si son comportement correspond à SPEC.md, ses critères TASKS.md passent, les tests automatisés pertinents sont présents et exécutés, les migrations et la documentation sont à jour, et aucune régression évidente n'est connue.
