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
        "net_profit":100.0,"sales":500.0,"equity":100.0,"total_debt":0.0,
        "shares_outstanding_cr":10.0,"shares_outstanding_source":"Reported company share-count disclosure",
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



def test_market_multiples_are_not_inferred_from_paid_up_capital():
    from valueforge.research import _derive_market_valuation

    frame=pd.DataFrame([{
        "close":100.0,"paid_up_capital":10.0,"face_value":1.0,
        "net_profit":10.0,"equity":50.0,"period_kind":"annual",
    }])
    row=_derive_market_valuation(frame).iloc[0]
    assert pd.isna(row["market_cap_cr"])
    assert pd.isna(row["pe"])
    assert pd.isna(row["pb"])


def test_market_multiples_use_reported_shares_and_preserve_provenance():
    from valueforge.research import _derive_market_valuation

    frame=pd.DataFrame([{
        "close":100.0,"shares_outstanding_cr":10.0,
        "shares_outstanding_source":"Exchange annual-report share-count disclosure",
        "net_profit":100.0,"equity":200.0,"period_kind":"TTM",
    }])
    row=_derive_market_valuation(frame).iloc[0]
    assert row["market_cap_cr"]==1000.0
    assert row["pe"]==10.0
    assert row["pb"]==5.0
    assert row["market_cap_source"]=="EOD price × reported shares outstanding"
