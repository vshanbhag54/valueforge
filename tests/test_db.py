import json

import pandas as pd

from valueforge import db


def test_database_url_is_optional(monkeypatch):
    monkeypatch.delenv("VALUEFORGE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.database_url() is None
    assert db.database_configured() is False


def test_company_identity_prefers_valid_isin_then_exchange_code_then_symbol():
    assert db.company_key({"isin":"INE002A01018","exchange":"BSE","symbol":"RELIANCE"})=="INE002A01018"
    assert db.company_key({"isin":None,"exchange":"BSE","security_code":"500001","symbol":"ACME"})=="BSE:CODE:500001"
    assert db.company_key({"exchange":"NSE","symbol":"ABC"})=="NSE:ABC"
    assert db.company_key({"symbol":"ABC"}) is None


def test_json_serialization_normalizes_pandas_and_numpy_values():
    record={
        "missing":pd.NA,
        "nan":float("nan"),
        "number":pd.Series([1],dtype="int64").iloc[0],
        "date":pd.Timestamp("2026-11-04"),
        "nested":{"items":[pd.NA,2.5]},
    }
    encoded=db._json(record)
    decoded=json.loads(encoded)
    assert decoded["missing"] is None
    assert decoded["nan"] is None
    assert decoded["number"]==1
    assert decoded["date"]=="2026-11-04T00:00:00"
    assert decoded["nested"]["items"]==[None,2.5]


def test_snapshot_persistence_is_a_noop_when_database_not_configured(monkeypatch):
    monkeypatch.delenv("VALUEFORGE_DATABASE_URL",raising=False)
    monkeypatch.delenv("DATABASE_URL",raising=False)
    result=db.persist_research_snapshot(
        market=pd.DataFrame([{"exchange":"NSE","symbol":"ABC","close":10.0}]),
        security_master=pd.DataFrame([{"exchange":"NSE","symbol":"ABC"}]),
        fundamentals=pd.DataFrame(),
        ranked=pd.DataFrame(),
        summary={"market_date":"2026-11-03"},
    )
    assert result=={
        "status":"NOT_CONFIGURED",
        "companies":0,
        "securities":0,
        "prices":0,
        "filings":0,
        "statements":0,
        "research_rows":0,
    }


def test_database_reads_return_safe_empty_values_when_unconfigured(monkeypatch):
    monkeypatch.delenv("VALUEFORGE_DATABASE_URL",raising=False)
    monkeypatch.delenv("DATABASE_URL",raising=False)
    assert db.database_overview()=={"status":"NOT_CONFIGURED"}
    assert db.load_latest_database_research().empty
    assert db.load_company_financial_history("INE002A01018").empty
