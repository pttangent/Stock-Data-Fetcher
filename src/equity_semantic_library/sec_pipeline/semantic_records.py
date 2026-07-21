from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .store import PipelineStore, canonical_json, stable_id, utc_now
from .taxonomy import EXTRACTOR_VERSION


@dataclass(frozen=True)
class CandidateDecision:
    promote: bool
    level: str
    status: str
    explicitness: str
    subject_binding: str = "not_applicable"
    polarity: str = "positive"
    modality: str = "actual"
    rejection_reason: str | None = None


def short_evidence(text: str, start: int, end: int, max_chars: int) -> tuple[int, int, str]:
    radius = max(80, max_chars // 3)
    lo, hi = max(0, start - radius), min(len(text), end + radius)
    snippet = " ".join(text[lo:hi].split())
    return lo, hi, snippet[:max_chars]


def record_candidate(
    store: PipelineStore,
    *,
    filing: dict[str, Any],
    section: dict[str, Any],
    section_role: str,
    start: int,
    end: int,
    predicate: str,
    object_value: dict[str, Any],
    candidate_type: str,
    confidence: float,
    decision: CandidateDecision,
    rule_id: str,
    max_chars: int,
    relation: dict[str, Any] | None = None,
) -> tuple[str, str, str | None, str | None]:
    lo, hi, snippet = short_evidence(section["text"], start, end, max_chars)
    object_json = canonical_json(object_value)
    evidence_id = stable_id("evidence", filing["filing_id"], section["section_id"], lo, hi, snippet)
    store.insert_many("evidence_snippet", [{
        "evidence_id": evidence_id,
        "filing_id": filing["filing_id"],
        "document_id": section.get("document_id"),
        "section_id": section["section_id"],
        "source_sha256": filing.get("raw_sha256") or "",
        "snippet": snippet,
        "snippet_hash": stable_id("snippet", snippet),
        "char_start": lo,
        "char_end": hi,
        "accepted_at": filing.get("accepted_at"),
        "available_at": filing["available_at"],
        "observed_at": filing.get("retrieved_at") or utc_now(),
        "extractor_version": EXTRACTOR_VERSION,
    }])
    candidate_id = stable_id("candidate", evidence_id, predicate, object_json, rule_id)
    store.insert_many("semantic_candidate", [{
        "candidate_id": candidate_id,
        "issuer_id": filing["issuer_id"],
        "security_id": None,
        "filing_id": filing["filing_id"],
        "section_id": section["section_id"],
        "evidence_id": evidence_id,
        "candidate_type": candidate_type,
        "predicate": predicate,
        "object_json": object_json,
        "confidence": confidence,
        "explicitness": decision.explicitness,
        "status": decision.status,
        "promotion_level": decision.level,
        "form": filing["form"],
        "section_role": section_role,
        "rule_id": rule_id,
        "rule_version": EXTRACTOR_VERSION,
        "subject_binding": decision.subject_binding,
        "polarity": decision.polarity,
        "modality": decision.modality,
        "rejection_reason": decision.rejection_reason,
        "available_at": filing["available_at"],
        "created_at": utc_now(),
    }])
    if not decision.promote:
        return evidence_id, candidate_id, None, None
    assertion_id, relation_id = promote_candidate(
        store,
        candidate_id=candidate_id,
        filing=filing,
        section=section,
        evidence_id=evidence_id,
        predicate=predicate,
        object_value=object_value,
        candidate_type=candidate_type,
        confidence=confidence,
        explicitness="explicit" if decision.explicitness in {"explicit", "structured"} else "inferred",
        method="deterministic_rule",
        relation=relation,
    )
    return evidence_id, candidate_id, assertion_id, relation_id


def promote_candidate(
    store: PipelineStore,
    *,
    candidate_id: str,
    filing: dict[str, Any],
    section: dict[str, Any] | None,
    evidence_id: str,
    predicate: str,
    object_value: dict[str, Any],
    candidate_type: str,
    confidence: float,
    explicitness: str,
    method: str,
    relation: dict[str, Any] | None = None,
    review_id: str | None = None,
) -> tuple[str, str | None]:
    assertion_id = stable_id("assertion", candidate_id, predicate, canonical_json(object_value), method)
    store.insert_many("semantic_assertion", [{
        "assertion_id": assertion_id,
        "security_id": None,
        "filing_id": filing["filing_id"],
        "section_id": section.get("section_id") if section else None,
        "evidence_id": evidence_id,
        "assertion_type": candidate_type,
        "subject_key": filing["issuer_id"],
        "predicate": predicate,
        "object_json": canonical_json(object_value),
        "confidence": confidence,
        "explicitness": explicitness,
        "status": "accepted",
        "available_at": filing["available_at"],
        "effective_from": filing["available_at"],
        "effective_to": None,
        "extractor_id": method,
        "extractor_version": EXTRACTOR_VERSION,
        "created_at": utc_now(),
    }])
    relation_id = None
    if relation:
        relation_id = stable_id("relation", candidate_id, relation["target_entity_key"], relation["relation_type"])
        store.insert_many("company_relation", [{
            "relation_id": relation_id,
            "source_issuer_id": filing["issuer_id"],
            "target_entity_key": relation["target_entity_key"],
            "target_ticker": relation.get("target_ticker"),
            "relation_type": relation["relation_type"],
            "product_scope": relation.get("product_scope"),
            "filing_id": filing["filing_id"],
            "section_id": section.get("section_id") if section else None,
            "evidence_id": evidence_id,
            "confidence": confidence,
            "explicitness": explicitness,
            "status": "accepted",
            "available_at": filing["available_at"],
            "effective_from": filing["available_at"],
            "effective_to": None,
            "extractor_version": EXTRACTOR_VERSION,
            "created_at": utc_now(),
        }])
    promotion_id = stable_id("promotion", candidate_id, assertion_id, relation_id, method, review_id)
    store.insert_many("candidate_promotion", [{
        "promotion_id": promotion_id,
        "candidate_id": candidate_id,
        "assertion_id": assertion_id,
        "relation_id": relation_id,
        "method": method,
        "review_id": review_id,
        "promoted_at": utc_now(),
    }])
    return assertion_id, relation_id
