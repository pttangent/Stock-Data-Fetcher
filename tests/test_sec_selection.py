from equity_semantic_library.providers.sec import SecProvider


def submissions(forms, dates=None):
    dates = dates or [f"2025-0{i + 1}-01" for i in range(len(forms))]
    return {
        "cik": "320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": [f"0000320193-25-0000{i}" for i in range(len(forms))],
                "filingDate": dates,
                "acceptanceDateTime": [f"{d}T12:00:00.000Z" for d in dates],
                "reportDate": ["2024-09-28"] * len(forms),
                "form": forms,
                "primaryDocument": [f"doc{i}.htm" for i in range(len(forms))],
            }
        },
    }


def test_selects_exact_annual_and_excludes_amendment():
    result = SecProvider.select_latest_annual_filing(
        submissions(["10-K/A", "10-K", "20-F"], ["2026-02-01", "2025-11-01", "2025-12-01"])
    )
    assert result is not None
    assert result.form == "20-F"
    assert result.filing_date == "2025-12-01"


def test_returns_none_without_supported_annual_form():
    assert SecProvider.select_latest_annual_filing(submissions(["10-Q", "8-K"])) is None
