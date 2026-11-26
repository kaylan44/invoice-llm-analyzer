# Projet : extraction de factures fournisseurs (portfolio AI engineer)

## Objectif
Extraire les champs de factures fournisseurs (français et anglais) avec Claude, contrôler leur cohérence, laisser un humain valider. Projet d'apprentissage : agents et MCP, évals, RAG sur pgvector. Architecture détaillée : docs/architecture.md.

## Décisions déjà prises
- Extraction v1 : pipeline sans agent (un appel Claude à sortie structurée, contrôles en Python). Elle sert de baseline aux évals. Un agent avec outils ne viendra qu'ensuite, et seulement s'il bat la baseline.
- RAG : rapprochement uniquement. Le fournisseur est normalisé (correspondance exacte sur n° de TVA ou SIRET, sinon recherche hybride pgvector + plein texte fusionnée par RRF) et chaque ligne est classée dans une catégorie comptable. Mesuré par recall@k et MRR, avec et sans reranking.
- Frontend : Next.js + TypeScript sur Vercel. Il n'appelle que l'API FastAPI, jamais Supabase ni Claude.
- Backend : FastAPI (Python) sur Railway, via Dockerfile.
- Base : Supabase (Postgres + pgvector, Storage privé) pour la production uniquement. Évals et tests : Postgres + pgvector local en Docker, mêmes migrations (supabase/migrations).
- MCP : serveur Python, transport stdio, appelle l'API FastAPI. Non déployé.
- Langues : français et anglais uniquement.
- Embeddings : fournisseur à choisir (Anthropic n'a pas de modèle d'embeddings), validé par recall@k.
- Hors périmètre : comptes utilisateurs, multi-tenant, paiement, intégration comptable, mobile.

## Environnement
- Le dépôt vit dans WSL (Ubuntu) : ~/invoice-llm-analyzer. Toutes les commandes (Python, Node, Docker, git, tests) s'exécutent dans WSL, jamais côté Windows.

## Structure du dépôt
web/ (Next.js), api/ (FastAPI), mcp/ (serveur MCP), evals/ (jeu de test, harnais), supabase/migrations/, docs/

## Mode apprentissage (prioritaire sur tout le reste)
Je suis développeur fullstack avec un fond DevOps. TypeScript, Next.js, Docker et CI sont acquis : va vite. Python, agents, évals et RAG sont ce que j'apprends : explique.
1. J'écris moi-même le code central : boucle d'agent, outils, requêtes pgvector, métriques d'évals. Toi : le boilerplate, la config, l'écran de revue, la CI.
2. Pour une partie que j'écris : explique le concept en 5 lignes maximum (pourquoi ce choix, une alternative écartée), donne l'interface attendue et écris d'abord les tests qui échouent. Attends mon code, puis relis-le. Ne donne pas ta version avant que j'aie essayé, sauf si je la demande.
3. Une étape = un objectif d'apprentissage, un critère de réussite vérifiable, un commit. En fin d'étape, pose-moi 2 questions courtes pour vérifier ma compréhension et n'enchaîne pas avant ma réponse.
4. Pas de framework d'orchestration (LangChain, LlamaIndex, etc.) : SDK Anthropic directement.
5. Explique les idiomes Python quand ils apparaissent (async, typage, pydantic, gestion d'erreurs).
6. Pour tout outil récent (SDK Anthropic, Supabase, Railway, MCP), lis la doc actuelle au lieu de te fier à ta mémoire et cite la source. Donne ton niveau de confiance quand tu n'es pas sûr.
7. Si mon raisonnement ou mon plan est faux, dis-le directement.

## Sécurité et exploitation
- Aucun secret dans le dépôt : .env ignoré par git, .env.example à jour. La clé service_role de Supabase reste dans l'API.
- Ni migration, ni déploiement, ni écriture sur la base Supabase de production sans mon accord explicite.
- Ni suppression de fichiers ni action git destructrice sans me demander.
- Une clé d'API Claude par usage (dev, CI, prod), avec plafond de dépense.
- Réponds en français. Code, commits (Conventional Commits) et identifiants en anglais.
