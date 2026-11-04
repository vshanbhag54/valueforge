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
