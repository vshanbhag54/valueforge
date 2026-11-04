from __future__ import annotations
import json
import os
import hmac
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from valueforge.agents import run_ai_committee
from valueforge.fundamentals import normalize_fundamentals
from valueforge.market_data import download_latest_market_data, load_market_snapshot
from valueforge.pdf_extract import extract_relevant_pdf_text
from valueforge.research import fundamental_eligibility_summary, merge_market_and_fundamentals
from valueforge.scoring import screen_universe
from valueforge.universe import attach_market_prices, fetch_security_master, load_security_master

st.set_page_config(page_title="ValueForge | Indian Value Research", page_icon="📈", layout="wide")
st.title("ValueForge")
st.caption("Indian equity research desk · NSE + BSE · Value investing · Research only")
st.caption(f"Build: {os.getenv('VALUEFORGE_BUILD_REV', 'source checkout')}")

def require_private_access():
    try:
        expected=st.secrets.get("VALUEFORGE_APP_PASSWORD")
    except Exception:
        expected=None
    expected=expected or os.getenv("VALUEFORGE_APP_PASSWORD")
    if not expected:
        st.error("ValueForge is locked. Set VALUEFORGE_APP_PASSWORD in Streamlit Secrets (or the local environment) before using this personal research dashboard.")
        st.code('VALUEFORGE_APP_PASSWORD = "choose-a-long-unique-password"', language="toml")
        st.stop()
    if not st.session_state.get("valueforge_authenticated",False):
        with st.form("valueforge_login"):
            supplied=st.text_input("Private dashboard password",type="password")
            submit=st.form_submit_button("Unlock ValueForge")
        if submit and hmac.compare_digest(str(supplied),str(expected)):
            st.session_state["valueforge_authenticated"]=True
            st.rerun()
        if submit:
            st.error("Incorrect password.")
        st.stop()

require_private_access()

def read_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

@st.cache_data(ttl=1800, show_spinner=False)
def get_market_data():
    local = load_market_snapshot()
    if not local.empty:
        return local, read_json("data/live/market_status.json")
    # Streamlit hosting does not persist the Actions runner filesystem.
    # Fetch the latest public EOD snapshot directly when no local snapshot exists.
    return download_latest_market_data()

@st.cache_data(ttl=86400, show_spinner=False)
def get_security_master_data():
    local=load_security_master()
    if not local.empty:
        return local,read_json("data/master/security_master_status.json")
    return fetch_security_master()

try:
    with st.spinner("Loading the latest NSE/BSE end-of-day snapshot..."):
        market, market_status = get_market_data()
    try:
        with st.spinner("Loading exchange-listed equity universe..."):
            security_master, security_master_status = get_security_master_data()
    except Exception as exc:
        security_master=pd.DataFrame()
        security_master_status={"coverage":"UNAVAILABLE","error":f"{type(exc).__name__}: {exc}"}
    if not security_master.empty:
        market=attach_market_prices(security_master,market)
except Exception as exc:
    st.error(f"Market data could not be loaded: {exc}")
    st.markdown("[TejHQ public Indian markets dataset](https://huggingface.co/datasets/tejhq/indian-markets)")
    st.stop()

if market.empty:
    st.error("The market-data provider returned an empty snapshot. No screening was run.")
    st.stop()

scan_status = read_json("data/live/research_status.json")
fundamentals_path = Path("data/fundamentals/company_fundamentals.csv")
xbrl_fundamentals_path = Path("data/fundamentals/xbrl_fundamentals.csv")
try:
    configured_gemini_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    configured_gemini_key = os.getenv("GEMINI_API_KEY")

with st.sidebar:
    st.header("Research settings")
    st.caption("Market prices are end-of-day, not intraday live quotes.")
    uploaded = st.file_uploader("Import Screener / fundamentals CSV", type=["csv"])
    st.divider()
    st.subheader("AI analyst team")
    st.write("Gemini analysis:", "Configured" if configured_gemini_key else "Not configured")
    st.caption("Add GEMINI_API_KEY to Streamlit Secrets for on-demand specialist analysis. The key is not stored in this repository.")

