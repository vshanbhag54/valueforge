# ValueForge

Research-only Indian equity value-investing desk for NSE and BSE.

## Daily market operation
After merge, GitHub Actions runs weekdays at 21:15 IST and on code changes. It reads the public TejHQ Indian Markets annual Parquet rollups, selects the most recent EOD snapshot from each exchange, joins daily derived metrics, and runs a deterministic research screen. The data source is third-party processed exchange bhavcopy, not intraday quotes: https://github.com/tejhq/tej-bazaar and https://huggingface.co/datasets/tejhq/indian-markets.

The dashboard fetches the latest available EOD data directly from the public dataset when no local snapshot is present. GitHub Actions stores each complete market/scan CSV as a 90-day workflow artifact; only compact status JSON and AI report markdown are committed to Git to avoid repository history growing by several megabytes per trading day.

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
