from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET

from india_xbrl.reader import read_instance


FLOW_ALIASES = {
    # SEBI Integrated Finance (Ind AS) taxonomy local names from the vendored
    # 2025 taxonomy, ordered from the most specific statement fact.
    "sales": ("RevenueFromOperations", "TurnoverOrTotalIncome", "Revenue", "RevenueFromOperationsGross"),
    "net_profit": ("ProfitLossForPeriodFromContinuingOperations", "ProfitLossForPeriod", "ProfitOrLossAttributableToOwnersOfParent", "NetProfitAfterTax", "ProfitLoss", "ProfitLossFromContinuingOperations"),
    "profit_before_tax": ("ProfitBeforeTax", "ProfitLossFromContinuingOperationsBeforeTax", "ProfitLossBeforeTax"),
    "finance_cost": ("FinanceCosts", "FinanceCost"),
    "operating_profit": ("OperatingProfitLoss", "ProfitLossFromOperatingActivities", "OperatingProfit"),
    "ocf": ("CashFlowsFromUsedInOperatingActivities", "CashFlowsFromUsedInOperations", "NetCashFlowsFromUsedInOperatingActivities", "CashFlowsFromOperatingActivities"),
    "basic_eps": ("BasicEarningsLossPerShareFromContinuingOperations", "BasicEarningsPerShare", "EarningsPerShareBasic", "BasicEarningsLossPerShare"),
}
INSTANT_ALIASES = {
    "equity": ("EquityAttributableToOwnersOfParent", "Equity", "TotalEquity", "EquityIncludingNoncontrollingInterest"),
    "assets": ("Assets", "TotalAssets"),
    "cash": ("CashAndCashEquivalents", "CashAndCashEquivalentsCashFlowStatement", "BankBalanceOtherThanCashAndCashEquivalents", "CashAndCashEquivalentsAtEndOfPeriod", "CashCashEquivalentsAndBankBalances", "CashAndBankBalances"),
    "total_debt": ("Borrowings", "TotalBorrowings", "BorrowingsCurrentAndNoncurrent"),
    "short_debt": ("BorrowingsCurrent", "CurrentBorrowings", "ShortTermBorrowings"),
    "long_debt": ("BorrowingsNoncurrent", "NonCurrentBorrowings", "LongTermBorrowings"),
    "paid_up_capital": ("PaidUpValueOfEquityShareCapital", "PaidUpEquityShareCapital", "EquityShareCapital"),
    "face_value": ("FaceValueOfEquityShareCapital", "FaceValueOfEquityShare", "FaceValueOfEquityShares", "FaceValuePerShare"),
}


def _num(value):
    try:
        text = str(value).strip().replace(",", "")
        if not text or text in {"-", "—"}:
            return None
        return float(Decimal(text))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _days(ctx):
    try:
        return (date.fromisoformat(ctx.end) - date.fromisoformat(ctx.start)).days + 1
    except (TypeError, ValueError):
        return None


def _period_target(relating_to: str | None, period_end: date | None):
    label = (relating_to or "").lower()
    if any(x in label for x in ("annual", "year ended", "full year", "yearly")):
        return "annual", 365, (300, 400)
    if "half" in label or "six month" in label or "6 month" in label:
        return "half_year", 183, (150, 215)
    if any(x in label for x in ("quarter", "q1", "q2", "q3", "q4", "three month")):
        return "quarter", 92, (65, 125)
    # Metadata often omits the period label. The caller then tries discrete
    # quarter first; if absent it falls back to annual/half-year contexts.
    return "unknown", 92, (65, 125)


