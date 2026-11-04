import pandas as pd

from valueforge.research import _ttm_xbrl_fundamentals


def test_ttm_requires_four_consecutive_quarters_and_recalculates_ratios():
    dates=["2024-12-31","2025-03-31","2025-06-30","2025-09-30","2025-12-31"]
    rows=[]
    for i,period in enumerate(dates):
        rows.append({
            "symbol":"ABC","isin":"INE000A01001","exchange":"NSE","sector":"Industrials",
            "period_end":period,"period_kind":"quarter","basis":"consolidated",
            "data_as_of":period,"sales":100.0,"net_profit":10.0,
            "profit_before_tax":14.0,"finance_cost":2.0,"operating_profit":20.0,"ocf":12.0,"capex":2.0,
            "equity":100.0+i*10,"total_debt":50.0,
        })
    ttm=_ttm_xbrl_fundamentals(pd.DataFrame(rows))
    assert len(ttm)==1
    row=ttm.iloc[0]
    assert row["net_profit"]==40
    assert row["sales"]==400
    assert row["ocf"]==48
    assert row["capex"]==8
    assert row["fcf"]==40
    assert row["ocf_to_net_profit"]==1.2
    assert row["operating_margin"]==20
    assert round(row["roe"],2)==33.33
    assert round(row["roce"],2)==37.65
    assert row["ttm_quarters"]==4


def test_ttm_does_not_sum_nonconsecutive_quarters():
    frame=pd.DataFrame([
        {"symbol":"ABC","exchange":"NSE","period_end":"2025-03-31","period_kind":"quarter","net_profit":1},
        {"symbol":"ABC","exchange":"NSE","period_end":"2025-09-30","period_kind":"quarter","net_profit":1},
        {"symbol":"ABC","exchange":"NSE","period_end":"2025-12-31","period_kind":"quarter","net_profit":1},
        {"symbol":"ABC","exchange":"NSE","period_end":"2026-03-31","period_kind":"quarter","net_profit":1},
    ])
    assert _ttm_xbrl_fundamentals(frame).empty


def test_latest_xbrl_does_not_promote_single_quarter_as_latest_fundamentals():
    from valueforge.research import _latest_xbrl

    history=pd.DataFrame([{
        "symbol":"ABC","exchange":"NSE","isin":"INE000A01001",
        "period_end":"2026-09-30","period_kind":"quarter","basis":"consolidated",
        "audited":False,"sales":100.0,"net_profit":10.0,
    }])
    assert _latest_xbrl(history).empty


def test_latest_xbrl_uses_audited_annual_when_ttm_is_not_available():
    from valueforge.research import _latest_xbrl

    history=pd.DataFrame([{
        "symbol":"ABC","exchange":"NSE","isin":"INE000A01001",
        "period_end":"2026-03-31","period_kind":"annual","basis":"consolidated",
        "audited":True,"sales":400.0,"net_profit":40.0,
    },{
        "symbol":"ABC","exchange":"NSE","isin":"INE000A01001",
        "period_end":"2026-06-30","period_kind":"quarter","basis":"consolidated",
        "audited":False,"sales":110.0,"net_profit":11.0,
    }])
    latest=_latest_xbrl(history)
    assert len(latest)==1
    assert latest.iloc[0]["period_kind"]=="annual"
    assert latest.iloc[0]["net_profit"]==40.0
