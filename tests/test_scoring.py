import math
import pandas as pd
from valueforge.scoring import score_company,screen_universe

def test_missing_values_are_not_zero():
    score,count=score_company({"roe":None,"pe":None})
    assert math.isnan(score) and count==0

def test_quality_company_passes_triage():
    df=pd.DataFrame([{"symbol":"X","name":"Test","roe":18,"roce":20,"debt_to_equity":.2,"pe":15,"pb":2}])
    assert screen_universe(df).companies.iloc[0].screen_status=="QUALIFIED_FOR_RESEARCH"

def test_missing_critical_data_is_reviewed():
    df=pd.DataFrame([{"symbol":"X","name":"Test","roe":18,"pe":15,"pb":2}])
    assert screen_universe(df).companies.iloc[0].screen_status=="REVIEW_DATA"
