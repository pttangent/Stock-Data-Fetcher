from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .semantic_records import promote_candidate
from .store import PipelineStore, canonical_json, stable_id, utc_now

REVIEW_CONTRACT_VERSION = "sec-semantic-review-v3"
_ALLOWED_DECISIONS = {"accept", "reject", "change", "ambiguous"}
_DEFAULT_LEVELS = ("B", "C", "D", "R")
_DEFAULT_STATUSES = ("rule_accepted", "review_required", "rejected")


def export_review_queue(
    store: PipelineStore,
    output: str | Path,
    *,
    limit: int | None = None,
    statuses: tuple[str, ...] | None = None,
    levels: tuple[str, ...] | None = None,
    include_reviewed: bool = False,
    dedupe_evidence: bool = True,
) -> dict[str, Any]:
    statuses = tuple(dict.fromkeys(statuses or _DEFAULT_STATUSES))
    levels = tuple(dict.fromkeys(levels or _DEFAULT_LEVELS))
    status_placeholders = ",".join("?" for _ in statuses)
    level_placeholders = ",".join("?" for _ in levels)
    reviewed_clause = "" if include_reviewed else (
        "AND NOT EXISTS (SELECT 1 FROM semantic_review r WHERE r.candidate_id=c.candidate_id)"
    )
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
    WHERE c.status IN ({status_placeholders})
      AND c.promotion_level IN ({level_placeholders})
      {reviewed_clause}
    ORDER BY c.available_at, e.snippet_hash, c.candidate_id
    """
    params: list[Any] = [*statuses, *levels]
    rows = store.query(sql, tuple(params))

    grouped: list[list[dict[str, Any]]] = []
    if dedupe_evidence:
        buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
        order: list[tuple[str, str]] = []
        for row in rows:
            key = (row["issuer_id"], row["snippet_hash"])
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(row)
        grouped = [buckets[key] for key in order]
    else:
        grouped = [[row] for row in rows]

    if limit is not None:
        grouped = grouped[: max(0, int(limit))]

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for group in grouped:
            first = group[0]
            candidate_count += len(group)
            payload = {
                "contract_version": REVIEW_CONTRACT_VERSION,
                "review_unit_id": stable_id(
                    "review-unit",
                    first["issuer_id"],
                    first["snippet_hash"],
                    *sorted(row["candidate_id"] for row in group),
                ),
                "issuer": {
                    "issuer_id": first["issuer_id"],
                    "legal_name": first.get("legal_name"),
                    "symbols": [
                        item
                        for item in str(first.get("issuer_symbols") or "").split(",")
                        if item
                    ],
                },
                "filing_instances": [
                    {
                        "filing_id": row["filing_id"],
                        "accession": row.get("accession"),
                        "form": row.get("form"),
                        "base_form": row.get("base_form"),
                        "report_date": row.get("report_date"),
                        "available_at": row["available_at"],
                        "item": row.get("item"),
                        "title": row.get("title"),
                        "section_role": row["section_role"],
                    }
                    for row in {
                        item["filing_id"]: item
                        for item in group
                    }.values()
                ],
                "candidates": [
                    {
                        "candidate_id": row["candidate_id"],
                        "filing_id": row["filing_id"],
                        "evidence_id": row["evidence_id"],
                        "available_at": row["available_at"],
                        "candidate_type": row["candidate_type"],
                        "predicate": row["predicate"],
                        "object": json.loads(row["object_json"]),
                        "confidence": row["confidence"],
                        "promotion_level": row["promotion_level"],
                        "status": row["status"],
                        "subject_binding": row["subject_binding"],
                        "polarity": row["polarity"],
                        "modality": row["modality"],
                        "rule_id": row["rule_id"],
                        "rejection_reason": row.get("rejection_reason"),
                    }
                    for row in group
                ],
                "evidence": {
                    "snippet": first["snippet"],
                    "snippet_hash": first["snippet_hash"],
                    "instance_count": len(
                        {
                            row["evidence_id"]
                            for row in group
                        }
                    ),
                },
                "evidence_instances": [
                    {
                        "evidence_id": row["evidence_id"],
                        "filing_id": row["filing_id"],
                        "source_sha256": row["source_sha256"],
                        "accepted_at": row.get("accepted_at"),
                        "available_at": row["available_at"],
                        "observed_at": row.get("observed_at"),
                    }
                    for row in {
                        item["evidence_id"]: item
                        for item in group
                    }.values()
                ],
                "allowed_output": {
                    "one_decision_per_candidate": True,
                    "decision": ["accept", "reject", "change", "ambiguous"],
                    "may_change": ["predicate", "object"],
                    "must_not_change": ["candidate_id", "evidence_id", "available_at"],
                    "must_not_add_entities_absent_from_evidence": True,
                },
            }
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "output": str(path),
        "review_units": len(grouped),
        "candidate_count": candidate_count,
        "contract_version": REVIEW_CONTRACT_VERSION,
        "levels": list(levels),
        "statuses": list(statuses),
        "dedupe_evidence": dedupe_evidence,
        "include_reviewed": include_reviewed,
    }


def _same_issuer_target(
    store: PipelineStore,
    issuer_id: str,
    target_ticker: str | None,
) -> bool:
    if not target_ticker:
        return False
    rows = store.query(
        "SELECT issuer_id FROM security WHERE symbol=?",
        (target_ticker.upper(),),
    )
    return bool(rows and rows[0]["issuer_id"] == issuer_id)


def _existing_outputs(
    store: PipelineStore,
    candidate_id: str,
) -> list[dict[str, Any]]:
    return store.query(
        """SELECT p.promotion_id,p.assertion_id,p.relation_id,p.method,
                  a.status AS assertion_status,r.status AS relation_status
           FROM candidate_promotion p
           LEFT JOIN semantic_assertion a ON a.assertion_id=p.assertion_id
           LEFT JOIN company_relation r ON r.relation_id=p.relation_id
           WHERE p.candidate_id=?
           ORDER BY p.promoted_at""",
        (candidate_id,),
    )


def _supersede_existing_outputs(
    store: PipelineStore,
    candidate_id: str,
) -> None:
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """UPDATE semantic_assertion SET status='superseded'
               WHERE assertion_id IN (
                 SELECT assertion_id FROM candidate_promotion
                 WHERE candidate_id=? AND assertion_id IS NOT NULL
               ) AND status='accepted'""",
            (candidate_id,),
        )
        conn.execute(
            """UPDATE company_relation SET status='superseded'
               WHERE relation_id IN (
                 SELECT relation_id FROM candidate_promotion
                 WHERE candidate_id=? AND relation_id IS NOT NULL
               ) AND status='accepted'""",
            (candidate_id,),
        )
        conn.commit()


def _record_review_confirmation(
    store: PipelineStore,
    *,
    candidate_id: str,
    review_id: str,
    reviewer_type: str,
    reviewer_id: str,
    outputs: list[dict[str, Any]],
) -> None:
    now = utc_now()
    rows = []
    for output in outputs:
        if (
            output.get("assertion_status") != "accepted"
            and output.get("relation_status") != "accepted"
        ):
            continue
        method = f"{reviewer_type}_review_confirm:{reviewer_id}"
        rows.append(
            {
                "promotion_id": stable_id(
                    "promotion-confirmation",
                    candidate_id,
                    output.get("assertion_id"),
                    output.get("relation_id"),
                    review_id,
                ),
                "candidate_id": candidate_id,
                "assertion_id": output.get("assertion_id"),
                "relation_id": output.get("relation_id"),
                "method": method,
                "review_id": review_id,
                "promoted_at": now,
            }
        )
    store.insert_many("candidate_promotion", rows)


def _relation_from_review(
    store: PipelineStore,
    candidate: dict[str, Any],
    object_value: dict[str, Any],
) -> dict[str, Any] | None:
    if candidate["candidate_type"] != "company_relation":
        return None
    if candidate["polarity"] != "positive" or candidate["modality"] != "actual":
        raise ValueError(
            "review cannot promote a negative, hypothetical, possible, "
            "or planned relation as an actual company relation"
        )
    target_ticker = object_value.get("target_ticker")
    if _same_issuer_target(store, candidate["issuer_id"], target_ticker):
        raise ValueError("review cannot promote a self-target company relation")
    relation = {
        "target_entity_key": (
            object_value.get("target_entity")
            or object_value.get("target_entity_key")
        ),
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
        raise ValueError(
            "review cannot add a relation target absent from the evidence snippet"
        )
    return relation


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
    counts: dict[str, Any] = {
        "accepted": 0,
        "confirmed_existing": 0,
        "rejected": 0,
        "changed": 0,
        "ambiguous": 0,
        "superseded_outputs": 0,
        "errors": 0,
    }
    for line_number, line in enumerate(
        Path(input_path).read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not line.strip():
            continue
        try:
            decision_row = json.loads(line)
            candidate_id = str(decision_row["candidate_id"])
            decision = str(decision_row["decision"]).lower()
            if decision not in _ALLOWED_DECISIONS:
                raise ValueError(f"unsupported decision {decision}")
            candidates = store.query(
                """SELECT c.*,e.snippet,e.snippet_hash,
                          e.available_at AS evidence_available_at,
                          f.issuer_id,f.security_id AS filing_security_id,
                          f.symbol,f.accession,f.accepted_at,f.retrieved_at,
                          f.raw_sha256,fs.document_id,fs.text,fs.section_id
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
            predicate = str(
                decision_row.get("corrected_predicate") or candidate["predicate"]
            )
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
                "promotion_level": candidate["promotion_level"],
                "status": candidate["status"],
            }
            input_hash = hashlib.sha256(
                canonical_json(decision_row).encode()
            ).hexdigest()
            review_id = stable_id(
                "review",
                candidate_id,
                reviewer_type,
                reviewer_id,
                reviewer_version,
                input_hash,
            )
            store.insert_many(
                "semantic_review",
                [
                    {
                        "review_id": review_id,
                        "candidate_id": candidate_id,
                        "candidate_snapshot_json": canonical_json(snapshot),
                        "reviewer_type": reviewer_type,
                        "reviewer_id": reviewer_id,
                        "reviewer_version": reviewer_version,
                        "decision": decision,
                        "corrected_predicate": (
                            predicate if decision == "change" else None
                        ),
                        "corrected_object_json": (
                            canonical_json(object_value)
                            if decision == "change"
                            else None
                        ),
                        "rationale": rationale,
                        "input_hash": input_hash,
                        "reviewed_at": utc_now(),
                    }
                ],
            )

            existing_outputs = _existing_outputs(store, candidate_id)
            relation = None
            if decision in {"accept", "change"}:
                relation = _relation_from_review(store, candidate, object_value)

            if decision == "accept" and existing_outputs:
                _record_review_confirmation(
                    store,
                    candidate_id=candidate_id,
                    review_id=review_id,
                    reviewer_type=reviewer_type,
                    reviewer_id=reviewer_id,
                    outputs=existing_outputs,
                )
                with store.connect() as conn:
                    conn.execute(
                        "UPDATE semantic_candidate "
                        "SET status='review_accepted' WHERE candidate_id=?",
                        (candidate_id,),
                    )
                counts["accepted"] += 1
                counts["confirmed_existing"] += 1
                continue

            if decision == "change" and existing_outputs:
                accepted_outputs = sum(
                    int(output.get("assertion_status") == "accepted")
                    + int(output.get("relation_status") == "accepted")
                    for output in existing_outputs
                )
                _supersede_existing_outputs(store, candidate_id)
                counts["superseded_outputs"] += accepted_outputs

            if decision in {"accept", "change"}:
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
                section = (
                    {
                        "section_id": candidate.get("section_id"),
                        "document_id": candidate.get("document_id"),
                    }
                    if candidate.get("section_id")
                    else None
                )
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
                    explicitness=(
                        "inferred" if reviewer_type == "llm" else "explicit"
                    ),
                    method=f"{reviewer_type}_review:{reviewer_id}",
                    relation=relation,
                    review_id=review_id,
                )
                with store.connect() as conn:
                    conn.execute(
                        "UPDATE semantic_candidate "
                        "SET status='review_accepted' WHERE candidate_id=?",
                        (candidate_id,),
                    )
                counts["changed" if decision == "change" else "accepted"] += 1
            elif decision == "reject":
                accepted_outputs = sum(
                    int(output.get("assertion_status") == "accepted")
                    + int(output.get("relation_status") == "accepted")
                    for output in existing_outputs
                )
                if existing_outputs:
                    _supersede_existing_outputs(store, candidate_id)
                    counts["superseded_outputs"] += accepted_outputs
                with store.connect() as conn:
                    conn.execute(
                        "UPDATE semantic_candidate "
                        "SET status='rejected',rejection_reason=? "
                        "WHERE candidate_id=?",
                        (f"review:{rationale[:500]}", candidate_id),
                    )
                counts["rejected"] += 1
            else:
                counts["ambiguous"] += 1
        except Exception as exc:
            counts["errors"] += 1
            counts.setdefault("error_details", []).append(
                {"line": line_number, "error": str(exc)}
            )
    return counts
