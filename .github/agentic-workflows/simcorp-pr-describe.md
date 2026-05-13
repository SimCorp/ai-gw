---
name: "PR Description Generator"
description: >
  Generates a structured SimCorp PR description when an engineer applies
  the 'ai-describe' label. Routes inference through the AI Gateway for
  caching, cost attribution, and guardrails.

on:
  label_command: ai-describe
  status-comment: true

engine:
  id: codex
  model: claude-haiku-4-5
  env:
    OPENAI_BASE_URL: ${{ vars.AIGW_BASE_URL }}
    OPENAI_API_KEY: ${{ secrets.AIGW_API_KEY }}

network:
  allowed:
    - defaults
    - aigw.simcorp.internal

tools:
  github:
    toolsets:
      - context
      - repos
      - pull_requests
      - issues
    read-only: true

permissions:
  contents: read
  pull-requests: read
  issues: read

safe-outputs:
  update-pull-request:
    max: 1
  add-labels:
    allowed: [description-generated]
    max: 1
  add-comment:
    max: 1
---

# PR Description Generator

You are a technical writer for SimCorp's AI Gateway team. Generate a
structured pull request description for the current PR.

Use the GitHub tools to:
1. Read the full PR diff
2. Read all changed files to understand their purpose
3. Read any linked issue (from the PR body or branch name)
4. Read recent commit messages for context

Then update the PR description using this exact structure:

```markdown
## Summary
<!-- 2-4 sentences explaining what this PR does and why -->

## Changes
<!-- Bullet list of key technical changes, grouped by service/area -->
- **service/component**: what changed and why

## Testing
<!-- How was this tested? What scenarios were covered? -->

## Breaking Changes
<!-- List any breaking changes to APIs, schemas, or behaviour. 
     "None" if not applicable. -->

## Reviewer Checklist
- [ ] Code is correct and follows existing patterns
- [ ] Tests cover the changed behaviour
- [ ] Documentation updated if needed
- [ ] No hardcoded secrets or credentials
```

Be specific and technical. Reference the actual service names, function
names, and file paths involved. Do not write generic descriptions.
If you cannot determine the purpose of a change, say so explicitly
rather than guessing.
