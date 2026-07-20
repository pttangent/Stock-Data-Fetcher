from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from sec_pipeline import (
    extract_inline_xbrl,
    extract_sections,
    extract_tables,
    main,
    parse_documents,
    parse_form4,
    parse_form144,
    parse_13f,
    stable_id,
    xml_root,
)


FORM4_XML = b'''<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000000001</issuerCik><issuerName>Example Corp</issuerName><issuerTradingSymbol>EX</issuerTradingSymbol></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerCik>0000000002</rptOwnerCik><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer></reportingOwnerRelationship></reportingOwner>
  <aff10b5One>1</aff10b5One>
  <nonDerivativeTable><nonDerivativeTransaction>
    <securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>2025-01-02</value></transactionDate>
    <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
    <transactionAmounts><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>12.5</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
    <postTransactionAmounts><sharesOwnedFollowingTransaction><value>900</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
    <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>'''

FORM144_XML = b'''<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/ownership"><formData><issuerInfo><issuerCik>0001</issuerCik><issuerName>Example</issuerName><nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>Jane Doe</nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold><relationshipsToIssuer><relationshipToIssuer>OFFICER</relationshipToIssuer></relationshipsToIssuer></issuerInfo><securitiesInformation><securitiesClassTitle>Common</securitiesClassTitle><brokerOrMarketmakerDetails><name>Broker</name></brokerOrMarketmakerDetails><noOfUnitsSold>50</noOfUnitsSold><aggregateMarketValue>1000</aggregateMarketValue><approxSaleDate>01/10/2025</approxSaleDate><securitiesExchangeName>NASDAQ</securitiesExchangeName></securitiesInformation><noticeSignature><noticeDate>01/05/2025</noticeDate><signature>Jane Doe</signature></noticeSignature></formData></edgarSubmission>'''

FORM13F_XML = b'''<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable"><infoTable><nameOfIssuer>Issuer A</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>123456789</cusip><value>2500000</value><shrsOrPrnAmt><sshPrnamt>1000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><investmentDiscretion>SOLE</investmentDiscretion><votingAuthority><Sole>1000</Sole><Shared>0</Shared><None>0</None></votingAuthority></infoTable></informationTable>'''


def submission(doc_type: str, filename: str, payload: bytes, wrapper: str = "XML") -> bytes:
    return (
        b"<SEC-DOCUMENT>x.txt\n<SEC-HEADER>header</SEC-HEADER>\n<DOCUMENT>\n<TYPE>" + doc_type.encode() +
        b"\n<SEQUENCE>1\n<FILENAME>" + filename.encode() + b"\n<DESCRIPTION>fixture\n<TEXT>\n<" +
        wrapper.encode() + b">\n" + payload + b"\n</" + wrapper.encode() + b">\n</TEXT>\n</DOCUMENT>"
    )


class SecPipelineTests(unittest.TestCase):
    def test_sgml_split_and_form4(self) -> None:
        docs = parse_documents(submission("4", "form4.xml", FORM4_XML))
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["content_kind"], "xml")
        root = xml_root(docs[0]["payload"])
        rows = parse_form4(root, {"filing_id": "f"})
        self.assertEqual(rows[0]["transaction_code"], "S")
        self.assertEqual(rows[0]["shares"], "100")
        self.assertEqual(rows[0]["aff10b5_one"], "1")

    def test_sections_choose_body_not_toc(self) -> None:
        text = "TABLE OF CONTENTS\nItem 1. Business 3\nItem 1A. Risk Factors 9\n" + ("x" * 100) + "\nPART I\nItem 1. Business\nReal business disclosure.\nItem 1A. Risk Factors\nReal risks.\nPART II\nItem 5. Market\nMarket text."
        sections = extract_sections(text, "10-K")
        self.assertEqual(sections[0]["item"], "1")
        self.assertIn("Real business disclosure", sections[0]["text"])

    def test_html_tables_and_inline_xbrl(self) -> None:
        raw = b'<html><body><h2>Item 2.02 Results</h2><table><caption>Revenue</caption><tr><th>Year</th><th>Value</th></tr><tr><td>2025</td><td>10</td></tr></table><ix:nonFraction name="us-gaap:Revenue" contextRef="C1" unitRef="USD" decimals="0">10</ix:nonFraction></body></html>'
        tables = extract_tables(raw)
        self.assertEqual(tables[0]["rows"][1][1], "10")
        facts = extract_inline_xbrl(raw)
        self.assertEqual(facts[0]["concept"], "us-gaap:Revenue")
        self.assertEqual(facts[0]["value"], "10")

    def test_end_to_end_zip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "ticker=EX.zip"
            accession = "ticker=EX/cik=0000000001/accession=0000000001-25-000001"
            raw = submission("4", "form4.xml", FORM4_XML)
            meta = {
                "accessionNumber": "0000000001-25-000001", "filingDate": "2025-01-03", "reportDate": "2025-01-02",
                "acceptanceDateTime": "2025-01-03T20:00:00.000Z", "form": "4", "ticker": "EX", "cik": "0000000001",
                "companyName": "Example Corp", "primaryDocument": "form4.xml", "documents": {"complete": {"sha256": __import__("hashlib").sha256(raw).hexdigest()}},
            }
            with ZipFile(archive, "w") as z:
                z.writestr(accession + "/complete-submission.txt", raw)
                z.writestr(accession + "/filing.json", json.dumps(meta))
            output = root / "out"
            rc = main(["--input", str(archive), "--output", str(output), "--document-mode", "all"])
            self.assertEqual(rc, 0)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["table_counts"]["form4_transactions"], 1)
            self.assertTrue(any((output / "documents").rglob("*form4.xml")))

    def test_form144_and_13f(self) -> None:
        filing = {"filing_id": "f", "report_date": "2025-03-31"}
        notices = parse_form144(xml_root(FORM144_XML), filing)
        self.assertEqual(notices[0]["units_to_sell"], "50")
        self.assertEqual(notices[0]["relationship_to_issuer"], "OFFICER")
        holdings = parse_13f(xml_root(FORM13F_XML), filing)
        self.assertEqual(holdings[0]["value_usd"], "2500000")
        self.assertEqual(holdings[0]["voting_sole"], "1000")

    def test_stable_id_is_deterministic(self) -> None:
        self.assertEqual(stable_id("a", 1), stable_id("a", 1))
        self.assertNotEqual(stable_id("a", 1), stable_id("a", 2))


if __name__ == "__main__":
    unittest.main()
