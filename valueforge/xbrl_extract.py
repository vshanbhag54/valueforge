from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
import xml.etree.ElementTree as ET

from india_xbrl.reader import read_instance

# SEBI Integrated Finance (in-capmkt, 2025+) and BSE legacy Financial Results
# (in-bse-fin, pre-2025) are different taxonomies. These maps include both.
FLOW_ALIASES = {
    "sales": ("RevenueFromOperations", "TurnoverOrTotalIncome", "Revenue"),
    "net_profit": (
        "ProfitOrLossAttributableToOwnersOfParent",
        "ProfitLossForPeriodFromContinuingOperations", "ProfitLossForPeriod",
        "NetProfitAfterTax", "ProfitLoss",
    ),
    "profit_before_tax": (
        "ProfitBeforeTax", "ProfitBeforeExceptionalItemsAndTax",
        "ProfitLossFromContinuingOperationsBeforeTax", "ProfitLossBeforeTax",
    ),
    "finance_cost": ("FinanceCosts", "FinanceCost"),
    "other_income": ("OtherIncome",),
    "ocf": (
        "CashFlowsFromUsedInOperatingActivities", "CashFlowsFromUsedInOperations",
        "NetCashFlowsFromUsedInOperatingActivities", "NetCashFlowFromOperatingActivities",
        "CashFlowsFromOperatingActivities",
    ),
    "basic_eps": (
        "BasicEarningsLossPerShareFromContinuingOperations",
        "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "BasicEarningsPerShare", "EarningsPerShareBasic",
    ),
}
CAPEX_ALIASES = (
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
    "PurchaseOfInvestmentPropertyClassifiedAsInvestingActivities",
    "PurchaseOfOtherLongTermAssetsClassifiedAsInvestingActivities",
)
INSTANT_ALIASES = {
    "equity": ("EquityAttributableToOwnersOfParent", "Equity", "TotalEquity", "EquityIncludingNoncontrollingInterest"),
    "assets": ("Assets", "TotalAssets"),
    "cash": (
        "CashAndCashEquivalents", "CashAndCashEquivalentsCashFlowStatement",
        "BankBalanceOtherThanCashAndCashEquivalents",
        "CashAndCashEquivalentsAtEndOfPeriod", "CashCashEquivalentsAndBankBalances",
    ),
    "total_debt": ("Borrowings", "TotalBorrowings", "TotalFinancialIndebtedness"),
    "short_debt": ("BorrowingsCurrent", "CurrentBorrowings", "ShortTermBorrowings"),
    "long_debt": ("BorrowingsNoncurrent", "NonCurrentBorrowings", "LongTermBorrowings"),
    "paid_up_capital": ("PaidUpValueOfEquityShareCapital", "PaidUpEquityShareCapital", "EquityShareCapital"),
    "face_value": ("FaceValueOfEquityShareCapital", "FaceValueOfEquityShare", "FaceValueOfEquityShares", "FaceValuePerShare"),
    "reported_debt_to_equity": ("DebtEquityRatio",),
    "reported_interest_coverage": ("InterestServiceCoverageRatio",),
}
RATIO_ALIASES = {
    "reported_debt_to_equity": ("DebtEquityRatio",),
    "reported_interest_coverage": ("InterestServiceCoverageRatio",),
}


def _num(value):
    try:
        text = str(value).strip().replace(",", "")
        if not text or text in {"-", "—"}:
            return None
        return float(Decimal(text))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _days(ctx):
    start, end = _as_date(ctx.start), _as_date(ctx.end)
    return (end - start).days + 1 if start and end else None


def _period_hint(relating_to, period_from=None, period_end=None):
    """Prefer explicit reporting-period dates over ambiguous exchange labels."""
    start, end = _as_date(period_from), _as_date(period_end)
    if start and end:
        days = (end - start).days + 1
        dated_kind = _kind_from_days(days)
        if dated_kind in {"quarter", "half_year", "annual"}:
            return dated_kind
    label = re.sub(r"[^a-z0-9]+", " ", str(relating_to or "").lower()).strip()
    if any(x in label for x in ("annual", "year ended", "full year", "yearly", "audited financial")):
        return "annual"
    # Integrated filing titles often say "quarter and half year ended".
    # A precise period_from is used above; without it, prefer discrete quarter
    # rather than silently treating a result as cumulative YTD.
    if re.search(r"q[1-4]", label) or "quarter" in label or "three month" in label:
        return "quarter"
    if any(x in label for x in ("half year", "half-year", "six month", "six months", "half yearly")):
        return "half_year"
    return "unknown"


