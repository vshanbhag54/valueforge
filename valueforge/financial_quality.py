from __future__ import annotations

from datetime import date
import math
import pandas as pd

CORE_STATEMENT_FIELDS = (
    "sales", "net_profit", "profit_before_tax",
    "equity", "assets", "total_debt",
    "ocf",
)


def _is_missing(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return str(value).strip().lower() in {"", "nan", "none", "<na>"}


def _safe_text(value):
    return "" if _is_missing(value) else str(value)


def assess_financial_quality(row, as_of=None):
    """Return an auditable quality gate; missing statement facts remain unknown."""
    as_of = as_of or date.today()
    missing = [field for field in CORE_STATEMENT_FIELDS if _is_missing(row.get(field))]
    period = pd.to_datetime(row.get("period_end"), errors="coerce")
    if pd.isna(period):
        age_days = None
        period_status = "PERIOD_MISSING"
    else:
        age_days = (pd.Timestamp(as_of) - period.normalize()).days
        period_status = "CURRENT" if 0 <= age_days <= 450 else "STALE_OR_FUTURE"

    basis = _safe_text(row.get("basis")).strip().lower()
    source_url = _safe_text(row.get("source_url")).strip()
    source_label = _safe_text(row.get("source_label")).lower()
    match_method = _safe_text(row.get("fundamental_match_method")) or "UNMATCHED"

    issues = []
    if missing:
        issues.append("MISSING_CORE_FIELDS:" + ",".join(missing))
    if period_status != "CURRENT":
        issues.append(period_status)
    if basis != "consolidated":
        issues.append("CONSOLIDATION_NOT_VERIFIED")
    if not source_url.startswith(("http://", "https://")):
        issues.append("PRIMARY_SOURCE_URL_MISSING")
    if match_method == "UNMATCHED":
        issues.append("COMPANY_IDENTITY_UNVERIFIED")

    numeric_issues = []
    equity_issue = False
    for field in ("sales", "assets", "paid_up_capital", "face_value"):
        try:
            value = float(row.get(field))
            if math.isfinite(value) and value < 0:
                numeric_issues.append(field.upper() + "_NEGATIVE")
        except (TypeError, ValueError):
            pass
    if numeric_issues:
        issues.extend(numeric_issues)
    if _is_missing(row.get("capex")):
        issues.append("CAPEX_NOT_DISCLOSED_DCF_UNAVAILABLE")

    if not _is_missing(row.get("equity")):
        try:
            if float(row.get("equity")) <= 0:
                issues.append("NON_POSITIVE_EQUITY")
                equity_issue = True
        except (TypeError, ValueError):
            pass

    strong_identity = match_method in {"ISIN", "EXCHANGE_SCRIP_CODE", "EXCHANGE_SYMBOL"}
    if (not missing and period_status == "CURRENT" and basis == "consolidated"
            and source_url.startswith(("http://", "https://")) and strong_identity
            and not numeric_issues and not equity_issue):
        status = "VALIDATED"
    elif "screener" in source_label or "manual" in source_label:
        status = "MANUAL_REVIEW_REQUIRED"
    elif period_status == "STALE_OR_FUTURE":
        status = "STALE"
    elif not strong_identity:
        status = "IDENTITY_REVIEW_REQUIRED"
    elif missing:
        status = "INCOMPLETE"
    else:
        status = "REVIEW_REQUIRED"

    return {
        "financial_quality_status": status,
        "financial_quality_issues": ";".join(issues),
        "financial_missing_core_fields": ",".join(missing),
        "financial_period_age_days": age_days,
        "financial_period_status": period_status,
        "financial_match_method": match_method,
    }


def apply_financial_quality(frame: pd.DataFrame, as_of=None) -> pd.DataFrame:
    if frame.empty:
        out = frame.copy()
        for field in ("financial_quality_status", "financial_quality_issues", "financial_missing_core_fields",
                      "financial_period_age_days", "financial_period_status", "financial_match_method"):
            out[field] = pd.Series(dtype="object")
        return out
    out = frame.copy()
    assessments = out.apply(lambda row: assess_financial_quality(row.to_dict(), as_of=as_of), axis=1, result_type="expand")
    for field in assessments.columns:
        out[field] = assessments[field]
    return out
