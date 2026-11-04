-- ValueForge operational store for PostgreSQL / Supabase.
-- This schema is intentionally private: do not expose it through the Supabase Data API.
create schema if not exists valueforge;

create table if not exists valueforge.schema_version (
    version integer primary key,
    applied_at timestamptz not null default now(),
    description text not null
);

create table if not exists valueforge.companies (
    company_key text primary key,
    isin varchar(12),
    canonical_name text,
    sector text,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    check (isin is null or isin ~ '^IN[A-Z0-9]{10}$')
);
create unique index if not exists companies_isin_uq
    on valueforge.companies(isin) where isin is not null;

create table if not exists valueforge.securities (
    exchange text not null check (exchange in ('NSE','BSE')),
    symbol text not null,
    series text not null default '',
    security_code text,
    isin varchar(12),
    company_key text references valueforge.companies(company_key),
    security_status text,
    master_as_of date,
    source_url text,
    updated_at timestamptz not null default now(),
    primary key (exchange, symbol, series)
);
create index if not exists securities_isin_idx on valueforge.securities(isin);
create index if not exists securities_company_idx on valueforge.securities(company_key);
create index if not exists securities_code_idx on valueforge.securities(exchange, security_code);

create table if not exists valueforge.market_prices (
    exchange text not null,
    symbol text not null,
    series text not null default '',
    snapshot_date date not null,
    company_key text references valueforge.companies(company_key),
    isin varchar(12),
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    volume numeric,
    turnover numeric,
    source text not null,
    ingested_at timestamptz not null default now(),
    primary key (exchange, symbol, series, snapshot_date)
);
create index if not exists market_prices_date_idx on valueforge.market_prices(snapshot_date desc);
create index if not exists market_prices_company_idx on valueforge.market_prices(company_key, snapshot_date desc);

create table if not exists valueforge.filings (
    filing_key text primary key,
    company_key text references valueforge.companies(company_key),
    exchange text,
    symbol text,
    security_code text,
    isin varchar(12),
    filing_id text,
    period_end date,
    filing_at timestamptz,
    reporting_basis text,
    audited boolean,
    source_url text not null,
    parser_version integer,
    parse_status text,
    fact_count integer,
    parse_error text,
    updated_at timestamptz not null default now()
);
create index if not exists filings_company_period_idx on valueforge.filings(company_key, period_end desc);
create index if not exists filings_status_idx on valueforge.filings(parse_status, parser_version);

create table if not exists valueforge.financial_statements (
    filing_key text primary key references valueforge.filings(filing_key) on delete cascade,
    company_key text not null references valueforge.companies(company_key),
    period_end date not null,
    period_kind text not null,
    period_days integer,
    reporting_basis text not null,
    audited boolean,
    data_as_of timestamptz,
    source_url text not null,
    taxonomy_family text,
    data_quality_status text,
    statement_completeness_pct numeric,
    metrics jsonb not null default '{}'::jsonb,
    fact_provenance jsonb not null default '{}'::jsonb,
    ingested_at timestamptz not null default now()
);
create index if not exists financial_statements_company_period_idx
    on valueforge.financial_statements(company_key, period_end desc, reporting_basis);
create index if not exists financial_statements_quality_idx
    on valueforge.financial_statements(data_quality_status, period_end desc);

create table if not exists valueforge.ingestion_runs (
    id bigint generated always as identity primary key,
    source text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    status text not null,
    rows_seen integer not null default 0,
    rows_written integer not null default 0,
    details jsonb not null default '{}'::jsonb
);

create table if not exists valueforge.research_runs (
    id bigint generated always as identity primary key,
    started_at timestamptz not null default now(),
    market_date date,
    model_version text not null,
    status text not null,
    summary jsonb not null default '{}'::jsonb
);

