# Muqola — Kit de démarrage Codex

Ce dépôt contient les décisions produit et les instructions nécessaires pour faire développer le MVP par Codex.

## Fichiers
- `SPEC.md` : périmètre et règles métier.
- `DESIGN.md` : direction UX/UI.
- `ARCHITECTURE.md` : contraintes techniques et sécurité, stack à choisir et justifier par Codex.
- `AGENTS.md` : méthode de travail permanente pour Codex.
- `TASKS.md` : lots de livraison et tests d'acceptation.
- `.env.example` : variables indicatives à adapter à la stack retenue.
- `.gitignore` : exclusions par défaut pour éviter d'envoyer secrets et données locales.
- `LAUNCH_CHECKLIST.md` : vérifications à mener avant l'ouverture des inscriptions.
- `CODEX_START_PROMPT.md` : consigne initiale à copier dans Codex.

## Démarrage avec Codex
1. Créer un dépôt GitHub privé ou public selon préférence.
2. Copier ces fichiers **à la racine** du dépôt, puis faire un commit initial.
3. Ouvrir le dépôt dans Codex et lui transmettre le prompt de `CODEX_START_PROMPT.md`.
4. Laisser Codex produire **uniquement le lot 0** sur une branche/PR ; relire `docs/adr/0001-stack.md`, vérifier les tests et **valider la stack avant le lot 1**.
5. Avancer par lots avec démonstrations et tests ; ne pas provisionner d'hébergement payant avant d'avoir choisi le VPS et le domaine. Les e-mails réels, le domaine, le VPS et les données de production restent hors du Cloud de développement.
6. Avant d'ouvrir la bêta, suivre `LAUNCH_CHECKLIST.md` ; une CI verte ne remplace pas les tests manuels ni les vérifications légales.

## À compléter avant ouverture au public
Choix et vérification du domaine/marque ; fournisseur e-mail et DNS ; mentions légales et confidentialité adaptées à l'exploitant ; contact ; VPS ; sauvegardes externalisées testées ; procédure de déploiement et de suppression des comptes.

## Note
Le kit est une spécification de travail : il ne contient pas encore l'application. Les secrets d'exemple sont volontairement invalides. Le délai de livraison dépend de l'exécution, des tests et des corrections.
