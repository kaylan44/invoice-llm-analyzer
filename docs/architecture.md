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

**Tableau d'évals.** Mesure du 27 novembre 2026 : `gemini-3.5-flash-lite`, prompt v1, jeu `evals/data/week2` (16 factures synthétiques : 8 FR, 8 EN ; 11 propres dont 5 piégées, 5 scans dégradés dont 1 avec une tache sur les totaux). Détail : `evals/baselines/week2.md` (extraction et contrôles) et `evals/baselines/week2_retrieval.md` (rapprochement). La mesure de la semaine 1 reste dans `evals/baselines/week1.md`.

| Champ | Français (n=8) | Anglais (n=8) | Scans dégradés (n=5) |
| --- | --- | --- | --- |
| Fournisseur | 100 % (24/24) | 100 % (24/24) | 100 % (15/15) |
| Date et n° de facture | 100 % (24/24) | 100 % (24/24) | 100 % (15/15) |
| Totaux et devise | 91 % (29/32) | 100 % (32/32) | 85 % (17/20) |
| Lignes (quantité, prix) | 100 % (163/163) | 100 % (158/158) | 100 % (130/130) |
| Catégorie comptable (recall@1, hybride) | 94 % sur 34 libellés FR et EN, dont 18 absents du catalogue | | |

Les 3 « erreurs » sur les totaux sont les 3 totaux cachés par la tache d'inv-011 : le modèle y répond `null`, ce qui est la bonne réponse, et la comparaison avec la valeur imprimée les compte « manqués ». Hors champs masqués, l'extraction est à 100 %.

Détection « à vérifier » : précision 100 % (6/6), rappel 100 % (6/6). Les 5 factures piégées échouent chacune au contrôle attendu, la facture tachée échoue sur les champs obligatoires (totaux absents), et aucune facture cohérente n'est envoyée en revue.

Rapprochement (recall@1) :

| Méthode | Fournisseurs (41 requêtes) | Catégories (34 requêtes) |
| --- | --- | --- |
| Plein texte seul | 88 % | 71 % |
| Vecteurs seuls | 100 % | 97 % |
| Hybride (RRF) | 100 % | 94 % |

Lecture :

- La tache d'inv-011 (dégradation `stain:totals`) remplace le scan entièrement illisible de la semaine 1, peu réaliste : une facture réelle est plutôt abîmée par endroits. Le modèle lit tout le reste de la page et laisse les trois totaux cachés à `null`, sans les recalculer à partir des lignes, comme le demande le prompt. L'extraction n'est toujours pas départagée (effet plafond).
- L'analyse d'erreur a trouvé un bug dans le jeu de test, pas dans le modèle : le piège sur la TVA n'était pas imprimé. Le gabarit imprime désormais toujours le total de TVA.
- Le plein texte seul échoue sur les fautes de frappe (fournisseurs) et sur les mots vides de la configuration `simple` (« de », « boîte de 50 ») pour les catégories. Les vecteurs seuls font légèrement mieux que l'hybride sur les catégories (1 requête d'écart sur 34) : pas assez pour trancher, à remesurer sur un jeu plus grand et après retrait des mots vides.
- Ces chiffres décrivent ce jeu synthétique, pas la qualité réelle. Prochaines étapes : niveaux de dégradation intermédiaires, factures sur plusieurs pages, vraies factures anonymisées (semaine 3).

**Jeu difficile (semaine 3).** Mesure du 27 novembre 2026, même modèle et même prompt, jeu `evals/data/week3` (24 factures : 12 FR, 12 EN, 12 scans). Il ajoute trois variantes qui rendent la lecture plus dure sans changer la bonne réponse : `long` (35 à 45 lignes sur deux pages, totaux en page 2), `client_vat` (n° de TVA du client imprimé avec le même libellé que celui du fournisseur), `deposit` (acompte déjà versé : le montant en gras en bas est le net à payer, pas le TTC), et un niveau de scan `medium` entre `heavy` et `illegible`. Détail : `evals/baselines/week3.md`.

| Groupe | Propres (n=12) | Scans (n=12) | Multipages (n=8) | Pièges de lecture (n=12) |
| --- | --- | --- | --- | --- |
| Fournisseur | 100 % (36/36) | 97 % (35/36) | 100 % (24/24) | 100 % (36/36) |
| Date et n° de facture | 100 % (36/36) | 100 % (36/36) | 100 % (24/24) | 100 % (36/36) |
| Totaux et devise | 100 % (48/48) | 100 % (48/48) | 100 % (32/32) | 100 % (48/48) |
| Lignes | 100 % (947/947) | 99 % (918/927) | 99 % (1609/1618) | 100 % (597/597) |

