from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .semantic_records import promote_candidate
from .store import PipelineStore, canonical_json, stable_id, utc_now

REVIEW_CONTRACT_VERSION = "sec-semantic-review-v1"
_ALLOWED_DECISIONS = {"accept", "reject", "change", "ambiguous"}


def export_review_queue(
    store: PipelineStore,
    output: str | Path,
    *,
    limit: int | None = None,
    statuses: tuple[str, ...] = ("review_required",),
) -> dict[str, Any]:
    placeholders = ",".join("?" for _ in statuses)
    sql = f"""
    SELECT c.*, e.snippet, e.snippet_hash, e.source_sha256, e.accepted_at,
           e.observed_at, f.accession, f.base_form, f.report_date,
           i.legal_name, fs.item, fs.title,
           (SELECT GROUP_CONCAT(symbol, ',') FROM security s WHERE s.issuer_id=c.issuer_id) AS issuer_symbols
    FROM semantic_candidate c
    JOIN evidence_snippet e ON e.evidence_id=c.evidence_id
    JOIN filing f ON f.filing_id=c.filing_id
    JOIN issuer i ON i.issuer_id=c.issuer_id
    LEFT JOIN filing_section fs ON fs.section_id=c.section_id
    WHERE c.status IN ({placeholders})
    ORDER BY c.available_at, c.candidate_id
    """
    params: list[Any] = list(statuses)
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = store.query(sql, tuple(params))
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            payload = {
                "contract_version": REVIEW_CONTRACT_VERSION,
                "candidate_id": row["candidate_id"],
                "issuer": {
                    "issuer_id": row["issuer_id"],
                    "legal_name": row.get("legal_name"),
                    "symbols": [item for item in str(row.get("issuer_symbols") or "").split(",") if item],
                },
                "filing": {
                    "filing_id": row["filing_id"],
                    "accession": row.get("accession"),
                    "form": row.get("form"),
                    "base_form": row.get("base_form"),
                    "report_date": row.get("report_date"),
                    "available_at": row["available_at"],
                    "item": row.get("item"),
                    "title": row.get("title"),
                    "section_role": row["section_role"],
                },
                "candidate": {
                    "candidate_type": row["candidate_type"],
                    "predicate": row["predicate"],
                    "object": json.loads(row["object_json"]),
                    "confidence": row["confidence"],
                    "promotion_level": row["promotion_level"],
                    "subject_binding": row["subject_binding"],
                    "polarity": row["polarity"],
                    "modality": row["modality"],
                    "rule_id": row["rule_id"],
                    "rejection_reason": row.get("rejection_reason"),
                },
                "evidence": {
                    "evidence_id": row["evidence_id"],
                    "snippet": row["snippet"],
                    "snippet_hash": row["snippet_hash"],
                    "source_sha256": row["source_sha256"],
                    "accepted_at": row.get("accepted_at"),
                    "available_at": row["available_at"],
                    "observed_at": row.get("observed_at"),
                },
                "allowed_output": {
                    "decision": ["accept", "reject", "change", "ambiguous"],
                    "may_change": ["predicate", "object"],
                    "must_not_change": ["candidate_id", "evidence_id", "available_at"],
                    "must_not_add_entities_absent_from_evidence": True,
                },
            }
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return {"output": str(path), "count": len(rows), "contract_version": REVIEW_CONTRACT_VERSION}


def _same_issuer_target(store: PipelineStore, issuer_id: str, target_ticker: str | None) -> bool:
    if not target_ticker:
        return False
    rows = store.query("SELECT issuer_id FROM security WHERE symbol=?", (target_ticker.upper(),))
    return bool(rows and rows[0]["issuer_id"] == issuer_id)


