#!/usr/bin/env python3
"""Generate semantic review reports for batch_01-06 symbols.

Focus on tier B and below candidates: analyze why promote, why reject, why establish relation.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def analyze_symbol(symbol: str, db_path: str) -> dict:
    """Analyze a single symbol's semantic candidates."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get candidate details for B/C/D/R
    candidates = conn.execute("""
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
            f.form,
            f.filing_date,
            e.snippet
        FROM semantic_candidate c
        JOIN filing f ON f.filing_id = c.filing_id
        JOIN evidence_snippet e ON e.evidence_id = c.evidence_id
        WHERE f.symbol = ? AND c.promotion_level IN ('B', 'C', 'D', 'R')
        ORDER BY c.promotion_level, c.candidate_type, c.confidence DESC
    """, (symbol,)).fetchall()

    # Group by promotion level
    by_level = {"B": [], "C": [], "D": [], "R": []}
    for row in candidates:
        by_level[row["promotion_level"]].append({
            "candidate_id": row["candidate_id"],
            "type": row["candidate_type"],
            "predicate": row["predicate"],
            "object": json.loads(row["object_json"]) if row["object_json"] else {},
            "confidence": row["confidence"],
            "explicitness": row["explicitness"],
            "status": row["status"],
            "section_role": row["section_role"],
            "form": row["form"],
            "filing_date": row["filing_date"],
            "snippet": row["snippet"][:200] if row["snippet"] else "",
        })

    conn.close()

    # Generate reasoning
    report = {
        "symbol": symbol,
        "total_candidates": len(candidates),
        "by_level": {k: len(v) for k, v in by_level.items()},
        "reasoning": {
            "promote": [],
            "reject": [],
            "relation": [],
        },
        "samples": by_level,
    }

    # Analyze B candidates (should promote to A or keep B)
    for c in by_level["B"][:5]:  # Top 5 B candidates
        if c["type"] == "company_relation" and c["confidence"] >= 0.9:
            report["reasoning"]["promote"].append({
                "candidate_id": c["candidate_id"],
                "reason": f"High-confidence ({c['confidence']}) company relation with explicit evidence. "
                          f"Form {c['form']} section {c['section_role']}. "
                          f"Evidence: {c['snippet'][:100]}...",
                "recommendation": "keep_B_or_promote_to_A",
            })
        elif c["type"] == "event" and c["confidence"] >= 0.9:
            report["reasoning"]["promote"].append({
                "candidate_id": c["candidate_id"],
                "reason": f"High-confidence event detection from {c['form']}. "
                          f"Explicit 8-K item reference. "
                          f"Evidence: {c['snippet'][:100]}...",
                "recommendation": "keep_B_or_promote_to_A",
            })
        else:
            report["reasoning"]["relation"].append({
                "candidate_id": c["candidate_id"],
                "reason": f"B-level candidate requires relation refinement. "
                          f"Type: {c['type']}, confidence: {c['confidence']}. "
                          f"May need scope or role clarification.",
                "recommendation": "review_relation_scope",
            })

    # Analyze C candidates (need mandatory review)
    for c in by_level["C"][:5]:
        report["reasoning"]["reject"].append({
            "candidate_id": c["candidate_id"],
            "reason": f"C-level: material semantic ambiguity. "
                      f"Type: {c['type']}, predicate: {c['predicate']}. "
                      f"Confidence: {c['confidence']}, explicitness: {c['explicitness']}. "
                      f"Evidence: {c['snippet'][:100]}...",
            "recommendation": "mandatory_review",
        })

    # Analyze D candidates (grouped review)
    for c in by_level["D"][:5]:
        report["reasoning"]["reject"].append({
            "candidate_id": c["candidate_id"],
            "reason": f"D-level: reviewer inference or unresolved scope. "
                      f"Type: {c['type']}, confidence: {c['confidence']}. "
                      f"May be lexical match without semantic grounding.",
            "recommendation": "grouped_review_or_retain_evidence",
        })

    # Analyze R candidates (rejection)
    for c in by_level["R"][:5]:
        report["reasoning"]["reject"].append({
            "candidate_id": c["candidate_id"],
            "reason": f"R-level: deterministic rejection. "
                      f"Type: {c['type']}, rule: {c.get('rule_id', 'unknown')}. "
                      f"Likely self-target, negation, or boilerplate.",
            "recommendation": "reject_with_audit_sample",
        })

    return report


def main():
    # Process batch_01-06
    batches = ["batch_01", "batch_02", "batch_03", "batch_04", "batch_05", "batch_06"]
    all_reports = {}

    for batch in batches:
        db_path = f"data/batches/{batch}/sec_yfinance_structured.db"
        if not Path(db_path).exists():
            continue

        conn = sqlite3.connect(db_path)
        symbols = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM filing").fetchall()]
        conn.close()

        for symbol in symbols:
            if symbol in all_reports:
                continue
            try:
                report = analyze_symbol(symbol, db_path)
                all_reports[symbol] = report
                print(f"Analyzed {symbol}: B={report['by_level']['B']} C={report['by_level']['C']} D={report['by_level']['D']} R={report['by_level']['R']}")
            except Exception as e:
                print(f"Error analyzing {symbol}: {e}")

    # Save reports
    output_dir = Path("data/symbols/reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Individual reports
    for symbol, report in all_reports.items():
        (output_dir / f"{symbol}_review.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    # Summary
    summary = {
        "total_symbols": len(all_reports),
        "total_b": sum(r["by_level"]["B"] for r in all_reports.values()),
        "total_c": sum(r["by_level"]["C"] for r in all_reports.values()),
        "total_d": sum(r["by_level"]["D"] for r in all_reports.values()),
        "total_r": sum(r["by_level"]["R"] for r in all_reports.values()),
        "symbols": list(all_reports.keys()),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8"
    )

    print(f"\nReports saved to {output_dir}")
    print(f"Total symbols: {summary['total_symbols']}")
    print(f"B: {summary['total_b']}, C: {summary['total_c']}, D: {summary['total_d']}, R: {summary['total_r']}")


if __name__ == "__main__":
    main()
