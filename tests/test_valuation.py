import pandas as pd

from valueforge.valuation import apply_intrinsic_valuation


def test_dcf_returns_sensitivity_range_and_margin_of_safety():
    frame=pd.DataFrame([{
        "close":100.0,
        "fcf":1000.0,
        "shares_outstanding_cr":10.0,
        "shares_outstanding_source":"Reported company share-count disclosure",
        "sales_cagr_5y":10.0,
        "profit_cagr_5y":8.0,
        "financial_quality_status":"VALIDATED",\n        "period_kind":"TTM from 4 discrete quarters",
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
        {"close":100.0,"fcf":-10.0,"shares_outstanding_cr":10.0,"shares_outstanding_source":"Exchange filing",
         "sales_cagr_5y":10.0,"profit_cagr_5y":8.0,"financial_quality_status":"VALIDATED","period_kind":"annual"},
        {"close":100.0,"fcf":100.0,
         "sales_cagr_5y":10.0,"profit_cagr_5y":8.0,"financial_quality_status":"VALIDATED"},
    ])
    out=apply_intrinsic_valuation(frame)
    assert pd.isna(out.loc[0,"dcf_fair_value_base"])
    assert pd.isna(out.loc[0,"margin_of_safety_pct"])
    assert out.loc[0,"valuation_status"]=="FCF_UNAVAILABLE_OR_NON_POSITIVE"
    assert pd.isna(out.loc[1,"dcf_fair_value_base"])
    assert out.loc[1,"valuation_status"]=="SHARE_COUNT_UNVERIFIED"


def test_dcf_requires_both_five_year_growth_series():
    frame=pd.DataFrame([{
        "close":100.0,"fcf":100.0,"shares_outstanding_cr":10.0,"shares_outstanding_source":"Exchange filing",
        "sales_cagr_5y":8.0,"profit_cagr_5y":None,"financial_quality_status":"VALIDATED","period_kind":"annual",
    }])
    row=apply_intrinsic_valuation(frame).iloc[0]
    assert pd.isna(row["dcf_fair_value_base"])
    assert row["valuation_status"]=="FIVE_YEAR_GROWTH_HISTORY_UNAVAILABLE"


def test_dcf_refuses_unvalidated_statements():
    frame=pd.DataFrame([{
        "close":100.0,"fcf":100.0,"shares_outstanding_cr":10.0,"shares_outstanding_source":"Exchange filing",
        "sales_cagr_5y":8.0,"profit_cagr_5y":8.0,
        "financial_quality_status":"IDENTITY_UNVERIFIED",
    }])
    row=apply_intrinsic_valuation(frame).iloc[0]
    assert pd.isna(row["dcf_fair_value_base"])
    assert row["valuation_status"]=="FINANCIAL_DATA_NOT_VALIDATED"
