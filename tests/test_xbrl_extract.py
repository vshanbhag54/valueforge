import pandas as pd

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


def test_unlabelled_filing_can_select_discrete_quarter():
    row=extract_filing_fundamentals(XML, {
        "symbol":"DEMO","period_end":"2025-06-30","consolidated":True,
        "xbrl_url":"https://example.com/demo.xml"
    })
    assert row["period_kind"]=="quarter"
