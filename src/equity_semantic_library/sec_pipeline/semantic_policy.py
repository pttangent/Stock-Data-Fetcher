from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

POLICY_VERSION = "sec-semantic-policy-v2"


@dataclass(frozen=True)
class SectionContext:
    section_role: str
    issuer_scope: str
    allow_topic_promotion: bool
    allow_concept_promotion: bool
    allow_relation_promotion: bool
    reasons: tuple[str, ...]

    def as_row(self, filing: dict[str, Any], section: dict[str, Any]) -> dict[str, Any]:
        data = asdict(self)
        return {
            "section_id": section["section_id"],
            "filing_id": filing["filing_id"],
            "form": filing["form"],
            "form_group": filing["form_group"],
            "section_role": data["section_role"],
            "issuer_scope": data["issuer_scope"],
            "allow_topic_promotion": int(data["allow_topic_promotion"]),
            "allow_concept_promotion": int(data["allow_concept_promotion"]),
            "allow_relation_promotion": int(data["allow_relation_promotion"]),
            "classifier_version": POLICY_VERSION,
            "reasons_json": list(data["reasons"]),
        }


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def classify_section(filing: dict[str, Any], section: dict[str, Any]) -> SectionContext:
    group = _norm(filing.get("form_group"))
    base_form = _norm(filing.get("base_form"))
    item = _norm(section.get("item")).replace("item ", "")
    title = _norm(section.get("title"))
    head = _norm(section.get("text"))[:1400]
    combined = f"{title} {head}"

    if group == "holdings":
        return SectionContext("structured_holding", "issuer", False, False, False, ("13f_structured_only",))
    if group == "event":
        return SectionContext("event_disclosure", "issuer", False, False, False, ("event_item_is_primary_semantics",))
    if group == "offering":
        return SectionContext("offering_terms", "issuer", False, False, False, ("offering_whitelist_only",))
    if group == "proxy":
        if re.search(r"biograph|business experience|director qualifications|background|former employer|career history", combined):
            return SectionContext("director_biography", "third_party", False, False, False, ("third_party_biography",))
        if re.search(r"proposal|election of directors|executive compensation|say.on.pay|ratif|shareholder vote|related person", combined):
            return SectionContext("governance_proposal", "issuer", False, False, False, ("proxy_whitelist_only",))
        return SectionContext("proxy_other", "mixed", False, False, False, ("proxy_whitelist_only",))
    if group == "regulatory":
        if base_form == "sd":
            return SectionContext("conflict_minerals", "issuer", False, False, False, ("regulatory_whitelist_only",))
        return SectionContext("sec_correspondence", "mixed", False, False, False, ("regulatory_whitelist_only",))
    if group == "annual":
        is_20f = base_form in {"20-f", "20f"}
        if (is_20f and item.startswith("3d")) or (not is_20f and item.startswith("1a")) or "risk factor" in title:
            return SectionContext("issuer_risk", "issuer", True, True, True, ("annual_risk_section",))
        if (
            (is_20f and (item == "4" or item.startswith("4.")))
            or (not is_20f and item == "1")
            or title in {"business", "information on the company"}
        ):
            return SectionContext("issuer_business", "issuer", True, True, True, ("annual_business_section",))
        if (
            (is_20f and (item == "5" or item.startswith("5.")))
            or (not is_20f and item == "7")
            or "management's discussion" in title
            or "management’s discussion" in title
            or "operating and financial review" in title
        ):
            return SectionContext("issuer_mda", "issuer", True, True, True, ("annual_mda_section",))
        return SectionContext("annual_other", "mixed", False, False, False, ("non_primary_annual_section",))
    if group == "quarterly":
        if item.startswith("1a") or "risk factor" in title:
            return SectionContext("issuer_risk", "issuer", True, True, True, ("quarterly_risk_section",))
        if item == "2" or "management" in title:
            return SectionContext("issuer_mda", "issuer", True, True, True, ("quarterly_mda_section",))
        if item == "1" or "financial statements" in title:
            return SectionContext("issuer_financial", "issuer", False, False, False, ("financial_statement_context",))
        return SectionContext("quarterly_other", "mixed", False, False, False, ("non_primary_quarterly_section",))
    return SectionContext("unclassified", "unknown", False, False, False, ("unknown_form_context",))


