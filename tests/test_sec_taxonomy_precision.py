from __future__ import annotations

from equity_semantic_library.sec_pipeline.taxonomy import COMPILED_TOPICS


def _patterns(topic: str):
    return next(patterns for name, _group, patterns in COMPILED_TOPICS if name == topic)


def test_digital_advertising_requires_business_model_language() -> None:
    patterns = _patterns("digital_advertising")
    assert not any(pattern.search("We have cooperative advertising and co-marketing programs with channel partners.") for pattern in patterns)
    assert any(pattern.search("The platform generates digital advertising revenue from advertiser campaigns.") for pattern in patterns)


def test_antitrust_does_not_match_generic_regulatory_investigation() -> None:
    patterns = _patterns("antitrust_regulation")
    assert not any(pattern.search("A security incident could result in litigation or a regulatory investigation.") for pattern in patterns)
    assert any(pattern.search("The company is subject to an antitrust investigation by competition authorities.") for pattern in patterns)
