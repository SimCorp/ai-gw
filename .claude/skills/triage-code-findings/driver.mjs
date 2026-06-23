#!/usr/bin/env node
// triage-code-findings driver
//
// Pulls open security/quality findings from GitHub and creates ONE issue PER
// source — Code scanning (CodeQL), Secret scanning, and Dependabot — each
// triaged (grouped + ranked) with a handoff section for the implementing agent.
//
// Dry-run by default (prints each issue body). Pass --create to open the issues
// via `gh issue create`. A source with zero open findings is skipped (no empty
// issue). Requires `gh` authenticated with security_events read (repo admin/maintainer).
//
// Usage:
//   node driver.mjs                          # dry-run, all 3 sources, current repo
//   node driver.mjs --include code,secret    # only these sources
//   node driver.mjs --severity high          # filter code/dependabot to >= high
//   node driver.mjs --create --assignee @me  # actually open the issues
//
// Flags:
//   --repo owner/name   target repo (default: current dir's repo via gh)
//   --include LIST      sources: code,secret,dependabot (default: all three)
//   --severity LEVEL    minimum severity for code+dependabot: critical|high|medium|low
//   --label LIST        extra labels added to every issue (source labels are automatic)
//   --assignee USER     assignee for every issue (e.g. @me)
//   --create            create the issues (otherwise print bodies to stdout)

import { execFileSync } from "node:child_process";

const args = process.argv.slice(2);
const flag = (name, def = null) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : def;
};
const has = (name) => args.includes(`--${name}`);

const SEV_ORDER = ["critical", "high", "medium", "low", "warning", "note", "error", "unknown"];
const SEV_RANK = Object.fromEntries(SEV_ORDER.map((s, i) => [s, i]));
const sevRank = (s) => SEV_RANK[s] ?? SEV_ORDER.length;

function ghJSON(path) {
  try {
    const out = execFileSync("gh", ["api", "--paginate", "--slurp", path], {
      encoding: "utf8", maxBuffer: 64 * 1024 * 1024,
    });
    let data = JSON.parse(out);
    if (Array.isArray(data) && data.length && Array.isArray(data[0])) data = data.flat();
    return Array.isArray(data) ? data : [];
  } catch (e) {
    const msg = (e.stderr || e.message || "").toString();
    // Feature off, no analysis yet, or caller lacks read access → skip this source.
    if (/404|403|no analysis found|not enabled|Not Found|disabled|not authorized|Forbidden|scope/i.test(msg)) return null;
    throw new Error(`gh api ${path} failed: ${msg.trim().split("\n").slice(0, 2).join(" ")}`);
  }
}

let repo = flag("repo");
if (!repo) {
  try {
    repo = execFileSync(
      "gh",
      ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
      { encoding: "utf8" },
    ).trim();
  } catch (e) {
    const msg = (e.stderr || e.message || "").toString().trim().split("\n")[0];
    throw new Error(
      `Unable to determine target repo. Run from a git checkout or pass --repo owner/name. ${msg}`,
    );
  }
}
const minSev = flag("severity");
const extraLabels = flag("label");
const assignee = flag("assignee");
const today = new Date().toISOString().slice(0, 10);
const sevOK = (s) => !minSev || sevRank(s) <= sevRank(minSev);

const PR_NOTE = `Code changes ship via PR (\`${repo}\` is PR-only — no direct pushes to the default branch). Reference this issue (\`Refs #<this>\`).`;

