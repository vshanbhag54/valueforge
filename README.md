# ValueForge

Research-only, multi-agent value-investing research desk for Indian listed equities (NSE/BSE).

> Not investment advice. No trading or broker order execution. Verify figures against primary filings before making investment decisions.

## MVP
- Streamlit dashboard for CSV imports, screening, company research and memo export.
- Transparent deterministic value/quality score; missing values are never treated as zero.
- Specialist research modules for financial quality, valuation, forensic accounting and industry context.
- Data provenance fields: source URL, period end, reporting basis and data-as-of date.
- Illustrative sample dataset clearly marked as fictitious.

## Quick start (Python 3.11+)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Upload a CSV matching `data/templates/company_fundamentals.csv`. Screener.in is supported via user-exported CSV; this project does not assume an official public Screener.in API or bypass site access controls.

## Architecture
CSV / permitted public filings -> normalized records -> validation -> deterministic screen -> specialist research roles -> committee memo -> human review.

The included roles are auditable Python modules, not unconstrained autonomous LLM agents. LLM narrative generation may be added later, but claims must cite evidence and may not override failed validation.

## Important limitations
Free sources alone do not guarantee complete NSE+BSE coverage or clean historical fundamentals. Financial institutions require sector-specific logic; this MVP flags missing industrial-company metrics rather than fabricating values. Screening scores are triage tools, not fair-value estimates or buy signals.
