# Architecture : extraction de factures fournisseurs

Nov 25, 2026 · @Guillaume

Présentation visuelle (vue d'ensemble, schéma, maquette de l'écran de revue, plan) : [Projet IA extraction de factures fournisseurs.pdf](Projet%20IA%20extraction%20de%20factures%20fournisseurs.pdf)

## Contexte, périmètre et décisions

Le projet extrait les champs de factures fournisseurs en français et en anglais, avec revue humaine, sur une base Supabase hébergée en production. Il sert de portfolio AI engineer et couvre trois axes : agents et MCP, évals, RAG sur pgvector.

| Décision | Choix retenu | Raison |
| --- | --- | --- |
| Langues | Français et anglais | Deux langues suffisent pour un jeu de test fiable et simplifient les embeddings |
| Base de données | Supabase : Postgres + pgvector, hébergée | Une seule base, SQL standard, extension vectorielle incluse |
| Frontend | Next.js + TypeScript, sur Vercel | Stack maîtrisée, écran de revue rapide à construire |
| Backend | FastAPI (Python), sur Railway via Dockerfile | Python demandé par 71 % des offres d'AI engineer analysées (source à ajouter) |
| Extraction | Pipeline sans agent en v1, agent en v2 | La v1 sert de référence : l'agent doit prouver qu'il fait mieux |
| RAG | Rapprochement fournisseur et catégorie par pgvector | Mesurable par recall@k et MRR sur une vérité terrain connue |
| Intégration Claude | Serveur MCP en Python | Exposer l'extraction à Claude Desktop |

Hors périmètre : comptes utilisateurs, multi-tenant, paiement, intégration comptable, application mobile.

## Vue d'ensemble

```
Interface Next.js ──> API FastAPI ──> Extraction ──────────────> Supabase Postgres
(dépôt, revue)        (jobs,          (modèle à vision ;          (pgvector, PDF,
     ^                 stockage)       v1 pipeline, v2 agent)       production)
     │                    ^              │            │                 │
     │                    │              v            v                 │
     │               Serveur MCP     Validation   Rapprochement         │
     │                    ^          (sommes,     (pgvector)            │
     │                    │          dates,                             │
     │              Claude Desktop   devise)                            │
     └──────────────────── revue et corrections ────────────────────────┘

Mesure et régression : Jeu de test (FR, EN) ──> Harnais d'évals (Postgres local) ──> CI de régression
```

L'interface Next.js et le serveur MCP passent tous deux par l'API FastAPI, la seule à détenir les clés de Supabase et de Claude. Les évals tournent à part, sur un Postgres local.

## Frontend Next.js

Le frontend ne tient aucune clé secrète et ne parle qu'à l'API FastAPI : ni Supabase ni Claude ne sont appelés depuis le navigateur. Les route handlers Next.js servent de relais, l'URL et le jeton de l'API restent côté serveur.

| Écran | Rôle | Données lues |
| --- | --- | --- |
| Dépôt | Envoi d'un PDF ou d'une image, suivi du traitement | Statut du traitement |
| Liste | Factures classées par statut : en attente, à vérifier, validée | Extractions et résultat des contrôles |
| Revue | Document à gauche ; à droite, champs extraits avec un badge « Sûr » ou « À vérifier », contrôles, lignes et catégories ; correction et validation | Une extraction, ses lignes, le PDF par URL signée |
| Export | Téléchargement CSV ou JSON des factures validées | Factures validées |

Points à retenir :

- Hébergement : Vercel, variables d'environnement pour l'URL de l'API.
- Pas de comptes utilisateurs. L'accès est fermé par une phrase secrète de démo dans un middleware Next.js (voir Risques).
- L'humain ne relit que ce que les contrôles automatiques signalent.
- Surlignage des champs sur le document : il suppose des coordonnées fiables. À valider en semaine 3 ; si le modèle en donne de peu précises, repli sur la recherche du texte extrait dans le PDF numérique.

## Backend FastAPI

Le backend orchestre l'extraction : il reçoit le fichier, appelle Claude, écrit le résultat dans Supabase et ne renvoie jamais de clé au client.

| Endpoint | Rôle |
| --- | --- |
| POST /invoices | Enregistre le fichier dans Supabase Storage, crée un traitement |
| GET /invoices | Liste, filtre par statut |
| GET /invoices/{id} | Extraction, contrôles, URL signée du document |
| PATCH /invoices/{id} | Corrections faites en revue |
| POST /invoices/{id}/validate | Passe la facture au statut validée |
| GET /export | CSV ou JSON des factures validées |

**Extraction v1 : pipeline sans agent (référence).** L'ordre des étapes est fixé dans le code :

