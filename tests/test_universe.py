import pandas as pd

from valueforge.universe import attach_market_prices, normalize_bse_equity, normalize_nse_equity


def test_normalize_nse_equity_master_fields():
    raw=pd.DataFrame([{
        "SYMBOL":"ABC","NAME OF COMPANY":"ABC Limited","SERIES":"EQ",
        "ISIN NUMBER":"INE000A01001","FACE VALUE":10,"PAID UP VALUE":10,
    }])
    row=normalize_nse_equity(raw).iloc[0]
    assert row["symbol"]=="ABC"
    assert row["isin"]=="INE000A01001"
    assert row["exchange"]=="NSE"
    assert row["face_value"]==10
    assert pd.isna(row["paid_up_capital"])


def test_normalize_bse_master_and_convert_face_value_paise():
    raw=[{
        "scrip_id":"TCS","SCRIP_CD":532540,"SCRIP_NAME":"TCS Limited",
        "ISIN_NUMBER":"INE467B01029","GROUP":"A","Face_Value":1000,"Industry":"IT",
    }]
    row=normalize_bse_equity(raw).iloc[0]
    assert row["symbol"]=="TCS"
    assert row["security_code"]=="532540"
    assert row["face_value"]==10
    assert row["sector"]=="IT"


def test_attach_prices_by_isin_and_bse_scrip_code_preserving_untraded_listing():
    master=pd.DataFrame([
        {"exchange":"NSE","symbol":"ABC","isin":"INE000A01001","name":"ABC Ltd","series":"EQ"},
        {"exchange":"BSE","symbol":"TCS","isin":"INE467B01029","name":"TCS Ltd","series":"A","security_code":"532540"},
        {"exchange":"BSE","symbol":"SMECO","isin":pd.NA,"name":"SME Co","series":"M","security_code":"500001"},
        {"exchange":"BSE","symbol":"UNTRADED","isin":pd.NA,"name":"Untraded Ltd","series":"X","security_code":"500002"},
    ])
    quotes=pd.DataFrame([
        {"exchange":"NSE","symbol":"ABC","isin":"INE000A01001","close":100.0,"snapshot_date":"2026-11-03"},
        {"exchange":"BSE","symbol":"532540","isin":"INE467B01029","close":200.0,"snapshot_date":"2026-11-03"},
        {"exchange":"BSE","symbol":"500001","isin":pd.NA,"close":50.0,"snapshot_date":"2026-11-03"},
    ])
    out=attach_market_prices(master,quotes).set_index("symbol")
    assert out.loc["ABC","close"]==100
    assert out.loc["TCS","close"]==200
    assert out.loc["SMECO","close"]==50
    assert out.loc["UNTRADED","price_status"]=="NO_EOD_PRICE"
    assert len(out)==4
