from datetime import datetime,timezone
import math

def fmt(x):
    try:
        v=float(x); return "not provided" if not math.isfinite(v) else f"{v:.2f}"
    except (TypeError,ValueError): return "not provided"

def run_research_committee(c):
    sections=[]
    roles=[
      ("Financial quality analyst",["roe","roce","operating_margin","debt_to_equity","interest_coverage","ocf_to_net_profit"]),
      ("Valuation analyst",["pe","pb"]),
      ("Forensic accounting analyst",["promoter_pledge_pct","contingent_liabilities","auditor_qualification","related_party_flags"]),
    ]
    for role,fields in roles:
        sections.append(f"## {role}")
        for field in fields:
            sections.append(f"- {field}: {fmt(c.get(field))}")
        missing=[f for f in fields if c.get(f) is None or str(c.get(f)).lower() in ("nan","")]
        if missing: sections.append("- **Open evidence:** "+", ".join(missing))
    return "\n".join([
      f"# Research committee memo — {c.get('name','Company')} ({c.get('symbol','N/A')})",
      f"Generated: {datetime.now(timezone.utc).isoformat()}",
      "> Preliminary triage only. Not a buy/sell recommendation.",
      f"- Exchange: {c.get('exchange','not provided')}",
      f"- Sector: {c.get('sector','not provided')}",
      f"- Period end: {c.get('period_end','not provided')}",
      f"- Basis: {c.get('basis','not provided')}",
      f"- Source: {c.get('source_url','not provided')}",
      *sections,
      "## Committee decision",
      "**RESEARCH INCOMPLETE — no investment call.** Obtain audited annual reports, quarterly statements, cash flows, shareholding pattern, auditor report and exchange announcements. Financial institutions require sector-specific analysis."
    ])
