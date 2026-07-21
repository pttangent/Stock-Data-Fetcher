from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from .semantic_policy import SectionContext, classify_section, concept_promotion, relation_promotion, topic_promotion
from .semantic_records import CandidateDecision, promote_candidate, record_candidate
from .store import PipelineStore, canonical_json, stable_id, utc_now
from .taxonomy import (
    COMPILED_CONCEPTS,
    COMPILED_ENTITIES,
    COMPILED_LOOSE_RELATIONS,
    COMPILED_STRICT_RELATIONS,
    COMPILED_TOPICS,
    CONCEPT_OWNERS,
    EVENT_ITEM_MAP,
    EXTRACTOR_VERSION,
)


def sentence_windows(text: str) -> list[tuple[int, int, str]]:
    out = []
    for match in re.finditer(r"[^.!?;\n]+(?:[.!?;]|$)", text):
        value = re.sub(r"\s+", " ", match.group()).strip()
        if len(value) >= 20:
            out.append((match.start(), match.end(), value))
    return out


def _section_context(store: PipelineStore, filing: dict[str, Any], section: dict[str, Any]) -> SectionContext:
    context = classify_section(filing, section)
    store.insert_many("section_semantic_context", [context.as_row(filing, section)], replace=True)
    return context


def _issuer_symbols(store: PipelineStore, issuer_id: str) -> set[str]:
    return {str(row["symbol"]).upper() for row in store.query("SELECT symbol FROM security WHERE issuer_id=?", (issuer_id,))}


def _concept_owned(store: PipelineStore, filing: dict[str, Any], concept: str) -> bool:
    owners = CONCEPT_OWNERS.get(concept)
    if not owners:
        return False
    symbols = _issuer_symbols(store, filing["issuer_id"]) or {str(filing.get("symbol") or "").upper()}
    return bool(symbols & set(owners))


def _self_target(store: PipelineStore, filing: dict[str, Any], entity_name: str, ticker: str | None) -> bool:
    if ticker:
        rows = store.query("SELECT issuer_id FROM security WHERE symbol=?", (ticker.upper(),))
        if rows and rows[0]["issuer_id"] == filing["issuer_id"]:
            return True
        if ticker.upper() in _issuer_symbols(store, filing["issuer_id"]):
            return True
    issuer = store.query("SELECT legal_name FROM issuer WHERE issuer_id=?", (filing["issuer_id"],))
    legal_name = re.sub(r"[^a-z0-9]+", " ", str(issuer[0].get("legal_name") or "").lower()).strip() if issuer else ""
    target = re.sub(r"[^a-z0-9]+", " ", entity_name.lower()).strip()
    return bool(legal_name and target and (target in legal_name or legal_name in target))


def _polarity_modality(sentence: str, relation_start: int) -> tuple[str, str]:
    prefix = sentence[max(0, relation_start - 80):relation_start].lower()
    polarity = "negative" if re.search(r"\b(?:not|never|no longer|do not|does not|did not)\b", prefix) else "positive"
    if re.search(r"\b(?:intend|plan|planned|expect)\s+to\b", prefix):
        modality = "planned"
    elif re.search(r"\b(?:may|might|could|would|potentially)\b", prefix):
        modality = "possible"
    else:
        modality = "actual"
    return polarity, modality


def _strict_relation(sentence: str, entity_start: int) -> tuple[str | None, int | None]:
    best: tuple[int, str, int] | None = None
    for relation_type, patterns in COMPILED_STRICT_RELATIONS:
        for pattern in patterns:
            for match in pattern.finditer(sentence):
                distance = entity_start - match.end()
                if 0 <= distance <= 220 and (best is None or distance < best[0]):
                    best = (distance, relation_type, match.start())
    return (best[1], best[2]) if best else (None, None)


def _loose_relation(sentence: str) -> str | None:
    return next((kind for kind, patterns in COMPILED_LOOSE_RELATIONS if any(pattern.search(sentence) for pattern in patterns)), None)