// ── Fetch + normalize per source ─────────────────────────────────────────────
function fetchCode() {
  const raw = ghJSON(`repos/${repo}/code-scanning/alerts?state=open&per_page=100`);
  if (raw === null) return null;
  return raw.map((a) => {
    const loc = a.most_recent_instance?.location || {};
    return {
      number: a.number,
      sev: (a.rule?.security_severity_level || a.rule?.severity || "unknown").toLowerCase(),
      ruleId: a.rule?.id || "?", desc: a.rule?.description || a.rule?.name || "",
      path: loc.path, line: loc.start_line, url: a.html_url,
    };
  }).filter((f) => sevOK(f.sev));
}
function fetchSecret() {
  const raw = ghJSON(`repos/${repo}/secret-scanning/alerts?state=open&per_page=100`);
  if (raw === null) return null;
  return raw.map((a) => ({
    number: a.number, type: a.secret_type_display_name || a.secret_type,
    validity: a.validity || "unknown", url: a.html_url,
  }));
}
function fetchDependabot() {
  const raw = ghJSON(`repos/${repo}/dependabot/alerts?state=open&per_page=100`);
  if (raw === null) return null;
  return raw.map((a) => ({
    number: a.number, sev: (a.security_advisory?.severity || "unknown").toLowerCase(),
    pkg: a.dependency?.package?.name, manifest: a.dependency?.manifest_path,
    summary: a.security_advisory?.summary, url: a.html_url,
  })).filter((f) => sevOK(f.sev));
}

// ── Builders: each returns {title, body, labels} or null when no findings ─────
const sevCounts = (list) => {
  const m = {};
  for (const f of list) m[f.sev] = (m[f.sev] || 0) + 1;
  return Object.keys(m).sort((a, b) => sevRank(a) - sevRank(b)).map((s) => `${m[s]} ${s}`).join(", ");
};
const header = (n, src) => [
  `> Auto-generated by the \`triage-code-findings\` skill on ${today} from \`${repo}\` (${src}).`,
  `> **${n}** open finding(s).`, "",
];

function buildCode(list) {
  if (!list?.length) return null;
  const bySev = {};
  for (const f of list) (bySev[f.sev] ??= []).push(f);
  const sevs = Object.keys(bySev).sort((a, b) => sevRank(a) - sevRank(b));
  const L = header(list.length, "Code scanning / CodeQL");
  for (const sev of sevs) {
    L.push(`## ${sev.toUpperCase()} — ${bySev[sev].length}`, "");
    const m = {};
    for (const f of bySev[sev]) (m[f.ruleId] ??= { desc: f.desc, items: [] }).items.push(f);
    for (const [ruleId, g] of Object.entries(m).sort((a, b) => b[1].items.length - a[1].items.length)) {
      L.push(`<details><summary><b>${ruleId}</b> — ${g.desc} (${g.items.length})</summary>`, "");
      for (const f of g.items) L.push(`- [ ] [#${f.number}](${f.url}) — \`${f.path}:${f.line}\``);
      L.push("", "</details>", "");
    }
  }
  L.push("## 🤝 Handoff — implementing agent", "");
  L.push("**Goal:** resolve or formally dismiss every checkbox.", "");
  L.push("1. Work highest severity first; fix a whole rule group together — same pattern repeats.");
  L.push("2. Per finding: read the data-flow on the linked alert, then **fix the code** or **dismiss** it in the Security tab with a reason (`false positive` / `used in tests` / `won't fix`) + one-line justification.");
  L.push(`3. ${PR_NOTE}`);
  L.push("4. **Verify:** pushing the branch re-runs CodeQL on the PR; the alert flips to `Fixed`/`Closed` when resolved. Re-run this skill to confirm the count dropped.");
  return { title: `🔎 Code scanning triage: ${list.length} CodeQL finding(s) (${sevCounts(list)}) — ${today}`, body: L.join("\n"), labels: ["security", "code-scanning"] };
}

