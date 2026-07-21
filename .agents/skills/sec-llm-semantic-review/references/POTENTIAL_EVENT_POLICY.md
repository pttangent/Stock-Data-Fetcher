# Potential Event Policy

## Purpose

The semantic review layer must distinguish **what has already happened** from **what may happen later**. Future possibility language is useful, but it must never be stored as a realized fact.

Potential events are stored as structured semantic assertions with:

```text
assertion_type = potential_event
predicate = potential_event
status = review_required
```

The event details live in the assertion object. A later realized event is a new assertion with its own filing, evidence, and availability time. It never retroactively changes the earlier potential event.

## Mandatory occurrence status

Every reviewed event-like claim must carry exactly one `occurrence_status`:

| Status | Meaning | Example |
|---|---|---|
| `occurred` | The event or accounting impact had happened by the source statement | AMD recorded an approximately $800M MI308-related charge |
| `ongoing` | A condition, restriction, process, or obligation was currently in force | Export licenses are required; a court remedy is in effect |
| `announced_not_occurred` | A committed plan or action was announced but had not yet occurred | A planned facility opening or product launch |
| `expected_not_occurred` | Management expects an event, amount, or result, but it has not happened | NVIDIA expected up to $5.5B of H20-related charges |
| `conditional_potential` | The event may occur only if stated conditions are met | Future China sales depend on licenses, import rules, and demand |
| `hypothetical_risk` | Generic risk-factor possibility without a specific expected event | Supply disruption could delay shipments |
| `undetermined` | Evidence does not safely establish whether it occurred | Ambiguous wording or incomplete evidence |
| `not_applicable` | The assertion is not event-like | A stable product taxonomy or explicit supplier relation |

## Fact versus potential rule

An event is `occurred` only when the eligible evidence explicitly reports that it happened, was recorded, was completed, was incurred, was issued, was granted, was terminated, or otherwise became effective.

The following language normally indicates a future or potential state:

```text
may
might
could
can
expects
anticipates
plans
intends
targets
subject to
conditioned on
depends on
if
unless
up to
potential
possible
proposed
scheduled
```

Language alone is not decisive. The reviewer must interpret grammar, tense, subject, and scope.

## Potential event object

A `potential_event` assertion should use an object shaped like:

```json
{
  "event_type": "future_export_licensed_sales",
  "occurrence_status": "conditional_potential",
  "affected_scope": {
    "product": "AMD Instinct MI308",
    "geography": "China"
  },
  "trigger_conditions": [
    "customer demand exists",
    "Chinese import rules permit shipment",
    "required U.S. export licenses are available"
  ],
  "expected_window": null,
  "quantitative_range": null,
  "probability_language": "depends on",
  "issuer_commitment_level": "conditional",
  "linked_occurred_event_id": null
}
```

Preserve nulls where the filing does not supply a field. Do not invent probability, timing, or amount.

## Occurred event object

An occurred event should be separate:

```json
{
  "event_type": "inventory_and_related_charge",
  "occurrence_status": "occurred",
  "affected_scope": {
    "product": "AMD Instinct MI308"
  },
  "amount": {
    "value": 800000000,
    "currency": "USD",
    "approximate": true
  },
  "accounting_period": "specified filing period",
  "resolves_prior_potential_review_id": null
}
```

The amount should come from deterministic XBRL/table data when available. The LLM only classifies meaning and scope.

## State transition rules

A potential event may later be resolved by a new filing:

```text
expected_not_occurred -> occurred
conditional_potential -> occurred
conditional_potential -> no longer expected
announced_not_occurred -> occurred
hypothetical_risk -> occurred
```

Rules:

1. Preserve the original potential assertion and original `available_at`.
2. Create a new occurred or cancelled/resolved assertion at the later evidence time.
3. Link the later review record through `resolves_prior_review_id` when the match is explicit.
4. Never use later evidence to relabel the earlier potential assertion as if it had already occurred.
5. A later outcome may resolve the event state, but it must not change the earlier confidence or wording retrospectively.

## Cancellation and non-occurrence

If a later filing explicitly states that a plan was cancelled, withdrawn, expired, abandoned, or no longer expected, create a new assertion with:

```text
occurrence_status = occurred
predicate = potential_event_resolution
resolution = cancelled | withdrawn | expired | abandoned | no_longer_expected
```

Do not delete the original potential event.

## Product lifecycle mapping

Product lifecycle language must use occurrence status:

| Filing statement | Correct status |
|---|---|
| Samples were delivered | `occurred` for sampling |
| Volume production began | `occurred` for volume production |
| Production is expected next year | `expected_not_occurred` |
| Launch is planned for Q4 | `announced_not_occurred` |
| Ramp depends on customer qualification | `conditional_potential` |
| A transition could create excess inventory | `hypothetical_risk` |

One product may have multiple simultaneous claims, for example:

```text
HBM4 sampling -> occurred
HBM4 volume production -> not established
HBM4 future qualification/ramp -> potential only if explicitly stated
```

## Financial guidance and targets

Guidance, compensation targets, and scenario ranges are potential states, not actual results.

Examples:

- “expected up to $5.5B charge” -> `expected_not_occurred`;
- later “recorded $4.5B charge” -> separate `occurred` assertion;
- CEO PSU “AI Revenue” target -> `conditional_potential`, not revenue guidance and not realized revenue;
- planned capex -> `announced_not_occurred` or `expected_not_occurred`, depending on wording;
- contractual commitment already signed -> agreement `occurred`, future payments remain scheduled obligations.

## Risk-factor language

Risk disclosures normally produce `hypothetical_risk`, not occurred events.

Only upgrade to `occurred` when the evidence explicitly states that the adverse condition has happened. Phrases such as “has adversely affected,” “we incurred,” “we recorded,” or “operations were disrupted” may support occurrence when scope is clear.

A risk paragraph may contain both:

```text
occurred impact
ongoing condition
future conditional potential
hypothetical broader risk
```

Split them into separate atomic assertions.

## PIT rule

Potential and occurred events use the same PIT gate:

- both become known only at their own governed `source_available_at`;
- the economic event time may precede filing availability but does not permit earlier use;
- later realized evidence cannot enter an earlier signal timestamp;
- a backtest must preserve the knowledge state that existed at each decision time.

## Uploaded archive examples

### MU HBM4

```text
Delivered HBM4 samples -> occurred
HBM4 volume production -> not established
Future customer qualification or production -> potential only if explicitly stated
```

### AMD MI308

```text
Approximately $800M charge recorded -> occurred
Export licensing requirement -> ongoing
Some licenses granted -> occurred
Future China sales depending on demand/rules/licenses -> conditional_potential
```

### NVIDIA H20

```text
April expected up to $5.5B charge -> expected_not_occurred
May reported $4.5B charge -> occurred
Material reuse explanation -> management_interpretation, not a separate future event
```

### AVGO AI Revenue PSU

```text
Compensation metric and target framework adopted -> occurred
Future achievement of target -> conditional_potential
Target amount -> not realized revenue and not ordinary company guidance
```

### GOOGL antitrust remedy

```text
Court remedies decision issued -> occurred
Obligations currently applicable -> ongoing
Future implementation or financial effect -> expected/conditional only if stated
```

## Completion gate

Reject an event-review batch when any of these is non-zero:

```text
missing_occurrence_status
potential_stored_as_occurred
occurred_stored_as_potential
later_resolution_rewrites_prior_state
future_amount_stored_as_actual
condition_missing_for_conditional_event
invented_probability
invented_event_date
```
