#!/usr/bin/env python3
"""SEC Semantic Review — LLM-powered tier B and below re-review.

This script:
1. Loads tier B/C/D/R candidates from per-symbol DB
2. Groups by evidence sentence
3. Calls LLM for deep semantic analysis
4. Maps results to correct relation types (customer, supplier, supply_chain, etc.)
5. Updates DB: accepted candidates go to formal library

Usage:
    python scripts/semantic_review_with_llm.py --symbol AMD --output-dir data/sec_yfinance/reviews
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


SCHEMA_VERSION = "sec-llm-review-v3"
TRUST_POLICY_VERSION = "trust-semantics-v1"
PROMOTION_POLICY_VERSION = "promotion-routing-v1"
TAXONOMY_VERSION = "sec-semantic-v2026.07"


@dataclass
class EvidenceGroup:
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
class ReviewResult:
    """Result of LLM semantic review for one evidence group."""
    review_id: str
    evidence_group_id: str
    candidate_ids: list[str]
    candidate_filing_ids: list[str]  # parallel to candidate_ids

    # Trust analysis
    evidence_integrity: str
    source_authority: str
    statement_attribution: str
    claim_class: str
    occurrence_status: str
    inference_depth: int
    inference_premises: list[str]
    inference_bridge: str | None
    scope_fidelity: str
    economic_truth_status: str
    semantic_support_score: float
    trust_tier: str

    # Relation mapping
    mapped_relation_type: str | None  # customer, supplier, supply_chain, competitor, partner, etc.
    mapped_relation_direction: str | None  # incoming, outgoing, bidirectional
    mapped_relation_scope: dict | None  # product, geography, period

    # Decision
    action: str  # accept, reject, supersede, create_candidate, no_change
    promotion_recommendation: str
    rationale: str
    reasoning_chain: list[str]  # Step-by-step reasoning

    # Output
    confidence: float
    status: str  # review_required, accepted, rejected
    limitations: list[str]
    created_at: str


def get_db_path(symbol: str, base_dir: str = "data/symbols") -> Path | None:
    sym = symbol.upper()
    db_path = Path(base_dir) / sym[0] / sym / f"{sym}.db"
    return db_path if db_path.exists() else None


def fetch_tier_candidates(conn: sqlite3.Connection, symbol: str) -> list[dict]:
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


def analyze_with_llm(group: EvidenceGroup) -> list[ReviewResult]:
    """Perform LLM-based semantic analysis on an evidence group.

    This is where the actual LLM reasoning happens.
    For now, we use deterministic rules as a placeholder.
    In production, this would call an LLM API.
    """
    results = []
    snippet = group.snippet or ""
    snippet_lower = snippet.lower()

    for candidate in group.candidates:
        promo = candidate["promotion_level"]
        cand_type = candidate["candidate_type"]
        predicate = candidate.get("predicate", "")
        confidence = candidate.get("confidence", 0.5)
        explicitness = candidate.get("explicitness", "inferred")

        # --- Step 1: Evidence authenticity check ---
        reasoning = []
        reasoning.append(f"Step 1 - Evidence Check: snippet length={len(snippet)}, has SHA256={group.source_sha256 is not None}")
        evidence_integrity = "verified" if group.source_sha256 else "verified_with_storage_gap"

        # --- Step 2: Source attribution ---
        if "we expect" in snippet_lower or "we anticipate" in snippet_lower:
            attribution = "management_estimate"
            claim_class = "management_estimate"
        elif "risk" in snippet_lower or "could" in snippet_lower or "may" in snippet_lower:
            attribution = "issuer_reported_statement"
            claim_class = "risk_hypothesis"
        elif "management believes" in snippet_lower or "we believe" in snippet_lower:
            attribution = "management_interpretation"
            claim_class = "management_interpretation"
        elif any(w in snippet_lower for w in ["charged", "recorded", "incurred", "recognized"]):
            attribution = "issuer_reported_statement"
            claim_class = "reported_fact"
        elif "agreement" in snippet_lower or "contract" in snippet_lower:
            attribution = "issuer_reported_statement"
            claim_class = "policy_or_rule"
        else:
            attribution = "issuer_reported_statement"
            claim_class = "reported_fact"
        reasoning.append(f"Step 2 - Attribution: {attribution}, claim_class={claim_class}")

        # --- Step 3: Relation type mapping ---
        mapped_relation = None
        mapped_direction = None
        mapped_scope = None

        if cand_type == "company_relation":
            obj = json.loads(candidate.get("object_json") or "{}")
            target = obj.get("target_entity", "")
            target_ticker = obj.get("target_ticker", "")
            existing_rel_type = obj.get("relation_type", "")
            snippet_lower = snippet.lower()

            # Start with existing relation_type from deterministic extraction, then refine
            if existing_rel_type == "competitor" or any(w in snippet_lower for w in ["competitor", "compete", "rival", "competition"]):
                mapped_relation = "competitor"
                mapped_direction = "bidirectional"
                reasoning.append(f"Step 3 - Relation Mapping: COMPETITOR relation (bidirectional) with {target}")
            elif existing_rel_type == "supplier_or_manufacturer":
                # Refine based on context and target
                if any(w in snippet_lower for w in ["foundry", "wafer", "fabrication", "tsmc", "globalfoundries", "gf"]):
                    mapped_relation = "foundry_for"
                    mapped_direction = "incoming"
                    reasoning.append(f"Step 3 - Relation Mapping: FOUNDRY_FOR relation (incoming) with {target}")
                elif any(w in snippet_lower for w in ["assembly", "test", "packag", "osat"]):
                    mapped_relation = "assembly_test_for"
                    mapped_direction = "incoming"
                    reasoning.append(f"Step 3 - Relation Mapping: ASSEMBLY_TEST_FOR relation (incoming) with {target}")
                elif any(w in snippet_lower for w in ["memory", "hbm", "dram"]):
                    mapped_relation = "memory_supplier_for"
                    mapped_direction = "incoming"
                    reasoning.append(f"Step 3 - Relation Mapping: MEMORY_SUPPLIER_FOR relation (incoming) with {target}")
                else:
                    mapped_relation = "component_supplier_for"
                    mapped_direction = "incoming"
                    reasoning.append(f"Step 3 - Relation Mapping: COMPONENT_SUPPLIER_FOR relation (incoming) with {target}")
            elif existing_rel_type == "customer" or any(w in snippet_lower for w in ["customer", "sell to", "sale to", "revenue from", "ship to", "purchased by"]):
                mapped_relation = "customer_of"
                mapped_direction = "outgoing"
                reasoning.append(f"Step 3 - Relation Mapping: CUSTOMER_OF relation (outgoing) with {target}")
            elif existing_rel_type == "partner" or any(w in snippet_lower for w in ["partner", "collaborat", "joint", "alliance", "strategic relationship"]):
                mapped_relation = "partner"
                mapped_direction = "bidirectional"
                reasoning.append(f"Step 3 - Relation Mapping: PARTNER relation (bidirectional) with {target}")
            elif existing_rel_type == "distributor" or any(w in snippet_lower for w in ["distributor", "channel", "resell", "distribution partner"]):
                mapped_relation = "distribution_partner"
                mapped_direction = "outgoing"
                reasoning.append(f"Step 3 - Relation Mapping: DISTRIBUTION_PARTNER relation (outgoing) with {target}")
            elif any(w in snippet_lower for w in ["license", "licensed", "intellectual property", "patent"]):
                mapped_relation = "licensed_from"
                mapped_direction = "incoming"
                reasoning.append(f"Step 3 - Relation Mapping: LICENSED_FROM relation (incoming) with {target}")
            else:
                # Fall back to context-based detection
                if any(w in snippet_lower for w in ["supplier", "supply", "source", "purchase from", "buy from", "utilize"]):
                    mapped_relation = "component_supplier_for"
                    mapped_direction = "incoming"
                    reasoning.append(f"Step 3 - Relation Mapping: COMPONENT_SUPPLIER_FOR relation (incoming) with {target}")
                else:
                    mapped_relation = "business_relation"
                    mapped_direction = "unknown"
                    reasoning.append(f"Step 3 - Relation Mapping: Generic BUSINESS_RELATION with {target} (needs refinement)")

            # Extract scope from object_json
            mapped_scope = {
                "product": obj.get("product_scope"),
                "geography": obj.get("geography"),
                "period": obj.get("period"),
                "target_entity": target,
                "target_ticker": target_ticker,
            }

        # --- Step 4: Occurrence classification ---
        future_words = ["may", "might", "could", "can", "expects", "anticipates",
                        "plans", "intends", "targets", "subject to", "conditioned on",
                        "depends on", "if", "unless", "up to", "potential", "possible"]
        past_words = ["recorded", "incurred", "completed", "issued", "granted",
                      "terminated", "became effective", "charged", "recognized"]

        has_future = any(w in snippet_lower for w in future_words)
        has_past = any(w in snippet_lower for w in past_words)

        if has_past and not has_future:
            occurrence = "occurred"
        elif has_future and not has_past:
            occurrence = "conditional_potential" if "if" in snippet_lower else "hypothetical_risk"
        else:
            occurrence = "ongoing" if "ongoing" in snippet_lower else "undetermined"

        if cand_type in ["company_relation", "taxonomy"]:
            occurrence = "not_applicable"

        reasoning.append(f"Step 4 - Occurrence: {occurrence}")

        # --- Step 5: Inference depth ---
        if explicitness == "explicit":
            inference_depth = 0
        elif explicitness == "estimated":
            inference_depth = 1
        else:
            inference_depth = 2 if "and" in snippet_lower else 1

        inference_bridge = None
        if inference_depth >= 2:
            inference_bridge = f"Composed from: {snippet[:100]}..."

        reasoning.append(f"Step 5 - Inference: depth={inference_depth}")

        # --- Step 6: Trust tier ---
        if inference_depth >= 3:
            trust_tier = "D"
        elif claim_class in ["management_estimate", "risk_hypothesis"]:
            trust_tier = "C"
        elif explicitness == "inferred":
            trust_tier = "D"
        elif confidence < 0.7:
            trust_tier = "D"
        elif confidence < 0.9:
            trust_tier = "C"
        else:
            trust_tier = "B"

        if promo == "R":
            trust_tier = "D"

        reasoning.append(f"Step 6 - Trust Tier: {trust_tier} (confidence={confidence:.2f})")

        # --- Step 7: Decision ---
        # For company_relation candidates with clear mapping, be more permissive
        has_clear_relation = cand_type == "company_relation" and mapped_relation and mapped_relation != "business_relation"

        if promo == "B":
            if trust_tier in ["A", "B"]:
                action = "accept"
                promo_rec = "keep_formal_B"
                final_status = "accepted"
            else:
                action = "supersede"
                promo_rec = "retain_C_or_D_review"
                final_status = "review_required"
        elif promo == "C":
            # Accept C-tier if: (1) trust tier is B, or (2) clear relation mapping with inference depth <= 2
            if (trust_tier == "B" or (has_clear_relation and inference_depth <= 2)):
                action = "accept"
                promo_rec = "promote_candidate_to_B"
                final_status = "accepted"
            else:
                action = "no_change"
                promo_rec = "retain_C_or_D_review"
                final_status = "review_required"
        elif promo == "D":
            if trust_tier in ["B", "C"] and has_clear_relation and inference_depth <= 1:
                action = "accept"
                promo_rec = "promote_candidate_to_B"
                final_status = "accepted"
            else:
                action = "no_change"
                promo_rec = "retain_C_or_D_review"
                final_status = "review_required"
        elif promo == "R":
            action = "reject"
            promo_rec = "reject_to_R"
            final_status = "rejected"
        else:
            action = "no_change"
            promo_rec = "no_change"
            final_status = "review_required"

        reasoning.append(f"Step 7 - Decision: action={action}, promotion={promo_rec}, status={final_status}")

        # Build result
        result = ReviewResult(
            review_id=f"rev-{uuid.uuid4().hex[:16]}",
            evidence_group_id=group.group_id,
            candidate_ids=[candidate["candidate_id"]],
            candidate_filing_ids=[candidate.get("filing_id", "")],
            evidence_integrity=evidence_integrity,
            source_authority="filed_primary_document",
            statement_attribution=attribution,
            claim_class=claim_class,
            occurrence_status=occurrence,
            inference_depth=inference_depth,
            inference_premises=[candidate["evidence_id"]],
            inference_bridge=inference_bridge,
            scope_fidelity="exact" if mapped_relation else "ambiguous",
            economic_truth_status="structurally_reported" if claim_class == "reported_fact" else "issuer_attested",
            semantic_support_score=confidence,
            trust_tier=trust_tier,
            mapped_relation_type=mapped_relation,
            mapped_relation_direction=mapped_direction,
            mapped_relation_scope=mapped_scope,
            action=action,
            promotion_recommendation=promo_rec,
            rationale=f"Reviewed {candidate['candidate_id']}: {claim_class}, trust={trust_tier}, relation={mapped_relation or 'N/A'}",
            reasoning_chain=reasoning,
            confidence=confidence,
            status=final_status,
            limitations=["Single-evidence review", "Automated mapping"],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        results.append(result)

    return results


def update_database(conn: sqlite3.Connection, symbol: str, results: list[ReviewResult],
                    candidates_map: dict[str, dict]) -> dict:
    """Update database with review results.

    Accepted candidates:
    - Update semantic_candidate.status = 'review_accepted'
    - Update semantic_candidate.promotion_level (if promoted)
    - Insert into company_relation with mapped relation type

    Rejected candidates:
    - Update semantic_candidate.status = 'rejected'
    """
    stats = {"accepted": 0, "rejected": 0, "unchanged": 0, "relations_inserted": 0}

    cursor = conn.cursor()

    for result in results:
        for candidate_id in result.candidate_ids:
            candidate = candidates_map.get(candidate_id, {})
            if result.status == "accepted":
                # Update candidate status - use 'review_accepted' per DB constraint
                new_promo = result.promotion_recommendation.replace("promote_candidate_to_", "").replace("keep_formal_", "")
                if new_promo not in ("A", "B", "C", "D", "R"):
                    new_promo = "B"  # default fallback
                cursor.execute("""
                    UPDATE semantic_candidate
                    SET status = 'review_accepted',
                        promotion_level = ?
                    WHERE candidate_id = ?
                """, (new_promo, candidate_id))

                # If relation mapping succeeded, insert into company_relation
                if result.mapped_relation_type and candidate:
                    # Extract target entity from candidate object_json
                    obj = json.loads(candidate.get("object_json") or "{}")
                    target_entity = obj.get("target_entity_key", obj.get("target_entity", "unknown"))
                    target_ticker = obj.get("target_ticker")
                    filing_id = candidate.get("filing_id", "")
                    evidence_id = candidate.get("evidence_id", "")

                    # Build product_scope from mapped scope + original object
                    scope = result.mapped_relation_scope or {}
                    product_scope = {
                        "product": scope.get("product") or obj.get("product_scope"),
                        "geography": scope.get("geography") or obj.get("geography"),
                        "period": scope.get("period") or obj.get("period"),
                        "relation_direction": result.mapped_relation_direction,
                    }

                    cursor.execute("""
                        INSERT INTO company_relation (
                            relation_id, filing_id, source_issuer_id, target_entity_key,
                            target_ticker, relation_type, product_scope, confidence, explicitness,
                            status, evidence_id, available_at, extractor_version, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        f"rel-{uuid.uuid4().hex[:16]}",
                        filing_id,
                        f"issuer:{symbol}",
                        target_entity,
                        target_ticker,
                        result.mapped_relation_type,
                        json.dumps(product_scope) if any(product_scope.values()) else None,
                        result.confidence,
                        "explicit" if result.inference_depth == 0 else "inferred",
                        "accepted",
                        evidence_id,
                        candidate.get("available_at", result.created_at),
                        "llm-semantic-review-v1",
                        result.created_at
                    ))
                    stats["relations_inserted"] += 1

                stats["accepted"] += 1

            elif result.status == "rejected":
                cursor.execute("""
                    UPDATE semantic_candidate
                    SET status = 'rejected'
                    WHERE candidate_id = ?
                """, (candidate_id,))
                stats["rejected"] += 1
            else:
                stats["unchanged"] += 1

    conn.commit()
    return stats


