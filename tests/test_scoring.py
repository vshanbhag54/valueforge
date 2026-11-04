import math
import pandas as pd
from valueforge.scoring import score_company,screen_universe

def test_missing_values_are_not_zero():
    score,count=score_company({"roe":None,"pe":None})
    assert math.isnan(score) and count==0

def test_recent_complete_company_can_enter_research_queue():
    recent=(pd.Timestamp.now().normalize()-pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    df=pd.DataFrame([{"symbol":"X","name":"Test","sector":"Industrials","roe":18,"roce":20,
      "debt_to_equity":.2,"pe":15,"pb":2,"period_end":recent}])
    assert screen_universe(df).companies.iloc[0].research_status=="VALUE_RESEARCH_CANDIDATE"

def test_missing_critical_data_is_blocked():
    df=pd.DataFrame([{"symbol":"X","name":"Test","roe":18,"pe":15,"pb":2}])
    assert screen_universe(df).companies.iloc[0].research_status=="FUNDAMENTALS_INCOMPLETE"

def test_old_period_is_stale():
    df=pd.DataFrame([{"symbol":"X","name":"Test","roe":18,"roce":20,"debt_to_equity":.2,"pe":15,
      "pb":2,"ocf_to_net_profit":1,"period_end":"2024-01-01"}])
    assert screen_universe(df).companies.iloc[0].research_status=="FUNDAMENTALS_STALE"
