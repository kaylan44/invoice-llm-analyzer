-- Initial schema: invoices, lines, extractions, jobs, and the two reference tables used for
-- retrieval (suppliers, categories) with a vector column and a full-text column each.
-- Applied locally by `python -m invoice_api.migrate`, in production by `supabase db push`.

create extension if not exists vector;

-- Embedding size: gemini-embedding-2 truncated to 768 dimensions (output_dimensionality).
-- An HNSW index on the vector type is limited to 2,000 dimensions, so 3072 would not fit.

-- --- Reference tables (retrieval) ----------------------------------------------------

create table suppliers (
  id bigint generated always as identity primary key,
  name text not null,
  aliases text[] not null default '{}',
  vat_number text unique,
  siret text unique,
  -- Normalized name and aliases (lowercase, no accents, no punctuation), written by the app.
  search_text text not null,
  fts tsvector generated always as (to_tsvector('simple', search_text)) stored,
  embedding vector(768),
  created_at timestamptz not null default now()
);
create index suppliers_fts_idx on suppliers using gin (fts);
create index suppliers_embedding_idx on suppliers using hnsw (embedding vector_cosine_ops);

create table categories (
  code text primary key,
  label text not null,
  description text not null,
  search_text text not null,
  fts tsvector generated always as (to_tsvector('simple', search_text)) stored,
  embedding vector(768)
);
create index categories_fts_idx on categories using gin (fts);
create index categories_embedding_idx on categories using hnsw (embedding vector_cosine_ops);

-- --- Invoices ------------------------------------------------------------------------

create type invoice_status as enum ('pending', 'to_review', 'validated');

create table invoices (
  id uuid primary key default gen_random_uuid(),
  status invoice_status not null default 'pending',
  review_reasons text[] not null default '{}',
  supplier_id bigint references suppliers (id),
  supplier_match text, -- how the supplier was matched: vat_number, siret, hybrid, none
  supplier_name text,
  supplier_vat_number text,
  supplier_siret text,
  invoice_number text,
  issue_date date,
  due_date date,
  currency text,
  total_excl_vat numeric(14, 2),
  total_vat numeric(14, 2),
  total_incl_vat numeric(14, 2),
  language text,
  file_path text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
-- Duplicate detection looks up (supplier, number); not unique: a duplicate is flagged, not refused.
create index invoices_supplier_number_idx on invoices (supplier_id, invoice_number);
create index invoices_status_idx on invoices (status);

create table invoice_lines (
  id bigint generated always as identity primary key,
  invoice_id uuid not null references invoices (id) on delete cascade,
  position int not null,
  description text,
  quantity numeric(14, 4),
  unit_price numeric(14, 4),
  vat_rate numeric(5, 2),
  amount numeric(14, 2),
  category_code text references categories (code),
  category_score real,
  unique (invoice_id, position)
);

-- One row per model run on an invoice: what was asked, what came back, what the checks said.
create table extractions (
  id bigint generated always as identity primary key,
  invoice_id uuid not null references invoices (id) on delete cascade,
  model text not null,
  prompt_version text not null,
  raw jsonb,
  checks jsonb not null default '[]',
  error text,
  input_tokens int,
  output_tokens int,
  latency_s real,
  created_at timestamptz not null default now()
);

create type job_status as enum ('queued', 'running', 'done', 'failed');

create table jobs (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references invoices (id) on delete cascade,
  status job_status not null default 'queued',
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- --- Security ------------------------------------------------------------------------
-- RLS on, no policy: only the backend, with the service_role key (which bypasses RLS),
-- can read or write. The anon key exposed by Supabase gets nothing.
alter table suppliers enable row level security;
alter table categories enable row level security;
alter table invoices enable row level security;
alter table invoice_lines enable row level security;
alter table extractions enable row level security;
alter table jobs enable row level security;

-- --- Hybrid search -------------------------------------------------------------------
-- Full-text and vector rankings fused with Reciprocal Rank Fusion (RRF), adapted from
-- https://supabase.com/docs/guides/ai/hybrid-search :
--   score(d) = sum over the two rankings of weight / (rrf_k + rank of d in that ranking)
-- A document ranked well by either method rises; one ranked well by both rises most.
-- Full text uses OR between the query words (a typo in one word must not discard the rest).

create function match_suppliers(
  query_text text,
  query_embedding vector(768),
  match_count int default 5,
  full_text_weight float default 1,
  semantic_weight float default 1,
  rrf_k int default 50
)
returns table (id bigint, score float, full_text_rank bigint, semantic_rank bigint)
language sql stable
as $$
  with full_text as (
    select s.id, row_number() over (order by ts_rank_cd(s.fts, q) desc) as rank_ix
    from suppliers s,
         to_tsquery('simple',
           array_to_string(tsvector_to_array(to_tsvector('simple', query_text)), ' | ')) q
    where s.fts @@ q
    order by rank_ix
    limit match_count * 4
  ),
  semantic as (
    select s.id, row_number() over (order by s.embedding <=> query_embedding) as rank_ix
    from suppliers s
    where s.embedding is not null
    order by rank_ix
    limit match_count * 4
  )
  select
    coalesce(f.id, v.id) as id,
    coalesce(full_text_weight / (rrf_k + f.rank_ix), 0.0)
      + coalesce(semantic_weight / (rrf_k + v.rank_ix), 0.0) as score,
    f.rank_ix as full_text_rank,
    v.rank_ix as semantic_rank
  from full_text f
  full outer join semantic v on f.id = v.id
  order by score desc
  limit match_count
$$;

create function match_categories(
  query_text text,
  query_embedding vector(768),
  match_count int default 5,
  full_text_weight float default 1,
  semantic_weight float default 1,
  rrf_k int default 50
)
returns table (code text, score float, full_text_rank bigint, semantic_rank bigint)
language sql stable
as $$
  with full_text as (
    select c.code, row_number() over (order by ts_rank_cd(c.fts, q) desc) as rank_ix
    from categories c,
         to_tsquery('simple',
           array_to_string(tsvector_to_array(to_tsvector('simple', query_text)), ' | ')) q
    where c.fts @@ q
    order by rank_ix
    limit match_count * 4
  ),
  semantic as (
    select c.code, row_number() over (order by c.embedding <=> query_embedding) as rank_ix
    from categories c
    where c.embedding is not null
    order by rank_ix
    limit match_count * 4
  )
  select
    coalesce(f.code, v.code) as code,
    coalesce(full_text_weight / (rrf_k + f.rank_ix), 0.0)
      + coalesce(semantic_weight / (rrf_k + v.rank_ix), 0.0) as score,
    f.rank_ix as full_text_rank,
    v.rank_ix as semantic_rank
  from full_text f
  full outer join semantic v on f.code = v.code
  order by score desc
  limit match_count
$$;
