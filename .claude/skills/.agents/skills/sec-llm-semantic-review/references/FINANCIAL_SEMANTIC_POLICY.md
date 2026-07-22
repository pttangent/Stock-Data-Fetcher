# Financial Semantic Policy

## Objective

Convert difficult SEC narrative into compact, auditable financial assertions without overstating what the filing proves. The goal is not prose summarization. The goal is a stable semantic layer suitable for company metadata, graph construction, event studies, theme research, and later human or model review.

## Claim classes

Every claim must carry one class:

| Class | Meaning | Example |
|---|---|---|
| `reported_fact` | Historical fact explicitly reported by the issuer | Revenue, supplier name, board appointment |
| `management_estimate` | Outlook, target, expectation, estimate, or guidance | Expected charge, projected capex |
| `risk_hypothesis` | Conditional risk that may occur | Supply disruption could delay shipments |
| `policy_or_rule` | Regulation, license, accounting policy, contract rule | Export license requirement |
| `management_interpretation` | Issuer explanation of causes or strategy | Demand was driven by AI infrastructure |
| `third_party_statement` | Statement attributed to another party | Government informed the company |
| `reviewer_inference` | Reviewer conclusion not explicitly stated | Product transition risk intensified |

A claim's class cannot be upgraded merely because later events confirmed it.

## Assertion dimensions

Each atomic assertion should capture, when applicable:

- subject entity;
- predicate or relation type;
- object entity/value;
- product or segment scope;
- geography;
- reporting period;
- actual versus guidance;
- GAAP versus non-GAAP;
- consolidated versus segment scope;
- currency and unit;
- confidence and explicitness;
- primary evidence and availability time.

Missing dimensions must remain null. Do not invent default scope.

## Business and product semantics

Allowed outputs include:

- business lines and operating segments;
- named products, platforms, architectures, services, and product families;
- end markets and customer categories;
- product lifecycle events: launch, transition, phase-out, delay, qualification, ramp;
- revenue or demand concentration by product or market;
- business-model changes and monetization mechanisms.

Rules:

- Keep issuer language and normalized ontology labels separate.
- A product mention is not proof of materiality.
- A product used in a risk example is not necessarily currently sold.
- A product family and a specific SKU must not be collapsed without an alias rule.
- Do not infer market share from adjectives such as leading, dominant, or industry-standard.

## Supply-chain semantics

Preferred relation types:

- `foundry_for`
- `memory_supplier_for`
- `assembly_test_for`
- `packaging_provider_for`
- `component_supplier_for`
- `manufacturing_partner_for`
- `cloud_provider_for`
- `distribution_partner_for`
- `depends_on_capacity_of`
- `single_source_dependency_on`
- `multi_source_dependency_on`

A relation requires an explicit issuer-first-person statement or a structured source. Co-mention is insufficient.

Capture separately:

- relationship direction;
- product scope;
- concentration level if explicitly stated;
- geography;
- exclusivity or single-source status;
- capacity or lead-time dependence;
- whether the statement is current, planned, or hypothetical.

Do not guess anonymous supplier or customer identities.

## Customer semantics

Allowed customer representations:

- named customer when explicitly identified by the issuer;
- anonymous concentration entity such as `anonymous_customer_A`;
- customer category such as hyperscaler, distributor, OEM, government, or enterprise;
- direct versus indirect customer when explicitly disclosed.

Hard rules:

- Never map Customer A/B/C to a real company using external speculation.
- A customer mentioned by analysts or media is external evidence, not issuer evidence.
- Revenue concentration does not imply contract duration, profitability, or dependence beyond what is disclosed.
- A distributor is not automatically the end customer.

## Competition semantics

Use `competes_with` only when the issuer explicitly identifies the entity, product, or category as competitive.

Capture:

- target company or product category;
- product/segment scope;
- basis of competition: price, performance, ecosystem, distribution, regulation, capacity, switching cost;
- whether the statement is current or prospective.

Do not infer rivalry from operating in the same industry. Do not convert a competitor's action described in the filing into an action by the issuer.

## Investment and 13F semantics

Structured 13F information supports:

- `reported_holding_in`;
- report period;
- issuer/class/CUSIP/FIGI;
- value and shares as filed;
- voting authority and investment discretion.

It does not support:

- strategic partnership;
- customer or supplier relationship;
- control or board influence;
- endorsement of management;
- current holding after the report period;
- purchase or sale timing within the quarter.

A change between two 13F reports is a disclosed quarter-end position delta, not necessarily a trade signal or transaction record.

## Risk semantics

Risk factors must be represented as exposures, not realized events, unless another filing explicitly reports realization.

