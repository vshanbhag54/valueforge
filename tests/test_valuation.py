import math
import pandas as pd

from valueforge.valuation import apply_intrinsic_valuation


def test_dcf_returns_sensitivity_range_and_margin_of_safety():
    frame=pd.DataFrame([{
        "close":100.0,
        "fcf":1000.0,
        "paid_up_capital":100.0,
        "face_value":10.0,
        "sales_cagr_5y":10.0,
        "profit_cagr_5y":8.0,
    }])
    row=apply_intrinsic_valuation(frame).iloc[0]
    assert row["dcf_fair_value_bear"] < row["dcf_fair_value_base"]
    assert row["dcf_fair_value_base"] < row["dcf_fair_value_bull"]
    assert row["shares_outstanding_crore"]==10.0
    assert row["dcf_growth_assumption_pct"]==4.0
    assert row["dcf_base_discount_rate_pct"]==14.0
    assert row["dcf_terminal_growth_pct"]==3.0
    assert row["margin_of_safety_pct"]>0
    assert row["valuation_status"]=="ATTRACTIVE_MARGIN_OF_SAFETY"


def test_dcf_refuses_to_invent_value_without_positive_fcf_or_share_count():
    frame=pd.DataFrame([
        {"close":100.0,"fcf":-10.0,"paid_up_capital":100.0,"face_value":10.0,
         "sales_cagr_5y":10.0,"profit_cagr_5y":8.0},
        {"close":100.0,"fcf":100.0,"paid_up_capital":None,"face_value":None,
         "sales_cagr_5y":10.0,"profit_cagr_5y":8.0},
    ])
    out=apply_intrinsic_valuation(frame)
    assert pd.isna(out.loc[0,"dcf_fair_value_base"])
    assert pd.isna(out.loc[0,"margin_of_safety_pct"])
    assert out.loc[0,"valuation_status"]=="FCF_UNAVAILABLE_OR_NON_POSITIVE"
    assert pd.isna(out.loc[1,"dcf_fair_value_base"])
    assert out.loc[1,"valuation_status"]=="SHARE_COUNT_UNVERIFIED"


def test_dcf_requires_both_five_year_growth_series():
    frame=pd.DataFrame([{
        "close":100.0,"fcf":100.0,"paid_up_capital":10.0,"face_value":1.0,
        "sales_cagr_5y":8.0,"profit_cagr_5y":None,
    }])
    row=apply_intrinsic_valuation(frame).iloc[0]
    assert pd.isna(row["dcf_fair_value_base"])
    assert row["valuation_status"]=="FIVE_YEAR_GROWTH_HISTORY_UNAVAILABLE"
