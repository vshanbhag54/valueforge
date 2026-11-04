# ValueForge

Research-only Indian equity value-investing desk for NSE and BSE.

## Daily market operation
After merge, GitHub Actions runs weekdays at 21:15 IST and on code changes. It reads the public TejHQ Indian Markets annual Parquet rollups, selects the most recent EOD snapshot from each exchange, joins daily derived metrics, and runs a deterministic research screen. The data source is third-party processed exchange bhavcopy, not intraday quotes: https://github.com/tejhq/tej-bazaar and https://huggingface.co/datasets/tejhq/indian-markets.

The dashboard fetches the latest available EOD data directly from the public dataset when no local snapshot is present. GitHub Actions commits compact status, exchange security-master and parsed filing data; raw market snapshots and raw XBRL payloads are not committed or published.

## Install locally (Python 3.11+)
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m valueforge.cli refresh-and-scan
streamlit run app.py
```

## Fundamentals
There is no official public Screener.in API integration. Use permitted Screener CSV exports or verified company/exchange filings. Upload CSV in the dashboard, normalize it, and commit the normalized rows to data/fundamentals/company_fundamentals.csv for persistent daily scans. ISIN is the preferred cross-exchange key. Missing values stay missing.

## AI analyst team
Optional Gemini API support runs four specialist analyses (financial quality, valuation, forensic accounting and bear case) plus a committee synthesis for selected candidates. Add GEMINI_API_KEY to GitHub Actions secrets for scheduled reports and Streamlit Secrets for on-demand reports. Without a key, deterministic scanning and evidence-gap memos remain available. Check current free-tier quotas and data-use terms before use.

See docs/OPERATIONS.md for deployment, workflows and data limitations.

**Research software only. No broker actions. Scores are triage signals, not investment advice.**


## Persistent PostgreSQL store (optional)

The repository includes a private PostgreSQL schema and an optional adapter for storing exchange securities, EOD prices, filings, normalized financial statements, research runs and research results. Local CSV checkpoints remain available when a database is not configured.

To enable it:
1. Provision a PostgreSQL database (Supabase Postgres is supported).
2. Run the complete `database/schema.sql` once in the database SQL editor. Keep the `valueforge` schema private; do not expose it through the Data API.
3. Add `VALUEFORGE_DATABASE_URL` as a GitHub Actions repository secret. Use a TLS connection string (for Supabase, use the database connection string with SSL enabled). Never commit credentials.
4. Trigger **ValueForge daily market refresh and research** from the Actions tab. The status JSON will report `database.status=CONNECTED` or an explicit error.

The adapter is optional: without the secret, daily research continues with local checkpoints and reports `NOT_CONFIGURED`. The database is not provisioned by this repository; run the SQL only after you have chosen and created a database project.
