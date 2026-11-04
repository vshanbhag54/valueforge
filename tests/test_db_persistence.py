import pandas as pd

from valueforge import db


class FakeCursor:
    def __init__(self, select_results=None):
        self.select_results = list(select_results or [])
        self.calls = []
        self.last_sql = None

    def execute(self, sql, params=None):
        self.calls.append((sql,params))
        self.last_sql = sql

    def fetchall(self):
        return self.select_results


def test_filing_registry_persists_parse_failures_and_skips_unchanged_rows():
    cur=FakeCursor([("OLD|1",10,"PARSED")])
    registry=[
        {
            "filing_key":"OLD|1","symbol":"OLD","exchange":"NSE","isin":"INE000A01001",
            "company":"Old Company","period_end":"2026-03-31","filing_id":"1",
            "xbrl_url":"https://exchange.example/old.xml","parser_version":10,
            "parse_status":"PARSED","consolidated":True,"audited":True,"fact_count":250,
        },
        {
            "filing_key":"NEW|2","symbol":"NEW","exchange":"NSE","isin":"INE000A01002",
            "company":"New Company","period_end":"2026-03-31","filing_id":"2",
            "xbrl_url":"https://exchange.example/new.xml","parser_version":10,
            "parse_status":"PARSE_FAILED: XBRL_NO_FLOW_CONTEXT","consolidated":True,
            "audited":True,"fact_count":0,
        },
    ]
    written=db._persist_filing_registry(cur,pd.DataFrame(registry))
    assert written==1
    insert_calls=[call for call in cur.calls if "insert into valueforge.filings" in call[0]]
    issue_calls=[call for call in cur.calls if "insert into valueforge.data_quality_issues" in call[0]]
    assert len(insert_calls)==1
    assert insert_calls[0][1][0]=="NEW|2"
    assert insert_calls[0][1][-1]=="XBRL_NO_FLOW_CONTEXT"
    assert len(issue_calls)==1
    assert issue_calls[0][1][1]=="NEW|2"


def test_financial_statement_persistence_reprocesses_only_new_parser_version():
    cur=FakeCursor([("OLD|1",10)])
    fundamentals=[{
        "filing_key":"OLD|1","parser_version":10,"exchange":"NSE","symbol":"OLD",
        "isin":"INE000A01001","name":"Old Ltd","period_end":"2026-03-31",
        "period_kind":"annual","basis":"consolidated","audited":True,
        "source_url":"https://exchange.example/old.xml","data_quality_status":"COMPLETE",
        "statement_completeness_pct":100,"sales":100.0,"net_profit":10.0,
        "equity":50.0,"assets":100.0,"total_debt":10.0,"ocf":12.0,
    },{
        "filing_key":"NEW|2","parser_version":11,"exchange":"NSE","symbol":"NEW",
        "isin":"INE000A01002","name":"New Ltd","period_end":"2026-03-31",
        "period_kind":"annual","basis":"consolidated","audited":True,
        "source_url":"https://exchange.example/new.xml","data_quality_status":"COMPLETE",
        "statement_completeness_pct":100,"sales":200.0,"net_profit":20.0,
        "equity":100.0,"assets":200.0,"total_debt":20.0,"ocf":24.0,
    }]
    written=db._persist_statements(cur,pd.DataFrame(fundamentals))
    assert written==1
    statement_calls=[call for call in cur.calls if "insert into valueforge.financial_statements" in call[0]]
    assert len(statement_calls)==1
    assert statement_calls[0][1][0]=="NEW|2"
    assert statement_calls[0][1][12]==11
