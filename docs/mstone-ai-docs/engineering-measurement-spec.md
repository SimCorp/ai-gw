# Engineering Measurement Specification

This document defines how engineering performance, investment, and GenAI utilization are measured across the organization. It is intended for engineering leaders, platform teams, and analysts who need to understand what is measured, how, and what actions the data should drive.

---

## 1. Performance Monitoring

**Goal:** Gain insight into engineering efficiency and code stability across groups, teams, and individual developers. Identify bottlenecks in the delivery pipeline and track improvement over time.

### Data Sources

| Source | What it provides |
|---|---|
| **Git** | PR activity, coding time, commit metadata, deployment events |
| **PM (Project Management)** | Issue lifecycle, backlog completion, SLA tracking, bug priority |

### 1.1 Cycle Time Metrics

These measure how long work takes to move through the delivery pipeline.

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **PR Cycle Time** | Time from PR open to merge (includes coding, pickup, review) | Trending down week-over-week | Identify which stage is the bottleneck and address it |
| **Coding Time** | Active commit activity duration on a branch | Consistent with story complexity estimates | Flag outliers — may indicate unclear requirements or blockers |
| **Pickup Time** | Time between PR creation and first reviewer comment | Under 4 hours for critical paths | Set review SLAs; alert when PRs sit idle |
| **Review Time** | Duration from first review comment to approval | Proportional to PR size | Large review times on small PRs indicate unclear code or missing context |
| **Review Depth** | Number of substantive review comments per PR | Non-trivial engagement on every PR | Low depth may signal rubber-stamping; high depth may signal poor code quality |
| **PR Size** | Lines of code added/removed per PR | Under 400 lines for most PRs | Large PRs slow reviews; coach teams to decompose work |
| **CR Impact** | Correlation between review activity and delivery speed | Positive correlation | Benchmark before/after changes to review practices |

### 1.2 Delivery Metrics

These measure throughput and alignment with planned work.

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **Lead Time** | Time from issue creation to production deployment | Trending down; within sprint commitment | Long lead times indicate WIP overload or deployment bottlenecks |
| **Completed Backlog Stories** | Count of issues closed per period | Stable or increasing velocity | Sudden drops may indicate unplanned work or external blockers |

### 1.3 Code Quality Metrics

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **Code Changes** | Volume (LOC) changed per period by team/repo | Steady; proportional to headcount | Spikes may signal rewrites or tech debt paydown; dips may signal inactivity |
| **Code Longevity** | How long code survives before being modified | High longevity in stable core modules | Low longevity in core code indicates instability or rework |

### 1.4 DORA Metrics (Restricted)

Industry-standard benchmarks for deployment health.

| Metric | How It Is Measured | Elite Target | Action When Off-Track |
|---|---|---|---|
| **Deployment Frequency** | Deployments to production per period | Multiple per day | Low frequency signals batch releases and high-risk deploys |
| **Lead Time for Changes** | Commit-to-production duration | Under 1 hour | Long lead times indicate pipeline or environment bottlenecks |
| **Change Failure Rate** | % of deployments that cause an incident or rollback | Under 5% | Invest in test coverage and canary deployments |
| **MTTR** | Time from incident detection to recovery | Under 1 hour | Invest in observability, runbooks, and on-call tooling |

### 1.5 Quality Indicators (Restricted)

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **Bug Density** | Bug count normalized to code volume (KLOC) | Declining per release | High density in specific repos → targeted quality reviews |
| **Issues out of SLA** | Count of issues not resolved within agreed time targets | Zero or near-zero | Triage backlog; review priority assignment process |
| **Bugs per Repo** | Bug distribution mapped to repositories | Even distribution or concentrated in known legacy areas | Concentrated bugs → dedicated stabilization sprints |
| **Bugs per Priority** | P1/P2/P3 breakdown over time | Declining P1/P2 count | Rising critical bugs → release gate reviews |

### 1.6 Advanced Metrics (Restricted)

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **Productiveness Score** | Composite of cycle time, throughput, and review engagement | Stable or improving trend | Score drops without headcount change → investigate morale or process friction |
| **PR/Issue Test Coverage** | Test coverage associated with each PR or issue | Coverage maintained or improved on every PR | Declining coverage → enforce coverage gates in CI |
| **Coding Time vs. Estimated** | Actual coding time compared to PM estimates | Within ±20% on average | Persistent underestimates → improve estimation practices or break work into smaller units |

---

## 2. Engineering Investment

**Goal:** Understand where engineering resources are being allocated across the organization and identify areas of waste or misalignment with strategic priorities.

### Data Sources

| Source | What it provides |
|---|---|
| **Git** | Commit activity, code volume, branch lifecycle |
| **PM** | Issue types, initiatives, estimated vs. actual effort |

### 2.1 Measurement Framework

Engineering effort is expressed either as normalized effort units or monetized ($ spend equivalent based on headcount cost), enabling direct comparison with business outcomes.

