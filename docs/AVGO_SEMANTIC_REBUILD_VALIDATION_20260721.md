# AVGO semantic rebuild validation — 2026-07-21

This validation used the candidate-first semantic pipeline against the AVGO filings already parsed in the user's preliminary SQLite database. It did not contact SEC and did not redownload or reparse raw filings.

## Scope

- AVGO filings rebuilt: 59
- parsed sections consumed: 348
- semantic rebuild time in the validation container: about 25 seconds
- ownership forms present: 0

The tested filings include 21 8-Ks, five 10-Qs, one 10-K, Proxy filings, SEC correspondence, conflict-minerals reports and multiple offering documents. The uploaded AVGO ZIP contains additional filings; this is a semantic-layer validation for rows already parsed in the preliminary database, not a claim of complete ZIP parser coverage.

## Candidate and promotion result

| Result | Rows |
|---|---:|
| short evidence snippets | 1,203 |
| semantic candidates | 1,218 |
| A-level structured candidates | 43 |
| B-level deterministic candidates | 535 |
| C-level review candidates | 125 |
| D-level lexical/form-policy candidates | 488 |
| R-level rejected candidates | 27 |
| automatically accepted assertions | 578 |
| review-required candidates | 613 |
| structurally rejected candidates | 27 |

Evidence recall remains broader than the formal accepted semantic layer.

## Form-policy checks

- accepted generic topic/concept/company-relation assertions from Proxy and Offering filings: **0**;
- Offering `subscription_services` lexical candidates: 16;
- Offering `subscription_services` automatically accepted assertions: **0**;
- Proxy Google Cloud biography candidates: 2;
- Proxy Google Cloud automatically accepted assertions: **0**;
- missing candidate `available_at`: 0;
- candidate evidence orphans: 0.

The Google Cloud mentions came from a director biography describing a former role at Alphabet. They remain D-level evidence and do not become Broadcom product facts. Securities-subscription language likewise remains reviewable evidence rather than becoming a Broadcom subscription-business assertion.

## Accepted issuer topics and concepts

The accepted AVGO business layer includes issuer-owned or issuer-scoped evidence for:

- semiconductors and custom AI accelerators;
- data center and networking products;
- advanced packaging and high-bandwidth memory integration;
- infrastructure software and VMware Cloud Foundation;
- VMware subscription licensing;
- enterprise software, cloud services and generative-AI capabilities;
- automotive and industrial-automation end markets;
- supply-chain dependency, customer concentration, export controls and inventory risk.

Accepted VMware evidence instances: 13.

Manual evidence inspection confirmed that:

- `subscription_services` in the accepted 10-K evidence refers to VCF software subscriptions and a transition to a subscription license model;
- `antitrust_regulation` comes from explicit antitrust-law disclosures;
- `taiwan_exposure` is supported by TSMC manufacturing dependence and China–Taiwan geopolitical risk, not merely a currency reference;
- HBM, advanced packaging, AI and cloud evidence comes from Broadcom's own Item 1 business description.

## Manufacturer relation recall finding and correction

The first AVGO pass produced zero accepted operating relations even though the filings explicitly state that Broadcom outsources wafer manufacturing to external foundries including TSMC and that TSMC, one of Broadcom's contract manufacturers, produced approximately 95% of relevant wafers.

The earlier strict binder only handled active first-person constructions such as `we rely on TSMC`. Semiconductor filings frequently use passive or entity-first constructions:

```text
The majority of our front-end wafer manufacturing operations is outsourced
 to external foundries, including TSMC.

TSMC, one of our CMs, manufactured approximately 95% of the wafers...
```

The deterministic relation binder was extended to recognize:

- issuer-owned passive manufacturing outsourced to or produced by a named entity;
- a named entity explicitly described as `one of our CMs`, suppliers, foundries or contract manufacturers;
- a named entity manufacturing, fabricating or producing issuer-owned products or wafers.

Loose supplier terms were also expanded to include manufactured, fabricated, produced wafers and contract manufacturers, preventing nearby `customer` language from assigning the wrong relation type.

## Relation result after correction

- accepted AVGO company relations: 9;
- accepted AVGO self-target relations: 0;
- accepted TSMC relations: 9;
- accepted relation type: `supplier_or_manufacturer`;
- first evidence time: 2025-03-12T20:38:04Z;
- latest evidence time: 2026-06-09T13:06:09Z;
- TSMC `customer_or_channel` candidates after correction: 0.

The accepted evidence includes multiple 10-K and 10-Q disclosures that TSMC is one of Broadcom's contract manufacturers, manufactures approximately 95% of the relevant wafers, or produces wafers used in Broadcom products. A regression test now preserves passive manufacturer binding and rejects the earlier customer-type fallback.

## Interpretation

The AVGO validation confirms both precision and recall behavior:

```text
short evidence retained broadly
  -> Proxy biography and Offering language remain candidates
  -> issuer-owned VMware/product facts can be accepted
  -> explicit passive manufacturer disclosures can be accepted
  -> customer-language proximity cannot override the manufacturer relation
  -> PIT time and evidence lineage remain unchanged
  -> optional LLM/human review remains available for C/D candidates
```

This is a semantic-layer validation for already parsed AVGO rows. Parser and full-archive coverage remain governed by the separate archive validation workflow.
