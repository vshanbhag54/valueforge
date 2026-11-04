from __future__ import annotations

import math
import pandas as pd


FORECAST_YEARS = 5
TERMINAL_GROWTH = 0.03
DISCOUNT_SCENARIOS = {
    "bear": 0.16,
    "base": 0.14,
    "bull": 0.12,
}


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _forecast_growth(row):
    """Use half the weaker verified five-year sales/profit CAGR, bounded conservatively."""
    values = [_finite(row.get("sales_cagr_5y")), _finite(row.get("profit_cagr_5y"))]
    values = [value / 100 for value in values if value is not None]
    if not values:
        return None
    return max(-0.05, min(0.08, min(values) * 0.5))


def _dcf_per_share(fcf_cr, shares_cr, growth, discount, terminal_growth):
    if fcf_cr is None or fcf_cr <= 0 or shares_cr is None or shares_cr <= 0:
        return None
    if growth is None or discount <= terminal_growth or terminal_growth < 0:
        return None
    projected = [fcf_cr * ((1 + growth) ** year) for year in range(1, FORECAST_YEARS + 1)]
    pv_explicit = sum(amount / ((1 + discount) ** year) for year, amount in enumerate(projected, start=1))
    terminal_value = projected[-1] * (1 + terminal_growth) / (discount - terminal_growth)
    pv_terminal = terminal_value / ((1 + discount) ** FORECAST_YEARS)
    equity_value_cr = pv_explicit + pv_terminal
    return equity_value_cr / shares_cr


def _value_row(row):
    fcf = _finite(row.get("fcf"))
    paid_up_cr = _finite(row.get("paid_up_capital"))
    face_value = _finite(row.get("face_value"))
    shares_cr = paid_up_cr / face_value if paid_up_cr and face_value and paid_up_cr > 0 and face_value > 0 else None
    growth = _forecast_growth(row)
    values = {}
    for name, discount in DISCOUNT_SCENARIOS.items():
        values[f"dcf_fair_value_{name}"] = _dcf_per_share(
            fcf, shares_cr, growth, discount, TERMINAL_GROWTH
        )
    price = _finite(row.get("close"))
    base = values["dcf_fair_value_base"]
    mos = (1 - price / base) * 100 if price is not None and price > 0 and base is not None and base > 0 else None
    if price is None or price <= 0:
        status = "NO_CURRENT_PRICE"
    elif fcf is None or fcf <= 0:
        status = "FCF_UNAVAILABLE_OR_NON_POSITIVE"
    elif shares_cr is None:
        status = "SHARE_COUNT_UNVERIFIED"
    elif growth is None:
        status = "FIVE_YEAR_GROWTH_HISTORY_UNAVAILABLE"
    elif base is None:
        status = "DCF_NOT_COMPUTABLE"
    elif mos >= 25:
        status = "ATTRACTIVE_MARGIN_OF_SAFETY"
    elif mos >= 10:
        status = "WATCH_MARGIN_OF_SAFETY"
    elif mos >= 0:
        status = "LIMITED_MARGIN_OF_SAFETY"
    else:
        status = "ABOVE_BASE_DCF_VALUE"
    return {
        **values,
        "shares_outstanding_crore": shares_cr,
        "dcf_growth_assumption_pct": round(growth * 100, 2) if growth is not None else None,
        "dcf_base_discount_rate_pct": round(DISCOUNT_SCENARIOS["base"] * 100, 2),
        "dcf_terminal_growth_pct": round(TERMINAL_GROWTH * 100, 2),
        "margin_of_safety_pct": mos,
        "valuation_status": status,
    }


def apply_intrinsic_valuation(frame):
    """Attach a five-year FCFE-style DCF range and an explicit MOS/status.

    Free cash flow is operating cash flow less reported cash capex. The model
    uses 12/14/16% discount rates and 3% terminal growth, with forecast growth
    based on half the weaker positive/negative five-year sales/profit CAGR,
    clipped to -5%..8%. It is a conservative screening proxy, not a formal
    appraisal: banks/insurers are excluded by the research screen, and
    companies without verified FCF, share count, and five-year growth history
    remain unvalued rather than receiving an invented fair value.
    """
    if frame.empty:
        return frame.copy()
    out = frame.copy()
    values = out.apply(lambda row: _value_row(row.to_dict()), axis=1, result_type="expand")
    for column in values.columns:
        out[column] = values[column]
    return out
