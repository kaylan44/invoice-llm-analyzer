# Architecture : extraction de factures fournisseurs

Nov 25, 2026 · @Guillaume · mis à jour le 26 novembre 2026 (passage de l'API Claude à l'API Gemini)

Présentation visuelle (vue d'ensemble, schéma, maquette de l'écran de revue, plan) : [Projet IA extraction de factures fournisseurs.pdf](Projet%20IA%20extraction%20de%20factures%20fournisseurs.pdf). Elle date d'avant le passage à Gemini : là où elle cite Claude comme modèle d'extraction, ce document fait foi.

## Contexte, périmètre et décisions

Le projet extrait les champs de factures fournisseurs en français et en anglais, avec revue humaine, sur une base Supabase hébergée en production. Il sert de portfolio AI engineer et couvre trois axes : agents et MCP, évals, RAG sur pgvector.

| Décision | Choix retenu | Raison |
| --- | --- | --- |
| Langues | Français et anglais | Deux langues suffisent pour un jeu de test fiable et simplifient les embeddings |
| Base de données | Supabase : Postgres + pgvector, hébergée | Une seule base, SQL standard, extension vectorielle incluse |
| Frontend | Next.js + TypeScript, sur Vercel | Stack maîtrisée, écran de revue rapide à construire |
| Backend | FastAPI (Python), sur Railway via Dockerfile | Python demandé par 71 % des offres d'AI engineer analysées (source à ajouter) |
| Modèles | API Gemini (Google), SDK Python `google-genai`, sans framework d'orchestration | Offre gratuite pour le développement, découverte d'un autre fournisseur ; une seule clé couvre aussi les embeddings (retenu le 26 novembre) |
| Extraction | Pipeline sans agent en v1, agent en v2 | La v1 sert de référence : l'agent doit prouver qu'il fait mieux |
| RAG | Rapprochement fournisseur et catégorie par pgvector | Mesurable par recall@k et MRR sur une vérité terrain connue |
| Intégration MCP | Serveur MCP en Python | Exposer l'extraction à un client MCP (Claude Desktop) ; MCP ne dépend pas du fournisseur du modèle d'extraction |

Hors périmètre : comptes utilisateurs, multi-tenant, paiement, intégration comptable, application mobile.

## Vue d'ensemble

```
Interface Next.js ──> API FastAPI ──> Extraction ──────────────> Supabase Postgres
(dépôt, revue)        (jobs,          (Gemini, vision ;           (pgvector, PDF,
     ^                 stockage)       v1 pipeline, v2 agent)       production)
     │                    ^              │            │                 │
     │                    │              v            v                 │
     │               Serveur MCP     Validation   Rapprochement         │
     │                    ^          (sommes,     (pgvector,            │
     │                    │          dates,        embeddings Gemini)   │
     │              Client MCP       devise)                            │
     │            (Claude Desktop)                                      │
     └──────────────────── revue et corrections ────────────────────────┘

Mesure et régression : Jeu de test (FR, EN) ──> Harnais d'évals (Postgres local) ──> CI de régression
```

L'interface Next.js et le serveur MCP passent tous deux par l'API FastAPI, la seule à détenir les clés de Supabase et de Gemini. Les évals tournent à part, sur un Postgres local.

## Frontend Next.js

Le frontend ne tient aucune clé secrète et ne parle qu'à l'API FastAPI : ni Supabase ni Gemini ne sont appelés depuis le navigateur. Les route handlers Next.js servent de relais, l'URL et le jeton de l'API restent côté serveur.

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
- Statut « en attente » : contrôles réussis, en attente d'une validation humaine. Le traitement en cours est un état du job, pas un statut de facture (à confirmer avec le schéma SQL).

## Backend FastAPI

Le backend orchestre l'extraction : il reçoit le fichier, appelle Gemini, écrit le résultat dans Supabase et ne renvoie jamais de clé au client.

