import pandas as pd

from valueforge.identity import resolve_fundamental_rows
from valueforge.financial_quality import assess_financial_quality


def test_identity_resolver_uses_isin_and_exchange_scoped_symbol():
    market=pd.DataFrame([
        {"exchange":"NSE","symbol":"ABC","isin":"INE000A01001","name":"ABC Limited"},
        {"exchange":"BSE","symbol":"ABC","isin":"INE000A01002","name":"ABC Limited"},
    ])
    fundamentals=pd.DataFrame([
        {"exchange":"NSE","symbol":"ABC","isin":"INE000A01001","net_profit":10},
        {"exchange":"BSE","symbol":"ABC","isin":"INE000A01002","net_profit":20},
    ])
    indexes,methods=resolve_fundamental_rows(market,fundamentals)
    assert indexes==[0,1]
    assert methods==["ISIN","ISIN"]


def test_identity_resolver_matches_bse_scrip_code_and_blocks_ambiguous_names():
    market=pd.DataFrame([
        {"exchange":"BSE","symbol":"TCS","security_code":"532540","name":"TCS Limited"},
        {"exchange":"BSE","symbol":"UNKNOWN1","security_code":"500001","name":"Same Company"},
        {"exchange":"BSE","symbol":"UNKNOWN2","security_code":"500002","name":"Same Company"},
    ])
    fundamentals=pd.DataFrame([
        {"exchange":"BSE","symbol":"BSE-532540","security_code":"532540","name":"TCS"},
        {"exchange":"NSE","symbol":"OTHER","name":"Same Company","net_profit":1},
        {"exchange":"BSE","symbol":"OTHER2","name":"Same Company","net_profit":2},
    ])
    indexes,methods=resolve_fundamental_rows(market,fundamentals)
    assert indexes[0]==0
    assert methods[0]=="EXCHANGE_SCRIP_CODE"
    assert indexes[1:]==[-1,-1]
    assert methods[1:]==["UNMATCHED","UNMATCHED"]


def _valid_row(**overrides):
    row={
        "sales":100.0,"net_profit":10.0,"profit_before_tax":12.0,
        "equity":50.0,"assets":100.0,"total_debt":10.0,"ocf":12.0,
        "period_end":"2026-09-30","basis":"consolidated",
        "source_url":"https://exchange.example/filing.xml",
        "source_label":"Exchange XBRL filing",
        "fundamental_match_method":"ISIN",
        "capex":None,
    }
    row.update(overrides)
    return row


def test_financial_quality_validates_complete_current_consolidated_source_with_strong_identity():
    result=assess_financial_quality(_valid_row(),as_of="2026-11-04")
    assert result["financial_quality_status"]=="VALIDATED"
    assert result["financial_missing_core_fields"]==""
    assert "CAPEX_NOT_DISCLOSED_DCF_UNAVAILABLE" in result["financial_quality_issues"]


def test_financial_quality_blocks_name_only_match_and_standalone_data():
    name_only=assess_financial_quality(_valid_row(fundamental_match_method="UNIQUE_COMPANY_NAME"),as_of="2026-11-04")
    standalone=assess_financial_quality(_valid_row(basis="standalone"),as_of="2026-11-04")
    assert name_only["financial_quality_status"]=="IDENTITY_REVIEW_REQUIRED"
    assert standalone["financial_quality_status"]=="REVIEW_REQUIRED"


def test_financial_quality_blocks_missing_core_values_and_old_periods():
    incomplete=assess_financial_quality(_valid_row(ocf=None),as_of="2026-11-04")
    stale=assess_financial_quality(_valid_row(period_end="2024-03-31"),as_of="2026-11-04")
    assert incomplete["financial_quality_status"]=="INCOMPLETE"
    assert "ocf" in incomplete["financial_missing_core_fields"]
    assert stale["financial_quality_status"]=="STALE"


def test_financial_quality_blocks_non_positive_equity():
    result=assess_financial_quality(_valid_row(equity=0),as_of="2026-11-04")
    assert result["financial_quality_status"]=="REVIEW_REQUIRED"
    assert "NON_POSITIVE_EQUITY" in result["financial_quality_issues"]
