# Point-in-Time Policy for SEC Semantic Review

## Core timestamps

The pipeline must keep these timestamps distinct:

| Field | Meaning | Research use |
|---|---|---|
| `report_date` | Economic/reporting period end | Never an availability timestamp |
| `filing_date` | Official EDGAR filing date | Date-level fallback only |
| `accepted_at` | EDGAR acceptance timestamp | Primary public-system timestamp when dissemination is not deferred |
| `available_at` | Governed public availability timestamp | Base timestamp for historical evidence eligibility |
| `observed_at` | Time the local pipeline retrieved or observed the evidence | Required for live operational use |
| `processed_at` | Time parsing/review completed | Required for live latency accounting |
| `signal_timestamp` | Historical decision time being simulated | Evidence must be usable no later than this time |
| `effective_from` | Economic period or state start described by the claim | Does not permit pre-availability trading use |
| `effective_to` | End of the claim's economic validity, when known | Must not retroactively erase prior knowledge states |

## Public availability rule

Default governed research availability is:

```text
public_usable_at = available_at
```

`available_at` should be derived from EDGAR `acceptanceDateTime` when the filing is disseminated on acceptance. However, SEC guidance states that most live submissions transmitted after 5:30 p.m. ET may receive the next business day's filing date and may not be disseminated until the next business day. Therefore the pipeline must support a conservative dissemination adjustment for affected forms.

Official references:

- SEC filing status and filing-date guidance: https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/determine-status-my-filing
- SEC EDGAR data access and dissemination guidance: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- SEC filing-date adjustment guidance: https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/request-filing-date-adjustment

## Conservative dissemination adjustment

For backtests, use a configurable form-aware rule rather than assuming every accepted filing was instantly tradeable.

Recommended default for 10-K, 10-Q, 8-K, 20-F, 40-F, 6-K, proxy, SD, CORRESP, registration, and prospectus forms:

1. If `accepted_at` is at or before 17:30 America/New_York on an EDGAR business day, set `available_at = accepted_at`.
2. If accepted after 17:30 and the form is subject to next-business-day dissemination, set `available_at` to the next EDGAR business day's configured dissemination boundary.
3. Record the rule version and whether the time is `exact`, `derived`, or `date_fallback`.
4. Never replace the original `accepted_at`; store the governed availability separately.

Forms with different SEC cut-off treatment must use a form-specific rule. Do not generalize the standard 17:30 rule to every EDGAR submission type.

## Backtest usable time

For historical research:

```text
backtest_usable_at = public_usable_at + configured_information_latency
```

Rules:

- The information latency must be fixed before evaluating alpha.
- Do not choose latency after seeing returns.
- Do not use the same bar in which evidence became available.
- Map the evidence to the first decision timestamp strictly after `backtest_usable_at`.
- For 15-minute decisions, an item available at 10:02 ET is not usable at the 10:00 decision and should normally enter at 10:15 or later, subject to the configured latency.
- If only date precision is available, exclude the evidence from intraday tests. A conservative daily test may make it usable at the next market session open.

## Live usable time

For live operation:

```text
live_usable_at = max(public_usable_at, observed_at, processed_at)
```

A live system cannot act on evidence before the local pipeline received and processed it. `accepted_at` alone is insufficient for live latency measurement.

## Amendment and correction policy

- Original filings and amendments are separate evidence events.
- An amendment becomes usable only at the amendment's own governed `available_at`.
- Do not rewrite the historical database as though the amended content had been known earlier.
- A superseded semantic assertion keeps its original record and receives `effective_to` or a superseding link at the amendment's availability time.
- A later filing may contradict an earlier filing; preserve both knowledge states.

## Cross-document comparison

A disclosure delta at time `T` may compare only documents whose governed availability is at or before `T`.

Preferred comparisons:

- 10-K vs prior 10-K;
- 10-Q vs prior comparable 10-Q and most recent 10-K where appropriate;
- 8-K event vs prior eligible event or most recent eligible guidance;
- proxy vs prior proxy;
- 13F vs prior 13F reporting period, while respecting delayed disclosure.

Do not compare against a later restatement, amendment, earnings release, or media explanation when evaluating the earlier state.

## Price and outcome firewall

During semantic review, the reviewer must not see:

- returns after `signal_timestamp`;
- whether a trade based on the assertion was profitable;
- future analyst estimates or ratings;
- later company outcomes used to judge whether an earlier risk statement was prescient;
- later taxonomy labels derived from future disclosures.

The semantic representation must be judged only on evidence available at the frozen PIT boundary.

## Date precision fallback

If `accepted_at` is absent:

- keep `available_at_precision = date`;
- never synthesize a false exact timestamp;
- prohibit intraday use;
- for conservative daily research, make the item eligible no earlier than the next market session;
- record the fallback rule and source field.

## Completion checks

A PIT-safe batch requires:

```text
missing_available_at = 0
used_after_signal_timestamp = 0
intraday_date_precision_evidence = 0
future_amendment_leakage = 0
future_price_visibility = 0
unversioned_dissemination_rules = 0
```
