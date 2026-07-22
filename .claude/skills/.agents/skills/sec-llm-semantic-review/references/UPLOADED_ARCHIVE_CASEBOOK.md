# Uploaded SEC Archive Casebook

## Scope

This casebook is based on the SEC ZIP archives actually uploaded and processed during development:

```text
MU
AMD
AVGO
NVDA
AMZN
GOOGL
META
```

The current uploaded set does **not** contain a standalone `ticker=AAPL.zip` or `ticker=TSM.zip`. TSM appears as a named counterparty in AMD and NVIDIA filings, but TSM issuer-side semantics must not be inferred without TSM's own governed filing evidence. Add AAPL or TSM issuer cases only after their archives are imported and validated.

The examples below define what should and should not enter the post-processing LLM queue. They do not authorize whole-document summarization.

## Deterministic extraction versus LLM review

### Keep deterministic; do not send to LLM

- accession, form, filing date, acceptance time, report date, and source URL;
- SGML document splitting, primary-document identification, attachment type, byte offsets, and SHA-256;
- Item/section boundaries and raw section text;
- HTML table rows and XBRL facts;
- 8-K Item-code event family;
- 13F holding rows and quarter-end position values;
- exact arithmetic values already present in XBRL or tables;
- a simple explicit named relation when role and direction are already fully captured;
- form exclusion policy for Forms 3, 4, 5, and 144.

### Send only these cases to post-processing LLM review

1. product lifecycle or ontology state cannot be represented by a keyword hit alone;
2. one paragraph contains several financially different claim classes;
3. a generic deterministic relation needs a precise role, direction, product scope, or dependency scope;
4. two PIT-eligible filings need semantic delta classification;
5. actual, guidance, estimate, risk, management interpretation, and third-party statements must be separated;
6. a filing describes a segment or accounting-scope change that affects comparability;
7. a legal/regulatory event needs obligation, remedy, uncertainty, or realized-impact decomposition;
8. a taxonomy candidate or entity alias requires controlled normalization;
9. deterministic extraction generated a likely self-relation, co-mention relation, or scope error;
10. evidence is explicit but economic significance remains ambiguous and must be left as `review_required` rather than guessed.

---

# MU cases

## MU-1 — HBM product lifecycle states

Source:

```text
Ticker: MU
Form: 10-K
Accession: 0000723125-25-000028
Accepted: 2025-10-03T18:42:25Z
Item: 1 Business
```

Relevant issuer statements include:

- HBM3E 8-high entered volume production in 2024;
- HBM3E 12-high represented the majority of HBM shipments in fiscal Q4 2025;
- HBM4 36GB 12-high samples were delivered to multiple key customers in 2025.

Why deterministic rules are insufficient:

A keyword extractor correctly identifies `HBM3E` and `HBM4`, but it cannot safely collapse these statements into one generic `has_product` fact. The financially relevant states differ:

```text
HBM3E 8-high -> volume_production
HBM3E 12-high -> majority_of_current_hbm_shipments
HBM4 36GB 12-high -> customer_sampling
```

Required LLM output:

- separate atomic lifecycle assertions;
- product generation, stack height, capacity, and state;
- actual versus prospective state;
- no revenue or production claim for HBM4 unless another eligible filing states it;
- no customer identity inference from “multiple key customers.”

Forbidden inference:

- HBM4 is in volume production;
- HBM4 generated revenue;
- a named AI accelerator company is one of the key customers;
- HBM3E majority of HBM shipments means majority of total company revenue.

## MU-2 — Product transition versus market significance

The same filing describes HBM demand from AI/data-centric workloads and technology improvements.

LLM review may classify:

- issuer-reported product state;
- management interpretation of end-market demand;
- product-transition exposure;
- taxonomy relation among `HBM`, `HBM3E`, `HBM4`, stack height, and capacity.

LLM review must not produce:

- market-share estimates;
- demand forecasts not explicitly disclosed;
- expected revenue contribution;
- an alpha or trade direction.

## MU-3 — Capital spending and memory-cycle risk

MU filings contain capital-expenditure, worldwide supply, wafer-output, yield, and pricing-risk language.

Send to LLM only when the task is to separate:

- actual capex;
- planned facility or capacity investment;
- competitor capacity expansion described by management;
- risk hypothesis that supply growth may exceed demand;
- management interpretation of memory-cycle pricing.

