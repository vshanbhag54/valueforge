import pandas as pd

from valueforge.fundamentals import normalize_fundamentals
from valueforge.research import merge_market_and_fundamentals


def test_bse_fundamentals_match_exchange_security_master_by_scrip_code():
    market=pd.DataFrame([{
        "exchange":"BSE","symbol":"TCS","security_code":"532540","isin":pd.NA,
        "name":"TCS Limited","sector":"IT","close":100.0,"snapshot_date":"2026-11-03",
    }])
    raw=pd.DataFrame([{
        "exchange":"BSE","symbol":"BSE-532540","security_code":"532540",
        "name":"TCS Limited","period_end":"2026-03-31","period_kind":"annual",
        "basis":"consolidated","data_as_of":"2026-05-01",
        "net_profit":100.0,"sales":500.0,"equity":100.0,
        "paid_up_capital":10.0,"face_value":1.0,"total_debt":0.0,
        "source_label":"Exchange XBRL filing",
    }])
    fundamentals=normalize_fundamentals(raw,source_label="Exchange XBRL filings")
    merged=merge_market_and_fundamentals(market,fundamentals)
    row=merged.iloc[0]
    assert row["net_profit"]==100
    assert row["period_end"]=="2026-03-31"
    assert row["fundamentals_match"]
    assert row["fundamental_match_method"]=="EXCHANGE_SCRIP_CODE"
    assert row["pe"]==10


def test_latest_market_snapshot_date_ignores_unpriced_listing_nulls():
    from valueforge.research import latest_market_snapshot_date

    market = pd.DataFrame({
        "snapshot_date": ["2026-11-03", pd.NA, float("nan"), "2026-11-02"],
    })
    assert latest_market_snapshot_date(market) == "2026-11-03"


def test_latest_market_snapshot_date_returns_unknown_when_all_missing():
    from valueforge.research import latest_market_snapshot_date

    market = pd.DataFrame({"snapshot_date": [pd.NA, float("nan")]})
    assert latest_market_snapshot_date(market) == "unknown"