Lecture :

- Les pièges de lecture n'ont piégé personne : le modèle prend le « Total TTC » et non le « Net à payer » en gras, et le n° de TVA du fournisseur et non celui du client, sur les 12 factures. Les libellés sémantiques ne sont pas une faiblesse de Flash-Lite.
- Les 40 lignes sur deux pages sont lues sans perte ni doublon sur les PDF propres : `line_count` à 100 %.
- Toutes les erreurs (10) viennent des scans `medium` : confusions de caractères B/8, E/8, 5/3, 6/0 dans les références de ligne, et un chiffre du SIRET d'inv-017. Ce SIRET faux échoue à la clé de Luhn et envoie la facture en revue : le contrôle rattrape l'erreur de lecture.
- Le harnais compte ce renvoi en revue comme un faux positif, parce que le statut attendu ne dépend que du document (piège, illisible, tache), pas de ce que le modèle a lu. Décision ouverte ci-dessous.
- Le plafond est cassé seulement sur les scans dégradés, et de peu : 1 erreur sur 72 champs d'en-tête. Avec 24 factures, un écart d'une ou deux erreurs entre deux versions ne prouve rien. Pour départager v1 et v2, il faut plus de scans `medium` et les vraies factures.

**Comparer deux versions.** `python -m invoice_evals.compare --data <jeu> --a <run A> --b <run B>` donne, par groupe de champs, l'exactitude de chaque run avec son intervalle de Wilson à 95 %, et la différence B − A avec un intervalle bootstrap apparié par facture. Le verdict « B meilleur » exige que tout l'intervalle soit au-dessus de 0. Deux runs de la v1 sur le jeu de la semaine 3 diffèrent sur 4 champs (2 dans chaque sens) : c'est le bruit du modèle à température par défaut, et l'outil conclut « pas de différence démontrée » (`evals/baselines/week3_v1_rerun.md`). À 100 % sur 72 champs, l'intervalle de Wilson va encore de 94,9 % à 100 %.

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
| 2. Contrôles, rapprochement, déploiement | Postgres local et migrations pgvector, fonctions de validation, rapprochement fournisseur et catégorie dans le pipeline v1, API FastAPI déployée sur Railway en fin de semaine | Les totaux incohérents passent à « à vérifier » ; un premier recall@k ; l'API répond sur Railway. État au 27 novembre : les deux premiers sont atteints ; l'image Docker est prête et testée en local, le déploiement attend ton accord (`docs/deploy.md`) |
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
- [x] Modèle d'extraction de départ : `gemini-3.5-flash-lite`, qui lit les PDF (vérifié par l'appel réel du 26 novembre). La comparaison avec Flash attend un jeu qui les départage.
- [x] Embeddings : `gemini-embedding-2` à 768 dimensions (27 novembre). Recall@1 de 100 % sur les fournisseurs ; 1 536 non testé, sans intérêt tant que 768 plafonne.
- [x] Schéma SQL : `supabase/migrations/20261127090000_init.sql` (27 novembre).
- [x] Factures scannées : PDF envoyé directement au modèle, sans OCR préalable (scans légers et lourds lus à 100 %).
- [ ] Catégories comptables : liste de départ proposée dans `api/src/invoice_api/reference/categories.json`, à valider.
- [ ] Rapprochement fournisseur par nom : règle actuelle « accepté si les deux classements le trouvent ». Seuil à calibrer sur des cas où le fournisseur est absent de l'annuaire.
- [ ] Plein texte : retirer les mots vides (configuration `simple` gardée pour être neutre en langue), puis remesurer hybride contre vecteurs seuls sur les catégories.
- [ ] Plan Supabase au moment de montrer la démo (gratuit ou Pro)
- [ ] Seuil de régression de la CI, à fixer après la première mesure
- [ ] Statut « à vérifier » attendu : le définir par le document seul (actuel) ou aussi par la justesse de l'extraction (une facture mal lue mérite la revue)
- [ ] Reranker : Gemini Flash-Lite ou modèle dédié, tranché par les évals (inutile tant que le recall@1 plafonne)
- [ ] Stockage des PDF en production : Supabase Storage à brancher avant de garder des documents (voir `docs/deploy.md`)

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