Do not ask the LLM to re-extract capex values already present in tables or XBRL.

---

# AMD cases

## AMD-1 — MI308 export-control event decomposition

Source:

```text
Ticker: AMD
Form: 10-Q
Accession: 0000002488-25-000166
Accepted: 2025-11-04T23:07:50Z
```

The filing states that AMD recorded approximately $800 million of inventory and related charges associated with U.S. export controls on MI308 products. It also states that some licenses were granted and future China sales depend on customer demand, Chinese import rules, and license availability.

One paragraph therefore contains at least four distinct claim classes:

```text
reported_fact:
  approximately $800 million charge was recorded

policy_or_rule:
  MI308 exports to covered destinations require government licensing

reported_fact:
  some licenses were granted

risk_hypothesis / management_estimate:
  future revenue depends on demand, import rules, and future licenses
```

Required LLM output:

- separate atomic records for charge, rule, license status, and conditional future exposure;
- preserve amount, period, product, cost classification, and actual/guidance state;
- classify the $800 million as realized accounting impact, not an estimate;
- keep future sales exposure as conditional.

Forbidden inference:

- all MI308 sales to China resumed;
- licenses cover every customer or quantity;
- $800 million equals lost revenue;
- the restriction permanently eliminates AMD from China;
- the event caused a specific stock-price move.

## AMD-2 — TSMC relation refinement

Source:

```text
Ticker: AMD
Form: 10-K
Accession: 0000002488-25-000012
Accepted: 2025-02-05T21:42:57Z
Item: 1 Business
```

AMD explicitly states that it uses TSMC for wafer production for HPC, FPGA, and Adaptive SoC products, while GlobalFoundries is used for specified 12nm and 14nm HPC wafer purchases; TSMC, UMC, and Samsung are also used for programmable-logic IC production.

The deterministic relation `supplier_or_manufacturer` is supported but too coarse.

The LLM may propose role-specific candidates:

```text
AMD --foundry_for--> TSMC
  product_scope: HPC, FPGA, Adaptive SoC wafer production

AMD --foundry_for--> GlobalFoundries
  product_scope: HPC wafers at 12nm and 14nm

AMD --foundry_for--> TSMC / UMC / Samsung
  product_scope: programmable-logic ICs
```

Governance rules:

- preserve separate relations by role and product scope;
- do not say TSMC manufactures all AMD products unless that exact scope is supported;
- do not convert “use” into exclusivity;
- do not infer current wafer volume or revenue share;
- do not create TSM issuer facts from AMD evidence.

## AMD-3 — Segment restatement and comparability

Source:

```text
Ticker: AMD
Form: 10-Q
Accession: 0000002488-25-000166
Accepted: 2025-11-04T23:07:50Z
```

The company changed its reportable segment structure by combining Client and Gaming, and retrospectively adjusted prior-period segment data.

This should enter LLM review because a semantic library must distinguish:

- the date the new reporting structure became available;
- the effective fiscal reporting structure;
- retrospective comparability of prior-period segment values;
- taxonomy aliases before and after the change;
- current three-segment structure versus historical four-segment references.

Required output:

- `segment_structure_change` event;
- old and new segment mappings;
- `not_comparable` flag for unadjusted historical segment data;
- explicit note that restated prior-period values may be comparable only when sourced from the restating filing.

Forbidden inference:

- the business economics changed merely because reporting segments changed;
- Client and Gaming operational performance should always be combined before the disclosed change;
- old filings may be retroactively rewritten.

## AMD-4 — Instinct generation ontology

AMD filings mention MI300X, MI308, and MI350 Series under the Instinct family.

LLM review is appropriate only for:

- product-family hierarchy;
- model/generation normalization;
- launch, shipment, demand, restricted-market, and revenue-driver states;
- distinguishing roadmap announcements from delivered products.

Do not use the LLM to infer benchmark leadership, market share, or future adoption.

---

# AVGO cases

## AVGO-1 — VMware Cloud Foundation ontology and business model

Source:

```text
Ticker: AVGO
Form: 10-K
Accession: 0001730168-25-000121
Accepted: 2025-12-18T21:04:47Z
Item: 1 Business
```

The filing describes VMware Cloud Foundation as an integrated platform covering compute, networking, storage, management, security, Kubernetes, AI/ML workloads, and data services, with optional services such as vDefend, Avi Load Balancer, Tanzu Platform, Private AI, Live Recovery, and others.