| Endpoint | Rôle |
| --- | --- |
| POST /invoices | Enregistre le fichier dans Supabase Storage, crée un traitement |
| GET /invoices | Liste, filtre par statut |
| GET /invoices/{id} | Extraction, contrôles, URL signée du document |
| PATCH /invoices/{id} | Corrections faites en revue |
| POST /invoices/{id}/validate | Passe la facture au statut validée |
| GET /export | CSV ou JSON des factures validées |

**Extraction v1 : pipeline sans agent (référence).** L'ordre des étapes est fixé dans le code :

1. Un appel au modèle Gemini lit le document (PDF envoyé en ligne, en base64) et produit une extraction structurée : le schéma JSON est dérivé du modèle Pydantic et imposé par la sortie structurée de l'API.
2. La fonction de validation contrôle les champs (voir ci-dessous).
3. La fonction de rapprochement interroge pgvector pour normaliser le fournisseur et classer chaque ligne.
4. Si un contrôle échoue, la facture passe à « à vérifier » avec le motif. Pas de nouvelle tentative automatique en v1.

**Extraction v2 : agent avec outils.** Les mêmes fonctions deviennent des outils (`validate_invoice`, `match_supplier_and_category`) que le modèle appelle lui-même par function calling, dans une boucle écrite à la main. En cas d'échec d'un contrôle, il reprend le document, dans la limite d'un nombre d'itérations fixé en configuration. La v2 n'est retenue que si elle bat la v1 sur les évals, coût et latence inclus.

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

**Modèles.** Point de départ : le modèle le moins cher qui lit les PDF, dans la famille Flash-Lite (candidat : `gemini-3.5-flash-lite`), pour l'extraction, le reranking et le juge de premier passage. Une famille Flash sert de point de comparaison. Le modèle est un paramètre de configuration, pas une constante du code. Hypothèse à trancher par les évals, pas avant. La page des modèles ne précise pas, pour chaque modèle 3.x, s'il accepte les PDF : à vérifier avant l'étape d'extraction.

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

**Recherche hybride.** Une requête combine la distance cosinus pgvector et le plein texte Postgres, fusionnées par RRF (Reciprocal Rank Fusion). Le plein texte utilise la configuration `simple`, qui ne dépend d'aucune langue. Un reranking optionnel (modèle Gemini Flash-Lite ou modèle dédié) réordonne les candidats ; les évals comparent avec et sans.

**Embeddings.** Candidat : `gemini-embedding-2`, sur la même clé que l'extraction. Il produit 3 072 dimensions par défaut, réglables de 128 à 3 072 (768 et 1 536 recommandés). Un index HNSW pgvector sur le type `vector` est limité à 2 000 dimensions : on retient donc 768 ou 1 536, tranché par le recall@k. Ce modèle n'a pas de paramètre `task_type` ; la doc recommande un préfixe dans le texte (forme requête contre forme document). La doc annonce plus de 100 langues sans citer le français : le recall@k en français et en anglais valide le choix.

## Serveur MCP

Le serveur MCP expose trois outils à un client MCP (Claude Desktop pour la démo) et appelle l'API FastAPI, jamais Supabase directement : la logique métier reste à un seul endroit.

| Outil | Entrée | Sortie |
| --- | --- | --- |
| `extract_invoice` | Chemin d'un fichier local | Identifiant de la facture et statut |
| `list_pending_invoices` | Filtre de statut | Liste des factures à relire |
| `get_invoice` | Identifiant | Champs extraits, lignes, résultat des contrôles |

