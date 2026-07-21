# MU semantic rebuild validation — 2026-07-21

This validation used the current candidate-first semantic rules against the already parsed MU rows in the user's preliminary SQLite database. It did not contact SEC and did not redownload or reparse raw files.

## Scope

- MU filings rebuilt: 36
- parsed sections consumed: 202
- elapsed semantic rebuild time in the validation container: about 10.3 seconds
- ownership forms present in the tested MU filing set: 0

## Candidate and promotion result

| Result | Rows |
|---|---:|
| short evidence snippets | 654 |
| semantic candidates | 658 |
| A-level structured candidates | 42 |
| B-level deterministic candidates | 189 |
| C-level review candidates | 101 |
| D-level lexical/form-policy candidates | 281 |
| R-level rejected candidates | 45 |
| automatically accepted assertions | 231 |
| review-required candidates | 382 |
| structurally rejected candidates | 45 |

The result intentionally retains more candidates than accepted assertions. Evidence recall remains high while the formal semantic layer is narrower.

## Form-policy checks

- Accepted generic topic/concept assertions from Proxy and Offering filings: **0**.
- Accepted Offering assertions were restricted to the capital-markets whitelist.
- Accepted Proxy assertions were restricted to the governance whitelist.
- 8-K accepted events: 42.
- Offering `subscription_services` lexical candidates: 4.
- Offering `subscription_services` automatically accepted assertions: **0**.

This confirms that `subscription` in securities language remains reviewable evidence rather than becoming an issuer subscription-business fact.

## Relation and PIT checks

- accepted MU company relations: 0;
- MU self-target relations: 0;
- candidates missing `available_at`: 0;
- candidates with missing evidence foreign keys: 0.

The absence of an accepted relation is preferable to promoting an unsupported company relation. Loose relationship language remains available in `semantic_candidate` for optional review.

## Accepted generic semantics by issuer section

Generic topic/concept promotion occurred only in these issuer contexts:

- 10-K Item 1 / issuer business;
- 10-K and 10-Q Item 1A / issuer risk;
- 10-K and 10-Q MD&A;
- issuer-owned product concepts in compatible issuer sections.

Offering and Proxy copies of business language still generated short evidence and candidates, but did not duplicate those passages into accepted generic issuer topics.

## Interpretation

The structure-only semantic rebuild is operational on real parsed SEC data. It demonstrates the intended boundary:

```text
broad short-evidence capture
  -> candidate classification
  -> narrow deterministic A/B promotion
  -> C/D review queue
  -> optional LLM/human decision without changing PIT evidence
```

This is a semantic-layer validation. The earlier full archive validation remains the parser/attachment/XBRL validation.
