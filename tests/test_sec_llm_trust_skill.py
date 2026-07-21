from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "sec-llm-semantic-review"
SCHEMA_PATH = SKILL_ROOT / "assets" / "llm_review_record.schema.json"
TRUST_POLICY_PATH = SKILL_ROOT / "references" / "TRUST_SEMANTICS_POLICY.md"
CANDIDATE_SQL_PATH = SKILL_ROOT / "assets" / "select_trust_review_candidates.sql"
BRANCH = "agent/sec-llm-semantic-review-potential"


def test_trust_skill_assets_exist() -> None:
    required = [
        SKILL_ROOT / "SKILL.md",
        TRUST_POLICY_PATH,
        SKILL_ROOT / "references" / "REVIEW_OUTPUT_CONTRACT.md",
        SKILL_ROOT / "references" / "PIT_POLICY.md",
        SKILL_ROOT / "references" / "FINANCIAL_SEMANTIC_POLICY.md",
        SKILL_ROOT / "references" / "POTENTIAL_EVENT_POLICY.md",
        SKILL_ROOT / "references" / "UPLOADED_ARCHIVE_CASEBOOK.md",
        SKILL_ROOT / "assets" / "review_batch_prompt.md",
        SCHEMA_PATH,
        CANDIDATE_SQL_PATH,
        ROOT / "LOCAL_AGENT_SEC_LLM_REVIEW.md",
        ROOT / "LOCAL_AGENT_FULL_PIPELINE.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert not missing, f"missing trust-skill assets: {missing}"


def test_review_schema_requires_multidimensional_trust_profile() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == "sec-llm-review-v2"
    assert schema["properties"]["trust_policy_version"]["const"] == "trust-semantics-v1"
    assert "trust_profile" in schema["required"]
    assert "confidence" in schema["required"]

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


def test_skill_rejects_single_score_truth_semantics() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    policy = TRUST_POLICY_PATH.read_text(encoding="utf-8")

    required_phrases = [
        "Trust is multidimensional",
        "economic_truth_status",
        "semantic_support_score",
        "confidence == semantic_support_score",
        "SEC filing status proves filing provenance and timing",
    ]
    combined = f"{skill}\n{policy}"
    for phrase in required_phrases:
        assert phrase in combined


def test_trust_candidate_sql_is_read_only_and_pit_bounded() -> None:
    sql = CANDIDATE_SQL_PATH.read_text(encoding="utf-8")
    upper = sql.upper()
    for mutation in ("INSERT ", "UPDATE ", "DELETE ", "REPLACE ", "DROP ", "ALTER "):
        assert mutation not in upper
    assert ":signal_timestamp" in sql
    assert "trust_profile_reconstruction" in sql
    assert "single_information_event" in (
        SKILL_ROOT / "references" / "TRUST_SEMANTICS_POLICY.md"
    ).read_text(encoding="utf-8")


def test_local_agent_documents_point_to_trust_branch() -> None:
    for path in (
        ROOT / "LOCAL_AGENT_SEC_LLM_REVIEW.md",
        ROOT / "LOCAL_AGENT_FULL_PIPELINE.md",
        SKILL_ROOT / "assets" / "review_batch_prompt.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert BRANCH in text, f"{path.name} does not point to {BRANCH}"
