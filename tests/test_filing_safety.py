from valueforge.filings import _strict_flag
from valueforge.xbrl_extract import extract_filing_fundamentals
from test_xbrl_extract import XML


def test_consolidation_classifier_rejects_unknown_and_standalone_values():
    assert _strict_flag("Consolidated") is True
    assert _strict_flag("Standalone") is False
    assert _strict_flag("Non-Consolidated") is False
    assert _strict_flag("Unaudited") is False
    assert _strict_flag("Audited") is True
    assert _strict_flag("Ind-AS New") is True
    assert _strict_flag("mystery status") is False


def test_context_selection_prefers_fullest_statement_fact_set():
    extra = b"""
    <xbrli:context id="AAA">
      <xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/xbrl">INE000A01001</xbrli:identifier></xbrli:entity>
      <xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2025-06-30</xbrli:endDate></xbrli:period>
    </xbrli:context>
    <in-capmkt:RevenueFromOperations contextRef="AAA" unitRef="INR" decimals="-3">999000000</in-capmkt:RevenueFromOperations>
    """
    xml=XML.replace(b"</xbrli:xbrl>",extra+b"</xbrli:xbrl>")
    row=extract_filing_fundamentals(xml,{
        "symbol":"DEMO","period_end":"2025-06-30","relating_to":"First Quarter",
        "consolidated":True,"xbrl_url":"https://example.com/demo.xml"
    })
    assert row["flow_context_id"]=="OneD"
    assert row["sales"]==50


def test_registry_keys_accept_numeric_csv_parser_versions():
    import pandas as pd
    from valueforge.filings import _registry_keys

    registry = pd.DataFrame({
        "filing_key": ["A|1", "B|2", "C|3", "D|4"],
        "parser_version": [8.0, "8", 3.0, None],
        "parse_status": ["PARSED", "PARSE_FAILED: unsupported context", "PARSED", "PARSED"],
    })
    assert _registry_keys(registry) == {"A|1", "B|2"}


def test_registry_keys_do_not_accept_older_parser_versions():
    import pandas as pd
    from valueforge.filings import _registry_keys

    registry = pd.DataFrame({
        "filing_key": ["OLD|1", "UNKNOWN|2"],
        "parser_version": [7.0, None],
        "parse_status": ["PARSED", "PARSED"],
    })
    assert _registry_keys(registry) == set()


def test_pending_filings_prioritize_recent_periods_before_history():
    from datetime import date, datetime
    from types import SimpleNamespace
    from valueforge.filings import _sort_pending_filings

    records = [
        SimpleNamespace(symbol="OLD", period_to=date(2020, 3, 31), filing_ts=datetime(2020, 5, 1)),
        SimpleNamespace(symbol="CURRENT", period_to=date(2026, 9, 30), filing_ts=datetime(2026, 11, 4)),
        SimpleNamespace(symbol="MID", period_to=date(2023, 3, 31), filing_ts=datetime(2023, 5, 1)),
        SimpleNamespace(symbol="UNKNOWN", period_to=None, filing_ts=None),
    ]
    ordered = _sort_pending_filings(records)
    assert [item.symbol for item in ordered] == ["CURRENT", "MID", "OLD", "UNKNOWN"]