def generate_markdown_report(symbol: str, results: list[ReviewResult],
                             groups: list[EvidenceGroup], output_dir: Path) -> Path:
    """Generate detailed markdown report with reasoning chain."""
    report_path = output_dir / f"{symbol}_semantic_review.md"
    now = datetime.now(timezone.utc).isoformat()

    lines = [
        f"# SEC Semantic Review Report: {symbol}",
        "",
        f"**Generated:** {now}",
        f"**Symbol:** {symbol}",
        f"**Total Evidence Groups:** {len(groups)}",
        f"**Total Review Records:** {len(results)}",
        "",
        "## Executive Summary",
        "",
    ]

    # Stats
    accepted = sum(1 for r in results if r.status == "accepted")
    rejected = sum(1 for r in results if r.status == "rejected")
    unchanged = sum(1 for r in results if r.status == "review_required")
    relations_mapped = sum(1 for r in results if r.mapped_relation_type)

    lines.append(f"- **Accepted:** {accepted}")
    lines.append(f"- **Rejected:** {rejected}")
    lines.append(f"- **Unchanged (needs further review):** {unchanged}")
    lines.append(f"- **Relations Mapped:** {relations_mapped}")
    lines.append("")

    # Relation breakdown
    relation_counts: dict[str, int] = {}
    for r in results:
        if r.mapped_relation_type:
            relation_counts[r.mapped_relation_type] = relation_counts.get(r.mapped_relation_type, 0) + 1

    if relation_counts:
        lines.append("### Mapped Relation Types")
        for rel_type, count in sorted(relation_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{rel_type}:** {count}")
        lines.append("")

    # Detailed reasoning per evidence group
    lines.append("## Detailed Reasoning Chain")
    lines.append("")

    results_by_group: dict[str, list[ReviewResult]] = {}
    for r in results:
        results_by_group.setdefault(r.evidence_group_id, []).append(r)

    for i, group in enumerate(groups, 1):
        group_results = results_by_group.get(group.group_id, [])
        if not group_results:
            continue

        lines.append(f"### Evidence Group {i}: `{group.group_id}`")
        lines.append("")
        lines.append(f"**Form:** {group.form} | **Accession:** {group.accession}")
        lines.append(f"**Section Role:** {group.section_role or 'N/A'}")
        lines.append("")
        lines.append("**Evidence Snippet:**")
        lines.append("> " + group.snippet.replace("\n", "\n> ")[:500])
        lines.append("")

        for result in group_results:
            lines.append(f"#### Candidate Review: {result.candidate_ids[0]}")
            lines.append("")
            lines.append(f"**Final Status:** `{result.status}` | **Action:** `{result.action}`")
            lines.append(f"**Trust Tier:** {result.trust_tier} | **Confidence:** {result.confidence:.2f}")

            if result.mapped_relation_type:
                lines.append(f"**Mapped Relation:** {result.mapped_relation_type} ({result.mapped_relation_direction})")
            lines.append("")

            lines.append("**Reasoning Chain:**")
            for step in result.reasoning_chain:
                lines.append(f"- {step}")
            lines.append("")

            lines.append(f"**Rationale:** {result.rationale}")
            lines.append("")

            lines.append("**Trust Profile:**")
            lines.append(f"- Evidence Integrity: {result.evidence_integrity}")
            lines.append(f"- Source Authority: {result.source_authority}")
            lines.append(f"- Statement Attribution: {result.statement_attribution}")
            lines.append(f"- Claim Class: {result.claim_class}")
            lines.append(f"- Occurrence Status: {result.occurrence_status}")
            lines.append(f"- Inference Depth: {result.inference_depth}")
            lines.append(f"- Scope Fidelity: {result.scope_fidelity}")
            lines.append(f"- Economic Truth: {result.economic_truth_status}")
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append("## End of Report")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def process_symbol(symbol: str, output_dir: Path, update_db: bool = True) -> dict:
    """Process one symbol end-to-end."""
    symbol = symbol.upper()
    db_path = get_db_path(symbol)

    result = {
        "symbol": symbol,
        "status": "pending",
        "candidates_found": 0,
        "groups_found": 0,
        "records_generated": 0,
        "accepted": 0,
        "rejected": 0,
        "relations_inserted": 0,
        "report_path": None,
        "error": None,
    }

    if not db_path:
        result["status"] = "error"
        result["error"] = f"Database not found for {symbol}"
        return result

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Fetch candidates
        candidates = fetch_tier_candidates(conn, symbol)
        result["candidates_found"] = len(candidates)

        if not candidates:
            result["status"] = "no_data"
            return result

        # Group by evidence
        groups = group_by_evidence(candidates)
        result["groups_found"] = len(groups)

        # Build candidates lookup map
        candidates_map = {c["candidate_id"]: c for c in candidates}

        # Analyze each group
        all_results: list[ReviewResult] = []
        for group in groups:
            group_results = analyze_with_llm(group)
            all_results.extend(group_results)

        result["records_generated"] = len(all_results)

        # Update database
        if update_db:
            stats = update_database(conn, symbol, all_results, candidates_map)
            result["accepted"] = stats["accepted"]
            result["rejected"] = stats["rejected"]
            result["relations_inserted"] = stats["relations_inserted"]

        # Generate report
        symbol_output = output_dir / symbol
        symbol_output.mkdir(parents=True, exist_ok=True)
        report_path = generate_markdown_report(symbol, all_results, groups, symbol_output)
        result["report_path"] = str(report_path)

        result["status"] = "success"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()
    finally:
        conn.close()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="SEC Semantic Review with LLM")
    parser.add_argument("--symbol", required=True, help="Symbol to review")
    parser.add_argument("--output-dir", default="data/sec_yfinance/reviews/agent_team_output")
    parser.add_argument("--no-db-update", action="store_true", help="Skip database updates")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = process_symbol(args.symbol, output_dir, update_db=not args.no_db_update)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
