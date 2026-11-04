# Operating ValueForge

## Daily operating cycle

GitHub Actions runs the weekday pipeline at 21:15 IST (cron 15:45 UTC):

1. Discover consolidated financial-result XBRL filings from NSE (legacy results + integrated filing feed) and the current BSE integrated-financial-results feed.
2. Keep a persistent discovery queue and process up to 180 filings per run, with bounded retries and polite request pacing.
3. Extract period-labelled facts into INR crore, preserve source URL, filing ID, basis, audited flag and XBRL parse diagnostics.
4. Refresh the latest NSE/BSE end-of-day price universe from TejHQ.
5. Merge the latest reliable fundamentals, derive TTM flows only from four consecutive discrete quarters, apply the value-investing research hurdles, and publish a status report.

The first successful filing sync automatically performs a one-time approximately five-year NSE discovery backfill. The persistent queue is then drained in bounded daily batches; later runs return to the configured incremental lookback. The initial backfill marker is stored at `data/fundamentals/backfill_state.json`. Discovery and parsing progress is written to `data/live/filings_status.json`.

Run manually from **Actions → ValueForge daily market refresh and research → Run workflow**. The default manual discovery lookback is 1,825 days; the default batch is 180 filings. Re-run manually to drain the queue faster if GitHub Actions runtime limits permit. The normal scheduled run uses a 45-day incremental discovery window.

## Market prices

The EOD price universe comes from the public TejHQ `tejhq/indian-markets` Hugging Face dataset. It is end-of-day bhavcopy-derived data, not intraday live quotes. The current pipeline selects the latest published trading date independently for NSE and BSE, rejects stale data older than ten calendar days, and uses supported equity series only. It does not claim to cover every suspended, non-traded, SME or delisted security.

TejHQ terms permit personal/private research but restrict redistribution of raw market data. Therefore raw market snapshots are ignored by Git and are not uploaded as public workflow artifacts. Do not publish the raw files or repurpose them commercially. Source: https://huggingface.co/datasets/tejhq/indian-markets and https://tejhq.com/terms.

## Fundamental filing ingestion

The current public free-data path is exchange XBRL, not a Screener.in API.

- NSE: official corporate financial-results discovery and Integrated Filing Financial XBRL attachments. Historical discovery is windowed; the queue preserves records that are not processed in the first batch.
- BSE: current Integrated Filing Financial RSS feed can expose XBRL XML instances. The older BSE result search commonly links to PDF attachments rather than XBRL; those records are not falsely treated as parsed XBRL.
- Screener.in: import a CSV export manually where convenient. ValueForge does not assume an official public Screener API, automate logins, bypass CAPTCHAs/paywalls or scrape restricted pages.
- Company reports and exchange filings remain the source of record. The XBRL reader is namespace/taxonomy-aware where possible, but each extracted value must still be verified against the filing.

NSE Integrated Filing Financial can have revised, consolidated, standalone, audited and unaudited records. ValueForge preserves filing-level identity and parser version; the current production queue prioritises consolidated records. Quarterly flows are not mixed with cumulative year-to-date contexts. TTM flows are calculated only from four consecutive discrete quarters. No missing number is converted to zero.

Extracted facts are in `data/fundamentals/xbrl_fundamentals.csv`; parse/discovery registry is `data/fundamentals/processed_filings.csv`; the persistent queue is `data/fundamentals/xbrl_filing_queue.jsonl`. Raw XBRL payload files are temporary and removed after parsing. Parser changes bump `PARSER_VERSION` and cause queued filings to be re-evaluated.

### Backfill / troubleshooting

- If the queue is not yet drained, `pending_after_batch` in `data/live/filings_status.json` shows what remains.
- `fetch_failed` indicates network / archive failure; these remain eligible for a later retry.
- `parse_failed` indicates the XML was downloaded but a safe period/context could not be selected or a taxonomy mapping is not supported. Do not treat it as a zero result.
- `COMPLETED_WITH_ERRORS` means the operation ran but some source, fetch or parse failures occurred.
- To force reprocessing after a parser change, increment `PARSER_VERSION` in `valueforge/filings.py`.
- Do not delete the queue/registry casually; they are the resumable checkpoint.

## Using the research dashboard

The app is a personal research dashboard and is password-locked. In Streamlit Cloud, add:

```toml
VALUEFORGE_APP_PASSWORD = "use-a-long-unique-password"
```

Also add `GEMINI_API_KEY` only if you want the optional AI specialist agents. The deterministic scanner, data-health tab and evidence-gap report continue to work without Gemini. Do not put secrets in Git.

Deploy through https://share.streamlit.io/ using repository `vshanbhag54/valueforge`, branch `main`, entry point `app.py`, Python 3.11. Keep the app password enabled. The hosted app fetches EOD prices if it has no local snapshot; its CSV upload is session-only and must be committed separately if it should feed future scheduled runs.

## Investment research safeguards

- A price-only security is never a value candidate.
- An instrument with missing / stale statement periods is blocked from a positive value-research status.
- Banks, NBFCs and insurers are routed to `SECTOR_MODEL_REQUIRED`; industrial ROCE/debt rules are not applied to them.
- High promoter pledge, excessive leverage, loss-making status and stale filings are separate review blockers.
- A high heuristic score means research priority, not fair value, probability of return or a buy recommendation.
- AI agents can summarise and challenge evidence, but cannot create facts, override validation failures or place orders.
- No broker API, order placement or automated trading is present.

## Current coverage limits

This is a continuously updating research operation, but free public sources do not guarantee a perfect, complete all-listings fundamental database:
- TejHQ's EOD universe is based on supported and traded series; inactive / suspended / non-traded instruments can be absent.
- The NSE result XBRL feed covers companies that publish accessible XBRL financial filings. BSE historical PDF result attachments are not yet normalized as full financial statements.
- Some XBRL taxonomies/concepts, reporting periods and issuer-specific extensions need mapping; all parse failures are retained in the registry and reported.
- The initial backfill takes multiple batches. A company is not eligible for deeper value screening until it has sufficiently complete, current fundamentals.
- Financial sector models, historical restatement handling, corporate-action adjustments, deeper annual-report PDF table extraction and full peer valuation remain further work.

ValueForge is research software, not investment advice or a SEBI-registered advisory service. It is not an execution system.
