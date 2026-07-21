from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "sec-llm-semantic-review"
SCHEMA_PATH = SKILL_ROOT / "assets" / "llm_review_record.schema.json"
TRUST_POLICY_PATH = SKILL_ROOT / "references" / "TRUST_SEMANTICS_POLICY.md"
ROUTING_POLICY_PATH = SKILL_ROOT / "references" / "LLM_ROUTING_POLICY.md"
ROUTING_SQL_PATH = SKILL_ROOT / "assets" / "select_llm_routing_candidates.sql"
BRANCH = "agent/sec-llm-semantic-review-potential"


def _normalize(text: str) -> str:
    text = text.lower().replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def test_trust_skill_assets_exist() -> None:
    required = [
        SKILL_ROOT / "SKILL.md",
        TRUST_POLICY_PATH,
        ROUTING_POLICY_PATH,
        SKILL_ROOT / "references" / "REVIEW_OUTPUT_CONTRACT.md",
        SKILL_ROOT / "references" / "PIT_POLICY.md",
        SKILL_ROOT / "references" / "FINANCIAL_SEMANTIC_POLICY.md",
        SKILL_ROOT / "references" / "POTENTIAL_EVENT_POLICY.md",
        SKILL_ROOT / "references" / "UPLOADED_ARCHIVE_CASEBOOK.md",
        SKILL_ROOT / "assets" / "review_batch_prompt.md",
        SCHEMA_PATH,
        ROUTING_SQL_PATH,
        ROOT / "LOCAL_AGENT_SEC_LLM_REVIEW.md",
        ROOT / "LOCAL_AGENT_FULL_PIPELINE.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert not missing, f"missing trust/routing Skill assets: {missing}"


def test_review_schema_requires_trust_and_promotion_dimensions() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == "sec-llm-review-v3"
    assert schema["properties"]["trust_policy_version"]["const"] == "trust-semantics-v1"

    required_top_level = {
        "input_promotion_level",
        "llm_route",
        "evidence_group_id",
        "candidate_ids",
        "promotion_recommendation",
        "routing_context",
        "trust_profile",
        "confidence",
    }
    assert required_top_level <= set(schema["required"])

    assert schema["properties"]["input_promotion_level"]["enum"] == [
        "A",
        "B",
        "C",
        "D1",
        "D2",
        "D3",
        "R",
    ]
    recommendations = schema["properties"]["promotion_recommendation"]["enum"]
    assert "promote_candidate_to_B" in recommendations
    assert "promote_candidate_to_A" not in recommendations

    trust = schema["properties"]["trust_profile"]
    expected_dimensions = {
        "evidence_integrity",
        "source_authority",
        "statement_attribution",
        "semantic_directness",
        "inference_depth",
        "inference_premises",
        "inference_bridge",
        "temporal_eligibility",
        "scope_fidelity",
        "corroboration_state",
        "contradiction_state",
        "economic_truth_status",
        "semantic_support_score",
        "trust_tier",
    }
    assert expected_dimensions == set(trust["required"])
    assert trust["properties"]["trust_tier"]["enum"] == ["A", "B", "C", "D", "X"]
    assert trust["properties"]["inference_depth"]["maximum"] == 3


def test_skill_separates_promotion_level_from_trust_tier() -> None:
    combined = _normalize(
        "\n".join(
            [
                (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"),
                TRUST_POLICY_PATH.read_text(encoding="utf-8"),
                ROUTING_POLICY_PATH.read_text(encoding="utf-8"),
            ]
        )
    )

    required_phrases = [
        "trust is multidimensional",
        "promotion_level is not trust_tier",
        "semantic_support_score",
        "confidence == semantic_support_score",
        "the llm cannot mint promotion level a",
        "one governed evidence group",
    ]
    for phrase in required_phrases:
        assert _normalize(phrase) in combined


def test_routing_policy_matches_expected_level_strategy() -> None:
    policy = _normalize(ROUTING_POLICY_PATH.read_text(encoding="utf-8"))
    required = [
        "a = 0% llm",
        "b = 1%-5% normal audit",
        "c = 100% of eligible evidence groups",
        "d1 = 100% after evidence grouping",
        "d3 = 0% by default",
        "r = 0.1%-1% stratified rule audit",
        "do not implement routing as",
        "where promotion_level != 'a'",
    ]
    for phrase in required:
        assert _normalize(phrase) in policy


def test_routing_sql_is_read_only_pit_bounded_and_grouped() -> None:
    sql = ROUTING_SQL_PATH.read_text(encoding="utf-8")
    upper = sql.upper()
    for mutation in ("INSERT ", "UPDATE ", "DELETE ", "REPLACE ", "DROP ", "ALTER "):
        assert mutation not in upper

    assert ":signal_timestamp" in sql
    assert "GROUP_CONCAT" in upper
    assert "evidence_group_key_material" in sql
    assert "grouped_mandatory" in sql
    assert "aggregate_then_review" in sql
    assert "no_default_review" in sql
    assert "sampled_audit" in sql
    assert "WHERE promotion_level != 'A'" not in sql


def test_local_agent_documents_point_to_trust_branch_and_routing_policy() -> None:
    for path in (
        ROOT / "LOCAL_AGENT_SEC_LLM_REVIEW.md",
        ROOT / "LOCAL_AGENT_FULL_PIPELINE.md",
        SKILL_ROOT / "assets" / "review_batch_prompt.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert BRANCH in text, f"{path.name} does not point to {BRANCH}"
        assert "LLM_ROUTING_POLICY.md" in text
        assert "select_llm_routing_candidates.sql" in text


def test_no_instruction_routes_every_non_a_record_to_llm() -> None:
    paths = [
        SKILL_ROOT / "SKILL.md",
        ROUTING_POLICY_PATH,
        SKILL_ROOT / "assets" / "review_batch_prompt.md",
        ROOT / "LOCAL_AGENT_SEC_LLM_REVIEW.md",
        ROOT / "LOCAL_AGENT_FULL_PIPELINE.md",
    ]
    prohibited = "where promotion_level != 'a'"
    for path in paths:
        text = _normalize(path.read_text(encoding="utf-8"))
        if prohibited in text:
            assert "never" in text or "do not" in text
