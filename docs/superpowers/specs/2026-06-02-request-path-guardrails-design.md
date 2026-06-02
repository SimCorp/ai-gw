# Request-Path Safety Guardrails (output scanning + redaction)

**Date:** 2026-06-02
**Status:** Approved (autonomous build under /goal) — feature #4 (riskiest; hot path)
**Spec + plan combined.**

## Problem & key finding

Most of the guardrail path already exists in the **cache** service (`services/cache/app/router.py`):
- Admin CRUD + admin→Redis sync of enabled rules (`guardrails:{team_id}`, `guardrails:global`).
- `_load_guardrails` (Redis, 60s) and `_check_guardrails` already run on the **input** with `block`
  (raises `_BlockedByGuardrail` → 400) and `flag` (async hit to observability).

**Missing pieces** (this feature):
1. **Output-side enforcement** — the model completion is never scanned.
2. **The `redact` action** — only `block`/`flag` are honoured; `redact` (mask matched content) is a no-op
   today. Redaction is the core of "PII/content enforcement."

## Design (surgical refactor of existing hot-path code; fail-open)

Extract the per-rule matching into a **pure, unit-testable** function and reuse it for input + output:

```python
@dataclass
class GuardrailOutcome:
    blocked_rule: str | None        # name of the first block rule that matched, else None
    text: str                       # input text with redactions applied (unchanged if none)
    hits: list[dict]                # one per matched rule, ready for _emit_guardrail_hit

def evaluate_guardrails(rules: list[dict], text: str, direction: str) -> GuardrailOutcome:
    """direction in {"input","output"}. Considers rules whose applies_to includes direction
    (input→{input,both}, output→{output,both}) and enabled. For each matched rule:
      - action 'block'  -> set blocked_rule (first wins), record hit, stop.
      - action 'redact' -> replace every match of each pattern with the rule's mask
                           (config.mask or '[REDACTED]') in `text`, record hit.
      - action 'flag' (or anything else) -> record hit only.
    Regex compiled via a module-level lru_cache; a bad pattern is skipped (never raises)."""
```

**Input path** (replace the body of the existing `_check_guardrails` call site, ~router.py:484):
load rules → `evaluate_guardrails(rules, prompt_text, "input")` → emit each hit async → if
`blocked_rule`: return the existing 400 `blocked_by_guardrail` JSON → else if text changed by
redaction, rewrite the prompt in `body` (the last user message / prompt) with the redacted text
before cache-key computation and upstream forward.

**Output path** (NEW, non-streaming only, after `response_body = resp.json()`, ~router.py:702,
before the `exact.set`/`semantic.set` caching): if `resp.status_code == 200` and the response is not
streamed, extract the completion text (`choices[0].message.content`), reuse the already-loaded rules,
`evaluate_guardrails(rules, completion, "output")` → emit hits → if `blocked_rule`: replace the
completion content with a safety notice (`"[response withheld by guardrail: <name>]"`) and do NOT
cache it → else if redacted, replace `choices[*].message.content` with the redacted text (and cache
the redacted version, so future cache hits are safe too).

**Risk controls (hot path):**
- **Fail-open** everywhere except `block`: any exception in load/evaluate/redact logs and passes the
  original text through unchanged. `block` is the only fail-closed action and is preserved exactly.
- **No new per-request work beyond a single rules load** (already happens for input; reuse the same
  list for output — pass it through, don't reload).
- **Compiled-pattern cache** (`functools.lru_cache`) avoids recompiling regex each request.
- **Streaming responses are not scanned** (documented limitation — can't redact a stream without
  buffering; `block`/`flag`/`redact` apply to non-streaming completions only). Input guardrails still
  apply to streaming requests (input is always buffered).

## Correctness requirements (pinned from review)

- **Provider scope = OpenAI-compatible path only** (`/v1/chat/completions[/auto]`), where guardrail
  enforcement already lives. The `/anthropic/*` native passthrough is **NOT guarded** — this is a
  *pre-existing* gap (input block never ran there either), and Anthropic's content-block/streaming
  body shape needs its own design. **Document this loudly** in the PR; it is a tracked follow-up, not
  silently dropped.
- **Redaction is per-message.** `_prompt_text` concatenates all messages, so block/flag may scan the
  concatenation, but `redact` MUST be applied by the caller to each `message.content` string
  individually (loop the `messages` array; skip non-string content). `evaluate_guardrails` works on
  one string; the caller maps it over messages.
- **Output: iterate all `choices`, skip null content.** Real completions have
  `choices[i].message.content == null` (tool/function calls) and may have `n > 1`. Never assume
  `choices[0].message.content` is a string.
- **Output block must NOT skip usage/cost accounting.** The tokens were already spent. Insert output
  enforcement so the existing observability/usage emit still runs (replace content + skip cache, but
  fall through to the usage emit — do not early-return past it).
- **Priority order:** the admin sync writes rules `ORDER BY priority ASC`, so the Redis list is
  already priority-sorted; evaluate in list order (block-first-wins respects priority).
- **Streaming:** input guardrails already fire on `stream:true` (input hook precedes the stream
  branch — keep it that way). Only *output* scanning is skipped for streamed responses.

## Out of scope
- The `/anthropic/*` native path (documented follow-up — see above).
- `rewrite` / `route` / `truncate` actions (not core PII/content; keep YAGNI).
- ML-based PII classification (regex/pattern rules only, as the registry already models).
- Scanning/redacting streamed completions.

## Plan (TDD)
1. **Pure `evaluate_guardrails` + `GuardrailOutcome`** in `services/cache/app/router.py` (or a small
   new `services/cache/app/guardrails.py` it imports). Unit tests
   (`services/cache/tests/test_guardrails.py`): block (first match wins, stops); redact (masks all
   matches, custom mask from config, multiple patterns/rules); flag (hit only, text unchanged);
   applies_to filtering (input vs output vs both); disabled rules skipped; bad regex skipped (no
   raise); empty rules → unchanged. Implement. Commit.
2. **Wire input path** to use `evaluate_guardrails` (preserve the existing 400 on block; apply input
   redaction to the forwarded/cached prompt). Extend `services/cache/tests/test_router.py`: existing
   block test still passes; new input-redaction test (forwarded body carries the mask). Commit.
3. **Wire output path** (new): block → safety notice + not cached; redact → masked completion +
   cached masked. Tests: output block returns notice and skips cache set; output redact masks the
   returned content. Commit.
4. `pytest services/cache` green; `ruff check`/`format` clean. Security review. PR.

## Success criteria
- Output completions are scanned; `block`/`flag`/`redact` all work on input AND output.
- Redaction masks matched content in the forwarded prompt and the returned/cached completion.
- Existing input-block behaviour unchanged; all enforcement is fail-open except `block`.
- Pure matching logic thoroughly unit-tested; hot path adds no extra rules load.
