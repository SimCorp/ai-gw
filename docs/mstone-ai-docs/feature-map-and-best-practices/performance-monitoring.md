# Performance Monitoring


Performance monitoring enables teams to examine efficiency and code stability across groups, teams, and individual developers.

## Tracked Metrics

21 metrics are organized by data source (PM = Project Management / Git) and access level.

### Open Access Metrics (✅)

#### Cycle Time

| Metric | Source | Description |
|---|---|---|
| Issues/PR Cycle Time | PM + Git | End-to-end cycle time from issue creation to PR merge |
| Coding Time | Git | Time spent actively coding on a PR |
| Pickup Time | Git | Time from PR open to first review |
| Review Time | Git | Time spent in the review stage |
| Review Depth | Git | Depth/thoroughness of code review activity |
| PR Size | Git | Size of pull requests (lines changed) |
| CR Impact | Git | Code review impact on delivery |

#### Delivery

| Metric | Source | Description |
|---|---|---|
| Lead Time | PM + Git | Total time from work start to production |
| Completed Backlog Stories | PM | Count of completed backlog items |

#### Code Quality

| Metric | Source | Description |
|---|---|---|
| Code Changes | Git | Volume of code changes over time |
| Code Longevity | Git | How long code survives before being changed |

### Restricted Access Metrics (🔒)

#### DORA Metrics

| Metric | Source | Description |
|---|---|---|
| Deployment Frequency | Git | How often code is deployed to production |
| Lead Time for Changes | Git | Time from commit to production deployment |
| Change Failure Rate | Git | Percentage of deployments causing failures |
| MTTR / Failed Deployment Recovery Time | Git | Mean time to recover from failed deployments |

#### Quality Indicators

| Metric | Source | Description |
|---|---|---|
| Bug Density | PM + Git | Bug count relative to code volume |
| Issues out of SLA | PM | Issues not resolved within SLA targets |
| Bugs per Repo | PM + Git | Bug distribution across repositories |
| Bugs per Priority | PM | Bug breakdown by priority level |

#### Advanced Metrics

| Metric | Source | Description |
|---|---|---|
| Productiveness Score | Git | Composite score of developer productivity |
| PR/Issue Test Coverage | Git | Test coverage linked to PRs and issues |
| Coding Time vs. Estimated | PM + Git | Actual coding time compared to estimates |

## Notes

Each metric includes:
- Data source identification
- Proof-of-concept (POC) status indicator
- Specific measurement definition
- Recommended business action
