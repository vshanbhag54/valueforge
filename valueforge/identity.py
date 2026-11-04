from __future__ import annotations

import re
import pandas as pd

_ISIN_RE = re.compile(r"^IN[A-Z0-9]{10}$")


def _text(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def normalize_isin(value):
    token = _text(value).strip().upper()
    return token if _ISIN_RE.fullmatch(token) else None


def normalize_symbol(value):
    token = _text(value).strip().upper()
    if token in {"", "NAN", "NONE", "<NA>"}:
        return None
    token = re.sub(r"^(NSE|BSE)[:_-]", "", token)
    token = re.sub(r"\.EQ$", "", token)
    return token


def normalize_code(value):
    token = _text(value).strip().upper()
    if token in {"", "NAN", "NONE", "<NA>"}:
        return None
    return re.sub(r"\.0$", "", token)


def normalize_company_name(value):
    token = re.sub(r"[^A-Z0-9]+", " ", _text(value).upper()).strip()
    tokens = [x for x in token.split() if x not in {
        "LIMITED", "LTD", "PRIVATE", "PVT", "PLC", "THE", "COMPANY", "CO"
    }]
    return " ".join(tokens) if tokens else None


def resolve_fundamental_rows(market: pd.DataFrame, fundamentals: pd.DataFrame):
    """Resolve every market listing to one latest fundamental row.

    Priority is stable ISIN, exchange+scrip-code, exchange+symbol, and only
    then a unique normalized company name. Symbol matches are exchange-scoped
    to prevent same-ticker collisions between NSE and BSE.
    """
    if market.empty or fundamentals.empty:
        return [-1] * len(market), ["UNMATCHED"] * len(market)

    by_isin = {}
    by_code = {}
    by_symbol = {}
    by_name = {}

    for idx, row in fundamentals.reset_index(drop=True).iterrows():
        isin = normalize_isin(row.get("isin"))
        exchange = str(row.get("exchange") or "").strip().upper()
        code = normalize_code(row.get("security_code"))
        symbol = normalize_symbol(row.get("symbol"))
        name = normalize_company_name(row.get("name"))
        if isin:
            by_isin.setdefault(isin, idx)
        if exchange and code:
            by_code.setdefault((exchange, code), idx)
        if exchange and symbol:
            by_symbol.setdefault((exchange, symbol), idx)
        if name:
            by_name.setdefault(name, []).append(idx)

    resolved, methods = [], []
    for _, row in market.reset_index(drop=True).iterrows():
        isin = normalize_isin(row.get("isin"))
        exchange = str(row.get("exchange") or "").strip().upper()
        code = normalize_code(row.get("security_code"))
        symbol = normalize_symbol(row.get("symbol"))
        name = normalize_company_name(row.get("name"))

        idx, method = -1, "UNMATCHED"
        if isin and isin in by_isin:
            idx, method = by_isin[isin], "ISIN"
        elif exchange and code and (exchange, code) in by_code:
            idx, method = by_code[(exchange, code)], "EXCHANGE_SCRIP_CODE"
        elif exchange and symbol and (exchange, symbol) in by_symbol:
            idx, method = by_symbol[(exchange, symbol)], "EXCHANGE_SYMBOL"
        elif name and len(by_name.get(name, [])) == 1:
            idx, method = by_name[name][0], "UNIQUE_COMPANY_NAME"
        resolved.append(idx)
        methods.append(method)
    return resolved, methods
