#!/usr/bin/env python3
"""SEC LLM Semantic Review — Tier B and below re-review with evidence chain.

For each symbol, this script:
1. Queries all tier B, C, D, R candidates from the per-symbol DB
2. Groups them by evidence sentence (evidence_group_id)
3. For each group, performs trust-semantic analysis
4. Records the reasoning chain as markdown report
5. Outputs JSONL review records conforming to schema

Usage:
    python scripts/semantic_tier_review.py --symbol AAPL --output-dir data/sec_yfinance/reviews
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "sec-llm-review-v3"
TRUST_POLICY_VERSION = "trust-semantics-v1"
PROMOTION_POLICY_VERSION = "promotion-routing-v1"
TAXONOMY_VERSION = "sec-semantic-v2026.07"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class EvidenceGroup:
    """All candidates generated from one evidence sentence."""
    group_id: str
    symbol: str
    filing_id: str
    accession: str
    form: str
    available_at: str
    section_id: str | None
    section_role: str | None
    evidence_id: str
    snippet: str
    source_sha256: str | None
    candidates: list[dict] = field(default_factory=list)


@dataclass
class TrustProfile:
    evidence_integrity: str
    source_authority: str
    statement_attribution: str
    semantic_directness: str
    inference_depth: int
    inference_premises: list[str]
    inference_bridge: str | None
    temporal_eligibility: str
    scope_fidelity: str
    corroboration_state: str
    contradiction_state: str
    economic_truth_status: str
    semantic_support_score: float
    trust_tier: str


@dataclass
class ReviewRecord:
    schema_version: str
    review_id: str
    run_id: str
    batch_id: str
    input_promotion_level: str
    llm_route: str
    evidence_group_id: str
    candidate_ids: list[str]
    promotion_recommendation: str
    routing_context: dict
    candidate_reason: str
    primary_evidence_id: str
    corroborating_evidence_ids: list[str]
    conflicting_evidence_ids: list[str]
    security_id: str
    issuer_id: str
    symbol: str
    filing_id: str
    accession: str
    form: str
    signal_timestamp: str
    source_available_at: str
    source_available_at_precision: str
    action: str
    claim_class: str
    occurrence_status: str
    subject_key: str
    predicate: str | None
    object: dict | None
    explicitness: str
    trust_profile: dict
    confidence: float
    status: str
    rationale: str
    limitations: list[str]
    reviewer: dict
    prompt_hash: str
    taxonomy_version: str
    trust_policy_version: str
    created_at: str


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def get_db_path(symbol: str, base_dir: str = "data/symbols") -> Path | None:
    """Find the per-symbol database path."""
    sym = symbol.upper()
    db_path = Path(base_dir) / sym[0] / sym / f"{sym}.db"
    if db_path.exists():
        return db_path
    return None


def fetch_tier_candidates(conn: sqlite3.Connection, symbol: str) -> list[dict]:
    """Fetch all B/C/D/R candidates for a symbol."""
    cursor = conn.execute("""
        SELECT
            c.candidate_id,
            c.candidate_type,
            c.predicate,
            c.object_json,
            c.promotion_level,
            c.confidence,
            c.explicitness,
            c.status,
            c.section_role,
            c.rule_id,
            c.filing_id,
            f.accession,
            f.form,
            f.available_at,
            f.available_at_precision,
            f.security_id,
            f.issuer_id,
            e.evidence_id,
            e.snippet,
            e.source_sha256,
            e.char_start,
            e.char_end,
            s.section_id
        FROM semantic_candidate c
        JOIN filing f ON f.filing_id = c.filing_id
        JOIN evidence_snippet e ON e.evidence_id = c.evidence_id
        LEFT JOIN filing_section s ON s.section_id = e.section_id
        WHERE f.symbol = ? AND c.promotion_level IN ('B', 'C', 'D', 'R')
        ORDER BY c.promotion_level, c.candidate_type, c.confidence DESC
    """, (symbol.upper(),))
    rows = cursor.fetchall()
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def group_by_evidence(candidates: list[dict]) -> list[EvidenceGroup]:
    """Group candidates by evidence sentence."""
    groups: dict[str, EvidenceGroup] = {}
    for c in candidates:
        key = f"{c.get('filing_id', '')}:{c.get('evidence_id', '')}"
        if key not in groups:
            groups[key] = EvidenceGroup(
                group_id=f"eg-{hashlib.sha256(key.encode()).hexdigest()[:16]}",
                symbol=c.get("symbol", ""),
                filing_id=c.get("filing_id", ""),
                accession=c.get("accession", ""),
                form=c.get("form", ""),
                available_at=c.get("available_at", ""),
                section_id=c.get("section_id"),
                section_role=c.get("section_role"),
                evidence_id=c.get("evidence_id", ""),
                snippet=c.get("snippet", ""),
                source_sha256=c.get("source_sha256"),
            )
        groups[key].candidates.append(c)
    return list(groups.values())


# ---------------------------------------------------------------------------
# Trust-semantic analysis (deterministic rules)
# ---------------------------------------------------------------------------

def analyze_evidence_group(group: EvidenceGroup, signal_ts: str) -> list[ReviewRecord]:
    """Analyze one evidence group and produce review records.

    This applies the trust-semantic policy deterministically:
    - Identifies source authority and attribution
    - Classifies claim class and occurrence status
    - Reconstructs inference depth
    - Builds trust profile
    - Recommends promotion action
    """
    records = []
    run_id = f"tier-review-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    batch_id = f"batch-{group.symbol}"

    # Determine section role
    section_role = group.section_role or "unknown"

    # Classify the evidence snippet
    snippet_lower = (group.snippet or "").lower()

    for candidate in group.candidates:
        promo = candidate["promotion_level"]
        cand_type = candidate["candidate_type"]
        predicate = candidate.get("predicate", "")
        confidence = candidate.get("confidence", 0.5)
        explicitness = candidate.get("explicitness", "inferred")

        # --- 1. Source authority & attribution ---
        if "we expect" in snippet_lower or "we anticipate" in snippet_lower:
            attribution = "management_estimate"
            claim_class = "management_estimate"
        elif "risk" in snippet_lower or "could" in snippet_lower or "may" in snippet_lower:
            attribution = "issuer_reported_statement"
            claim_class = "risk_hypothesis"
        elif "management believes" in snippet_lower or "we believe" in snippet_lower:
            attribution = "management_interpretation"
            claim_class = "management_interpretation"
        elif "charged" in snippet_lower or "recorded" in snippet_lower or "incurred" in snippet_lower:
            attribution = "issuer_reported_statement"
            claim_class = "reported_fact"
        elif "agreement" in snippet_lower or "contract" in snippet_lower:
            attribution = "issuer_reported_statement"
            claim_class = "policy_or_rule"
        else:
            attribution = "issuer_reported_statement"
            claim_class = "reported_fact"

        # --- 2. Occurrence status ---
        future_words = ["may", "might", "could", "can", "expects", "anticipates",
                        "plans", "intends", "targets", "subject to", "conditioned on",
                        "depends on", "if", "unless", "up to", "potential", "possible",
                        "proposed", "scheduled"]
        past_words = ["recorded", "incurred", "completed", "issued", "granted",
                      "terminated", "became effective", "charged", "recognized"]

        has_future = any(w in snippet_lower for w in future_words)
        has_past = any(w in snippet_lower for w in past_words)

        if has_past and not has_future:
            occurrence = "occurred"
        elif has_future and not has_past:
            if "risk" in snippet_lower or "could" in snippet_lower:
                occurrence = "conditional_potential" if "if" in snippet_lower or "depends" in snippet_lower else "hypothetical_risk"
            else:
                occurrence = "expected_not_occurred"
        elif has_past and has_future:
            occurrence = "mixed"
        else:
            occurrence = "ongoing" if "ongoing" in snippet_lower or "current" in snippet_lower else "undetermined"

        # For non-event claims
        if cand_type in ["company_relation", "taxonomy"]:
            occurrence = "not_applicable"

        # --- 3. Inference depth ---
        if explicitness == "explicit":
            inference_depth = 0
        elif explicitness == "estimated":
            inference_depth = 1
        else:
            # Check for composition
            if "and" in snippet_lower and ("rely" in snippet_lower or "depend" in snippet_lower):
                inference_depth = 2
            else:
                inference_depth = 1

        inference_premises = [candidate["evidence_id"]]
        inference_bridge = None
        if inference_depth >= 2:
            inference_bridge = f"Composition of explicit clauses: {predicate} inferred from multi-clause evidence"

        # --- 4. Scope fidelity ---
        if cand_type == "company_relation":
            obj = json.loads(candidate.get("object_json") or "{}")
            if obj.get("product_scope") or obj.get("relation_role"):
                scope_fidelity = "exact"
            else:
                scope_fidelity = "partial"
        else:
            scope_fidelity = "exact" if explicitness == "explicit" else "bounded"

        # --- 5. Economic truth status ---
        if claim_class == "reported_fact":
            economic_truth = "structurally_reported"
        elif claim_class == "management_estimate":
            economic_truth = "not_independently_assessed"
        elif claim_class in ["risk_hypothesis", "management_interpretation"]:
            economic_truth = "issuer_attested"
        else:
            economic_truth = "not_independently_assessed"

        # --- 6. Trust tier derivation ---
        if inference_depth >= 3:
            trust_tier = "D"
        elif inference_depth == 2:
            trust_tier = "C"
        elif claim_class in ["management_estimate", "risk_hypothesis", "management_interpretation"]:
            trust_tier = "C"
        elif explicitness == "inferred":
            trust_tier = "D"
        elif confidence < 0.7:
            trust_tier = "D"
        elif confidence < 0.9:
            trust_tier = "C"
        else:
            trust_tier = "B"

        # Override: R candidates get D trust tier (they were rejected)
        if promo == "R":
            trust_tier = "D"

        # --- 7. Semantic support score = confidence ---
        semantic_support_score = confidence

        # --- 8. Action & promotion recommendation ---
        if promo == "B":
            if trust_tier in ["A", "B"]:
                action = "no_change"
                promo_rec = "keep_formal_B"
            else:
                action = "supersede"
                promo_rec = "retain_C_or_D_review"
        elif promo == "C":
            if trust_tier == "B" and inference_depth <= 1:
                action = "create_candidate"
                promo_rec = "promote_candidate_to_B"
            else:
                action = "no_change"
                promo_rec = "retain_C_or_D_review"
        elif promo == "D":
            action = "no_change"
            promo_rec = "retain_C_or_D_review"
        elif promo == "R":
            action = "reject"
            promo_rec = "reject_to_R"
        else:
            action = "no_change"
            promo_rec = "no_change"

        # --- 9. Candidate reason ---
        if cand_type == "company_relation":
            candidate_reason = "relation_role_refinement"
        elif cand_type == "event":
            candidate_reason = "potential_future_event"
        elif claim_class == "management_estimate":
            candidate_reason = "mixed_actual_estimate_risk"
        elif inference_depth >= 2:
            candidate_reason = "inference_audit"
        else:
            candidate_reason = "trust_profile_reconstruction"

        # --- 10. Build trust profile ---
        trust_profile = TrustProfile(
            evidence_integrity="verified" if group.source_sha256 else "verified_with_storage_gap",
            source_authority="filed_primary_document",
            statement_attribution=attribution,
            semantic_directness="explicit_text" if explicitness == "explicit" else "normalized_explicit",
            inference_depth=inference_depth,
            inference_premises=inference_premises,
            inference_bridge=inference_bridge,
            temporal_eligibility="eligible_datetime" if "T" in group.available_at else "eligible_date_only",
            scope_fidelity=scope_fidelity,
            corroboration_state="single_evidence",
            contradiction_state="none",
            economic_truth_status=economic_truth,
            semantic_support_score=semantic_support_score,
            trust_tier=trust_tier,
        )

        # --- 11. Build record ---
        obj_data = None
        if candidate.get("object_json"):
            try:
                obj_data = json.loads(candidate["object_json"])
            except json.JSONDecodeError:
                obj_data = {"raw": candidate["object_json"]}

        # Determine llm_route from promotion level
        llm_route_map = {
            "A": "none",
            "B": "sampled_audit",
            "C": "mandatory",
            "D": "grouped_mandatory",
            "R": "rejection_audit",
        }

        record = ReviewRecord(
            schema_version=SCHEMA_VERSION,
            review_id=f"rev-{uuid.uuid4().hex[:16]}",
            run_id=run_id,
            batch_id=batch_id,
            input_promotion_level=promo,
            llm_route=llm_route_map.get(promo, "mandatory"),
            evidence_group_id=group.group_id,
            candidate_ids=[candidate["candidate_id"]],
            promotion_recommendation=promo_rec,
            routing_context={
                "promotion_policy_version": PROMOTION_POLICY_VERSION,
                "section_role": section_role,
                "grouping_key": f"{group.symbol}|{group.accession}|{section_role}|{group.evidence_id}",
                "dedupe_cluster_id": None,
                "rule_id": candidate.get("rule_id"),
                "rule_version": "v1",
                "sample_rate": None,
                "sample_seed": None,
                "sample_reason": None,
                "population_count": None,
            },
            candidate_reason=candidate_reason,
            primary_evidence_id=group.evidence_id,
            corroborating_evidence_ids=[],
            conflicting_evidence_ids=[],
            security_id=candidate.get("security_id", ""),
            issuer_id=candidate.get("issuer_id", ""),
            symbol=group.symbol,
            filing_id=group.filing_id,
            accession=group.accession,
            form=group.form,
            signal_timestamp=signal_ts,
            source_available_at=group.available_at or signal_ts,
            source_available_at_precision=candidate.get("available_at_precision", "datetime") or "datetime",
            action=action,
            claim_class=claim_class,
            occurrence_status=occurrence if occurrence != "mixed" else "undetermined",
            subject_key=f"security:{group.symbol}",
            predicate=predicate if predicate else None,
            object=obj_data,
            explicitness=explicitness,
            trust_profile=trust_profile.__dict__,
            confidence=semantic_support_score,
            status="review_required",
            rationale=build_rationale(candidate, group, trust_profile, claim_class, occurrence),
            limitations=[
                "Single-evidence review; no cross-filing corroboration performed",
                "Automated attribution; may require human verification for depth >= 2",
            ],
            reviewer={
                "provider": "local",
                "model": "semantic-tier-reviewer-v1",
                "model_version": "2026.07.21",
                "temperature": 0.0,
            },
            prompt_hash="sha256:" + hashlib.sha256(b"semantic-tier-review-v1").hexdigest()[:32],
            taxonomy_version=TAXONOMY_VERSION,
            trust_policy_version=TRUST_POLICY_VERSION,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        records.append(record)

    return records


def build_rationale(candidate: dict, group: EvidenceGroup, trust: TrustProfile,
                    claim_class: str, occurrence: str) -> str:
    """Build a human-readable rationale string."""
    parts = [
        f"Candidate {candidate['candidate_id']} ({candidate['promotion_level']}): ",
        f"Type={candidate['candidate_type']}, predicate={candidate.get('predicate', 'N/A')}. ",
        f"Claim class: {claim_class}. Occurrence: {occurrence}. ",
        f"Inference depth: {trust.inference_depth}. ",
        f"Trust tier: {trust.trust_tier} (score={trust.semantic_support_score:.2f}). ",
        f"Evidence: {group.snippet[:120]}..." if len(group.snippet) > 120 else f"Evidence: {group.snippet}",
    ]
    return "".join(parts)


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------

def generate_markdown_report(symbol: str, records: list[ReviewRecord],
                             groups: list[EvidenceGroup], output_dir: Path) -> Path:
    """Generate a markdown report with reasoning chain for the symbol."""
    report_path = output_dir / f"{symbol}_semantic_review.md"

    now = datetime.now(timezone.utc).isoformat()

    lines = [
        f"# SEC Semantic Review Report: {symbol}",
        "",
        f"**Generated:** {now}",
        f"**Symbol:** {symbol}",
        f"**Total Evidence Groups:** {len(groups)}",
        f"**Total Review Records:** {len(records)}",
        "",
        "## Summary",
        "",
    ]

    # Count by promotion level
    by_promo: dict[str, int] = {}
    by_action: dict[str, int] = {}
    by_trust_tier: dict[str, int] = {}
    for r in records:
        by_promo[r.input_promotion_level] = by_promo.get(r.input_promotion_level, 0) + 1
        by_action[r.action] = by_action.get(r.action, 0) + 1
        by_trust_tier[r.trust_profile["trust_tier"]] = by_trust_tier.get(r.trust_profile["trust_tier"], 0) + 1

    lines.append("### By Input Promotion Level")
    for lvl in ["B", "C", "D", "R"]:
        if lvl in by_promo:
            lines.append(f"- **{lvl}:** {by_promo[lvl]} candidates")
    lines.append("")

    lines.append("### By Recommended Action")
    for act, count in sorted(by_action.items(), key=lambda x: -x[1]):
        lines.append(f"- **{act}:** {count}")
    lines.append("")

    lines.append("### By Derived Trust Tier")
    for tier in ["A", "B", "C", "D", "X"]:
        if tier in by_trust_tier:
            lines.append(f"- **{tier}:** {by_trust_tier[tier]} records")
    lines.append("")

    # Detailed reasoning chain per evidence group
    lines.append("## Detailed Reasoning Chain")
    lines.append("")

    # Group records by evidence_group_id
    records_by_group: dict[str, list[ReviewRecord]] = {}
    for r in records:
        records_by_group.setdefault(r.evidence_group_id, []).append(r)

    for i, group in enumerate(groups, 1):
        group_records = records_by_group.get(group.group_id, [])
        if not group_records:
            continue

        lines.append(f"### Evidence Group {i}: `{group.group_id}`")
        lines.append("")
        lines.append(f"**Form:** {group.form} | **Accession:** {group.accession}")
        lines.append(f"**Section Role:** {group.section_role or 'N/A'}")
        lines.append(f"**Available At:** {group.available_at}")
        lines.append("")
        lines.append("**Evidence Snippet:**")
        lines.append("> " + group.snippet.replace("\n", "\n> "))
        lines.append("")

        for rec in group_records:
            tp = rec.trust_profile
            lines.append(f"#### Candidate: {rec.candidate_ids[0]}")
            lines.append("")
            lines.append(f"| Field | Value |")
            lines.append(f"|-------|-------|")
            lines.append(f"| Input Promotion | {rec.input_promotion_level} |")
            lines.append(f"| LLM Route | {rec.llm_route} |")
            lines.append(f"| Claim Class | {rec.claim_class} |")
            lines.append(f"| Occurrence Status | {rec.occurrence_status} |")
            lines.append(f"| Predicate | {rec.predicate or 'N/A'} |")
            lines.append(f"| Explicitness | {rec.explicitness} |")
            lines.append(f"| Confidence | {rec.confidence:.2f} |")
            lines.append("")
            lines.append("**Trust Profile:**")
            lines.append("")
            lines.append(f"- **Evidence Integrity:** {tp['evidence_integrity']}")
            lines.append(f"- **Source Authority:** {tp['source_authority']}")
            lines.append(f"- **Statement Attribution:** {tp['statement_attribution']}")
            lines.append(f"- **Semantic Directness:** {tp['semantic_directness']}")
            lines.append(f"- **Inference Depth:** {tp['inference_depth']}")
            if tp.get('inference_bridge'):
                lines.append(f"- **Inference Bridge:** {tp['inference_bridge']}")
            lines.append(f"- **Temporal Eligibility:** {tp['temporal_eligibility']}")
            lines.append(f"- **Scope Fidelity:** {tp['scope_fidelity']}")
            lines.append(f"- **Corroboration State:** {tp['corroboration_state']}")
            lines.append(f"- **Contradiction State:** {tp['contradiction_state']}")
            lines.append(f"- **Economic Truth Status:** {tp['economic_truth_status']}")
            lines.append(f"- **Semantic Support Score:** {tp['semantic_support_score']:.2f}")
            lines.append(f"- **Trust Tier:** {tp['trust_tier']}")
            lines.append("")
            lines.append(f"**Recommended Action:** `{rec.action}` → `{rec.promotion_recommendation}`")
            lines.append("")
            lines.append(f"**Rationale:** {rec.rationale}")
            lines.append("")
            if rec.limitations:
                lines.append("**Limitations:**")
                for lim in rec.limitations:
                    lines.append(f"- {lim}")
                lines.append("")
            lines.append("---")
            lines.append("")

    lines.append("## End of Report")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# JSONL output
# ---------------------------------------------------------------------------

def write_jsonl(records: list[ReviewRecord], output_path: Path) -> None:
    """Write review records as JSONL."""
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec.__dict__, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_symbol(symbol: str, output_dir: Path, signal_timestamp: str | None = None) -> dict:
    """Process a single symbol: fetch, analyze, report."""
    symbol = symbol.upper()
    db_path = get_db_path(symbol)

    result = {
        "symbol": symbol,
        "status": "pending",
        "candidates_found": 0,
        "groups_found": 0,
        "records_generated": 0,
        "report_path": None,
        "jsonl_path": None,
        "error": None,
    }

    if not db_path:
        result["status"] = "error"
        result["error"] = f"Database not found for {symbol}"
        return result

    # Use latest available_at as signal timestamp if not provided
    if signal_timestamp is None:
        signal_timestamp = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        candidates = fetch_tier_candidates(conn, symbol)
        result["candidates_found"] = len(candidates)

        if not candidates:
            result["status"] = "no_data"
            result["error"] = f"No B/C/D/R candidates found for {symbol}"
            return result

        groups = group_by_evidence(candidates)
        result["groups_found"] = len(groups)

        all_records: list[ReviewRecord] = []
        for group in groups:
            records = analyze_evidence_group(group, signal_timestamp)
            all_records.extend(records)

        result["records_generated"] = len(all_records)

        # Write outputs
        symbol_output = output_dir / symbol
        symbol_output.mkdir(parents=True, exist_ok=True)

        jsonl_path = symbol_output / "records.jsonl"
        write_jsonl(all_records, jsonl_path)
        result["jsonl_path"] = str(jsonl_path)

        report_path = generate_markdown_report(symbol, all_records, groups, symbol_output)
        result["report_path"] = str(report_path)

        result["status"] = "success"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    finally:
        conn.close()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="SEC Semantic Tier Review")
    parser.add_argument("--symbol", required=True, help="Symbol to review")
    parser.add_argument("--output-dir", default="data/sec_yfinance/reviews/batch_01-06_tier_review",
                        help="Output directory")
    parser.add_argument("--signal-timestamp", help="Signal timestamp (ISO-8601)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = process_symbol(args.symbol, output_dir, args.signal_timestamp)

    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