def _kind_from_days(days):
    if days is None:
        return "unknown"
    if 65 <= days <= 125:
        return "quarter"
    if 150 <= days <= 215:
        return "half_year"
    if 300 <= days <= 400:
        return "annual"
    return "other"


def _dimension_safe(context):
    if not context.dimensions:
        return True
    members = " ".join(str(member).lower() for _, member in context.dimensions)
    return "consolidated" in members and not any(
        term in members for term in ("segment", "geography", "product", "classof")
    )


def _facts_for_context(summary, context_id):
    context = summary.contexts.get(context_id)
    if context is None or not _dimension_safe(context):
        return []
    return [fact for fact in summary.facts if fact.context_ref == context_id]


def _unit_measures(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    xbrli = "{http://www.xbrl.org/2003/instance}"
    units = {}
    for unit in root.findall(f"{xbrli}unit"):
        unit_id = unit.attrib.get("id")
        measures = [
            (measure.text or "").strip().split(":")[-1].lower()
            for measure in unit.findall(f".//{xbrli}measure")
        ]
        if unit_id:
            units[unit_id] = measures
    return units


def _lookup_fact(facts, aliases, unit_measures=None):
    alias_order = {name.lower(): i for i, name in enumerate(aliases)}
    matches = [fact for fact in facts if fact.local_name.lower() in alias_order]

    def priority(fact):
        unit_id = (fact.unit_ref or "").lower()
        measures = (unit_measures or {}).get(fact.unit_ref or "", [])
        measure = " ".join(measures)
        unit_priority = 0 if "inr" in measure or unit_id == "inr" else 1
        return alias_order[fact.local_name.lower()], unit_priority

    matches.sort(key=priority)
    for fact in matches:
        value = _num(fact.value)
        if value is not None:
            return value, fact
    return None, None


def _lookup(facts, aliases, unit_measures=None):
    return _lookup_fact(facts, aliases, unit_measures)[0]


def _context_fact_coverage(facts, alias_map, unit_measures=None):
    return sum(_lookup(facts, aliases, unit_measures) is not None for aliases in alias_map.values())


def _date_gap(context_date, target_date):
    context_date = _as_date(context_date)
    if not context_date or not target_date:
        return 9999
    return abs((context_date - target_date).days)


def _pick_flow_context(summary, period_end, relating_to, unit_measures=None, period_from=None):
    """Choose flow context by filing date, actual duration, taxonomy facts and OneD/FourD hints."""
    hint = _period_hint(relating_to, period_from, period_end)
    candidates = []
    for ctx in summary.contexts.values():
        if ctx.is_instant or not ctx.start or not ctx.end:
            continue
        end_gap = _date_gap(ctx.end, period_end)
        if end_gap > 7:
            continue
        days = _days(ctx)
        kind = _kind_from_days(days)
        if kind not in {"quarter", "half_year", "annual"}:
            continue
        facts = _facts_for_context(summary, ctx.context_id)
        coverage = _context_fact_coverage(facts, FLOW_ALIASES, unit_measures)
        if coverage == 0:
            continue
        hint_penalty = 0 if hint == "unknown" or hint == kind else 1
        duration_target = {"quarter": 92, "half_year": 183, "annual": 365}[hint if hint != "unknown" else "quarter"]
        marker_penalty = 0 if (
            (kind == "quarter" and ctx.context_id.upper() == "ONED") or
            (kind in {"half_year", "annual"} and ctx.context_id.upper() in {"FOURD", "ONEY"})
        ) else 1
        candidates.append((
            hint_penalty, -coverage, end_gap, abs(days - duration_target),
            marker_penalty, ctx.context_id, kind, days,
        ))
    if not candidates:
        return None, "unknown", None, None, 0
    candidates.sort()
    _, neg_coverage, end_gap, _, _, context_id, kind, days = candidates[0]
    return context_id, kind, days, end_gap, -neg_coverage


def _instant_context(summary, period_end, unit_measures=None):
    candidates = []
    for ctx in summary.contexts.values():
        if not ctx.is_instant or not ctx.instant:
            continue
        gap = _date_gap(ctx.instant, period_end)
        if gap > 7:
            continue
        facts = _facts_for_context(summary, ctx.context_id)
        coverage = _context_fact_coverage(facts, INSTANT_ALIASES, unit_measures)
        if coverage == 0:
            continue
        marker_penalty = 0 if ctx.context_id.upper() == "N1D" else 1
        candidates.append((-coverage, gap, marker_penalty, ctx.context_id))
    if not candidates:
        return None, None, 0
    candidates.sort()
    neg_coverage, gap, _, context_id = candidates[0]
    return context_id, gap, -neg_coverage


def _prior_equity(summary, period_end, aliases, unit_measures=None):
    candidates = []
    for ctx in summary.contexts.values():
        if not ctx.is_instant or not ctx.instant:
            continue
        d = _as_date(ctx.instant)
        if not d:
            continue
        gap = (period_end - d).days
        if 300 <= gap <= 430:
            value, fact = _lookup_fact(_facts_for_context(summary, ctx.context_id), aliases, unit_measures)
            if value is not None and fact is not None:
                candidates.append((gap, value, fact))
    return sorted(candidates, key=lambda x: x[0])[0][1:] if candidates else (None, None)


def _to_crore(value, fact, unit_measures):
    if value is None or fact is None:
        return None
    unit_id = (fact.unit_ref or "").lower()
    measures = " ".join(unit_measures.get(fact.unit_ref or "", []))
    token = unit_id + " " + measures
    if "pershare" in token or "per share" in token:
        return value
    if "crore" in token:
        return value
    if "lakh" in token or "lac" in token:
        return value / 100
    if "million" in token:
        return value / 10
    if "thousand" in token:
        return value / 10000
    if "inr" in token:
        return value / 10_000_000
    return None


def _get_isin(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() == "identifier" and element.text:
            value = element.text.strip().upper()
            if re.fullmatch(r"IN[A-Z0-9]{10}", value):
                return value
    return None


def extract_filing_fundamentals(xml_bytes: bytes, filing: dict) -> dict:
    """Extract taxonomy-aware financial facts; keep quarter, YTD and annual periods distinct."""
    summary = read_instance(xml_bytes)
    period_end = _as_date(filing.get("period_end"))
    if not period_end:
        ends = [_as_date(ctx.end) for ctx in summary.contexts.values() if ctx.end and not ctx.is_instant]
        ends = [d for d in ends if d]
        if not ends:
            raise ValueError("XBRL_NO_DURATION_CONTEXT")
        period_end = max(ends)

    unit_measures = _unit_measures(xml_bytes)
    flow_id, period_kind, period_days, flow_date_gap, flow_coverage = _pick_flow_context(
        summary, period_end, filing.get("relating_to"), unit_measures, filing.get("period_from")
    )
    instant_id, instant_date_gap, instant_coverage = _instant_context(summary, period_end, unit_measures)
    if not flow_id:
        ends = sorted({ctx.end for ctx in summary.contexts.values() if ctx.end})
        raise ValueError(
            f"XBRL_NO_FLOW_CONTEXT: filing_end={period_end.isoformat()}, "
            f"relating_to={filing.get('relating_to')!r}, available_ends={ends[:12]}"
        )
    if not instant_id:
        instants = sorted({ctx.instant for ctx in summary.contexts.values() if ctx.instant})
        raise ValueError(
            f"XBRL_NO_INSTANT_CONTEXT: filing_end={period_end.isoformat()}, available_instants={instants[:12]}"
        )

    flows = _facts_for_context(summary, flow_id)
    instants = _facts_for_context(summary, instant_id)
    raw, fact_refs = {}, {}
    for key, aliases in FLOW_ALIASES.items():
        raw[key], fact_refs[key] = _lookup_fact(flows, aliases, unit_measures)
    for key, aliases in INSTANT_ALIASES.items():
        raw[key], fact_refs[key] = _lookup_fact(instants, aliases, unit_measures)
    for key, aliases in RATIO_ALIASES.items():
        raw[key], fact_refs[key] = _lookup_fact(instants + flows, aliases, unit_measures)

    capex_components, capex_tags = [], []
    for tag in CAPEX_ALIASES:
        value, fact = _lookup_fact(flows, (tag,), unit_measures)
        if value is not None and fact is not None:
            converted = _to_crore(value, fact, unit_measures)
            if converted is not None:
                capex_components.append(abs(converted))
                capex_tags.append(fact.local_name)
    raw["capex"] = sum(capex_components) if capex_components else None

    monetary = {
        "sales", "net_profit", "profit_before_tax", "finance_cost", "other_income",
        "ocf", "equity", "assets", "cash", "total_debt", "short_debt",
        "long_debt", "paid_up_capital",
    }
    out = {}
    for key, value in raw.items():
        fact = fact_refs.get(key)
        out[key] = _to_crore(value, fact, unit_measures) if key in monetary and fact is not None else value

    if out.get("total_debt") is None:
        short, long = out.get("short_debt"), out.get("long_debt")
        if short is not None and long is not None:
            out["total_debt"] = short + long
    out["fcf"] = out["ocf"] - out["capex"] if out.get("ocf") is not None and out.get("capex") is not None else None

    actual_flow_end = _as_date(summary.contexts[flow_id].end) or period_end
    actual_instant = _as_date(summary.contexts[instant_id].instant) or period_end
    equity, debt = out.get("equity"), out.get("total_debt")
    profit, pbt, finance = out.get("net_profit"), out.get("profit_before_tax"), out.get("finance_cost")
    prior_equity_raw, prior_equity_fact = _prior_equity(
        summary, actual_instant, INSTANT_ALIASES["equity"], unit_measures
    )
    prior_equity = _to_crore(prior_equity_raw, prior_equity_fact, unit_measures)

    if out.get("reported_debt_to_equity") is not None:
        out["debt_to_equity"] = out["reported_debt_to_equity"]
    elif debt is not None and equity is not None and equity > 0:
        out["debt_to_equity"] = debt / equity
    if profit not in (None, 0) and out.get("ocf") is not None:
        out["ocf_to_net_profit"] = out["ocf"] / profit
    if pbt is not None and finance is not None and finance > 0:
        out["interest_coverage"] = out.get("reported_interest_coverage")
        if out["interest_coverage"] is None:
            out["interest_coverage"] = (pbt + finance) / finance
    elif out.get("reported_interest_coverage") is not None:
        out["interest_coverage"] = out["reported_interest_coverage"]
    out["roe"] = (
        profit / ((equity + prior_equity) / 2) * 100
        if period_kind == "annual" and profit is not None and equity and equity > 0 and prior_equity and prior_equity > 0
        else None
    )
    # Do not fabricate consolidated operating margin/ROCE from PBT alone.
    out["operating_margin"] = None
    out["roce"] = None

    income_fields = ("sales", "net_profit", "profit_before_tax")
    balance_fields = ("equity", "assets", "total_debt")
    cash_fields = ("ocf", "capex")
    missing_income = [field for field in income_fields if out.get(field) is None]
    missing_balance = [field for field in balance_fields if out.get(field) is None]
    missing_cash = [field for field in cash_fields if out.get(field) is None]
    checks = len(income_fields) + len(balance_fields) + len(cash_fields)
    completeness_pct = round(100 * (checks - len(missing_income) - len(missing_balance) - len(missing_cash)) / checks, 1)
    if not missing_income and not missing_balance and not missing_cash:
        data_quality = "COMPLETE"
    elif not missing_income and not missing_balance:
        data_quality = "PARTIAL_CASH_FLOW"
    elif out.get("sales") is not None and out.get("net_profit") is not None:
        data_quality = "PARTIAL_STATEMENTS"
    else:
        data_quality = "INSUFFICIENT"

    matched_tags = {key: fact.local_name for key, fact in fact_refs.items() if fact is not None}
    isin = filing.get("isin") or _get_isin(xml_bytes)
    out.update({
        "symbol": filing.get("symbol"), "security_code": filing.get("security_code"),
        "name": filing.get("company"), "exchange": filing.get("exchange", "NSE"),
        "isin": isin, "sector": filing.get("sector"),
        "period_end": actual_flow_end.isoformat(), "period_kind": period_kind,
        "period_days": period_days, "period_end_gap_days": flow_date_gap,
        "instant_date_gap_days": instant_date_gap,
        "basis": "consolidated" if filing.get("consolidated") else "standalone",
        "audited": bool(filing.get("audited")),
        "data_as_of": filing.get("filing_ts") or filing.get("period_end"),
        "source_url": filing.get("xbrl_url"), "source_label": "Exchange XBRL filing",
        "filing_id": filing.get("filing_id"), "taxonomy_family": summary.taxonomy_family.value,
        "fact_count": len(summary.facts), "context_count": len(summary.contexts),
        "flow_context_id": flow_id, "instant_context_id": instant_id,
        "flow_fact_coverage": flow_coverage, "instant_fact_coverage": instant_coverage,
        "matched_fact_tags": json.dumps(matched_tags, sort_keys=True),
        "diagnostic_fact_names": json.dumps(sorted({fact.local_name for fact in summary.facts})),
        "capex_fact_tags": json.dumps(capex_tags),
        "missing_income_fields": json.dumps(missing_income),
        "missing_balance_fields": json.dumps(missing_balance),
        "missing_cash_flow_fields": json.dumps(missing_cash),
        "statement_completeness_pct": completeness_pct,
        "data_quality_status": data_quality,
        "unit_currency_note": "Monetary values normalized to INR crore where source unit is INR; per-share values remain INR",
    })
    return out