- **Transport.** stdio en local, déclaré dans la configuration du client MCP. Un transport HTTP distant est possible ensuite, mais exige une authentification que le MVP n'a pas.
- **Fichiers.** Le serveur lit le fichier sur la machine de l'utilisateur et l'envoie à l'API.
- **Authentification vers l'API.** Un jeton de service lu dans une variable d'environnement du processus MCP, jamais écrit dans la configuration versionnée.
- **Facturation.** Le client MCP passe par son propre abonnement (Claude Desktop : abonnement Claude de l'utilisateur, sans API Claude). Une extraction déclenchée par l'outil s'exécute dans le backend et se paie sur la clé Gemini.

Démo attendue : demander au client MCP « quelles factures sont à vérifier ? » puis « ouvre la dernière », enregistrée en GIF dans le README.

## Évals et CI de régression

Les évals rejouent l'extraction sur un jeu de test à vérité terrain connue et mesurent chaque champ ; la CI bloque toute PR qui fait baisser un score.

| Ce qui est mesuré | Méthode |
| --- | --- |
| Champs objectifs (fournisseur, numéro, dates, devise, totaux, lignes) | Exactitude par champ après normalisation des dates et des montants ; précision et rappel pour les champs facultatifs (SIRET, n° de TVA) |
| Détection des incohérences | Précision et rappel du statut « à vérifier » sur des factures piégées (total faux, champ absent) |
| Rapprochement fournisseur et catégorie | recall@k et MRR sur la recherche pgvector, avec et sans reranking |
| Qualité des catégories attribuées | Juge LLM, calibré sur 30 notes manuelles ; accord visé d'au moins 80 % |
| Pipeline v1 contre agent v2 | Mêmes métriques, plus coût et latence par facture |
| Flash-Lite contre Flash | Mêmes métriques, plus coût et latence par facture |

- **Jeu de test.** Factures synthétiques en français et en anglais générées par script, dont une part dégradée (rotation, flou, scan bruité). Les 10 premiers documents générés sont versionnés pour figer la baseline. Une vingtaine de vraies factures anonymisées servent au test final et restent en local.
- **Exécution.** En local et en CI, sur Postgres avec pgvector dans Docker, jamais sur la base Supabase de production.
- **Référence.** Un fichier de scores versionné dans le dépôt. Le seuil de régression se fixe après la première mesure, pas avant.
- **CI.** GitHub Actions lance un sous-ensemble sur chaque PR, compare à la référence et échoue si un score baisse au-delà du seuil. Chaque exécution appelle l'API : la clé de la CI est dédiée, dans son propre projet Google.

**Tableau d'évals.** Première mesure le 26 novembre 2026 : `gemini-3.5-flash-lite`, prompt v1, jeu `evals/data/week1` (10 factures synthétiques : 5 FR, 5 EN, dont 4 scans dégradés). Détail et analyse des erreurs : `evals/baselines/week1.md`.

| Champ | Français (n=5) | Anglais (n=5) | Scans dégradés (n=4) |
| --- | --- | --- | --- |
| Fournisseur | 100 % (15/15) | 100 % (15/15) | 100 % (12/12) |
| Date et n° de facture | 100 % (15/15) | 100 % (15/15) | 100 % (12/12) |
| Totaux et devise | 100 % (20/20) | 100 % (20/20) | 100 % (16/16) |
| Lignes (quantité, prix) | 100 % (110/110) | 100 % (120/120) | 100 % (109/109) |
| Catégorie comptable | à mesurer (semaine 2) | à mesurer (semaine 2) | à mesurer (semaine 2) |

Lecture : ce jeu est trop facile pour départager quoi que ce soit (effet plafond). Un score de 100 % ne peut ni montrer un progrès ni, avec 10 documents, garantir l'absence d'erreur en conditions réelles. Avant toute optimisation, le jeu de test doit être durci : dégradations plus fortes, mises en page plus variées, factures sur plusieurs pages, factures piégées (semaine 2) et vraies factures anonymisées (semaine 3).

## Clé d'API Gemini, offre gratuite et coûts

Une clé Gemini, créée dans Google AI Studio et rattachée à un projet Google Cloud, couvre l'extraction, l'agent, le juge, le reranking et les embeddings.

| Besoin | Couvert par la clé Gemini | Solution |
| --- | --- | --- |
| Extraction par vision (PDF, images) | Oui | Famille Flash-Lite, Flash en comparaison |
| Agent et appels d'outils (v2) | Oui | Function calling, boucle manuelle |
| Juge LLM des évals | Oui | Flash-Lite ou Flash |
| Reranking | Oui | Flash-Lite, comparé à un modèle de reranking dédié dans les évals |
| Embeddings pour pgvector | Oui | `gemini-embedding-2`, validé par le recall@k |
| Client MCP (Claude Desktop) | Hors clé | Abonnement du client MCP |
| Supabase, hébergement | Non | Comptes séparés |

**Offre gratuite : ce que disent les conditions** ([Gemini API Additional Terms](https://aistudio.google.com/docs/terms), en vigueur depuis le 23 mars 2026) :

- Sur l'offre gratuite (« Unpaid Services »), Google utilise le contenu envoyé pour améliorer ses produits et ses modèles, et des humains peuvent lire les entrées et les sorties.
- Les conditions demandent de ne pas envoyer d'informations sensibles, confidentielles ou personnelles sur l'offre gratuite.
- Les conditions excluent l'offre gratuite pour les clients d'API mis à disposition d'utilisateurs dans l'EEE, en Suisse ou au Royaume-Uni.
- Sur l'offre payante, les requêtes et les réponses ne servent pas à améliorer les produits ; elles sont journalisées brièvement pour la détection d'abus.

**Conséquences pour le projet.**

- Offre gratuite : uniquement les factures synthétiques, en développement local et en évals. Jamais de vraie facture, même anonymisée.
- Offre payante (facturation activée sur le projet Google) : obligatoire pour la démo déployée, accessible depuis la France, et pour le test final sur les vraies factures anonymisées.
- La portée exacte de l'exclusion EEE pour un développeur qui teste depuis la France est à relire dans les conditions avant le premier appel (confiance moyenne sur leur interprétation).

**Ordre de grandeur des coûts** (approximation, hypothèses non mesurées, tarifs à revérifier avant usage). Tarifs de la [page officielle](https://aistudio.google.com/docs/pricing), offre payante, relevés le 26 novembre 2026 : `gemini-3.5-flash-lite` à 0,30 $ en entrée et 2,50 $ en sortie par million de tokens, `gemini-3.8-flash` à 0,75 $ et 3,75 $ jusqu'au 31 décembre 2026 (1,50 $ et 7,50 $ ensuite), `gemini-embedding-2` à 0,20 $ en entrée, Batch API à moitié prix. Plusieurs tarifs changent le 1er décembre 2026 et le 1er janvier 2027.

| Poste | Hypothèse | Coût estimé |
| --- | --- | --- |
| Évals complètes, 60 factures, Flash-Lite | 12 000 tokens en entrée et 2 000 en sortie par facture, boucle d'outils comprise (la v1 sans agent en consomme moins) | 0,52 $ |
| Juge, 60 appels, Flash-Lite | 3 000 en entrée et 500 en sortie | 0,13 $ |
| Une passe complète | Somme des deux | environ 0,65 $ |
| 20 passes pendant le développement | Flash-Lite seul | environ 13 $, moitié moins avec la Batch API, 0 $ sur l'offre gratuite |
| Embeddings | 2 millions de tokens | environ 0,40 $, 0 $ sur l'offre gratuite |

Le volume de tokens d'une page de facture n'est pas donné par la page de tarifs : le mesurer avec le comptage de tokens de l'API avant de croire ces chiffres.

**Garde-fous.** Une clé par usage (développement, CI, production), chacune dans son propre projet Google. Sur l'offre payante, un budget avec alerte dans Google Cloud Billing ; les limites de débit par projet servent de plafond sur l'offre gratuite.

## Plan sur 4 semaines

Les évals arrivent avant l'optimisation. Chaque semaine se termine par un résultat vérifiable.

| Semaine | Contenu | Résultat vérifiable |
| --- | --- | --- |
| 1. Données et première mesure | Générateur de factures synthétiques (FR et EN, dégradations), normalisation et métriques, extraction v1 sur 10 documents | Une première exactitude par champ, versionnée comme baseline |
| 2. Contrôles, rapprochement, déploiement | Postgres local et migrations pgvector, fonctions de validation, rapprochement fournisseur et catégorie dans le pipeline v1, API FastAPI déployée sur Railway en fin de semaine | Les totaux incohérents passent à « à vérifier » ; un premier recall@k ; l'API répond sur Railway |
| 3. Revue, jeu de test, agent | Écran de revue Next.js, jeu de test élargi avec vingt vraies factures, agent v2, variantes comparées une par une | Un tableau avant et après pour chaque changement, dont v1 contre v2 |
| 4. MCP, CI, publication | Serveur MCP, contrôle de régression en CI, README avec résultats chiffrés et démo en GIF | Une PR qui dégrade le score est bloquée |

Le déploiement Railway suppose deux conditions : un accord explicite avant toute migration sur la base Supabase de production, et un jeton d'accès sur l'API.

## Risques et décisions ouvertes

Le risque principal est financier : un dépôt de fichiers ouvert à tous sur une application branchée à une clé d'API payante peut vider les crédits.

| Risque | Gravité | Parade |
| --- | --- | --- |
| Dépôt public sans authentification, dépenses d'API incontrôlées | Élevée | Phrase secrète en middleware, taille de fichier et débit limités, budget et alerte Google Cloud, démo publique sur documents préchargés |
| Fuite d'une clé (`service_role`, Gemini) | Élevée | Variables d'environnement, rien dans le dépôt, une clé par usage |
| Vraies factures envoyées sur l'offre gratuite Gemini | Élevée | Offre gratuite réservée aux factures synthétiques ; vraies factures uniquement sur un projet avec facturation activée |
| Vraies factures dans le dépôt ou en production | Élevée | Anonymisation, stockage local uniquement |
| Démo déployée sur l'offre gratuite, accessible depuis l'EEE | Élevée | Facturation activée sur le projet de production |
| Projet Supabase gratuit en pause pendant une démo | Moyenne | Plan Pro, ou réveil manuel avant chaque démo |
| Écart entre factures synthétiques et réelles | Moyenne | Vingtaine de vraies factures anonymisées pour le test final |
| Sortie structurée Gemini en preview sur les séries 3 et 4 | Moyenne | Validation Pydantic de chaque réponse côté Python ; un échec de validation compte comme une erreur dans les évals |
| Surlignage des champs peu fiable | Faible | Repli sur la recherche du texte extrait dans le PDF |

**Décisions ouvertes**

- [x] Hébergement du backend FastAPI : Railway (retenu le 25 novembre)
- [x] Fournisseur des modèles : API Gemini (retenu le 26 novembre)
- [ ] Modèle d'extraction exact (Flash-Lite ou Flash), après vérification de la lecture des PDF et tranché par les évals
- [ ] Dimension des embeddings (768 ou 1 536), validée par le recall@k en français et en anglais
- [ ] Plan Supabase au moment de montrer la démo (gratuit ou Pro)
- [ ] Seuil de régression de la CI, à fixer après la première mesure
- [ ] Reranker : Gemini Flash-Lite ou modèle dédié, tranché par les évals
- [ ] Factures scannées : PDF envoyé directement au modèle, ou OCR préalable
- [ ] Schéma SQL détaillé (colonnes, types, contraintes)

## Sources

Pages Gemini lues le 26 novembre 2026 (les adresses ai.google.dev redirigent vers aistudio.google.com) :

- [Modèles Gemini](https://aistudio.google.com/docs/models)
- [Tarifs de l'API Gemini](https://aistudio.google.com/docs/pricing)
- [Limites de débit](https://aistudio.google.com/docs/rate-limits)
- [Gemini API Additional Terms of Service](https://aistudio.google.com/docs/terms)
- [Sortie structurée](https://aistudio.google.com/docs/structured-output)
- [Traitement des documents (PDF)](https://aistudio.google.com/docs/document-processing)
- [Embeddings](https://aistudio.google.com/docs/embeddings)
- [Function calling](https://aistudio.google.com/docs/function-calling)

Autres sources :

- [Pause des projets gratuits Supabase](https://supabase.com/docs/guides/platform/free-plan-pausing)
- [Limite de 0,5 Go par projet gratuit](https://supabase.com/changelog/33121-relaxing-database-size-limit-on-free-plan-0-5-gb-database-size-per-project)
- [Tarifs Supabase](https://supabase.com/docs/pricing)
