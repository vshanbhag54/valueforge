from __future__ import annotations

import math
import pandas as pd


SECTOR_METRICS = {
    "BANK": {
        "required": ("roe","roa_pct","nim_pct","gnpa_pct","nnpa_pct","crar_pct","cost_to_income_pct"),
        "label": "Bank",
    },
    "NBFC": {
        "required": ("roe","roa_pct","gnpa_pct","nnpa_pct","capital_adequacy_pct","debt_to_equity","aum_growth_5y"),
        "label": "NBFC",
    },
    "INSURANCE": {
        "required": ("roe","solvency_ratio","claims_ratio_pct","persistency_13m_pct"),
        "label": "Insurance",
    },
    "ASSET_MANAGER": {
        "required": ("roe","operating_margin","aum_growth_5y","net_flows_cr"),
        "label": "Asset manager",
    },
    "BROKER": {
        "required": ("roe","operating_margin","client_assets_growth_5y","net_cash_cr"),
        "label": "Broker",
    },
    "OTHER_FINANCIAL": {
        "required": ("roe","pb","debt_to_equity","ocf_to_net_profit"),
        "label": "Other financial",
    },
}


def _token(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower()


def classify_sector(row) -> str | None:
    sector=_token(row.get("sector"))
    name=_token(row.get("name"))
    text=f"{sector} {name}"
    if any(term in text for term in ("asset management","mutual fund","asset manager","amc ")):
        return "ASSET_MANAGER"
    if any(term in text for term in ("insurance","life insurer","general insurer")):
        return "INSURANCE"
    if "bank" in text and not any(term in text for term in ("investment bank","merchant bank")):
        return "BANK"
    if any(term in text for term in ("nbfc","non banking financial","housing finance","microfinance")):
        return "NBFC"
    if any(term in text for term in ("stock broker","stockbroking","broking","brokerage")):
        return "BROKER"
    if any(term in text for term in ("finance","financial","lending","credit")):
        return "OTHER_FINANCIAL"
    return None


def _value(row, field):
    try:
        value=float(row.get(field))
        return value if math.isfinite(value) else None
    except (TypeError,ValueError):
        return None


def evaluate_sector_metrics(row) -> dict:
    """Measure evidence coverage for a sector model; not a buy/sell signal."""
    model=classify_sector(row)
    if model is None:
        return {
            "sector_model":None,
            "sector_metrics_status":"NOT_APPLICABLE",
            "sector_metrics_missing":"",
            "sector_metrics_coverage_pct":None,
            "sector_quality_score":None,
            "sector_research_status":"NOT_FINANCIAL_SECTOR",
        }
    spec=SECTOR_METRICS[model]
    required=spec["required"]
    present=[field for field in required if _value(row,field) is not None]
    missing=[field for field in required if field not in present]
    coverage=round(100*len(present)/len(required),1)
    # A transparent, low-conviction coverage score is useful for sorting
    # diligence queues; it is never allowed to become a value-candidate score.
    quality_score=coverage
    if missing:
        status="INCOMPLETE"
        research_status="SECTOR_MODEL_REQUIRED"
    else:
        status="METRICS_COMPLETE"
        research_status="SECTOR_RESEARCH_REVIEW"
    return {
        "sector_model":model,
        "sector_metrics_status":status,
        "sector_metrics_missing":",".join(missing),
        "sector_metrics_coverage_pct":coverage,
        "sector_quality_score":quality_score,
        "sector_research_status":research_status,
    }


def apply_sector_models(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        out=frame.copy()
        for field in ("sector_model","sector_metrics_status","sector_metrics_missing",
                      "sector_metrics_coverage_pct","sector_quality_score","sector_research_status"):
            out[field]=pd.Series(dtype="object")
        return out
    assessed=frame.apply(lambda row:evaluate_sector_metrics(row.to_dict()),axis=1,result_type="expand")
    out=frame.copy()
    for field in assessed.columns:
        out[field]=assessed[field]
    return out
