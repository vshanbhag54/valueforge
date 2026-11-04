from __future__ import annotations
import json, os
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

from valueforge.agents import gemini_enabled, run_ai_committee
from valueforge.data import load_sample_data
from valueforge.fundamentals import normalize_fundamentals
from valueforge.market_data import load_market_snapshot
from valueforge.pdf_extract import extract_relevant_pdf_text
from valueforge.research import merge_market_and_fundamentals
from valueforge.scoring import screen_universe

st.set_page_config(page_title="ValueForge | Indian Value Research", page_icon="📈", layout="wide")
st.title("ValueForge")
st.caption("India equity research desk · NSE + BSE · Value investing · Research only")

def read_json(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return {}

market=load_market_snapshot()
status=read_json("data/live/market_status.json")
scan_status=read_json("data/live/research_status.json")
repo_fund_path=Path("data/fundamentals/company_fundamentals.csv")

with st.sidebar:
    st.header("Research settings")
    st.caption("Daily EOD data is refreshed by GitHub Actions after the market-data publisher's nightly release.")
    uploaded=st.file_uploader("Import Screener/export CSV",type=["csv"])
    use_sample=st.toggle("Show illustrative sample only",value=False)
    st.divider()
    st.caption("AI analyst team")
    st.write("Gemini agent calls:", "Enabled" if gemini_enabled() else "Not configured")
    st.caption("Add GEMINI_API_KEY to Streamlit Secrets to enable independent LLM analyst calls. The app never stores the key in this repository.")

if uploaded is not None:
    try:
        imported=normalize_fundamentals(pd.read_csv(uploaded))
        fundamentals_source="Session upload (not persisted)"
    except Exception as exc:
        st.error(f"Could not import CSV: {exc}"); st.stop()
else:
    if repo_fund_path.exists():
        imported=normalize_fundamentals(pd.read_csv(repo_fund_path),source_label="Repository fundamentals")
        fundamentals_source="Repository data"
    else:
        imported=pd.DataFrame()
        fundamentals_source="No fundamentals file"

if market.empty and use_sample:
    market=load_sample_data()
    source_label="Illustrative data — not live"
elif market.empty:
    source_label="No market snapshot yet"
else:
    source_label="TejHQ nightly EOD dataset"

if market.empty:
    st.warning("No live market snapshot is checked into this deployment yet. Merge the project PR and run the GitHub Actions workflow (or trigger Refresh manually).")
    st.markdown("Market dataset: [TejHQ Indian Markets](https://huggingface.co/datasets/tejhq/indian-markets)")
    st.stop()

combined=merge_market_and_fundamentals(market,imported)
result=screen_universe(combined)
df=result.companies
date_labels=status.get("exchange_dates",{})
c1,c2,c3,c4,c5=st.columns(5)
c1.metric("EOD instruments",f"{len(market):,}")
c2.metric("NSE EOD date",date_labels.get("NSE","—"))
c3.metric("BSE EOD date",date_labels.get("BSE","—"))
c4.metric("Fundamental rows",f"{len(imported):,}")
c5.metric("Research candidates",f"{result.summary['research_candidates']:,}")
st.caption(f"Market source: {source_label} · Fundamentals: {fundamentals_source} · Retrieved: {status.get('retrieved_at_utc','not available')}")
st.warning("This system receives end-of-day prices, not intraday live quotes. A company is not a value candidate until current, source-backed fundamentals are available. No orders are placed.")

tab1,tab2,tab3,tab4=st.tabs(["Market universe","Value opportunities","Research lab","Data health"])

with tab1:
    st.subheader("Latest traded equity universe")
    st.caption("A daily bhavcopy snapshot of the supported NSE/BSE equity series. Securities not traded or not present in the vendor file may be absent.")
    filters=st.columns(3)
    ex=filters[0].selectbox("Exchange",["All","NSE","BSE"])
    q=filters[1].text_input("Find company / symbol")
    min_turnover=filters[2].number_input("Min daily turnover (₹ crore)",min_value=0.0,value=0.0,step=1.0)
    view=df.copy()
    if ex!="All": view=view[view["exchange"].astype(str).str.upper()==ex]
    if q: view=view[view.astype(str).apply(lambda col:col.str.contains(q,case=False,na=False)).any(axis=1)]
    if "turnover" in view:
        view=view[pd.to_numeric(view["turnover"],errors="coerce").fillna(0)>=min_turnover*1e7]
    columns=[c for c in ["exchange","symbol","name","isin","series","snapshot_date","close","ret_1d","ret_21d","ret_252d","pct_off_52w_high","volume","turnover","value_score","research_status"] if c in view]
    st.dataframe(view[columns].sort_values("turnover",ascending=False,na_position="last"),use_container_width=True,hide_index=True)
    st.download_button("Download full market universe CSV",view.to_csv(index=False).encode(),"valueforge_market_universe.csv","text/csv")

with tab2:
    st.subheader("Value research queue")
    ready=df[df["research_status"].isin(["VALUE_RESEARCH_CANDIDATE","VALUE_WATCHLIST"])].copy()
    if ready.empty:
        st.info("No fully-qualified value candidates yet. This is expected until the company fundamentals file is populated with recent, source-backed financial data.")
    else:
        ready=ready.sort_values("value_score",ascending=False)
        show=[c for c in ["exchange","symbol","name","sector","close","pe","pb","roe","roce","debt_to_equity","ocf_to_net_profit","value_score","research_status","period_end","source_url"] if c in ready]
        st.dataframe(ready[show],use_container_width=True,hide_index=True)
        st.download_button("Download value research queue",ready[show].to_csv(index=False).encode(),"valueforge_value_queue.csv","text/csv")
    counts=df["research_status"].value_counts().rename_axis("status").reset_index(name="companies")
    st.plotly_chart(px.bar(counts,x="status",y="companies",title="Research coverage by status"),use_container_width=True)

with tab3:
    st.subheader("Multi-agent research lab")
    source_options=df.apply(lambda r:f"{r.get('exchange','')}:{r.get('symbol','')} — {r.get('name','')}",axis=1).tolist()
    selected=st.selectbox("Company to investigate",source_options)
    company=df.iloc[source_options.index(selected)].to_dict()
    pdf=st.file_uploader("Optional annual report / results PDF",type=["pdf"],key="annual_report")
    st.caption("The PDF is processed for text only; table extraction can be imperfect. Verify every extracted figure against the report.")
    if st.button("Run specialist analysts + committee",type="primary"):
        pdf_text=""
        if pdf is not None:
            try: pdf_text=extract_relevant_pdf_text(pdf.getvalue())
            except Exception as exc: st.error(f"PDF extraction failed: {exc}")
        api_key=None
        try: api_key=st.secrets.get("GEMINI_API_KEY")
        except Exception: api_key=os.getenv("GEMINI_API_KEY")
        with st.spinner("Running specialist research..."):
            report,meta=run_ai_committee(company,pdf_text,api_key=api_key)
        st.session_state["last_report"]=report
        st.session_state["last_report_meta"]=meta
    if "last_report" in st.session_state:
        st.caption(f"Research mode: {st.session_state.get('last_report_meta',{}).get('mode','deterministic')}")
        st.markdown(st.session_state["last_report"])
        st.download_button("Download research memo",st.session_state["last_report"].encode(),"valueforge_research_memo.md","text/markdown")

with tab4:
    st.subheader("Data freshness and integrity")
    st.json(status)
    st.json(scan_status)
    st.markdown("**Fundamentals import**")
    st.write(f"Rows available: {len(imported):,} · Source: {fundamentals_source}")
    if uploaded is not None:
        st.dataframe(imported,use_container_width=True,hide_index=True)
        st.download_button("Download normalized fundamentals CSV",imported.to_csv(index=False).encode(),"company_fundamentals_normalized.csv","text/csv")
        st.info("For persistence across refreshes, commit the normalized CSV to data/fundamentals/company_fundamentals.csv in GitHub. Session uploads are not retained by the hosted app.")
    st.markdown("**Market-data limitations**")
    st.write(status.get("coverage_note","No coverage metadata available."))
    st.write("This feed is EOD, third-party processed exchange bhavcopy data. Prices, corporate-action adjustments and symbol coverage must be independently verified.")
    st.markdown("[TejHQ dataset and schema](https://huggingface.co/datasets/tejhq/indian-markets) · [NSE reports portal](https://www.nseindia.com/all-reports)")
