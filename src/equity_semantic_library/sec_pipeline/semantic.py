from __future__ import annotations

import json
import re
from typing import Any, Iterable

from .store import PipelineStore, canonical_json, stable_id, utc_now
from .taxonomy import (
    COMPILED_CONCEPTS, COMPILED_ENTITIES, COMPILED_RELATIONS, COMPILED_TOPICS,
    EVENT_ITEM_MAP, EXTRACTOR_VERSION,
)


def sentence_windows(text: str) -> list[tuple[int, int, str]]:
    out = []
    for match in re.finditer(r"[^.!?;\n]+(?:[.!?;]|$)", text):
        value = re.sub(r"\s+", " ", match.group()).strip()
        if len(value) >= 20:
            out.append((match.start(), match.end(), value))
    return out


def short_evidence(text: str, start: int, end: int, max_chars: int) -> tuple[int, int, str]:
    radius = max(80, max_chars // 3)
    lo, hi = max(0, start - radius), min(len(text), end + radius)
    snippet = re.sub(r"\s+", " ", text[lo:hi]).strip()
    return lo, hi, snippet[:max_chars]


def add_evidence_and_assertion(store: PipelineStore, *, filing: dict[str, Any], section: dict[str, Any], start: int, end: int, predicate: str, object_value: dict[str, Any], assertion_type: str, confidence: float, explicitness: str, max_chars: int, status: str = "accepted") -> tuple[str, str]:
    lo, hi, snippet = short_evidence(section["text"], start, end, max_chars)
    evidence_id = stable_id("evidence", filing["filing_id"], section["section_id"], lo, hi, snippet)
    store.insert_many("evidence_snippet", [{
        "evidence_id": evidence_id, "filing_id": filing["filing_id"], "document_id": section.get("document_id"),
        "section_id": section["section_id"], "source_sha256": filing.get("raw_sha256") or "",
        "snippet": snippet, "snippet_hash": stable_id("snippet", snippet), "char_start": lo, "char_end": hi,
        "accepted_at": filing.get("accepted_at"), "available_at": filing["available_at"],
        "observed_at": filing.get("retrieved_at") or utc_now(), "extractor_version": EXTRACTOR_VERSION,
    }])
    assertion_id = stable_id("assertion", filing["filing_id"], section["section_id"], predicate, canonical_json(object_value), lo)
    store.insert_many("semantic_assertion", [{
        "assertion_id": assertion_id, "security_id": filing.get("security_id"), "filing_id": filing["filing_id"],
        "section_id": section["section_id"], "evidence_id": evidence_id, "assertion_type": assertion_type,
        "subject_key": filing.get("security_id") or filing["symbol"], "predicate": predicate,
        "object_json": canonical_json(object_value), "confidence": confidence, "explicitness": explicitness,
        "status": status, "available_at": filing["available_at"], "effective_from": filing["available_at"],
        "effective_to": None, "extractor_id": "deterministic_rules", "extractor_version": EXTRACTOR_VERSION,
        "created_at": utc_now(),
    }])
    return evidence_id, assertion_id


def extract_topics_and_concepts(store: PipelineStore, filing: dict[str, Any], sections: Iterable[dict[str, Any]], max_chars: int) -> dict[str, int]:
    topic_count = concept_count = relation_count = 0
    for section in sections:
        text = section["text"]
        for name, group, patterns in COMPILED_TOPICS:
            match = next((p.search(text) for p in patterns if p.search(text)), None)
            if match:
                add_evidence_and_assertion(store, filing=filing, section=section, start=match.start(), end=match.end(), predicate="has_topic", object_value={"topic": name, "group": group}, assertion_type="topic", confidence=0.82 if group != "risk" else 0.78, explicitness="explicit", max_chars=max_chars)
                topic_count += 1
        for name, group, patterns in COMPILED_CONCEPTS:
            match = next((p.search(text) for p in patterns if p.search(text)), None)
            if match:
                add_evidence_and_assertion(store, filing=filing, section=section, start=match.start(), end=match.end(), predicate="mentions_concept", object_value={"concept": name, "concept_type": group}, assertion_type="concept", confidence=0.90, explicitness="explicit", max_chars=max_chars)
                concept_count += 1
        for sent_start, sent_end, sentence in sentence_windows(text):
            relation_type = next((kind for kind, patterns in COMPILED_RELATIONS if any(p.search(sentence) for p in patterns)), None)
            if not relation_type or not re.search(r"(?i)\b(we|our|us)\b", sentence):
                continue
            for entity_name, ticker, patterns in COMPILED_ENTITIES:
                if ticker and ticker.upper() == str(filing.get("symbol") or "").upper():
                    continue
                entity_match = next((p.search(sentence) for p in patterns if p.search(sentence)), None)
                if not entity_match:
                    continue
                evidence_id, _ = add_evidence_and_assertion(store, filing=filing, section=section, start=sent_start, end=sent_end, predicate="has_company_relation", object_value={"target_entity": entity_name, "target_ticker": ticker, "relation_type": relation_type}, assertion_type="company_relation", confidence=0.88, explicitness="explicit", max_chars=max_chars)
                store.insert_many("company_relation", [{
                    "relation_id": stable_id("relation", filing["filing_id"], section["section_id"], entity_name, relation_type, sent_start),
                    "source_issuer_id": filing["issuer_id"], "target_entity_key": entity_name, "target_ticker": ticker,
                    "relation_type": relation_type, "product_scope": None, "filing_id": filing["filing_id"],
                    "section_id": section["section_id"], "evidence_id": evidence_id, "confidence": 0.88,
                    "explicitness": "explicit", "status": "accepted", "available_at": filing["available_at"],
                    "effective_from": filing["available_at"], "effective_to": None,
                    "extractor_version": EXTRACTOR_VERSION, "created_at": utc_now(),
                }])
                relation_count += 1
    return {"topics": topic_count, "concepts": concept_count, "relations": relation_count}


def extract_8k_events(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int) -> int:
    count = 0
    for section in sections:
        item = section.get("item") or ""
        if item not in EVENT_ITEM_MAP:
            continue
        event_type = EVENT_ITEM_MAP[item]
        evidence_id, _ = add_evidence_and_assertion(store, filing=filing, section=section, start=0, end=min(len(section["text"]), 300), predicate="reported_event", object_value={"event_type": event_type, "item": item, "title": section.get("title")}, assertion_type="event", confidence=0.97, explicitness="explicit", max_chars=max_chars)
        store.insert_many("event_ledger", [{
            "event_id": stable_id("event", filing["filing_id"], item, event_type),
            "filing_id": filing["filing_id"], "security_id": filing.get("security_id"), "symbol": filing["symbol"],
            "event_type": event_type, "item": item, "event_time": filing["available_at"],
            "event_time_precision": filing["available_at_precision"], "title": section.get("title"),
            "payload_json": canonical_json({"evidence_id": evidence_id, "form": filing["form"]}),
            "confidence": 0.97, "extractor_version": EXTRACTOR_VERSION,
        }])
        count += 1
    return count


def extract_13f_relations(store: PipelineStore, filing: dict[str, Any]) -> int:
    holdings = store.query("SELECT * FROM form13f_holding WHERE filing_id=?", (filing["filing_id"],))
    if not holdings:
        return 0
    rows = store.query("SELECT * FROM filing_section WHERE filing_id=? ORDER BY ordinal LIMIT 1", (filing["filing_id"],))
    section = rows[0] if rows else None
    count = 0
    for holding in holdings:
        snippet = f"13F information table: {holding.get('issuer_name')} | {holding.get('class_title')} | CUSIP {holding.get('cusip')} | value USD {holding.get('value_usd')} | shares {holding.get('shares_or_principal')}"
        evidence_id = stable_id("evidence", filing["filing_id"], holding["holding_id"], snippet)
        store.insert_many("evidence_snippet", [{
            "evidence_id": evidence_id, "filing_id": filing["filing_id"],
            "document_id": section.get("document_id") if section else None,
            "section_id": section.get("section_id") if section else None,
            "source_sha256": filing.get("raw_sha256") or "", "snippet": snippet,
            "snippet_hash": stable_id("snippet", snippet), "char_start": None, "char_end": None,
            "accepted_at": filing.get("accepted_at"), "available_at": filing["available_at"],
            "observed_at": filing.get("retrieved_at") or utc_now(), "extractor_version": EXTRACTOR_VERSION,
        }])
        target = holding.get("issuer_name") or holding.get("cusip") or "unknown"
        store.insert_many("company_relation", [{
            "relation_id": stable_id("13f_relation", filing["filing_id"], holding["holding_id"]),
            "source_issuer_id": filing["issuer_id"], "target_entity_key": target, "target_ticker": None,
            "relation_type": "investment_or_holding", "product_scope": holding.get("class_title"),
            "filing_id": filing["filing_id"], "section_id": section.get("section_id") if section else None,
            "evidence_id": evidence_id, "confidence": 0.995, "explicitness": "explicit", "status": "accepted",
            "available_at": filing["available_at"], "effective_from": filing.get("report_date") or filing["available_at"],
            "effective_to": None, "extractor_version": EXTRACTOR_VERSION, "created_at": utc_now(),
        }])
        count += 1
    return count


def _extract_pattern_semantics(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int, *, predicate: str, assertion_type: str, confidence: float, patterns: dict[str, str]) -> int:
    count = 0
    for section in sections:
        for topic, pattern in patterns.items():
            match = re.search(pattern, section["text"], re.I)
            if match:
                add_evidence_and_assertion(store, filing=filing, section=section, start=match.start(), end=match.end(), predicate=predicate, object_value={"topic": topic}, assertion_type=assertion_type, confidence=confidence, explicitness="explicit", max_chars=max_chars)
                count += 1
    return count


def extract_proxy_semantics(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int) -> int:
    return _extract_pattern_semantics(store, filing, sections, max_chars, predicate="proxy_topic", assertion_type="governance", confidence=0.90, patterns={
        "say_on_pay": r"say[- ]on[- ]pay|advisory vote on executive compensation",
        "director_election": r"election of directors?|nominees? for director",
        "auditor_ratification": r"ratif(?:y|ication).*independent registered public accounting firm",
        "equity_plan": r"equity incentive plan|stock incentive plan",
        "related_party_transactions": r"related person transactions?|related party transactions?",
    })


def extract_regulatory_semantics(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int) -> int:
    return _extract_pattern_semantics(store, filing, sections, max_chars, predicate="regulatory_topic", assertion_type="regulatory", confidence=0.88, patterns={
        "conflict_minerals": r"conflict minerals?|tantalum|tin|tungsten|gold|covered countries|Democratic Republic of the Congo",
        "sec_comment": r"comment letter|response to the staff|Division of Corporation Finance|we respectfully submit",
        "disclosure_commitment": r"in future filings|we will revise|we propose to revise|undertakes? to",
    })


def extract_offering_semantics(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int) -> int:
    return _extract_pattern_semantics(store, filing, sections, max_chars, predicate="capital_markets_topic", assertion_type="capital_markets", confidence=0.90, patterns={
        "common_stock": r"common stock", "preferred_stock": r"preferred stock",
        "debt_securities": r"debt securities|senior notes|convertible notes",
        "use_of_proceeds": r"use of proceeds", "plan_of_distribution": r"plan of distribution", "dilution": r"dilution",
    })
