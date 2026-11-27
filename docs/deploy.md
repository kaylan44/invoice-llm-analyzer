# Déploiement de l'API (Railway + Supabase)

Ce guide met en production l'API FastAPI. Chaque étape qui touche la production (base Supabase, service Railway, clés) se fait **avec ton accord explicite**, et c'est toi qui saisis les secrets : ils ne passent jamais par le dépôt ni par Claude.

État au 27 novembre 2026 : l'image Docker est construite et testée en local (santé, jeton obligatoire, utilisateur non privilégié). Rien n'est déployé.

## Ce qu'il faut avant

| Élément | Pourquoi |
| --- | --- |
| Projet Supabase (production) | Base Postgres + pgvector, stockage des PDF |
| Supabase CLI sur ta machine | `supabase db push` applique `supabase/migrations/` |
| Projet Google « prod » **avec facturation activée** | L'offre gratuite Gemini est exclue pour un service ouvert depuis l'EEE ; budget et alerte à configurer |
| Compte Railway relié au dépôt GitHub | Railway construit le `Dockerfile` à la racine |
| Un jeton d'API aléatoire | Protège tous les endpoints sauf `/health` |

## 1. Base Supabase (accord requis)

```bash
supabase login
supabase link --project-ref <ref-du-projet>
supabase db push            # applique supabase/migrations/ sur la base distante
```

Puis charger les catégories comptables (un appel d'embedding, sur la clé Gemini de prod) :

```bash
DATABASE_URL='<chaîne de connexion Supabase>' GEMINI_API_KEY='<clé prod>' \
  uv run python -m invoice_api.seed --production
```

`invoice_api.migrate` et `invoice_api.seed` refusent un hôte Supabase par défaut : la production passe par `supabase db push` et par l'option `--production`, jamais par accident.

## 2. Service Railway

1. New Project → Deploy from GitHub repo → ce dépôt, branche `main`. Railway détecte le `Dockerfile` à la racine.
2. Variables du service (onglet Variables) :

| Variable | Valeur |
| --- | --- |
| `API_TOKEN` | jeton aléatoire, par exemple `openssl rand -base64 32` |
| `DATABASE_URL` | chaîne de connexion Supabase (pooler) |
| `GEMINI_API_KEY` | clé du projet Google **prod** (facturation activée) |
| `EXTRACTION_MODEL` | `gemini-3.5-flash-lite` |
| `EMBEDDING_MODEL` | `gemini-embedding-2` |
| `MAX_UPLOAD_MB` | `10` |

3. Settings → Healthcheck Path : `/health`. Railway attend une réponse 2xx avant d'activer un déploiement (délai par défaut : 300 s). Railway injecte `PORT`, que le conteneur écoute.
4. Pas de `railway.json` : la configuration par fichier (« Config as Code ») est dépréciée par Railway, avec un retrait annoncé le 1er décembre 2026 ([doc](https://docs.railway.com/reference/config-as-code)). Les réglages se font dans le tableau de bord.

## 3. Vérification

```bash
curl https://<service>.up.railway.app/health                  # {"status":"ok"}
curl -i https://<service>.up.railway.app/invoices             # 401 sans jeton
curl -H "Authorization: Bearer $API_TOKEN" https://<service>.up.railway.app/invoices
curl -H "Authorization: Bearer $API_TOKEN" -F file=@evals/data/week2/inv-001.pdf \
  https://<service>.up.railway.app/invoices                    # 202, puis GET /invoices/{id}
```

N'envoie que des factures synthétiques tant que le stockage n'est pas réglé (point suivant).

## Limites connues avant une démo publique

- **Stockage des fichiers** : l'API écrit les PDF sur le disque du conteneur (`STORAGE_DIR`), qui est **effacé à chaque redéploiement** sur Railway. Supabase Storage (bucket privé, URL signées) doit le remplacer avant de garder des documents en production.
- **Débit** : pas encore de limite de requêtes par client. Le jeton d'API, la taille maximale des fichiers et le budget Google Cloud sont les seuls garde-fous.
- **Pool de connexions** : une connexion Postgres par requête. Suffisant pour une démo, à remplacer par un pool si le trafic augmente.

## Sources

- [Railway, Dockerfiles](https://docs.railway.com/guides/dockerfiles)
- [Railway, Healthchecks](https://docs.railway.com/guides/healthchecks)
- [Railway, Config as Code (déprécié)](https://docs.railway.com/reference/config-as-code)
- [uv dans Docker](https://docs.astral.sh/uv/guides/integration/docker/)
- [Supabase, migrations](https://supabase.com/docs/guides/deployment/database-migrations)
