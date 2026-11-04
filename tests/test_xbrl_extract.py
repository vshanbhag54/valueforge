import pandas as pd
from pathlib import Path

from valueforge.xbrl_extract import extract_filing_fundamentals


XML = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:link="http://www.xbrl.org/2003/linkbase"
 xmlns:xlink="http://www.w3.org/1999/xlink"
 xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2025-01-31">
 <link:schemaRef xlink:type="simple" xlink:href="in-capmkt-ent-2025-01-31.xsd"/>
 <xbrli:context id="OneD">
  <xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/xbrl">INE000A01001</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2025-06-30</xbrli:endDate></xbrli:period>
 </xbrli:context>
 <xbrli:context id="N1D">
  <xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/xbrl">INE000A01001</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:instant>2025-06-30</xbrli:instant></xbrli:period>
 </xbrli:context>
 <xbrli:context id="Prior">
  <xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/xbrl">INE000A01001</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:instant>2024-06-30</xbrli:instant></xbrli:period>
 </xbrli:context>
 <in-capmkt:RevenueFromOperations contextRef="OneD" unitRef="INR" decimals="-3">500000000</in-capmkt:RevenueFromOperations>
 <in-capmkt:ProfitLossForPeriodFromContinuingOperations contextRef="OneD" unitRef="INR" decimals="-3">50000000</in-capmkt:ProfitLossForPeriodFromContinuingOperations>
 <in-capmkt:ProfitBeforeTax contextRef="OneD" unitRef="INR" decimals="-3">70000000</in-capmkt:ProfitBeforeTax>
 <in-capmkt:FinanceCosts contextRef="OneD" unitRef="INR" decimals="-3">10000000</in-capmkt:FinanceCosts>
 <in-capmkt:OperatingProfit contextRef="OneD" unitRef="INR" decimals="-3">100000000</in-capmkt:OperatingProfit>
 <in-capmkt:CashFlowsFromUsedInOperatingActivities contextRef="OneD" unitRef="INR" decimals="-3">60000000</in-capmkt:CashFlowsFromUsedInOperatingActivities>
 <in-capmkt:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities contextRef="OneD" unitRef="INR" decimals="-3">-10000000</in-capmkt:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities>
 <in-capmkt:EquityAttributableToOwnersOfParent contextRef="N1D" unitRef="INR" decimals="-3">300000000</in-capmkt:EquityAttributableToOwnersOfParent>
 <in-capmkt:EquityAttributableToOwnersOfParent contextRef="Prior" unitRef="INR" decimals="-3">250000000</in-capmkt:EquityAttributableToOwnersOfParent>
 <in-capmkt:Assets contextRef="N1D" unitRef="INR" decimals="-3">500000000</in-capmkt:Assets>
 <in-capmkt:Borrowings contextRef="N1D" unitRef="INR" decimals="-3">100000000</in-capmkt:Borrowings>
 <in-capmkt:PaidUpValueOfEquityShareCapital contextRef="N1D" unitRef="INR" decimals="-3">50000000</in-capmkt:PaidUpValueOfEquityShareCapital>
 <in-capmkt:FaceValueOfEquityShareCapital contextRef="N1D" unitRef="INRPerShare" decimals="0">10</in-capmkt:FaceValueOfEquityShareCapital>
</xbrli:xbrl>
"""


def test_extracts_quarter_and_normalizes_currency_to_crore():
    row=extract_filing_fundamentals(XML, {
        "symbol":"DEMO","company":"Demo Ltd","exchange":"NSE","period_end":"2025-06-30",
        "relating_to":"First Quarter","consolidated":True,"audited":False,
        "xbrl_url":"https://example.com/demo.xml","filing_id":"123"
    })
    assert row["isin"]=="INE000A01001"
    assert row["period_kind"]=="quarter"
    assert row["sales"]==50
    assert row["net_profit"]==5
    assert row["equity"]==30
    assert row["total_debt"]==10
    assert round(row["debt_to_equity"],3)==0.333
    assert round(row["ocf_to_net_profit"],2)==1.2
    assert pd.isna(row.get("roe"))  # a quarterly earnings figure is not annual ROE
    assert round(row["interest_coverage"],2)==8
    assert pd.isna(row.get("roce"))  # quarter-only PBT is not annual ROCE
    assert row["paid_up_capital"]==5
    assert row["face_value"]==10
    assert row["capex"]==1
    assert row["fcf"]==5


def test_unlabelled_filing_can_select_discrete_quarter():
    row=extract_filing_fundamentals(XML, {
        "symbol":"DEMO","period_end":"2025-06-30","consolidated":True,
        "xbrl_url":"https://example.com/demo.xml"
    })
    assert row["period_kind"]=="quarter"


def test_legacy_bse_fin_taxonomy_is_parsed_and_one_d_quarter_beats_four_d_ytd():
    fixture=Path("tests/fixtures/in-bse-fin/sample_legacy_2021.xml").read_bytes()
    row=extract_filing_fundamentals(fixture, {
        "symbol":"RELIANCE","company":"Reliance Industries","exchange":"BSE",
        "period_end":"2021-03-31","relating_to":"Financial Results",
        "consolidated":True,"audited":True,"xbrl_url":"https://example.com/legacy.xml",
    })
    assert row["taxonomy_family"]=="in-bse-fin"
    assert row["isin"]=="INE002A08JTW"
    assert row["period_kind"]=="quarter"
    assert row["flow_context_id"]=="OneD"
    assert row["sales"]==2512.5
    assert row["net_profit"]==360.1
    assert row["profit_before_tax"]==483.0
    assert row["other_income"]==41.2
    assert row["paid_up_capital"]==934.219573
    assert row["data_quality_status"]=="PARTIAL_STATEMENTS"


def test_period_context_can_differ_by_a_few_days_without_using_wrong_period():
    xml=XML.replace(b"2025-06-30</xbrli:endDate>",b"2025-07-01</xbrli:endDate>",1)
    xml=xml.replace(b"2025-06-30</xbrli:instant>",b"2025-07-01</xbrli:instant>",1)
    row=extract_filing_fundamentals(xml, {
        "symbol":"DEMO","period_end":"2025-06-30","relating_to":"First Quarter",
        "consolidated":True,"xbrl_url":"https://example.com/demo.xml",
    })
    assert row["period_end"]=="2025-07-01"
    assert row["period_end_gap_days"]==1
    assert row["instant_date_gap_days"]==1


def test_period_from_overrides_ambiguous_quarter_and_half_year_label():
    from valueforge.xbrl_extract import _period_hint

    assert _period_hint(
        "Financial results for the quarter and half year ended",
        "2025-07-01","2025-09-30"
    )=="quarter"
    assert _period_hint(
        "Financial results for the quarter and half year ended",
        "2025-04-01","2025-09-30"
    )=="half_year"