Useful risk families:

- export-control and sanctions exposure;
- supply-chain concentration;
- customer concentration;
- inventory and purchase-commitment risk;
- product-transition and obsolescence risk;
- demand cyclicality;
- pricing and margin pressure;
- cybersecurity and privacy;
- litigation and regulatory scrutiny;
- capital intensity and capacity commitments;
- geographic and geopolitical exposure;
- reliance on intellectual property or licenses.

For each risk, separate:

- exposure driver;
- affected product/segment/geography;
- possible consequence;
- mitigation, if disclosed;
- realized versus hypothetical status;
- disclosure change versus prior comparable filing.

Do not score risk severity solely by word count.

## Event semantics

For 8-K and 6-K, Item code anchors event classification. Narrative review may refine but not override the filed Item.

Typical event families:

- earnings or financial results;
- guidance initiation, reaffirmation, increase, reduction, or withdrawal;
- material agreement;
- acquisition or disposition;
- restructuring or impairment;
- debt or financing;
- auditor or accounting matter;
- executive or board change;
- regulatory restriction or license requirement;
- legal proceeding;
- security issuance;
- shareholder vote.

An event record must distinguish:

- event occurrence time, if explicitly stated;
- filing availability time;
- reporting period;
- actual event versus management expectation;
- quantitative impact versus qualitative description.

## Financial-statement logic

### Stock versus flow

- Balance-sheet values are point-in-time stocks.
- Income-statement and cash-flow values are period flows.
- Do not subtract a quarterly flow from an annual flow without aligning periods.

### Actual versus guidance

- Actual results, estimates, targets, and ranges are different fact classes.
- Midpoints may be calculated only when the formula and source range are recorded.
- Guidance changes require a comparable prior guidance record available before the new filing.

### GAAP versus non-GAAP

- Never combine or compare without labeling.
- Preserve reconciliation status and metric definition.
- A non-GAAP metric with the same name may differ across issuers or periods.

### Consolidated versus segment

- Preserve scope.
- Segment revenue, operating income, and capex cannot be treated as consolidated values.
- A segment reorganization may break historical comparability; record the change.

### Units and scale

Always preserve:

- currency;
- raw value;
- scale or unit;
- percentage versus decimal;
- shares versus dollars;
- basis points versus percentage points;
- per-share versus aggregate value.

For Form 13F, follow the applicable SEC schema and filed unit. Current SEC technical specifications report value to the nearest dollar; do not apply legacy thousands scaling without evidence.

## Disclosure-delta logic

Compare only PIT-eligible, comparable documents.

Delta labels:

- `new`: disclosure or relation appears with substantive content not present before;
- `removed`: previously explicit disclosure is absent from an equivalent-scope section and removal is supported;
- `intensified`: stronger language, larger quantified exposure, broader scope, or more immediate consequence;
- `de_intensified`: narrower or reduced exposure or weaker language;
- `unchanged`: substantively equivalent disclosure;
- `wording_only`: wording changed without semantic change;
- `not_comparable`: scope, segment, accounting basis, or document structure changed materially.

Absence is not removal when:

- the section was shortened or incorporated by reference;
- reporting scope changed;
- the prior disclosure was event-specific;
- a table or exhibit moved;
- the filing is a different form with different requirements.

## Causality and market interpretation

The semantic library may store management-attributed causes, but must label them `management_interpretation`.

Do not assert that a disclosure caused a stock move unless a separate event-study layer establishes the timing and methodology. Even then, use probabilistic language and keep the semantic evidence separate from market-response evidence.

Do not create alpha labels, trade direction, expected return, or valuation conclusions inside semantic assertions.

## Ontology governance

New ontology entries must be proposed as `taxonomy_candidate` and include:

- proposed canonical label;
- aliases found in evidence;
- parent category;
- definition;
- inclusion and exclusion examples;
- evidence IDs;
- collision check against existing labels;
- whether the label is issuer-specific or reusable;
- reviewer confidence.

Do not automatically merge labels based only on embedding similarity.

## Final decision test

Before emitting a claim, ask:

1. What exactly did the issuer or structured filing state?
2. Is this actual, estimated, hypothetical, attributed, or inferred?
3. What is the subject, direction, object, product scope, period, and geography?
4. Is the evidence available at the frozen PIT timestamp?
5. Is a deterministic table or XBRL fact more authoritative?
6. Am I guessing an identity, relation, causality, unit, or economic significance?
7. Would the claim remain defensible if later prices and outcomes were hidden?

If any required answer is unknown, keep the field null or return `no_change`.