fundamental_frames=[]
if uploaded is not None:
    try:
        fundamental_frames.append(normalize_fundamentals(pd.read_csv(uploaded),source_label="Manual Screener / session upload"))
        fundamentals_source="Session Screener upload + repository XBRL history"
    except Exception as exc:
        st.error(f"Could not read the fundamentals CSV: {exc}")
        st.stop()
elif fundamentals_path.exists():
    fundamental_frames.append(normalize_fundamentals(pd.read_csv(fundamentals_path),source_label="Manual Screener / repository fundamentals"))
    fundamentals_source="Repository Screener fundamentals + XBRL history"
else:
    fundamentals_source="Exchange XBRL history"
if xbrl_fundamentals_path.exists():
    try:
        fundamental_frames.append(normalize_fundamentals(pd.read_csv(xbrl_fundamentals_path),source_label="Exchange XBRL filings"))
    except Exception as exc:
        st.warning(f"XBRL fundamentals could not be read: {exc}")
fundamentals=pd.concat(fundamental_frames,ignore_index=True,sort=False) if fundamental_frames else pd.DataFrame()
try:
    eligibility_summary=fundamental_eligibility_summary(fundamentals)
except Exception as exc:
    eligibility_summary={"status":"ERROR","error":f"{type(exc).__name__}: {exc}"}

companies = merge_market_and_fundamentals(market, fundamentals)
result = screen_universe(companies)
df = result.companies

dates = market_status.get("exchange_dates", {}) if isinstance(market_status, dict) else {}
nse_date = dates.get("NSE", str(df.loc[df["exchange"].astype(str).str.upper()=="NSE", "snapshot_date"].max()) if "snapshot_date" in df else "—")
bse_date = dates.get("BSE", str(df.loc[df["exchange"].astype(str).str.upper()=="BSE", "snapshot_date"].max()) if "snapshot_date" in df else "—")

priced=int(market.get("price_status",pd.Series("EOD_PRICE_AVAILABLE",index=market.index)).eq("EOD_PRICE_AVAILABLE").sum())
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Listed equities", f"{len(market):,}")
c2.metric("EOD prices available", f"{priced:,}")
c3.metric("NSE EOD date", nse_date)
c4.metric("BSE EOD date", bse_date)
c5.metric("Value candidates", f"{result.summary['research_candidates']:,}")
provider = market_status.get("provider", "TejHQ / Hugging Face") if isinstance(market_status, dict) else "TejHQ / Hugging Face"
retrieved = market_status.get("retrieved_at_utc", "not available") if isinstance(market_status, dict) else "not available"
st.caption(f"Market source: {provider} · Security master: {security_master_status.get('coverage','UNAVAILABLE')} · Fundamentals: {fundamentals_source} · Retrieved: {retrieved}")
st.warning("This is end-of-day data, not intraday live pricing. A price-only record is not an investment opportunity. Scores are research triage signals, not buy/sell advice.")
if eligibility_summary.get("status")!="ERROR":
    st.caption(
        f"Fundamental eligibility: {eligibility_summary.get('xbrl_company_count',0):,} XBRL companies · "
        f"{eligibility_summary.get('eligible_xbrl_company_count',0):,} with audited annual / 4-quarter TTM records · "
        f"{eligibility_summary.get('interim_only_company_count',0):,} interim-only."
    )

tab1,tab2,tab3,tab4 = st.tabs(["Market universe","Value opportunities","Research lab","Data health"])

with tab1:
    st.subheader("Latest traded equity universe")
    st.caption("Supported NSE EQ/BE/BZ and BSE A/B/T bhavcopy rows for each exchange's latest available trading date. Non-traded and suspended instruments may be absent.")
    filters = st.columns(3)
    exchange_filter = filters[0].selectbox("Exchange", ["All","NSE","BSE"])
    query = filters[1].text_input("Find company / symbol")
    turnover_min = filters[2].number_input("Minimum daily turnover (₹ crore)", min_value=0.0, value=0.0, step=1.0)
    view = df.copy()
    if exchange_filter != "All":
        view = view[view["exchange"].astype(str).str.upper() == exchange_filter]
    if query:
        view = view[view.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)]
    if "turnover" in view:
        view = view[pd.to_numeric(view["turnover"], errors="coerce").fillna(0) >= turnover_min * 1e7]
    wanted = ["exchange","symbol","name","isin","series","snapshot_date","close","ret_1d","ret_21d","ret_252d","pct_off_52w_high","volume","turnover","pe","pb","dcf_fair_value_bear","dcf_fair_value_base","dcf_fair_value_bull","margin_of_safety_pct","valuation_status","value_score","research_status"]
    columns = [c for c in wanted if c in view.columns]
    sort_col = "turnover" if "turnover" in view.columns else ("volume" if "volume" in view.columns else "symbol")
    st.dataframe(view[columns].sort_values(sort_col, ascending=False, na_position="last"), use_container_width=True, hide_index=True)
    st.download_button("Download market universe CSV", view.to_csv(index=False).encode(), "valueforge_market_universe.csv", "text/csv")