def _get_isin(xml_bytes: bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "identifier" and element.text:
            value = element.text.strip().upper()
            if len(value) == 12 and value[:2].isalpha():
                return value
    return None


def _facts_for_context(summary, context_id):
    return [f for f in summary.facts if f.context_ref == context_id and
            (not f.namespace or context_id in summary.contexts) and
            not summary.contexts[context_id].dimensions]


def _lookup(facts, aliases):
    alias_order = {name.lower(): i for i, name in enumerate(aliases)}
    matches = [f for f in facts if f.local_name.lower() in alias_order]
    matches.sort(key=lambda f: (alias_order[f.local_name.lower()], 0 if (f.unit_ref or "").upper() in {"INR", "ISO4217INR"} else 1))
    for fact in matches:
        value = _num(fact.value)
        if value is not None:
            return value
    return None


def _pick_flow_context(summary, period_end, relating_to):
    kind, target, bounds = _period_target(relating_to, period_end)
    candidates = []
    for ctx in summary.contexts.values():
        if ctx.is_instant or not ctx.start or not ctx.end or ctx.end != period_end.isoformat():
            continue
        if ctx.dimensions:
            continue
        days = _days(ctx)
        if days is not None and bounds[0] <= days <= bounds[1]:
            candidates.append((abs(days-target), ctx.context_id, days))
    if not candidates and kind == "unknown":
        # Missing metadata: select a discrete quarter if present. Only fall
        # back to annual/half-year when no quarter context exists.
        fallback = []
        for ctx in summary.contexts.values():
            if ctx.is_instant or not ctx.start or not ctx.end or ctx.end != period_end.isoformat() or ctx.dimensions:
                continue
            days = _days(ctx)
            if days is not None and 150 <= days <= 400:
                fallback.append((abs(days-365), ctx.context_id, days))
        if fallback:
            fallback.sort()
            _, context_id, days = fallback[0]
            return context_id, "annual" if days >= 300 else "half_year", days
    if not candidates:
        return None, kind, None
    candidates.sort()
    _, context_id, days = candidates[0]
    if kind == "unknown":
        kind = "quarter"
    return context_id, kind, days


def _instant_context(summary, period_end):
    candidates = [c for c in summary.contexts.values()
                  if c.is_instant and c.instant == period_end.isoformat() and not c.dimensions]
    return candidates[0].context_id if candidates else None


def _prior_equity(summary, period_end, aliases):
    candidates = []
    for ctx in summary.contexts.values():
        if not ctx.is_instant or not ctx.instant or ctx.dimensions:
            continue
        try:
            d = date.fromisoformat(ctx.instant)
        except ValueError:
            continue
        gap = (period_end - d).days
        if 300 <= gap <= 430:
            value = _lookup(_facts_for_context(summary, ctx.context_id), aliases)
            if value is not None:
                candidates.append((gap, value))
    return sorted(candidates, key=lambda x: x[0])[0][1] if candidates else None


def extract_filing_fundamentals(xml_bytes: bytes, filing: dict) -> dict:
    """Extract a conservative company-period record from one XBRL instance.

    Monetary values are stored in INR crore. Quarterly flows are kept as
    discrete quarters; YTD contexts are deliberately not substituted.
    """
    summary = read_instance(xml_bytes)
    period_end = filing.get("period_end")
    if isinstance(period_end, str):
        period_end = date.fromisoformat(period_end)
    if not period_end:
        ends = [date.fromisoformat(c.end) for c in summary.contexts.values()
                if c.end and not c.is_instant]
        if not ends:
            raise ValueError("XBRL instance has no usable period end")
        period_end = max(ends)

    flow_id, period_kind, period_days = _pick_flow_context(summary, period_end, filing.get("relating_to"))
    instant_id = _instant_context(summary, period_end)
    if not flow_id or not instant_id:
        raise ValueError("No matching discrete flow context and/or balance-sheet instant context")

    flows = _facts_for_context(summary, flow_id)
    instants = _facts_for_context(summary, instant_id)
    out = {}
    for key, aliases in FLOW_ALIASES.items():
        out[key] = _lookup(flows, aliases)
    for key, aliases in INSTANT_ALIASES.items():
        out[key] = _lookup(instants, aliases)

    # Total borrowings wins. Otherwise sum current + non-current only when both exist.
    if out.get("total_debt") is None:
        short, long = out.get("short_debt"), out.get("long_debt")
        if short is not None and long is not None:
            out["total_debt"] = short + long

    # XBRL monetary facts in the INR unit are rupees. Normalize money to crore.
    monetary = {"sales", "net_profit", "profit_before_tax", "finance_cost", "operating_profit",
                "ocf", "equity", "assets", "cash", "total_debt", "short_debt",
                "long_debt", "paid_up_capital"}
    for key in monetary:
        if out.get(key) is not None:
            out[key] = out[key] / 10_000_000

    prior_equity_raw = _prior_equity(summary, period_end, INSTANT_ALIASES["equity"])
    prior_equity = prior_equity_raw / 10_000_000 if prior_equity_raw is not None else None
    equity = out.get("equity")
    debt = out.get("total_debt")
    profit = out.get("net_profit")
    sales = out.get("sales")
    ocf = out.get("ocf")
    finance = out.get("finance_cost")
    pbt = out.get("profit_before_tax")
    op_profit = out.get("operating_profit")

    if debt is not None and equity and equity > 0:
        out["debt_to_equity"] = debt / equity
    if ocf is not None and profit not in (None, 0):
        out["ocf_to_net_profit"] = ocf / profit
    if profit is not None and equity and equity > 0 and prior_equity and prior_equity > 0:
        out["roe"] = profit / ((equity + prior_equity) / 2) * 100
    if pbt is not None and finance and finance > 0:
        out["interest_coverage"] = (pbt + finance) / finance
    if pbt is not None and finance is not None and equity and debt is not None and equity + debt > 0:
        out["roce"] = (pbt + finance) / (equity + debt) * 100
    if op_profit is not None and sales and sales > 0:
        out["operating_margin"] = op_profit / sales * 100

    isin = filing.get("isin") or _get_isin(xml_bytes)
    out.update({
        "symbol": filing.get("symbol"),
        "name": filing.get("company"),
        "exchange": filing.get("exchange", "NSE"),
        "isin": isin,
        "sector": filing.get("sector"),
        "period_end": period_end.isoformat(),
        "period_kind": period_kind,
        "period_days": period_days,
        "basis": "consolidated" if filing.get("consolidated") else "standalone",
        "audited": bool(filing.get("audited")),
        "data_as_of": filing.get("filing_ts") or filing.get("period_end"),
        "source_url": filing.get("xbrl_url"),
        "source_label": "Exchange XBRL filing",
        "filing_id": filing.get("filing_id"),
        "taxonomy_family": summary.taxonomy_family.value,
        "fact_count": len(summary.facts),
        "context_count": len(summary.contexts),
        "unit_currency_note": "Monetary values normalized to INR crore; per-share values in INR",
    })
    return out