1. Un appel au modèle à vision lit le document et produit une extraction structurée (schéma JSON imposé).
2. La fonction de validation contrôle les champs (voir ci-dessous).
3. La fonction de rapprochement interroge pgvector pour normaliser le fournisseur et classer chaque ligne.
4. Si un contrôle échoue, la facture passe à « à vérifier » avec le motif. Pas de nouvelle tentative automatique en v1.

**Extraction v2 : agent avec outils.** Les mêmes fonctions deviennent des outils (`validate_invoice`, `match_supplier_and_category`) que le modèle appelle lui-même. En cas d'échec d'un contrôle, il reprend le document, dans la limite d'un nombre d'itérations fixé en configuration. La v2 n'est retenue que si elle bat la v1 sur les évals, coût et latence inclus.

**Champs extraits** (première version, à affiner) :

- Fournisseur : nom tel que lu, n° de TVA intracommunautaire, SIRET (si présent)
- N° de facture, date d'émission, date d'échéance
- Devise, total HT, total TVA, total TTC
- Lignes : désignation, quantité, prix unitaire, taux de TVA, montant
- Langue détectée (fr / en)

**Contrôles de cohérence** (déterministes, en Python) :

- Somme des lignes = total HT ; HT + TVA = TTC (tolérance d'arrondi)
- Dates valides, échéance postérieure à l'émission
- Devise reconnue
- Format du n° de TVA ou du SIRET
- Doublon : même fournisseur et même n° de facture déjà en base

**Traitement asynchrone.** Une table `jobs` dans Postgres et les tâches de fond de FastAPI suffisent pour le MVP : pas de Redis ni de file dédiée.

**Modèles.** Point de départ : un modèle de la famille Sonnet pour l'extraction, un modèle de la famille Haiku pour les tâches simples (reranking, juge de premier passage). Hypothèse à trancher par les évals, pas avant.

## Base de données Supabase

Supabase héberge la seule base du projet : Postgres avec l'extension `vector`, le stockage privé des PDF, et rien d'autre. Le schéma est écrit en migrations SQL versionnées dans le dépôt (`supabase/migrations`).

| Table | Contenu | Particularité |
| --- | --- | --- |
| `invoices` | Statut, fournisseur, numéro, dates d'émission et d'échéance, devise, totaux HT, TVA et TTC, langue, chemin du fichier | Un statut parmi : en attente, à vérifier, validée |
| `invoice_lines` | Désignation, quantité, prix unitaire, taux de TVA, montant, catégorie | Liée à `invoices` |
| `suppliers` | Nom normalisé, alias, n° de TVA, SIRET | Colonne `embedding` + index HNSW |
| `categories` | Catégories comptables définies par toi | Colonne `embedding` + index HNSW |
| `extractions` | JSON brut, modèle, version du prompt, contrôles | Traçabilité de chaque exécution |
| `jobs` | État du traitement, erreur | Remplace une file de messages |

**Sécurité.**

- RLS activée sur toutes les tables, aucune politique publique.
- Seul le backend FastAPI accède à la base, avec la clé `service_role`, qui contourne la RLS : elle ne doit jamais atteindre Next.js ni le dépôt.
- Bucket Storage privé, URL signées à durée courte pour l'affichage.

**Production et évals.** La base Supabase ne reçoit que de vraies exécutions. Les évals tournent sur un Postgres avec pgvector en local (Docker) et les mêmes migrations : elles écrivent des centaines d'extractions de test qui fausseraient les listes et les statistiques de production. Les vraies factures anonymisées restent en local, hors dépôt public et hors production.

**Offre.** Le plan gratuit [met en pause un projet après une semaine d'inactivité](https://supabase.com/docs/guides/platform/free-plan-pausing) et limite chaque projet actif à [0,5 Go de base](https://supabase.com/changelog/33121-relaxing-database-size-limit-on-free-plan-0-5-gb-database-size-per-project). Pour une démo montrée à des recruteurs, un projet en pause casse la démo : le plan [Pro, à 25 $ par mois](https://supabase.com/docs/pricing), n'est jamais mis en pause.

## RAG : rapprochement fournisseur et catégorie

pgvector sert à rattacher ce que le modèle a lu à des entités connues : le fournisseur normalisé et la catégorie comptable de chaque ligne.

**Fournisseur.**

1. Correspondance exacte : si un n° de TVA ou un SIRET est lisible, recherche par SQL.
2. Sinon (identifiant absent, mal lu, nom variable comme « ACME SAS » contre « Acme ») : recherche hybride sur `suppliers`.

**Catégorie.** Chaque désignation de ligne est rapprochée des `categories` par recherche hybride.

**Recherche hybride.** Une requête combine la distance cosinus pgvector et le plein texte Postgres, fusionnées par RRF (Reciprocal Rank Fusion). Le plein texte utilise la configuration `simple`, qui ne dépend d'aucune langue. Un reranking optionnel (Claude Haiku ou modèle dédié) réordonne les candidats ; les évals comparent avec et sans. La dimension des vecteurs est fixée par le modèle d'embedding retenu (voir la section sur la clé d'API).

## Serveur MCP et Claude

Le serveur MCP expose trois outils à Claude Desktop et appelle l'API FastAPI, jamais Supabase directement : la logique métier reste à un seul endroit.

| Outil | Entrée | Sortie |
| --- | --- | --- |
| `extract_invoice` | Chemin d'un fichier local | Identifiant de la facture et statut |
| `list_pending_invoices` | Filtre de statut | Liste des factures à relire |
| `get_invoice` | Identifiant | Champs extraits, lignes, résultat des contrôles |

- **Transport.** stdio en local, déclaré dans la configuration de Claude Desktop. Un transport HTTP distant est possible ensuite, mais exige une authentification que le MVP n'a pas.
- **Fichiers.** Le serveur lit le fichier sur la machine de l'utilisateur et l'envoie à l'API.
- **Authentification vers l'API.** Un jeton de service lu dans une variable d'environnement du processus MCP, jamais écrit dans la configuration versionnée.
- **Facturation.** Claude Desktop passe par l'abonnement Claude de l'utilisateur. Une extraction déclenchée par l'outil s'exécute dans le backend et se paie sur la clé d'API.

Démo attendue : demander à Claude « quelles factures sont à vérifier ? » puis « ouvre la dernière », enregistrée en GIF dans le README.

## Évals et CI de régression

Les évals rejouent l'extraction sur un jeu de test à vérité terrain connue et mesurent chaque champ ; la CI bloque toute PR qui fait baisser un score.

| Ce qui est mesuré | Méthode |
| --- | --- |
| Champs objectifs (fournisseur, numéro, dates, devise, totaux, lignes) | Comparaison exacte après normalisation des dates et des montants |
| Détection des incohérences | Précision et rappel du statut « à vérifier » sur des factures piégées (total faux, champ absent) |
| Rapprochement fournisseur et catégorie | recall@k et MRR sur la recherche pgvector, avec et sans reranking |
| Qualité des catégories attribuées | Juge LLM, calibré sur 30 notes manuelles ; accord visé d'au moins 80 % |
| Pipeline v1 contre agent v2 | Mêmes métriques, plus coût et latence par facture |

- **Jeu de test.** Factures synthétiques en français et en anglais générées par script, dont une part dégradée (rotation, flou, scan bruité). Une vingtaine de vraies factures anonymisées servent au test final et restent en local.
- **Exécution.** En local et en CI, sur Postgres avec pgvector dans Docker, jamais sur la base Supabase de production.
- **Référence.** Un fichier de scores versionné dans le dépôt. Le seuil de régression se fixe après la première mesure, pas avant.
- **CI.** GitHub Actions lance un sous-ensemble sur chaque PR, compare à la référence et échoue si un score baisse au-delà du seuil. Chaque exécution appelle l'API : la clé de la CI est dédiée et plafonnée.

**Tableau d'évals, à remplir après la première mesure.** Aucun chiffre avant d'avoir mesuré.

| Champ | Français | Anglais | Scans dégradés |
| --- | --- | --- | --- |
| Fournisseur | à mesurer | à mesurer | à mesurer |
| Date et n° de facture | à mesurer | à mesurer | à mesurer |
| Totaux et devise | à mesurer | à mesurer | à mesurer |
| Lignes (quantité, prix) | à mesurer | à mesurer | à mesurer |
| Catégorie comptable | à mesurer | à mesurer | à mesurer |

## Clé d'API Claude, embeddings et coûts

La clé d'API Claude couvre tout ce que fait le modèle, mais pas les embeddings : [Anthropic ne propose pas de modèle d'embeddings](https://platform.claude.com/docs/en/build-with-claude/embeddings) et oriente vers Voyage AI. Il faut donc une seconde clé chez un fournisseur d'embeddings pour pgvector.

| Besoin | Couvert par la clé Claude | Solution |
| --- | --- | --- |
| Extraction par vision (PDF, images) | Oui | Modèle de la famille Sonnet |
| Agent et appels d'outils (v2) | Oui | Même clé |
| Juge LLM des évals | Oui | Modèle Haiku ou Sonnet |
| Reranking | Oui, via un modèle Claude | Haiku comme reranker, comparé à un modèle de reranking dédié dans les évals |
| Embeddings pour pgvector | Non | Voyage AI, ou un autre fournisseur ; vérifier le français et l'anglais par le recall@k |
| Claude Desktop et MCP | Hors clé | Abonnement Claude de l'utilisateur |
| Supabase, hébergement | Non | Comptes séparés |

La clé d'API se paie à l'usage, sur des crédits de la Console, à part de l'abonnement Claude.

**Ordre de grandeur des coûts** (approximation, hypothèses non mesurées, tarifs à revérifier avant usage). Tarifs de la [page officielle](https://platform.claude.com/docs/en/about-claude/pricing) : Sonnet 5.5 à 2 $ en entrée et 10 $ en sortie par million de tokens, Haiku 5.5 à 0,10 $ et 0,50 $, Batch API à moitié prix.

| Poste | Hypothèse | Coût estimé |
| --- | --- | --- |
| Évals complètes, 60 factures, Sonnet | 12 000 tokens en entrée et 2 000 en sortie par facture, boucle d'outils comprise (la v1 sans agent en consomme moins) | 2,64 $ |
| Juge, 60 appels, Sonnet | 3 000 en entrée et 500 en sortie | 0,66 $ |
| Une passe complète | Somme des deux | environ 3,30 $ |
| 20 passes pendant le développement | Sonnet seul | environ 66 $, moitié moins avec la Batch API |
| Embeddings | 2 millions de tokens, à environ 0,06 $ le million selon un [comparatif tiers](https://blogs.novita.ai/anthropic-embeddings-api/) | environ 0,12 $ |

Le volume de tokens d'une page de facture n'est pas donné par la page de tarifs : le mesurer avec le point d'accès de comptage de tokens avant de croire ces chiffres. Passer le juge sur Haiku divise son coût par vingt environ.

**Garde-fous.** Une clé par usage (développement, CI, production) et un plafond de dépense mensuel dans la Console Anthropic.

## Plan sur 4 semaines

Les évals arrivent avant l'optimisation. Chaque semaine se termine par un résultat vérifiable.

| Semaine | Contenu | Résultat vérifiable |
| --- | --- | --- |
| 1. Données et base | Générateur de factures synthétiques (FR et EN, dégradations), schéma pgvector en migrations, extraction v1 sur 10 documents | Un premier chiffre de précision par champ |
| 2. Contrôles et rapprochement | Fonctions de validation, rapprochement fournisseur et catégorie avec pgvector, dans le pipeline v1 | Les totaux incohérents passent à « à vérifier » ; un premier recall@k |
| 3. Revue, jeu de test, agent | Écran de revue Next.js, jeu de test élargi avec vingt vraies factures, agent v2, variantes comparées une par une | Un tableau avant et après pour chaque changement, dont v1 contre v2 |
| 4. MCP, CI, publication | Serveur MCP, contrôle de régression en CI, README avec résultats chiffrés et démo en GIF | Une PR qui dégrade le score est bloquée |

## Risques et décisions ouvertes

Le risque principal est financier : un dépôt de fichiers ouvert à tous sur une application branchée à une clé d'API payante peut vider les crédits.

| Risque | Gravité | Parade |
| --- | --- | --- |
| Dépôt public sans authentification, dépenses d'API incontrôlées | Élevée | Phrase secrète en middleware, taille de fichier et débit limités, plafond mensuel dans la Console, démo publique sur documents préchargés |
| Fuite d'une clé (`service_role`, Claude, embeddings) | Élevée | Variables d'environnement, rien dans le dépôt, une clé par usage |
| Vraies factures dans le dépôt ou en production | Élevée | Anonymisation, stockage local uniquement |
| Projet Supabase gratuit en pause pendant une démo | Moyenne | Plan Pro, ou réveil manuel avant chaque démo |
| Écart entre factures synthétiques et réelles | Moyenne | Vingtaine de vraies factures anonymisées pour le test final |
| Surlignage des champs peu fiable | Faible | Repli sur la recherche du texte extrait dans le PDF |

**Décisions ouvertes**

- [x] Hébergement du backend FastAPI : Railway (retenu le 25 novembre)
- [ ] Modèle d'embeddings, validé par le recall@k en français et en anglais
- [ ] Plan Supabase au moment de montrer la démo (gratuit ou Pro)
- [ ] Seuil de régression de la CI, à fixer après la première mesure
- [ ] Reranker : Claude Haiku ou modèle dédié, tranché par les évals
- [ ] Factures scannées : PDF envoyé directement au modèle, ou OCR préalable
- [ ] Schéma SQL détaillé (colonnes, types, contraintes)

## Sources

- [Embeddings, documentation Claude](https://platform.claude.com/docs/en/build-with-claude/embeddings)
- [Tarifs de l'API Claude](https://platform.claude.com/docs/en/about-claude/pricing)
- [Pause des projets gratuits Supabase](https://supabase.com/docs/guides/platform/free-plan-pausing)
- [Limite de 0,5 Go par projet gratuit](https://supabase.com/changelog/33121-relaxing-database-size-limit-on-free-plan-0-5-gb-database-size-per-project)
- [Tarifs Supabase](https://supabase.com/docs/pricing)
- [Prix Voyage, relevé par un tiers le 8 septembre 2026](https://blogs.novita.ai/anthropic-embeddings-api/)
