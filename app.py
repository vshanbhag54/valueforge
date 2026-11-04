from __future__ import annotations
import pandas as pd
import streamlit as st
from valueforge.data import load_companies, load_sample_data
from valueforge.scoring import screen_universe
from valueforge.agents import run_research_committee

st.set_page_config(page_title="ValueForge", page_icon="📊", layout="wide")
st.title("ValueForge")
st.caption("Indian equity research desk · Value investing · Research only")
with st.sidebar:
    st.header("Data")
    upload=st.file_uploader("Upload fundamentals CSV",type=["csv"])
    sample=st.toggle("Use illustrative sample data",value=upload is None)
    st.divider()
    min_roe=st.slider("Minimum ROE (%)",0,40,12)
    max_de=st.slider("Maximum debt/equity",0.0,3.0,1.0,0.1)
    max_pe=st.slider("Maximum P/E",5,100,30)
try:
    if upload is not None:
        frame=pd.read_csv(upload); source="User CSV"
    else:
        frame=load_companies(); source="Local dataset"
        if frame.empty and sample:
            frame=load_sample_data(); source="Illustrative only"
except Exception as exc:
    st.error(f"CSV could not be read: {exc}"); st.stop()
if frame.empty:
    st.info("Upload a fundamentals CSV to begin, or enable the clearly labelled sample dataset."); st.stop()
result=screen_universe(frame,min_roe=min_roe,max_de=max_de,max_pe=max_pe)
a,b,c,d=st.columns(4)
a.metric("Companies",len(frame)); b.metric("Qualified",result.summary["qualified"])
c.metric("Need more data",result.summary["insufficient_data"]); d.metric("Dataset",source)
st.warning("Scores are research triage signals, not investment recommendations. Verify original filings.")
t1,t2,t3=st.tabs(["Opportunity screen","Company research","Data quality"])
with t1:
    wanted=["symbol","name","sector","exchange","value_score","screen_status","pe","pb","roe","roce","debt_to_equity","data_status"]
    view=result.companies[[x for x in wanted if x in result.companies.columns]].sort_values("value_score",ascending=False,na_position="last")
    st.dataframe(view,use_container_width=True,hide_index=True)
    st.download_button("Download screen CSV",view.to_csv(index=False).encode(),"valueforge_screen.csv","text/csv")
with t2:
    options=result.companies.apply(lambda x:f"{x.get('symbol','?')} — {x.get('name','Unknown')}",axis=1).tolist()
    item=st.selectbox("Company",options)
    company=result.companies.iloc[options.index(item)].to_dict()
    st.subheader(item)
    if st.button("Run research committee",type="primary"):
        st.session_state["memo"]=run_research_committee(company)
    if "memo" in st.session_state:
        memo=st.session_state["memo"]
        st.markdown(memo)
        st.download_button("Download memo",memo.encode(),"research_memo.md","text/markdown")
with t3:
    rows=[]
    for field in ["source_url","period_end","basis","data_as_of"]:
        n=int(frame[field].notna().sum()) if field in frame else 0
        rows.append({"Field":field,"Present":n,"Missing":len(frame)-n,"Coverage %":round(n*100/len(frame),1)})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    if "source_url" in frame:
        st.dataframe(frame[["symbol","name","source_url"]].dropna(subset=["source_url"]),use_container_width=True,hide_index=True)
