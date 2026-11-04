from datetime import date
import math
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from valueforge.market_data import latest_annual_partition, MarketDataError, _read_latest_day
from valueforge.fundamentals import normalize_fundamentals
from valueforge.scoring import screen_universe, score_company

def test_latest_annual_rollup_chooses_current_year():
    files=["nse/year=2024/nse_2024.parquet","nse/year=2025/nse_2025.parquet","nse/year=2026/nse_2026.parquet"]
    assert latest_annual_partition(files,"nse",date(2026,11,4))==files[2]

def test_bse_annual_rollup_selected():
    files=["bse/year=2024/bse_2024.parquet","bse/year=2025/bse_2025.parquet"]
    assert latest_annual_partition(files,"bse",date(2026,11,4))==files[1]

def test_unknown_exchange_rollup_raises():
    try:
        latest_annual_partition(["nse/year=2026/nse_2026.parquet"],"bse",date(2026,11,4))
        assert False
    except MarketDataError: pass

def test_read_latest_day_filters_parquet_rows(tmp_path):
    path=tmp_path/"prices.parquet"
    table=pa.table({
        "date":[date(2026,11,2),date(2026,11,3),date(2026,11,3)],
        "symbol":["AAA","AAA","BBB"],
        "close":[10.0,11.0,12.0],
    })
    pq.write_table(table,path,row_group_size=1)
    frame, latest=_read_latest_day(path,date(2026,11,4))
    assert latest==date(2026,11,3)
    assert set(frame["symbol"])=={"AAA","BBB"}
    assert len(frame)==2

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
