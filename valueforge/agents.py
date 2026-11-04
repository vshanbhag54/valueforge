from __future__ import annotations
from datetime import datetime, timezone
import math
import os
import requests

AGENT_ROLES = {
 "Financial Quality Analyst": "Evaluate profitability, ROE/ROCE, margins, cash conversion, leverage, interest coverage and earnings durability. Separate reported facts from interpretation.",
 "Valuation Analyst": "Evaluate valuation using P/E, P/B, earnings quality, growth, cyclicality and margin of safety. Do not call a low multiple cheap without explaining possible value traps.",
 "Forensic Accountant": "Search for accounting-quality concerns: cash conversion, debt, promoter pledging, auditor qualifications, contingent liabilities, related-party transactions, dilution and unexplained divergences. State unknown when evidence is absent.",
 "Bear-Case Analyst": "Construct the strongest reasonable bear case, including permanent capital loss risks, business deterioration, cyclicality, governance, valuation and evidence that would invalidate the thesis."
}

def _fmt(v):
    try:
        x=float(v)
        return "not provided" if not math.isfinite(x) else f"{x:.3f}"
    except (TypeError,ValueError): return "not provided"

def deterministic_research(company, annual_report_text=""):
    lines=[
      f"# Research committee memo — {company.get('name','Company')} ({company.get('symbol','N/A')})",
      f"Generated: {datetime.now(timezone.utc).isoformat()}",
      "> Research triage only. Not a buy/sell recommendation. All facts must be checked against the linked source documents.",
      "",
      "## Company data",
    ]
    for k in ("exchange","sector","isin","period_end","basis","source_url","source_label","data_as_of","pe","pb","roe","roce",
              "debt_to_equity","interest_coverage","operating_margin","ocf_to_net_profit","sales_cagr_5y","profit_cagr_5y",
              "promoter_holding_pct","promoter_pledge_pct","net_profit","sales","total_debt","cash","equity","ocf","fcf",
              "close","volume","ret_21d","ret_252d","pct_off_52w_high"):
        if k in company: lines.append(f"- {k}: {_fmt(company.get(k))}")
    lines += ["", "## Specialist review"]
    blockers=[]
    for k,label in (("pe","P/E"),("roe","ROE"),("roce","ROCE"),("debt_to_equity","debt/equity"),
                    ("ocf_to_net_profit","operating cash-flow conversion"),("period_end","financial period"),
                    ("source_url","primary source URL")):
        if company.get(k) is None or str(company.get(k)).lower() in ("nan",""):
            blockers.append(f"Missing {label}")
    if blockers:
        lines += ["### Evidence gaps"] + [f"- {x}" for x in blockers]
    if not annual_report_text:
        lines.append("- No annual-report text was supplied for this review.")
    lines += [
      "", "## Preliminary committee disposition",
      "**NO INVESTMENT CONCLUSION.** This record is ready only for further research if source documents and required metrics can be verified.",
      "Before a decision, review at least five years of consolidated statements, quarterly trends, cash flows, notes to accounts, auditor report, promoter/shareholding disclosures, related-party transactions, contingent liabilities, capital allocation and current valuation.",
      "Sector-specific valuation is required for banks, NBFCs, insurers and other financial businesses.",
    ]
    return "\n".join(lines)

def gemini_enabled():
    return bool(os.getenv("GEMINI_API_KEY"))

def run_ai_committee(company, annual_report_text="", api_key=None, model=None):
    """Runs four separate specialist calls and one committee synthesis.

    Requires a user-supplied Gemini Developer API key. No key is stored by ValueForge.
    """
    key=api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        return deterministic_research(company,annual_report_text), {"mode":"deterministic","agents_run":0}
    model=model or os.getenv("GEMINI_MODEL","gemini-2.5-flash-lite")
    facts={k:company.get(k) for k in company.keys() if k not in ("raw_pdf","_internal")}
    context="COMPANY FACTS (may be missing/incomplete; never invent values):\n"+str(facts)
    if annual_report_text:
        context+="\n\nEXTRACTED ANNUAL REPORT TEXT (primary source; quote page references if visible):\n"+annual_report_text[:24000]
    outputs={}
    endpoint=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for role,instruction in AGENT_ROLES.items():
        prompt=f"""You are the {role} on an Indian equity research team. {instruction}

Rules:
- Only use supplied facts and extracted primary-source text.
- Never invent financial figures, management statements, citations, source links, or page numbers.
- If data is missing or not current, explicitly say UNKNOWN / NOT VERIFIED.
- Distinguish facts, inferences, assumptions and questions.
- Do not give a buy/sell order or a target price.
- Be sceptical and concise. Point out contradictions and what would change your view.

{context}

Prepare a structured specialist note with: mandate, verified observations, interpretation, red flags, missing evidence, and questions for the next analyst."""
        payload={"contents":[{"role":"user","parts":[{"text":prompt}]}],
                 "generationConfig":{"temperature":0.2,"maxOutputTokens":1000}}
        try:
            response=requests.post(endpoint,params={"key":key},json=payload,timeout=90)
            response.raise_for_status()
            body=response.json()
            text="\n".join(p.get("text","") for p in body["candidates"][0]["content"]["parts"])
            outputs[role]=text
        except Exception as exc:
            outputs[role]=f"Agent unavailable: {type(exc).__name__}: {exc}"
    notes="\n\n".join(f"## {role}\n{note}" for role,note in outputs.items())
    synthesis_prompt=f"""You are chairing an investment research committee for a value-investing process. Reconcile the independent notes below. Explicitly surface disagreements. Never fill missing facts. Set disposition to RESEARCH INCOMPLETE when evidence is insufficient. You may label a company as candidate for further due diligence, but never issue a trade instruction or guarantee a return. Include an evidence checklist and a disconfirming evidence section.

Company facts: {context}

Independent analyst notes:
{notes}

Write a concise committee conclusion with: thesis, valuation caveats, bear case, governance/accounting risks, data gaps, follow-up work, and disposition."""
    try:
        response=requests.post(endpoint,params={"key":key},json={
            "contents":[{"role":"user","parts":[{"text":synthesis_prompt}]}],
            "generationConfig":{"temperature":0.15,"maxOutputTokens":1200}
        },timeout=90)
        response.raise_for_status()
        committee="".join(p.get("text","") for p in response.json()["candidates"][0]["content"]["parts"])
    except Exception as exc:
        committee=f"Committee synthesis unavailable: {type(exc).__name__}: {exc}"
    report=deterministic_research(company,annual_report_text)+"\n\n# AI specialist analysis\n\n"+notes+"\n\n# AI committee synthesis\n\n"+committee
    return report,{"mode":"gemini","model":model,"agents_run":len(outputs),"generated_at_utc":datetime.now(timezone.utc).isoformat()}