def import_review_decisions(
    store: PipelineStore,
    input_path: str | Path,
    *,
    reviewer_type: str,
    reviewer_id: str,
    reviewer_version: str | None = None,
) -> dict[str, Any]:
    if reviewer_type not in {"llm", "human"}:
        raise ValueError("reviewer_type must be llm or human")
    counts: dict[str, Any] = {"accepted": 0, "rejected": 0, "changed": 0, "ambiguous": 0, "errors": 0}
    for line_number, line in enumerate(Path(input_path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            decision_row = json.loads(line)
            candidate_id = str(decision_row["candidate_id"])
            decision = str(decision_row["decision"]).lower()
            if decision not in _ALLOWED_DECISIONS:
                raise ValueError(f"unsupported decision {decision}")
            candidates = store.query(
                """SELECT c.*,e.snippet,e.snippet_hash,e.available_at AS evidence_available_at,
                          f.issuer_id,f.security_id AS filing_security_id,f.symbol,f.accession,
                          f.accepted_at,f.retrieved_at,f.raw_sha256,
                          fs.document_id,fs.text,fs.section_id
                   FROM semantic_candidate c
                   JOIN evidence_snippet e ON e.evidence_id=c.evidence_id
                   JOIN filing f ON f.filing_id=c.filing_id
                   LEFT JOIN filing_section fs ON fs.section_id=c.section_id
                   WHERE c.candidate_id=?""",
                (candidate_id,),
            )
            if not candidates:
                raise LookupError(f"candidate not found: {candidate_id}")
            candidate = candidates[0]
            predicate = str(decision_row.get("corrected_predicate") or candidate["predicate"])
            object_value = decision_row.get("corrected_object")
            if object_value is None:
                object_value = json.loads(candidate["object_json"])
            rationale = str(decision_row.get("rationale") or "").strip()
            if not rationale:
                raise ValueError("rationale is required")
            snapshot = {
                "candidate_id": candidate_id,
                "predicate": candidate["predicate"],
                "object": json.loads(candidate["object_json"]),
                "evidence_id": candidate["evidence_id"],
                "snippet_hash": candidate["snippet_hash"],
                "available_at": candidate["available_at"],
            }
            input_hash = hashlib.sha256(canonical_json(decision_row).encode()).hexdigest()
            review_id = stable_id("review", candidate_id, reviewer_type, reviewer_id, reviewer_version, input_hash)
            store.insert_many("semantic_review", [{
                "review_id": review_id,
                "candidate_id": candidate_id,
                "candidate_snapshot_json": canonical_json(snapshot),
                "reviewer_type": reviewer_type,
                "reviewer_id": reviewer_id,
                "reviewer_version": reviewer_version,
                "decision": decision,
                "corrected_predicate": predicate if decision == "change" else None,
                "corrected_object_json": canonical_json(object_value) if decision == "change" else None,
                "rationale": rationale,
                "input_hash": input_hash,
                "reviewed_at": utc_now(),
            }])
            if decision in {"accept", "change"}:
                if candidate["candidate_type"] == "company_relation":
                    if candidate["polarity"] != "positive" or candidate["modality"] != "actual":
                        raise ValueError("review cannot promote a negative, hypothetical, possible, or planned relation as an actual company relation")
                    target_ticker = object_value.get("target_ticker")
                    if _same_issuer_target(store, candidate["issuer_id"], target_ticker):
                        raise ValueError("review cannot promote a self-target company relation")
                    relation = {
                        "target_entity_key": object_value.get("target_entity") or object_value.get("target_entity_key"),
                        "target_ticker": target_ticker,
                        "relation_type": object_value.get("relation_type"),
                        "product_scope": object_value.get("product_scope"),
                    }
                    if not relation["target_entity_key"] or not relation["relation_type"]:
                        raise ValueError("company relation requires target entity and relation type")
                    evidence_lower = str(candidate["snippet"]).lower()
                    target_tokens = [str(relation["target_entity_key"]).lower()]
                    if target_ticker:
                        target_tokens.append(str(target_ticker).lower())
                    if not any(token and token in evidence_lower for token in target_tokens):
                        raise ValueError("review cannot add a relation target absent from the evidence snippet")
                else:
                    relation = None
                filing = {
                    "filing_id": candidate["filing_id"],
                    "issuer_id": candidate["issuer_id"],
                    "security_id": candidate.get("filing_security_id"),
                    "symbol": candidate["symbol"],
                    "accession": candidate["accession"],
                    "available_at": candidate["available_at"],
                    "accepted_at": candidate.get("accepted_at"),
                    "retrieved_at": candidate.get("retrieved_at"),
                    "raw_sha256": candidate.get("raw_sha256"),
                }
                section = {"section_id": candidate.get("section_id"), "document_id": candidate.get("document_id")} if candidate.get("section_id") else None
                promote_candidate(
                    store,
                    candidate_id=candidate_id,
                    filing=filing,
                    section=section,
                    evidence_id=candidate["evidence_id"],
                    predicate=predicate,
                    object_value=object_value,
                    candidate_type=candidate["candidate_type"],
                    confidence=max(float(candidate["confidence"]), 0.85),
                    explicitness="inferred" if reviewer_type == "llm" else "explicit",
                    method=f"{reviewer_type}_review:{reviewer_id}",
                    relation=relation,
                    review_id=review_id,
                )
                with store.connect() as conn:
                    conn.execute("UPDATE semantic_candidate SET status='review_accepted' WHERE candidate_id=?", (candidate_id,))
                counts["changed" if decision == "change" else "accepted"] += 1
            elif decision == "reject":
                with store.connect() as conn:
                    conn.execute(
                        "UPDATE semantic_candidate SET status='rejected',rejection_reason=? WHERE candidate_id=?",
                        (f"review:{rationale[:500]}", candidate_id),
                    )
                counts["rejected"] += 1
            else:
                counts["ambiguous"] += 1
        except Exception as exc:
            counts["errors"] += 1
            counts.setdefault("error_details", []).append({"line": line_number, "error": str(exc)})
    return counts
