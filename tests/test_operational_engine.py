from datetime import date
import math
import pandas as pd
from valueforge.market_data import latest_partition, MarketDataError
from valueforge.fundamentals import normalize_fundamentals
from valueforge.scoring import screen_universe, score_company

def test_latest_partition_chooses_newest_available():
    files=["nse/year=2026/month=11/date=2026-11-02.parquet","nse/year=2026/month=11/date=2026-11-03.parquet"]
    assert latest_partition(files,"nse",date(2026,11,4))==files[1]

def test_latest_partition_rejects_stale_data():
    try:
        latest_partition(["nse/year=2026/month=10/date=2026-10-01.parquet"],"nse",date(2026,11,4))
        assert False
    except MarketDataError: pass

def test_screener_export_normalization():
    raw=pd.DataFrame([{"NSE Code":"ABC","Company Name":"ABC Ltd","Stock P/E":"12.5","ROE %":"18","Debt to equity":"0.2","Period End":"2025-03-31"}])
    out=normalize_fundamentals(raw)
    assert out.loc[0,"symbol"]=="ABC" and out.loc[0,"pe"]==12.5
    assert out.loc[0,"roe"]==18 and out.loc[0,"debt_to_equity"]==.2

def test_missing_fields_are_not_zero():
    score,count=score_company({"pe":None,"roe":None})
    assert math.isnan(score) and count==0

def test_financial_sector_requires_own_model():
    row={"symbol":"BANK","name":"Bank","sector":"Banking","pe":9,"pb":1,"roe":14,"roce":15,"debt_to_equity":.2,"period_end":"2025-03-31"}
    result=screen_universe(pd.DataFrame([row]))
    assert result.companies.iloc[0].research_status=="SECTOR_MODEL_REQUIRED"