function buildSecret(list) {
  if (!list?.length) return null;
  const L = header(list.length, "Secret scanning");
  L.push("⚠️ A detected secret may be **live and is in git history** — deleting the line is not enough; **rotate** it. Confirm real-vs-fixture for each, then dismiss false positives.", "");
  for (const s of list) L.push(`- [ ] [#${s.number}](${s.url}) — **${s.type}** (validity: ${s.validity})`);
  L.push("", "## 🤝 Handoff — implementing agent", "");
  L.push("1. Open each alert; identify the file/commit and whether the secret is real or a fixture/example.");
  L.push("2. **If real:** rotate/revoke the credential at the provider immediately, replace usage with a secret store, and dismiss as `revoked`. (History rewrite is optional and high-risk — rotation is what matters.)");
  L.push("3. **If fixture/example:** dismiss as `used in tests` / `false positive` with a one-line note.");
  L.push(`4. ${PR_NOTE}`);
  return { title: `🔐 Secret scanning triage: ${list.length} secret alert(s) — ${today}`, body: L.join("\n"), labels: ["security", "secret-scanning"] };
}

function buildDependabot(list) {
  if (!list?.length) return null;
  const L = header(list.length, "Dependabot");
  const bySev = {};
  for (const f of list) (bySev[f.sev] ??= []).push(f);
  for (const sev of Object.keys(bySev).sort((a, b) => sevRank(a) - sevRank(b))) {
    L.push(`## ${sev.toUpperCase()} — ${bySev[sev].length}`, "");
    for (const d of bySev[sev]) L.push(`- [ ] [#${d.number}](${d.url}) — **${d.pkg}** \`${d.manifest || ""}\`: ${d.summary}`);
    L.push("");
  }
  L.push("## 🤝 Handoff — implementing agent", "");
  L.push("1. Most are fixable by merging the Dependabot **PR** (security updates are enabled) — check the Pull requests tab first.");
  L.push("2. Where no PR exists, bump the dependency manually to the patched version.");
  L.push(`3. ${PR_NOTE}`);
  L.push("4. **Verify:** the alert auto-closes once the patched version is on the default branch. Re-run this skill to confirm.");
  return { title: `📦 Dependabot triage: ${list.length} vulnerable dep alert(s) (${sevCounts(list)}) — ${today}`, body: L.join("\n"), labels: ["security", "dependencies"] };
}

// ── Drive ────────────────────────────────────────────────────────────────────
const sources = [
  ["code", fetchCode, buildCode],
  ["secret", fetchSecret, buildSecret],
  ["dependabot", fetchDependabot, buildDependabot],
].filter(([name]) => include.includes(name));

const issues = [];
for (const [name, fetch, build] of sources) {
  const data = fetch();
  if (data === null) { console.error(`note: ${name} not enabled / no analysis for ${repo} — skipped`); continue; }
  const issue = build(data);
  if (!issue) { console.error(`note: ${name} has 0 open findings — no issue`); continue; }
  if (extraLabels) issue.labels.push(...extraLabels.split(",").map((s) => s.trim()));
  issues.push(issue);
}

if (issues.length === 0) { console.error("Nothing to triage."); process.exit(0); }

if (!has("create")) {
  for (const it of issues) {
    console.log(`\n${"=".repeat(80)}\n# ${it.title}\n# labels: ${it.labels.join(", ")}\n${"=".repeat(80)}\n`);
    console.log(it.body);
  }
  console.error(`\n--- dry run: would create ${issues.length} issue(s). Re-run with --create. ---`);
  process.exit(0);
}

// ensure labels exist (idempotent) so `gh issue create --label` can't fail
const COLORS = { security: "b60205", "code-scanning": "d93f0b", "secret-scanning": "5319e7", dependencies: "0366d6" };
for (const name of new Set(issues.flatMap((i) => i.labels))) {
  try { execFileSync("gh", ["label", "create", name, "--repo", repo, "--color", COLORS[name] || "ededed"], { stdio: "ignore" }); } catch {}
}
for (const it of issues) {
  const a = ["issue", "create", "--repo", repo, "--title", it.title, "--body", it.body, "--label", it.labels.join(",")];
  if (assignee) a.push("--assignee", assignee);
  console.log(execFileSync("gh", a, { encoding: "utf8" }).trim());
}
