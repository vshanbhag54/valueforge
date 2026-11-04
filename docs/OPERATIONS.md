# Operating ValueForge

## Automatic daily cycle
After merging to the default branch, GitHub Actions is scheduled weekdays at 21:15 India Standard Time. It lists TejHQ dataset partitions, downloads the latest NSE and BSE daily EOD bhavcopy Parquet files, joins available derived metrics, writes the latest market universe, runs the deterministic scanner and commits snapshots under data/live. You can also run this workflow manually from GitHub Actions.

The TejHQ dataset is a third-party cleaned dataset built from exchange bhavcopy. Its documentation describes supported equity series, 2024+ CMTS coverage, daily-traded instrument limits, Parquet schema and adjusted-close reconciliation gaps. It is not a promise of every listed, suspended or non-trading security. Dataset: https://huggingface.co/datasets/tejhq/indian-markets ; pipeline: https://github.com/tejhq/tej-bazaar

## Getting real value research
Price data does not tell us whether a company is undervalued. No free full-market fundamentals API is assumed.

1. Export a Screener.in screen as CSV or prepare data matching data/fundamentals/company_fundamentals.csv.
2. Upload the CSV in the dashboard to normalize and preview it.
3. Download the normalized CSV and commit it to data/fundamentals/company_fundamentals.csv.
4. Supply symbol or preferably ISIN, period_end, consolidated/standalone basis, and source provenance.
5. The daily scanner joins fundamentals by ISIN first, symbol as fallback, and only ranks companies with sufficient recent evidence.

Avoid ticker-only mapping where symbols are ambiguous or have changed. Include separate rows for historical periods if you want historical statement analysis; the current scanner selects the latest period per company.

## Optional AI analyst team
Create a Gemini Developer API key in Google AI Studio and add GEMINI_API_KEY to Streamlit app Secrets. GEMINI_MODEL can override the default gemini-2.5-flash-lite. Clicking Run runs four specialists and one committee synthesis for one selected company. It does not call the LLM across all securities automatically, to avoid quota exhaustion and weak conclusions. Google currently offers limited free model tiers, and says free-tier content may be used to improve its products. Check quotas and terms in AI Studio; do not submit confidential material.

Without a key, the dashboard still produces a deterministic facts-and-gaps memo.

## Free dashboard deployment
1. Open https://share.streamlit.io/ and connect the GitHub account that has access.
2. Create an app for vshanbhag54/valueforge, branch main, file app.py.
3. Select Python 3.11 if available, then deploy.
4. Add GEMINI_API_KEY under app Settings → Secrets only if using AI analysis.

The hosted app reads the daily snapshots committed by GitHub Actions. Session CSV uploads are not retained; commit the normalized file to the repository for future runs.

## Status labels
VALUE_RESEARCH_CANDIDATE means the heuristic passes a research hurdle, not buy. VALUE_WATCHLIST is an intermediate score. FUNDAMENTALS_INCOMPLETE, PERIOD_NOT_VERIFIED and FUNDAMENTALS_STALE block a positive call. GOVERNANCE_REVIEW, LEVERAGE_REVIEW and LOSS_MAKING_REVIEW require manual review. SECTOR_MODEL_REQUIRED deliberately excludes banks, NBFCs and insurers from industrial-company ratio rules.

## Limitations
- Free TejHQ dataset contains EOD market prices/metrics, not full balance sheets or audited income/cash-flow statements.
- Screener uploads are not persistent until committed to the repository.
- PDF text extraction may miss statement tables, footnotes or scanned pages. Check the source PDF.
- LLM output can be wrong and is not investment advice.
- No broker integration, portfolio execution, order placement or SEBI-regulated advisory.
