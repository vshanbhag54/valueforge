from __future__ import annotations
from datetime import datetime, timezone
import math, os
import requests

AGENT_ROLES={
"Financial Quality Analyst":"Assess profitability, ROE/ROCE, margins, cash conversion, leverage, interest coverage and earnings durability.",
"Valuation Analyst":"Assess P/E, P/B, earnings quality, growth, cyclicality and margin of safety. A low multiple is not automatically cheap.",
"Forensic Accountant":"Investigate cash conversion, debt, promoter pledging, auditor qualifications, contingent liabilities, related parties and dilution.",
"Bear-Case Analyst":"Construct the strongest reasonable bear case and list evidence that would invalidate the thesis."
}

def _fmt(v):
    try:
        x=float(v)
        return "not provided" if not math.isfinite(x) else f"{x:.3f}"
    except (TypeError,ValueError): return "not provided"

def deterministic_research(company,annual_report_text=""):
    fields=("exchange","sector","isin","period_end","basis","source_url","source_label","data_as_of","pe","pb","roe","roce",
      "debt_to_equity","interest_coverage","operating_margin","ocf_to_net_profit","sales_cagr_5y","profit_cagr_5y",
      "promoter_holding_pct","promoter_pledge_pct","net_profit","sales","total_debt","cash","equity","ocf","fcf",
      "close","volume","ret_21d","ret_252d","pct_off_52w_high")
    lines=[f"# Research committee memo — {company.get('name','Company')} ({company.get('symbol','N/A')})",
      f"Generated: {datetime.now(timezone.utc).isoformat()}",
      "> Research triage only. Not a buy/sell recommendation. Verify figures against source documents.","","## Company data"]
    lines += [f"- {k}: {_fmt(company.get(k))}" for k in fields if k in company]
    gaps=[k for k in ("pe","roe","roce","debt_to_equity","ocf_to_net_profit","period_end","source_url")
          if company.get(k) is None or str(company.get(k)).lower() in ("nan","")]
    lines += ["","## Evidence gaps"]+([f"- Missing or unverified: {k}" for k in gaps] if gaps else ["- Core metrics populated; primary-source checks remain necessary."])
    if not annual_report_text: lines.append("- No annual-report text supplied.")
    lines += ["","## Preliminary disposition","**NO AUTOMATIC INVESTMENT CONCLUSION.** Validate five years of consolidated statements, quarterly trends, cash flows, notes, auditor opinion, shareholding, related-party transactions, contingent liabilities and capital allocation.","Sector-specific valuation is required for banks, NBFCs and insurers."]
    return "\n".join(lines)

def gemini_enabled(): return bool(os.getenv("GEMINI_API_KEY"))

def run_ai_committee(company,annual_report_text="",api_key=None,model=None):
    key=api_key or os.getenv("GEMINI_API_KEY")
    if not key: return deterministic_research(company,annual_report_text),{"mode":"deterministic","agents_run":0}
    model=model or os.getenv("GEMINI_MODEL","gemini-3.5-flash-lite")
    facts={k:v for k,v in company.items() if k not in ("raw_pdf","_internal")}
    context="COMPANY FACTS (may be missing/incomplete; never invent values):\n"+str(facts)
    if annual_report_text: context+="\n\nEXTRACTED PRIMARY-REPORT TEXT (cite pages only if visible):\n"+annual_report_text[:24000]
    endpoint=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    notes={}
    for role,instruction in AGENT_ROLES.items():
        prompt=f"""You are the {role} on an Indian value-investing research desk. {instruction}
Rules: use only supplied data; never invent figures, sources or page citations; say UNKNOWN when evidence is absent; separate facts from inference; do not give buy/sell orders or target prices.
{context}
Return a structured note with verified observations, interpretation, red flags, unknowns and follow-up questions."""
        try:
            r=requests.post(endpoint,headers={"x-goog-api-key":key,"Content-Type":"application/json"},json={"contents":[{"role":"user","parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.2,"maxOutputTokens":900}},timeout=(10,60))
            r.raise_for_status()
            notes[role]="\n".join(p.get("text","") for p in r.json()["candidates"][0]["content"]["parts"])
        except Exception as exc: notes[role]=f"Agent unavailable: {type(exc).__name__}: {exc}"
    agent_text="\n\n".join(f"## {role}\n{note}" for role,note in notes.items())
    prompt=f"""Act as the investment committee chair. Reconcile the notes, surface disagreements and the strongest bear case. Do not invent facts. If evidence is insufficient, disposition must be RESEARCH INCOMPLETE. A diligence candidate is not a buy recommendation. No trade instructions.
Company context: {context}
Analyst notes:
{agent_text}
Write thesis, valuation caveats, accounting/governance risks, bear case, disconfirming evidence, gaps and next diligence steps."""
    try:
        r=requests.post(endpoint,headers={"x-goog-api-key":key,"Content-Type":"application/json"},json={"contents":[{"role":"user","parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.15,"maxOutputTokens":1200}},timeout=(10,60))
        r.raise_for_status()
        synthesis="\n".join(p.get("text","") for p in r.json()["candidates"][0]["content"]["parts"])
    except Exception as exc: synthesis=f"Committee synthesis unavailable: {type(exc).__name__}: {exc}"
    report=deterministic_research(company,annual_report_text)+"\n\n# Specialist AI analyses\n\n"+agent_text+"\n\n# Committee synthesis\n\n"+synthesis
    return report,{"mode":"gemini","model":model,"agents_run":sum(not v.startswith("Agent unavailable") for v in notes.values()),"generated_at_utc":datetime.now(timezone.utc).isoformat()}