def _topic_semantic_gate(topic_name: str, snippet: str) -> tuple[bool, str | None]:
    text = _norm(snippet)

    if topic_name == "privacy_regulation":
        regulatory = re.search(
            r"\b(?:law|laws|regulation|regulations|regulatory|compliance|authority|authorities|"
            r"requirements?|framework|gdpr|ccpa|privacy act|data protection act|enforcement)\b",
            text,
        )
        return bool(regulatory), None if regulatory else "privacy_without_regulatory_binding"

    if topic_name == "subscription_services":
        capital_markets = re.search(
            r"subscription (?:of|for) (?:preferred|common) stock|subscription rights?|"
            r"subscribe for shares?|debt securities|subordinated bonds?|prospectus|securities offering",
            text,
        )
        business_model = re.search(
            r"saas|subscription[- ]based model|subscription model|subscription revenue|subscription fees?|"
            r"software subscriptions?|recurring revenue|customers? (?:subscribe|renew)|subscribers?|membership fees?",
            text,
        )
        allowed = bool(business_model) and not bool(capital_markets)
        return allowed, None if allowed else "subscription_without_business_model_binding"

    if topic_name == "data_center":
        internal_use = re.search(
            r"our (?:own )?data cent(?:er|re)s?|(?:expand|operate|monitor|host|optimiz)[a-z]* "
            r"(?:our )?data cent(?:er|re)s?|data cent(?:er|re)s? to (?:host|support) our",
            text,
        )
        end_market = re.search(
            r"(?:products?|solutions?|services?|systems?)\b.{0,140}\bdata cent(?:er|re)s?|"
            r"data cent(?:er|re)\b.{0,140}\b(?:customers?|market|applications?|demand|sales|revenue|interconnect|operators?)|"
            r"hyperscale\b.{0,100}\b(?:customers?|market|data cent(?:er|re)s?)|colocation customers?",
            text,
        )
        allowed = bool(end_market) and not bool(internal_use)
        return allowed, None if allowed else "data_center_without_end_market_binding"

    if topic_name == "social_media":
        channel_use = re.search(
            r"social media initiatives?|use (?:these channels|social media)|social media communities|"
            r"postings?, articles?, or comments? on social media|communicat[a-z]*.{0,50}social media",
            text,
        )
        business_context = re.search(
            r"social media\b.{0,120}\b(?:platforms?|users?|audience|advertis|revenue|market|vertical|"
            r"compete|content|apps?|customers?)|(?:platforms?|verticals?|markets?|competitors?)\b.{0,120}\bsocial media",
            text,
        )
        allowed = bool(business_context) and not bool(channel_use)
        return allowed, None if allowed else "social_media_without_business_binding"

    if topic_name == "search":
        if re.search(r"search engine marketing", text):
            return False, "search_used_as_marketing_channel"
        search_business = re.search(
            r"search advertising|google search|internet search|search engine\b.{0,100}\b(?:business|market|platform|service|revenue)",
            text,
        )
        return bool(search_business), None if search_business else "search_without_business_binding"

    if topic_name == "robotics":
        internal_use = re.search(r"integrat[a-z]*.{0,100}(?:robotics?|industrial automation).{0,100}(?:our )?manufacturing", text)
        end_market = re.search(
            r"(?:products?|solutions?|services?|systems?)\b.{0,120}\b(?:robotics?|industrial automation)|"
            r"(?:robotics?|industrial automation)\b.{0,120}\b(?:customers?|market|applications?|sales|revenue)",
            text,
        )
        allowed = bool(end_market) and not bool(internal_use)
        return allowed, None if allowed else "robotics_without_end_market_binding"

    return True, None


def topic_promotion(
    context: SectionContext,
    topic_name: str,
    topic_group: str,
    snippet: str,
) -> tuple[bool, str, str | None]:
    if not context.allow_topic_promotion:
        return False, "D", "form_section_policy"

    semantic_ok, semantic_reason = _topic_semantic_gate(topic_name, snippet)
    if not semantic_ok:
        return False, "C", semantic_reason

    if topic_group == "risk":
        allowed = context.section_role == "issuer_risk"
        return allowed, "B" if allowed else "C", None if allowed else "risk_outside_risk_section"
    if topic_group == "finance":
        allowed = context.section_role in {"issuer_mda", "issuer_financial"}
        return allowed, "B" if allowed else "C", None if allowed else "finance_outside_financial_context"
    if topic_group == "geography":
        exposure_terms = re.search(
            r"(?i)operations?|manufactur|suppliers?|customers?|revenue|sales|facilit|located|offices?|"
            r"subsidiar|employees?|assets?|cash flows?|costs?|profit|currency|export|import|tariff|trade restriction|business in",
            snippet,
        )
        allowed = context.section_role in {"issuer_business", "issuer_risk"} and bool(exposure_terms)
        return allowed, "B" if allowed else "C", None if allowed else "geography_without_exposure_binding"
    allowed = context.section_role == "issuer_business"
    return allowed, "B" if allowed else "C", None if allowed else "topic_outside_business_section"


def concept_promotion(context: SectionContext, *, issuer_owns_concept: bool) -> tuple[bool, str, str | None]:
    if not context.allow_concept_promotion:
        return False, "D", "form_section_policy"
    if not issuer_owns_concept:
        return False, "C", "concept_not_linked_to_filing_issuer"
    allowed = context.section_role in {"issuer_business", "issuer_mda", "issuer_risk"}
    return allowed, "B" if allowed else "C", None if allowed else "concept_outside_issuer_context"


def relation_promotion(context: SectionContext, *, subject_bound: bool, self_target: bool) -> tuple[bool, str, str | None]:
    if self_target:
        return False, "R", "self_target"
    if not context.allow_relation_promotion:
        return False, "D", "form_section_policy"
    if not subject_bound:
        return False, "C", "issuer_subject_unresolved"
    return True, "B", None