with tab2:
    st.subheader("Value research queue")
    ready = df[df["research_status"].isin(["VALUE_RESEARCH_CANDIDATE","VALUE_WATCHLIST"])].copy()
    if ready.empty:
        st.info("No company currently passes the full fundamentals, cash-flow valuation and margin-of-safety gates. This is intentional: low P/E or price momentum alone is not an intrinsic-value case.")
    else:
        ready = ready.sort_values("value_score", ascending=False)
        cols = [c for c in ["exchange","symbol","name","sector","close","pe","pb","roe","roce","debt_to_equity","ocf_to_net_profit","fcf","dcf_fair_value_bear","dcf_fair_value_base","dcf_fair_value_bull","margin_of_safety_pct","dcf_growth_assumption_pct","valuation_status","value_score","research_status","period_end","source_url"] if c in ready]
        st.dataframe(ready[cols], use_container_width=True, hide_index=True)
        st.download_button("Download value research queue", ready[cols].to_csv(index=False).encode(), "valueforge_value_queue.csv", "text/csv")
    st.subheader("Intrinsic-value coverage")
    valuation_cols=[c for c in ["exchange","symbol","name","close","fcf","dcf_fair_value_bear","dcf_fair_value_base","dcf_fair_value_bull","margin_of_safety_pct","dcf_growth_assumption_pct","valuation_status","source_url"] if c in df]
    valued=df[df["valuation_status"].isin(["ATTRACTIVE_MARGIN_OF_SAFETY","WATCH_MARGIN_OF_SAFETY","LIMITED_MARGIN_OF_SAFETY","ABOVE_BASE_DCF_VALUE"])].copy() if "valuation_status" in df else pd.DataFrame()
    if valued.empty:
        st.caption("No verified DCF valuations yet. The model requires positive free cash flow, verified share count and five-year sales/profit history.")
    else:
        valued=valued.sort_values("margin_of_safety_pct",ascending=False,na_position="last")
        st.dataframe(valued[valuation_cols],use_container_width=True,hide_index=True)
    st.caption("DCF assumptions: five-year FCF projection; cost of equity 12% / 14% / 16%; terminal growth 3%; forecast growth equals half the weaker verified five-year sales/profit CAGR, bounded to -5%..8%. It is a screening proxy, not a formal appraisal.")
    st.subheader("Financial-sector research queue")
    sector_rows=df[df.get("sector_model",pd.Series(index=df.index,dtype=object)).notna()].copy()
    if sector_rows.empty:
        st.caption("No financial-sector listings identified in the current universe.")
    else:
        sector_cols=[c for c in ["exchange","symbol","name","sector_model","sector_metrics_status","sector_metrics_coverage_pct","sector_metrics_missing","sector_research_status"] if c in sector_rows]
        sector_rows=sector_rows.sort_values(["sector_metrics_coverage_pct","symbol"],ascending=[False,True],na_position="last")
        st.dataframe(sector_rows[sector_cols],use_container_width=True,hide_index=True)
        st.download_button("Download financial-sector diligence queue",sector_rows[sector_cols].to_csv(index=False).encode(),"valueforge_sector_research.csv","text/csv")
    st.caption("Banks, NBFCs, insurers, asset managers and brokers use separate evidence checklists. Complete sector metrics route to sector research review; they are not automatic buy recommendations.")
    counts = df["research_status"].value_counts().rename_axis("status").reset_index(name="companies")
    st.plotly_chart(px.bar(counts, x="status", y="companies", title="Research coverage by status"), use_container_width=True)

