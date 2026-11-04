import pandas as pd

from valueforge.sector_models import classify_sector, evaluate_sector_metrics
from valueforge.scoring import screen_universe


def test_bank_sector_uses_bank_metrics_not_industrial_model():
    row={"name":"Example Bank Ltd","sector":"Banking"}
    result=evaluate_sector_metrics(row)
    assert result["sector_model"]=="BANK"
    assert result["sector_metrics_status"]=="INCOMPLETE"
    assert "gnpa_pct" in result["sector_metrics_missing"]
    assert result["sector_research_status"]=="SECTOR_MODEL_REQUIRED"


def test_complete_bank_metrics_are_routed_to_sector_review_not_automatic_buy():
    row={
        "name":"Example Bank Ltd","sector":"Banking","roe":15,
        "roa_pct":1.5,"nim_pct":3.5,"gnpa_pct":2.0,"nnpa_pct":0.5,
        "crar_pct":17,"cost_to_income_pct":45,
        "source_url":"https://exchange.example/bank-results.pdf","period_end":"2026-03-31",
    }
    result=evaluate_sector_metrics(row)
    assert result["sector_metrics_status"]=="METRICS_COMPLETE"
    assert result["sector_metrics_coverage_pct"]==100
    assert result["sector_research_status"]=="SECTOR_RESEARCH_REVIEW"
    screened=screen_universe(pd.DataFrame([{
        **row,"close":100,"period_end":"2026-03-31","pe":10,
        "pb":1.2,"debt_to_equity":0.2,
    }]))
    assert screened.companies.iloc[0]["research_status"]=="SECTOR_RESEARCH_REVIEW"


def test_insurer_and_asset_manager_models_are_distinguished():
    assert classify_sector({"name":"ABC Life Insurance Ltd","sector":"Insurance"})=="INSURANCE"
    assert classify_sector({"name":"ABC Asset Management Ltd","sector":"Financial Services"})=="ASSET_MANAGER"


def test_non_financial_company_is_not_given_sector_review_label():
    result=evaluate_sector_metrics({"name":"ABC Manufacturing Ltd","sector":"Industrials"})
    assert result["sector_model"] is None
    assert result["sector_metrics_status"]=="NOT_APPLICABLE"


def test_sector_metrics_without_primary_source_or_current_period_remain_incomplete():
    row={
        "name":"Example Bank Ltd","sector":"Banking","roe":15,
        "roa_pct":1.5,"nim_pct":3.5,"gnpa_pct":2.0,"nnpa_pct":0.5,
        "crar_pct":17,"cost_to_income_pct":45,
    }
    result=evaluate_sector_metrics(row)
    assert result["sector_metrics_status"]=="INCOMPLETE"
    assert "sector_data_source_url" in result["sector_metrics_missing"]
    assert "sector_data_as_of" in result["sector_metrics_missing"]


def test_non_banking_financial_wording_is_classified_as_nbfc():
    assert classify_sector({
        "name":"Example Lending Limited",
        "sector":"Non-Banking Financial Company",
    })=="NBFC"