def extract_topics_and_concepts(
    store: PipelineStore,
    filing: dict[str, Any],
    sections: Iterable[dict[str, Any]],
    max_chars: int,
) -> dict[str, int]:
    counts = {
        "topic_candidates": 0,
        "topic_assertions": 0,
        "concept_candidates": 0,
        "concept_assertions": 0,
        "relation_candidates": 0,
        "relations": 0,
    }
    for section in sections:
        context = _section_context(store, filing, section)
        text = section["text"]
        for name, group, patterns in COMPILED_TOPICS:
            match = next((found for pattern in patterns if (found := pattern.search(text))), None)
            if not match:
                continue
            snippet = text[max(0, match.start() - 180):min(len(text), match.end() + 180)]
            promote, level, reason = topic_promotion(context, group, snippet)
            decision = CandidateDecision(
                promote=promote,
                level=level,
                status="rule_accepted" if promote else "review_required",
                explicitness="explicit" if promote else "lexical",
                rejection_reason=reason,
            )
            _, _, assertion_id, _ = record_candidate(
                store,
                filing=filing,
                section=section,
                section_role=context.section_role,
                start=match.start(),
                end=match.end(),
                predicate="has_topic",
                object_value={"topic": name, "group": group},
                candidate_type="topic",
                confidence=0.88 if promote else 0.58,
                decision=decision,
                rule_id=f"topic:{name}",
                max_chars=max_chars,
            )
            counts["topic_candidates"] += 1
            counts["topic_assertions"] += int(assertion_id is not None)
        for name, group, patterns in COMPILED_CONCEPTS:
            match = next((found for pattern in patterns if (found := pattern.search(text))), None)
            if not match:
                continue
            promote, level, reason = concept_promotion(
                context,
                issuer_owns_concept=_concept_owned(store, filing, name),
            )
            decision = CandidateDecision(
                promote=promote,
                level=level,
                status="rule_accepted" if promote else "review_required",
                explicitness="explicit" if promote else "lexical",
                rejection_reason=reason,
            )
            _, _, assertion_id, _ = record_candidate(
                store,
                filing=filing,
                section=section,
                section_role=context.section_role,
                start=match.start(),
                end=match.end(),
                predicate="mentions_concept",
                object_value={"concept": name, "concept_type": group},
                candidate_type="concept",
                confidence=0.94 if promote else 0.62,
                decision=decision,
                rule_id=f"concept:{name}",
                max_chars=max_chars,
            )
            counts["concept_candidates"] += 1
            counts["concept_assertions"] += int(assertion_id is not None)
        for sent_start, sent_end, sentence in sentence_windows(text):
            loose_type = _loose_relation(sentence)
            if not loose_type:
                continue
            for entity_name, ticker, patterns in COMPILED_ENTITIES:
                entity_match = next((found for pattern in patterns if (found := pattern.search(sentence))), None)
                if not entity_match:
                    continue
                strict_type, relation_start = _strict_relation(sentence, entity_match.start())
                relation_type = strict_type or loose_type
                self_target = _self_target(store, filing, entity_name, ticker)
                subject_bound = strict_type is not None
                polarity, modality = _polarity_modality(sentence, relation_start or 0)
                promote, level, reason = relation_promotion(
                    context,
                    subject_bound=subject_bound,
                    self_target=self_target,
                )
                if polarity != "positive" or modality != "actual":
                    promote = False
                    level = "C" if not self_target else "R"
                    reason = "negative_or_nonactual_relation"
                decision = CandidateDecision(
                    promote=promote,
                    level=level,
                    status="rule_accepted" if promote else ("rejected" if level == "R" else "review_required"),
                    explicitness="explicit" if promote else "lexical",
                    subject_binding="issuer_bound" if subject_bound else "unresolved",
                    polarity=polarity,
                    modality=modality,
                    rejection_reason=reason,
                )
                relation = {
                    "target_entity_key": entity_name,
                    "target_ticker": ticker,
                    "relation_type": relation_type,
                    "product_scope": None,
                }
                _, _, _, relation_id = record_candidate(
                    store,
                    filing=filing,
                    section=section,
                    section_role=context.section_role,
                    start=sent_start,
                    end=sent_end,
                    predicate="has_company_relation",
                    object_value={
                        "target_entity": entity_name,
                        "target_ticker": ticker,
                        "relation_type": relation_type,
                    },
                    candidate_type="company_relation",
                    confidence=0.93 if promote else 0.55,
                    decision=decision,
                    rule_id=f"relation:{relation_type}:{'strict' if strict_type else 'loose'}",
                    max_chars=max_chars,
                    relation=relation if promote else None,
                )
                counts["relation_candidates"] += 1
                counts["relations"] += int(relation_id is not None)
    return counts


