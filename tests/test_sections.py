from equity_semantic_library.providers.sec import extract_sections


def test_sections_preserve_exact_offsets():
    text = (
        "Cover\n" + "x" * 6000 + "\nITEM 1. BUSINESS\nWe sell products.\n"
        "ITEM 1A. RISK FACTORS\nRisks.\nITEM 2. PROPERTIES\nOffices.\n"
    )
    sections = extract_sections(text)
    by_key = {section.key: section for section in sections}
    assert "business" in by_key
    section = by_key["business"]
    assert text[section.char_start : section.char_end] == section.text
    assert "We sell products" in section.text