A keyword extractor can identify VMware, cloud, AI, subscription, networking, and security, but it cannot determine ontology hierarchy.

Required LLM review:

```text
VMware -> acquired software platform / portfolio
VCF -> core private-cloud infrastructure suite
vDefend, Avi, Tanzu, Private AI, Live Recovery -> optional/add-on services
license portability -> commercial/product capability
subscription -> delivery/commercial model
```

Forbidden inference:

- every VMware product is included in every VCF subscription;
- optional services are separate reportable segments;
- VCF is a public-cloud provider;
- product descriptions prove customer adoption or revenue materiality.

## AVGO-2 — Customer concentration without identity guessing

Source:

```text
Ticker: AVGO
Form: 10-K
Accession: 0001730168-25-000121
Accepted: 2025-12-18T21:04:47Z
```

The company estimates that its top five end customers represented approximately 40% of net revenue and describes significant concentration risk. It also discusses distributors, OEMs, contract manufacturers, and AI customers.

LLM review may normalize:

- direct channel versus end customer;
- distributor concentration versus end-customer concentration;
- actual historical concentration versus expected future concentration;
- AI-customer contractual and credit-risk language;
- anonymous customer stable keys.

Hard prohibition:

- do not identify customers using market rumors, external estimates, or product speculation;
- do not equate distributor share with end-customer share;
- do not infer that any named hyperscaler represents a disclosed percentage.

## AVGO-3 — AI Revenue compensation metric

Source:

```text
Ticker: AVGO
Form: 8-K
Accession: 0001193125-25-199281
Accepted: 2025-09-09T21:28:00Z
Item: 5.02
```

The 8-K defines an “AI Revenue” performance metric for a CEO performance-stock-unit award, including custom AI accelerators, XPUs, ASICs, networking, and connectivity solutions over a future performance period.

This is not ordinary reported revenue and must be classified as:

```text
compensation_performance_metric_definition
management/board target framework
future performance condition
```

Required LLM distinctions:

- metric definition versus realized revenue;
- compensation target versus company guidance;
- product scope included in the metric;
- measurement window and vesting condition.

Forbidden inference:

- target values are revenue guidance;
- achieving the target is probable;
- “AI Revenue” is identical to GAAP segment revenue;
- the award proves future financial performance.

## AVGO-4 — Subscription transition and revenue comparability

Broadcom describes infrastructure-software subscription licensing and revenue-recognition variation.

Send to LLM only for:

- commercial-model transition classification;
- distinguishing subscription contract structure from recognized revenue;
- identifying comparability breaks caused by acquisition or licensing changes;
- separating management explanation from reported accounting values.

Do not let the LLM recalculate revenue recognition.

---

# NVDA cases

## NVDA-1 — H20 estimate-to-actual PIT chain

Initial event:

```text
Ticker: NVDA
Form: 8-K
Accession: 0001045810-25-000082
Accepted: 2025-04-15T21:22:59Z
Item: 8.01
```

The 8-K states that first-quarter results were expected to include up to approximately $5.5 billion of H20-related charges.

Later actual disclosure:

```text
Ticker: NVDA
Form: 10-Q
Accession: 0001045810-25-000116
Accepted: 2025-05-28T20:32:57Z
```

The 10-Q reports a $4.5 billion charge and explains that it was lower than initially anticipated because certain materials could be reused.

This is a model case for post-processing LLM review:

```text
2025-04-15 knowledge state:
  management_estimate = up to approximately $5.5B

2025-05-28 knowledge state:
  reported_fact = $4.5B actual charge
  management_interpretation = lower due to material reuse
```

Required behavior:

- preserve both records;
- never rewrite the April knowledge state with the May actual;
- classify estimate-to-actual delta;
- preserve charge components and period;
- make the later actual usable only after its own `available_at`.

## NVDA-2 — Supply-chain role decomposition

Source:

```text
Ticker: NVDA
Form: 10-K
Accession: 0001045810-25-000023
Accepted: 2025-02-26T21:48:33Z
Item: 1 Business
```

The filing distinguishes:

- TSMC and Samsung as wafer foundries;
- SK hynix, Micron, and Samsung as memory suppliers;
- CoWoS as packaging technology;
- Hon Hai/Foxconn, Wistron, and Fabrinet as assembly, testing, and packaging partners.

The LLM may refine generic deterministic relations into these exact roles and product/process scopes.

Hard rules:

- Samsung may have more than one role; emit separate atomic relations;
- CoWoS is a technology/process, not automatically a company relation;
- do not infer exclusivity, capacity allocation, or contract economics;
- do not create supplier facts from risk-section examples unless the issuer explicitly says “supplier of ours” or equivalent.

## NVDA-3 — Anonymous customer concentration

NVIDIA filings disclose Customer A/B/C/D concentration and explicitly state that customer labels may represent different customers across periods.

LLM may:

- create period-specific anonymous customer keys;
- preserve direct versus indirect customer distinction;
- preserve percentage, segment, and period;
- flag non-comparability of anonymous labels across periods.

LLM must not:

- map labels to Microsoft, Amazon, Google, Meta, or any other company;
- assume Customer A is stable across quarters;
- merge direct and indirect customer concentration.

---

# GOOGL case

## GOOGL-1 — Antitrust remedy event

Source:

```text
Ticker: GOOGL
Form: 8-K
Accession: 0001652044-25-000067
Accepted: 2025-09-03T20:30:34Z
Item: 8.01
```

The filing reports a court remedies decision imposing distribution limits and requiring search-data sharing and syndication services for certain competitors.

LLM review is appropriate for:

- realized legal event versus ongoing litigation risk;
- remedy obligations;
- affected product scope: online search and service distribution;
- relation to the previously disclosed liability decision;
- uncertainty about implementation, appeal, timing, or financial impact when not explicitly resolved.

Forbidden inference:

- exact revenue impact;
- finality if appeal rights remain;
- causal effect on stock price;
- competitor identities not stated in evidence.

---

# META case

## META-1 — Llama open-source strategy

Source:

```text
Ticker: META
Form: 10-K
Accession: 0001326801-25-000017
Accepted: 2025-01-30T01:00:50Z
```

The issuer states that Llama models were made available for researchers and developers, with aims including accelerating research, improving Meta products, and fostering collaboration.

LLM may classify:

- Llama as an AI-model family;
- availability/open-development strategy;
- issuer-stated strategic objectives;
- use in internal-product improvement as management intent.

LLM must not infer:

- direct monetization;
- open-source license compatibility beyond the filed wording;
- adoption, market share, or developer preference;
- that every Meta product uses Llama.

---

# AMZN and 13F cases

## AMZN-1 — 13F entity normalization only

AMZN's uploaded archive contains structured 13F holdings.

The LLM is normally unnecessary because issuer name, class, CUSIP, value, and shares are structured.

Permitted optional review:

- issuer alias resolution;
- ticker mapping with deterministic identifier support;
- duplicate share-class normalization;
- quarter-over-quarter position-state description.

Forbidden inference:

- trade date within the quarter;
- purchase price;
- strategic partnership;
- supplier/customer relation;
- current holding after the report period;
- investment thesis or endorsement.

---

# Review routing matrix

| Candidate type | LLM needed? | Example |
|---|---:|---|
| Exact XBRL fact | No | Revenue, assets, charge value already structured |
| Exact 13F row | No | Issuer, CUSIP, shares, value |
| 8-K Item event type | No | Item 5.02 = officer/director event |
| Product name mention | Usually no | HBM4, MI308, VCF |
| Product lifecycle state | Yes | Sampled versus volume production |
| Generic supplier relation | Sometimes | Refine TSMC into foundry role and scope |
| Anonymous customer identity | Never | Preserve anonymous key |
| Risk realized versus hypothetical | Yes | MI308 charge plus future license risk |
| Estimate-to-actual chain | Yes | NVDA $5.5B expected to $4.5B actual |
| Segment restatement | Yes | AMD Client + Gaming combination |
| Compensation metric versus guidance | Yes | AVGO AI Revenue PSU target |
| Legal remedy obligations | Yes | GOOGL antitrust remedy |
| Whole filing summary | No | Not a governed semantic task |
| Trade recommendation | No | Outside semantic library |

# Batch-selection principle

Do not send every accepted assertion to the LLM. Build a review batch only from:

```text
status = review_required
OR confidence below the configured review threshold
OR relation type is generic and product_scope is missing
OR lifecycle language appears around a known product
OR actual/guidance/risk classes coexist in one evidence window
OR a comparable prior filing exists and a delta review was requested
OR segment/accounting scope changed
OR a governance validator explicitly flags the record
```

Everything else remains deterministic and bypasses LLM processing.
