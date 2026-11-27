# Écran de revue (Next.js)

Liste des factures, dépôt, revue (document à gauche, champs à droite avec badge « Sûr » ou « À vérifier »), correction, validation, export. Le frontend n'appelle que l'API FastAPI : `lib/api.ts` est le seul module qui lui parle, côté serveur, avec `API_TOKEN`. Le navigateur ne voit jamais le jeton.

```bash
cp .env.example .env.local   # API_URL, API_TOKEN (le même que l'API), DEMO_PASSPHRASE
npm install
npm run dev                   # http://localhost:3000
```

En local, l'API tourne avec `uv run uvicorn invoice_api.app:app --env-file .env.local` depuis la racine du dépôt (base Docker : `docker compose up -d db`).

- `proxy.ts` : phrase secrète de démo, un cookie qui contient son empreinte. Sans `DEMO_PASSPHRASE`, personne n'entre.
- `app/api/invoices/[id]/document` et `app/api/export` : relais vers l'API, qui ajoutent le jeton.
- Next 16 : `middleware` s'appelle `proxy`, et avec `cacheComponents` les lectures liées à la requête sont sous `<Suspense>` (voir `node_modules/next/dist/docs`).
