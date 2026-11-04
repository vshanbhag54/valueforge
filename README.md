# ValueForge

Research-only Indian equity value-investing desk for NSE and BSE.

## Live market operation
After merge, GitHub Actions runs weekdays at 21:15 IST. It:
1. Finds latest NSE and BSE annual exchange rollups in the public TejHQ Indian Markets dataset.
2. Downloads daily EOD OHLCV and joins available derived market metrics.
3. Saves market source/freshness status and latest universe.
4. Runs the value screener against the fundamentals available in the repository.
5. Commits updated snapshots under data/live.

This is end-of-day data, not an intraday feed. The dataset is third-party processed exchange bhavcopy with documented coverage and reconciliation limits: https://github.com/tejhq/tej-bazaar and https://huggingface.co/datasets/tejhq/indian-markets.

## Local installation (Python 3.11+)
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m valueforge.cli refresh-and-scan
streamlit run app.py
```

## Fundamentals
There is no official public Screener.in API integration. Use permitted Screener CSV exports or verified company/exchange filings. Upload CSV in the dashboard, normalize it, then commit the result to data/fundamentals/company_fundamentals.csv for persistent daily scans. ISIN is the preferred join key. Missing values stay missing.

## AI analyst team
Optional Gemini API support runs four specialist analyses (financial quality, valuation, forensic accounting and bear case) plus a committee synthesis for a selected company. Add GEMINI_API_KEY to Streamlit Secrets. Without a key, deterministic screening and evidence-gap memos remain available. Google says free-tier content may be used to improve products; check current terms and avoid confidential data.

See docs/OPERATIONS.md for deployment and data limitations.

**Research software only. No broker actions. Scores are triage signals, not investment advice.**