with tab3:
    st.subheader("Daily automated agent reports")
    report_dir = Path("data/live/reports")
    reports = sorted(report_dir.glob("*.md"), reverse=True) if report_dir.exists() else []
    if reports:
        chosen = st.selectbox("Committee memo", reports)
        st.markdown(chosen.read_text(encoding="utf-8"))
    else:
        st.info("No automated LLM reports yet. Configure GEMINI_API_KEY in GitHub Actions secrets; daily AI research is capped at two qualifying companies. Without a key, the deterministic scan continues.")
    st.divider()
    st.subheader("On-demand multi-agent research")
    options = df.apply(lambda r: f"{r.get('exchange','')}:{r.get('symbol','')} — {r.get('name','')}", axis=1).tolist()
    selected = st.selectbox("Company to investigate", options)
    company = df.iloc[options.index(selected)].to_dict()
    pdf = st.file_uploader("Optional annual report / results PDF", type=["pdf"], key="annual_report")
    st.caption("PDF extraction is assistive. Tables, footnotes and scanned pages may be missed; verify source documents.")
    if st.button("Run specialist analysts + committee", type="primary"):
        pdf_text = ""
        if pdf is not None:
            try:
                pdf_text = extract_relevant_pdf_text(pdf.getvalue())
            except Exception as exc:
                st.error(f"PDF extraction failed: {exc}")
        with st.spinner("Running specialist research..."):
            memo, meta = run_ai_committee(company, pdf_text, api_key=configured_gemini_key)
        st.session_state["last_report"] = memo
        st.session_state["last_report_meta"] = meta
    if "last_report" in st.session_state:
        st.caption(f"Research mode: {st.session_state.get('last_report_meta',{}).get('mode','deterministic')}")
        st.markdown(st.session_state["last_report"])
        st.download_button("Download research memo", st.session_state["last_report"].encode(), "valueforge_research_memo.md", "text/markdown")

with tab4:
    st.subheader("Data freshness and integrity")
    st.json(market_status)
    st.subheader("Exchange security master")
    st.json(security_master_status)
    st.subheader("Fundamental eligibility")
    st.json(eligibility_summary)
    st.subheader("Fundamental / filing ingestion")
    st.json(scan_status)
    st.json(read_json("data/live/filings_status.json"))
    st.write(f"Fundamentals: {len(fundamentals):,} rows · {fundamentals_source}")
    if uploaded is not None:
        st.dataframe(fundamentals, use_container_width=True, hide_index=True)
        st.download_button("Download normalized fundamentals CSV", fundamentals.to_csv(index=False).encode(), "company_fundamentals_normalized.csv", "text/csv")
        st.info("Session uploads are not persistent. Commit the normalized rows to data/fundamentals/company_fundamentals.csv in GitHub to use them in daily scheduled scans.")
    st.subheader("Persistent research database")
    try:
        from valueforge.db import database_overview, load_latest_database_research
        db_overview=database_overview()
    except Exception as exc:
        db_overview={"status":"ERROR","error":f"{type(exc).__name__}: {exc}"}
    st.json(db_overview)
    if db_overview.get("status")=="CONNECTED":
        try:
            history=load_latest_database_research(limit=100)
            if not history.empty:
                st.caption("Latest persisted research results")
                show=[c for c in ["exchange","symbol","close","value_score","research_status","financial_quality_status","valuation_status","margin_of_safety_pct","fair_value_base"] if c in history]
                st.dataframe(history[show],use_container_width=True,hide_index=True)
        except Exception as exc:
            st.warning(f"Could not read persisted research history: {type(exc).__name__}: {exc}")
    st.markdown("**Feed limitations**")
    st.write(market_status.get("coverage_note", "No coverage note supplied."))
    st.write("TejHQ is a third-party processed EOD bhavcopy dataset. Verify symbol coverage, corporate actions and source values before use.")
    st.markdown("[TejHQ dataset and schema](https://huggingface.co/datasets/tejhq/indian-markets) · [NSE reports portal](https://www.nseindia.com/all-reports)")
