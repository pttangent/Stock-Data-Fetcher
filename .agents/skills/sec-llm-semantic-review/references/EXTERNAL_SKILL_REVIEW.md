# External Financial Skill Review

## Purpose

This note records public Skill patterns reviewed while designing `sec-llm-semantic-review`. Public Skills are reference material only. Do not install or execute an external Skill bundle in the production workspace without source review, dependency review, and explicit approval.

## Skill format references

### Agent Skills specification

Source:

- https://github.com/agentskills/agentskills
- https://github.com/MicrosoftDocs/semantic-kernel-docs/blob/main/agent-framework/agents/skills.md

Useful patterns adopted:

- YAML frontmatter with precise activation description;
- progressive disclosure using `SKILL.md`, `references/`, `scripts/`, and `assets/`;
- keep the activation file focused and move detailed policies into references;
- package repeatable domain workflow and completion gates instead of vague persona instructions;
- version the skill and its supporting contracts.

## Financial and SEC skills reviewed

### Financial Deep Research

Source:

- https://www.skills.sh/eng0ai/eng0-template-skills/financial-deep-research

Useful pattern:

- phased workflow: scope, retrieve, triangulate, synthesize, critique, refine, package;
- source credibility and citation discipline;
- explicit review step before final output.

Adopted here as:

- freeze PIT scope first;
- classify source statement;
- apply form-specific logic;
- review contradiction/comparability;
- emit governed output;
- validate before promotion.

Not adopted:

- broad web research by default;
- report-oriented prose as the main output;
- allowing secondary sources to overwrite primary filing evidence.

### US Stock Researcher

Source:

- https://www.skills.sh/skindhu/skind-skills/us-stock-researcher

Useful pattern:

- SEC filing specialization;
- explicit research modes;
- professional report structure.

Not adopted:

- full investment-report generation inside the semantic extraction step;
- any workflow that mixes current web research with historical PIT extraction without separate evidence timestamps.

### TradingAgents skill

Source:

- https://clawhub.ai/huahang/skills/trading-agents-skill

Useful patterns:

- parallel specialists;
- adversarial bull/bear critique;
- dedicated risk review;
- primary-source-first and unit/period citation requirements;
- partial-failure reporting.

Adopted here as:

- separate relation, risk, event, product, quantitative, and contradiction review roles may run in parallel;
- no single reviewer can both create and approve a new assertion;
- optional challenger review for low-confidence or material claims.

Not adopted:

- BUY/SELL/HOLD output;
- position sizing, entry/exit, price targets, or portfolio decisions;
- technical indicators or sentiment inside the SEC semantic database;
- debates that are not tied to exact evidence IDs.

### Institutional Flow Tracker

Source:

- https://www.skills.sh/tradermonty/claude-trading-skills/institutional-flow-tracker

Useful patterns:

- dedicated 13F workflow;
- quarter-over-quarter holding comparison;
- structured position fields.

Hard correction applied here:

- 13F is delayed position disclosure, not a transaction tape;
- position changes do not reveal trade date within the quarter;
- a holding does not establish supplier/customer/partnership/control;
- claims that institutional flows generally lead price by a fixed number of quarters are hypotheses, not database facts.

### Edgar Crawler

Source:

- https://clawhub.ai/tangweigang-jpg/skills/edgar-crawler

Useful patterns:

- SEC User-Agent requirement;
- request rate limits, timeout, local cache, incremental processing;
- anti-pattern and lock documentation.

Not adopted:

- unrelated trading-pipeline locks;
- any rule whose evidence quality is not independently verified;
- external execution code.

### Fin Intel Hub

Source:

- https://clawhub.ai/xuan622/skills/fin-intel-hub

Useful pattern:

- separate source families for filings, market data, news, and macro data.

Adopted here as a strict source boundary:

- SEC evidence remains SEC evidence;
- yfinance remains a supplemental observed snapshot;
- external news/macro sources require separate source records and timestamps;
- source families do not silently overwrite each other.

### Financial Statements skill

Source:

- https://www.skills.sh/anthropics/knowledge-work-plugins/financial-statements

Useful patterns:

- period-over-period comparison;
- GAAP presentation awareness;
- qualified review warning;
- preserve accounting-statement distinctions.

Adopted here as:

- stock versus flow distinction;
- GAAP versus non-GAAP labeling;
- consolidated versus segment scope;
- period, currency, unit, and comparability checks.

Not adopted:

- preparation of official financial statements;
- journal-entry or accounting-close workflows.

## Security review of public Skill registries

Public Skills are executable or operational supply-chain inputs. Review findings published in 2026 indicate that registry risk cannot be handled by trusting a single marketplace badge or scanner.

Research references:

- https://arxiv.org/abs/2604.13064
- https://arxiv.org/abs/2606.01494
- https://arxiv.org/abs/2605.11418

Operational rules:

1. Never install a public financial Skill directly into the production repository.
2. Read `SKILL.md` and every bundled script before reuse.
3. Do not execute unknown install hooks, shell scripts, binaries, or dependency installers.
4. Do not provide SEC identity, API keys, database credentials, or local paths to third-party Skills.
5. Copy only reviewed conceptual patterns into a first-party skill.
6. Pin and record source version when a pattern is adopted.
7. Treat descriptions and trigger metadata as operational code because they influence agent selection.
8. Run external code only in an isolated environment with no production credentials or writable evidence store.

## Final design decision

The local first-party skill deliberately combines:

- Agent Skills progressive disclosure;
- financial deep-research phase gates;
- TradingAgents-style role separation and challenge review;
- SEC crawler operational anti-patterns;
- financial-statement comparability discipline;
- strict PIT and append-only evidence governance specific to this repository.

It deliberately excludes:

- investment recommendations;
- future-return-informed semantic labels;
- unaudited public Skill execution;
- generic whole-document LLM summaries;
- direct LLM writes to accepted database facts;
- relation inference from co-mention;
- current-web enrichment inside historical PIT review.