create table if not exists valueforge.research_results (
    research_run_id bigint not null references valueforge.research_runs(id) on delete cascade,
    company_key text not null references valueforge.companies(company_key),
    exchange text,
    symbol text,
    close numeric,
    value_score numeric,
    research_status text,
    financial_quality_status text,
    valuation_status text,
    margin_of_safety_pct numeric,
    fair_value_bear numeric,
    fair_value_base numeric,
    fair_value_bull numeric,
    payload jsonb not null default '{}'::jsonb,
    primary key (research_run_id, company_key, exchange)
);
create index if not exists research_results_status_idx
    on valueforge.research_results(research_status, value_score desc);

create table if not exists valueforge.agent_reports (
    id bigint generated always as identity primary key,
    research_run_id bigint references valueforge.research_runs(id) on delete cascade,
    company_key text references valueforge.companies(company_key),
    agent_role text not null,
    model text,
    report text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists valueforge.watchlists (
    id bigint generated always as identity primary key,
    name text not null unique,
    description text,
    created_at timestamptz not null default now()
);
create table if not exists valueforge.watchlist_items (
    watchlist_id bigint not null references valueforge.watchlists(id) on delete cascade,
    company_key text not null references valueforge.companies(company_key),
    note text,
    added_at timestamptz not null default now(),
    primary key (watchlist_id, company_key)
);

create table if not exists valueforge.paper_portfolios (
    id bigint generated always as identity primary key,
    name text not null unique,
    base_currency text not null default 'INR',
    initial_cash numeric not null default 0,
    created_at timestamptz not null default now()
);
create table if not exists valueforge.paper_transactions (
    id bigint generated always as identity primary key,
    portfolio_id bigint not null references valueforge.paper_portfolios(id) on delete cascade,
    company_key text not null references valueforge.companies(company_key),
    exchange text not null,
    symbol text not null,
    side text not null check (side in ('BUY','SELL')),
    quantity numeric not null check (quantity > 0),
    price numeric not null check (price > 0),
    fees numeric not null default 0,
    traded_at timestamptz not null,
    note text,
    created_at timestamptz not null default now()
);
create index if not exists paper_transactions_portfolio_date_idx
    on valueforge.paper_transactions(portfolio_id, traded_at);
create table if not exists valueforge.data_quality_issues (
    id bigint generated always as identity primary key,
    company_key text references valueforge.companies(company_key),
    filing_key text references valueforge.filings(filing_key) on delete cascade,
    issue_code text not null,
    severity text not null check (severity in ('INFO','WARNING','ERROR')),
    detail text not null,
    detected_at timestamptz not null default now(),
    resolved_at timestamptz
);
create index if not exists data_quality_open_idx
    on valueforge.data_quality_issues(severity, detected_at desc) where resolved_at is null;

-- Keep all operational tables out of the exposed public API and enable RLS
-- as defense in depth. The backend uses a private Postgres connection.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'companies','securities','market_prices','filings','financial_statements',
        'ingestion_runs','research_runs','research_results','agent_reports',
        'watchlists','watchlist_items','paper_portfolios','paper_transactions',
        'data_quality_issues'
    ] loop
        execute format('alter table valueforge.%I enable row level security', table_name);
        execute format('revoke all on table valueforge.%I from public', table_name);
        if exists (select 1 from pg_roles where rolname = 'anon') then
            execute format('revoke all on table valueforge.%I from anon', table_name);
        end if;
        if exists (select 1 from pg_roles where rolname = 'authenticated') then
            execute format('revoke all on table valueforge.%I from authenticated', table_name);
        end if;
        if exists (select 1 from pg_roles where rolname = 'service_role') then
            execute format('grant all on table valueforge.%I to service_role', table_name);
        end if;
    end loop;
end $$;

revoke all on schema valueforge from public;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on schema valueforge from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on schema valueforge from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        grant usage on schema valueforge to service_role;
        grant usage, select on all sequences in schema valueforge to service_role;
    end if;
end $$;

insert into valueforge.schema_version(version, description)
values (1, 'Initial private operational research store')
on conflict (version) do nothing;