def extract_8k_events(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int) -> int:
    count = 0
    for section in sections:
        context = _section_context(store, filing, section)
        item = section.get("item") or ""
        if item not in EVENT_ITEM_MAP:
            continue
        event_type = EVENT_ITEM_MAP[item]
        evidence_id, candidate_id, _, _ = record_candidate(
            store,
            filing=filing,
            section=section,
            section_role=context.section_role,
            start=0,
            end=min(len(section["text"]), 300),
            predicate="reported_event",
            object_value={"event_type": event_type, "item": item, "title": section.get("title")},
            candidate_type="event",
            confidence=0.99,
            decision=CandidateDecision(True, "A", "rule_accepted", "structured"),
            rule_id=f"8k_item:{item}",
            max_chars=max_chars,
        )
        store.insert_many("event_ledger", [{
            "event_id": stable_id("event", filing["filing_id"], item, event_type),
            "filing_id": filing["filing_id"],
            "security_id": filing.get("security_id"),
            "symbol": filing["symbol"],
            "event_type": event_type,
            "item": item,
            "event_time": filing["available_at"],
            "event_time_precision": filing["available_at_precision"],
            "title": section.get("title"),
            "payload_json": canonical_json({"evidence_id": evidence_id, "candidate_id": candidate_id, "form": filing["form"]}),
            "confidence": 0.99,
            "extractor_version": EXTRACTOR_VERSION,
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
            "evidence_id": evidence_id,
            "filing_id": filing["filing_id"],
            "document_id": section.get("document_id") if section else None,
            "section_id": section.get("section_id") if section else None,
            "source_sha256": filing.get("raw_sha256") or "",
            "snippet": snippet,
            "snippet_hash": stable_id("snippet", snippet),
            "char_start": None,
            "char_end": None,
            "accepted_at": filing.get("accepted_at"),
            "available_at": filing["available_at"],
            "observed_at": filing.get("retrieved_at") or utc_now(),
            "extractor_version": EXTRACTOR_VERSION,
        }])
        target = holding.get("issuer_name") or holding.get("cusip") or "unknown"
        object_value = {
            "target_entity": target,
            "target_ticker": None,
            "relation_type": "investment_or_holding",
            "holding_id": holding["holding_id"],
        }
        candidate_id = stable_id("candidate", evidence_id, "has_company_relation", canonical_json(object_value), "13f_holding")
        store.insert_many("semantic_candidate", [{
            "candidate_id": candidate_id,
            "issuer_id": filing["issuer_id"],
            "security_id": None,
            "filing_id": filing["filing_id"],
            "section_id": section.get("section_id") if section else None,
            "evidence_id": evidence_id,
            "candidate_type": "company_relation",
            "predicate": "has_company_relation",
            "object_json": canonical_json(object_value),
            "confidence": 0.995,
            "explicitness": "structured",
            "status": "rule_accepted",
            "promotion_level": "A",
            "form": filing["form"],
            "section_role": "structured_holding",
            "rule_id": "13f_holding",
            "rule_version": EXTRACTOR_VERSION,
            "subject_binding": "structured",
            "polarity": "positive",
            "modality": "actual",
            "rejection_reason": None,
            "available_at": filing["available_at"],
            "created_at": utc_now(),
        }])
        promote_candidate(
            store,
            candidate_id=candidate_id,
            filing=filing,
            section=section,
            evidence_id=evidence_id,
            predicate="has_company_relation",
            object_value=object_value,
            candidate_type="company_relation",
            confidence=0.995,
            explicitness="explicit",
            method="structured_13f",
            relation={
                "target_entity_key": target,
                "target_ticker": None,
                "relation_type": "investment_or_holding",
                "product_scope": holding.get("class_title"),
            },
        )
        count += 1
    return count