### 2.2 Metrics

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **Engineering Effort Overview** | Total effort (hours or $) aggregated by team, group, and period | Effort proportional to strategic priority | Realign team allocations when effort and roadmap diverge |
| **Wasted Spend / Non-Prod Work** | % of effort on code that has been idle for >3 months or never deployed to production | Below 10% of total effort | Identify idle code; decide to ship, archive, or delete |
| **Investment by Work Type** | Effort breakdown across: new features, maintenance, tech debt, operations, and other | Majority in new value delivery; <30% in maintenance | Use as input to quarterly planning when maintenance creep is detected |
| **Teams/Groups Work Time per Category** | Per-team effort cross-tabulated by work type | Even distribution aligned with team charters | Teams spending disproportionately on maintenance may need refactoring investment |
| **Non-Prod Work Analysis** | Non-production effort per team/group by effort type | Minimized; tracked trends | Persistent non-prod work may indicate unclear deployment practices |
| **Feature Spend by Issue Type** | Dev effort mapped to initiatives and individual issues from PM | Spend concentrated on highest-value initiatives | Use to validate that roadmap investment matches delivery evidence |
| **Coding Time vs. Estimated (Feature/Issue)** | Actual coding time per feature or issue vs. PM estimate | Within ±20% at issue level; closer at aggregate | Persistent overruns → decompose work earlier; persistent underestimates → review velocity assumptions |

---

## 3. GenAI Utilization and Impact

**Goal:** Track adoption of GenAI coding tools (e.g. GitHub Copilot, Cursor, Codium, Augment) across teams, measure actual contribution to engineering output, and calculate return on investment.

### Data Sources

| Source | What it provides |
|---|---|
| **GenAI API** | Seat assignments, active users, suggestion acceptance rates, usage by language |
| **Git** | Commits, PRs, LOC attributable to GenAI-assisted sessions |
| **Qodo** | PR and LOC coverage from Qodo Gen specifically |

### 3.1 Adoption Metrics

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **GenAI Adoption Rate** | % of licensed developers with at least one active session in the period | >70% monthly active among licensed seats | Identify low-usage teams; run targeted enablement or training |
| **Active Users** | Unique users with at least one session per week/month | Growing month-over-month | Flat or declining active users → investigate friction or poor suggestion quality |
| **Usage Distribution** | Frequency segmentation: Rare (<1/week), Occasional (1–3/week), Regular (daily) | Majority in Regular tier | Large Rare segment → re-run onboarding; gather qualitative feedback |
| **Developers per Product** | Adoption rate broken down by GenAI tool (Copilot, Codium, etc.) | Tool mix aligned with team language/workflow | Low adoption of a specific tool → evaluate if it fits the team's stack |

### 3.2 Engagement Metrics

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **Accepted Code Completion Suggestions** | Accepted suggestions ÷ total suggestions shown | >30% acceptance rate | Low acceptance → suggestions are poor quality or misconfigured for the codebase |
| **Engagement Patterns** | Usage broken down by programming language and command type | Broad usage across primary languages | Narrow usage (e.g. only boilerplate) may indicate developers don't trust the tool for complex work |
| **Commits Impacted by GenAI** | Commits containing GenAI-assisted code as % of all commits | Growing week-over-week | Plateau may indicate adoption ceiling; investigate if tools are set up on critical workflows |

### 3.3 Quality & Review Impact Metrics

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **Activities Impacted by GenAI Tools** | Code commits, test commits, and PR reviews that include GenAI-assisted content | GenAI present across all activity types, not just code generation | If only code commits are impacted, expand use to test generation and review assistance |
| **Qodo Gen: Impacted PRs** | PRs with Qodo Gen involvement ÷ total PRs | >50% of PRs touched | Low % → expand Qodo configuration to additional repos |
| **Qodo Gen: Impacted LOCs** | LOC written with Qodo Gen ÷ total LOC | Growing share over time | Stagnant share → reassess tool placement in the workflow |

### 3.4 ROI Metrics

| Metric | How It Is Measured | What Good Looks Like | Action When Off-Track |
|---|---|---|---|
| **Productivity Impact** | Delta in cycle time, bug rate, and code longevity between high-GenAI and low-GenAI cohorts | Shorter cycle time, fewer bugs, longer-lived code in high-GenAI cohort | No measurable delta → investigate whether adoption is real or superficial; re-evaluate tooling choice |

### 3.5 Calculating ROI

A simple ROI frame:

```
ROI = (Value Gained − Cost of Licenses) / Cost of Licenses

Value Gained = (Hours saved per developer per month) × (Number of active developers) × (Average fully-loaded hourly rate)

Hours saved = measured as reduction in coding time for comparable tasks (GenAI-assisted vs. baseline cohort)
```

Track this monthly and compare against the license cost per seat to produce a running ROI figure for executive reporting.

---

## Summary: Measurement Cadence

| Area | Recommended Review Cadence | Primary Audience |
|---|---|---|
| Performance Monitoring (cycle time, DORA) | Weekly | Engineering leads, team leads |
| Engineering Investment | Monthly / Quarterly | VP Engineering, Finance |
| GenAI Utilization | Monthly | Platform team, engineering leadership |
| GenAI ROI | Quarterly | CTO, VP Engineering, Finance |
