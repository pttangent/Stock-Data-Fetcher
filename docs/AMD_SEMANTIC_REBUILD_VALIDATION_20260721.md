# AMD semantic rebuild validation — 2026-07-21

This validation used the current candidate-first semantic rules against the already parsed AMD rows in the user's preliminary SQLite database. It did not contact SEC and did not redownload or reparse raw files.

## Scope

- AMD filings rebuilt: 44
- parsed sections consumed: 190
- elapsed semantic rebuild time in the validation container: about 13.5 seconds
- ownership forms present in the tested filing set: 0

The uploaded AMD archive contains more filings than this semantic-only test. This run covers the 44 AMD filings that had already reached `parsed` or `structured` status in the preliminary database. Full-archive parser coverage remains a separate validation.

## Candidate and promotion result

| Result | Rows |
|---|---:|
| short evidence snippets | 820 |
| semantic candidates | 833 |
| A-level structured candidates | 65 |
| B-level deterministic candidates | 266 |
| C-level review candidates | 204 |
| D-level lexical/form-policy candidates | 210 |
| R-level rejected candidates | 88 |
| automatically accepted assertions | 331 |
| review-required candidates | 414 |
| structurally rejected candidates | 88 |

Evidence recall remains broader than the accepted semantic layer.

## Relation checks

- accepted AMD company relations: 18;
- accepted AMD self-target relations: 0;
- AMD → Intel `customer_or_channel` candidates: 6;
- AMD → Intel `customer_or_channel` accepted relations: 0.

The six Intel/customer candidates all came from risk language describing Intel targeting **AMD's** customers and channel partners. Their subject binding remained unresolved, so they stayed in the review queue rather than becoming a false AMD → Intel customer relation.

The principal deterministic operating relation was:

- AMD → TSMC / Taiwan Semiconductor Manufacturing Company;
- relation: `supplier_or_manufacturer`;
- accepted evidence instances: 12 across multiple 10-K/10-Q filings;
- evidence includes issuer-bound language such as “We rely on TSMC for the production of all wafers...”

The remaining accepted relations were structured 13F investment holdings and were promoted at A level.

## Form-policy checks

- accepted generic topic/concept/company-relation assertions from Proxy and Offering filings: 0;
- Offering `subscription_services` lexical candidates: 5;
- Offering `subscription_services` automatically accepted assertions: 0;
- missing candidate `available_at`: 0;
- candidate evidence orphans: 0.

## Taxonomy precision findings and correction

The first AMD pass exposed two overly broad topic patterns:

1. `cooperative advertising` in AMD channel marketing was being treated as a digital-advertising business model;
2. generic `regulatory investigation` language in cybersecurity risk was being treated as antitrust risk.

The taxonomy was tightened so that:

- `digital_advertising` requires digital/online advertising, advertising revenue, ad impressions or advertiser-platform/revenue language;
- `antitrust_regulation` requires antitrust, competition-law, anti-competitive, competition-authority or monopoly language.

After the correction:

- AMD accepted `digital_advertising`: 0;
- AMD accepted `antitrust_regulation`: 0.

Regression tests preserve both exclusions while confirming that genuine digital-advertising revenue and antitrust language still match.

## Accepted product concepts

| Concept | Accepted evidence instances |
|---|---:|
| Instinct | 15 |
| Ryzen | 15 |
| EPYC | 9 |
| ROCm | 5 |

These concepts are issuer-owned through the explicit concept-owner map and appear in compatible AMD issuer sections.

## Interpretation

The AMD test confirms the intended design:

```text
short evidence retained broadly
  -> loose or ambiguous relationships remain candidates
  -> issuer-bound supplier language can be promoted
  -> structured 13F holdings can be promoted
  -> form-policy and taxonomy false positives do not enter the formal library
  -> optional LLM/human review remains available for Intel/NVIDIA competitor and other C-level candidates
```

The result is suitable as a semantic-layer validation for already parsed AMD filings. It is not a claim that every filing in the uploaded AMD ZIP has been parsed by this particular run.