def _extract_pattern_semantics(
    store: PipelineStore,
    filing: dict[str, Any],
    sections: list[dict[str, Any]],
    max_chars: int,
    *,
    predicate: str,
    assertion_type: str,
    confidence: float,
    patterns: dict[str, str],
    rule_prefix: str,
) -> int:
    count = 0
    for section in sections:
        context = _section_context(store, filing, section)
        for topic, pattern in patterns.items():
            match = re.search(pattern, section["text"], re.I)
            if not match:
                continue
            record_candidate(
                store,
                filing=filing,
                section=section,
                section_role=context.section_role,
                start=match.start(),
                end=match.end(),
                predicate=predicate,
                object_value={"topic": topic},
                candidate_type=assertion_type,
                confidence=confidence,
                decision=CandidateDecision(True, "B", "rule_accepted", "explicit"),
                rule_id=f"{rule_prefix}:{topic}",
                max_chars=max_chars,
            )
            count += 1
    return count


def extract_proxy_semantics(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int) -> int:
    return _extract_pattern_semantics(
        store,
        filing,
        sections,
        max_chars,
        predicate="proxy_topic",
        assertion_type="governance",
        confidence=0.94,
        rule_prefix="proxy_whitelist",
        patterns={
            "say_on_pay": r"say[- ]on[- ]pay|advisory vote on executive compensation",
            "director_election": r"election of directors?|nominees? for director",
            "auditor_ratification": r"ratif(?:y|ication).*independent registered public accounting firm",
            "equity_plan": r"equity incentive plan|stock incentive plan",
            "related_party_transactions": r"related person transactions?|related party transactions?",
        },
    )


def extract_regulatory_semantics(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int) -> int:
    return _extract_pattern_semantics(
        store,
        filing,
        sections,
        max_chars,
        predicate="regulatory_topic",
        assertion_type="regulatory",
        confidence=0.93,
        rule_prefix="regulatory_whitelist",
        patterns={
            "conflict_minerals": r"conflict minerals?|covered countries|Democratic Republic of the Congo",
            "sec_comment": r"comment letter|response to the staff|Division of Corporation Finance|we respectfully submit",
            "disclosure_commitment": r"in future filings|we will revise|we propose to revise|undertakes? to",
        },
    )


def extract_offering_semantics(store: PipelineStore, filing: dict[str, Any], sections: list[dict[str, Any]], max_chars: int) -> int:
    return _extract_pattern_semantics(
        store,
        filing,
        sections,
        max_chars,
        predicate="capital_markets_topic",
        assertion_type="capital_markets",
        confidence=0.95,
        rule_prefix="offering_whitelist",
        patterns={
            "common_stock": r"common stock",
            "preferred_stock": r"preferred stock",
            "debt_securities": r"debt securities|senior notes|convertible notes",
            "use_of_proceeds": r"use of proceeds",
            "plan_of_distribution": r"plan of distribution",
            "dilution": r"\bdilution\b",
            "interest_rate": r"\b\d+(?:\.\d+)?%\s+(?:senior |convertible )?notes\b",
            "maturity": r"\bmatur(?:e|es|ity)\b.{0,50}\b20\d{2}\b",
        },
    )
