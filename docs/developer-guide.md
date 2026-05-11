# SimCorp AI Gateway — Developer Guide

> For ~2000 SimCorp engineers who want to add AI capabilities to their projects.  
> Updated: 2026-05-11

> **Full technical reference:** See [`docs/SYSTEM_REFERENCE.md`](./SYSTEM_REFERENCE.md) for complete API documentation, schema specs, all configuration options, portal page descriptions, and workflow designer details.

---

## Table of contents

1. [5-minute quickstart](#1-5-minute-quickstart)
2. [Choosing a model](#2-choosing-a-model)
3. [Integration examples](#3-integration-examples)
4. [Interactive sandbox (Claude Code via SSH)](#4-interactive-sandbox-claude-code-via-ssh)
5. [Testing your integration](#5-testing-your-integration)
5a. [Session context headers and self-service stats](#5a-session-context-headers-and-self-service-stats)
6. [Streaming](#6-streaming)
7. [Understanding the cache](#7-understanding-the-cache)
8. [Rate limits](#8-rate-limits)
9. [Common pitfalls](#9-common-pitfalls)
10. [Getting help](#10-getting-help)

---

## 1. 5-minute quickstart

### Step 1 — Get an API key

Open the self-service portal: **http://localhost:3002/portal**

1. Sign up with your email and password — no admin approval required.
2. Go to **API keys** and click **Issue key**.
3. Copy the key — it starts with `sk-` and is shown only once.

No admin approval is needed. Keys are provisioned instantly.

### Step 2 — Make your first call

Replace `sk-YOUR-KEY-HERE` with the key you just created.

```bash
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-KEY-HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-haiku-4-5",
    "messages": [
      {"role": "user", "content": "Hello, which model are you?"}
    ]
  }'
```

You should get a JSON response in under two seconds. If you see `x-cache: HIT` in the response headers on a second identical call, the semantic cache is working.

### How the request flows

```
Your code
  |
  v
Auth service (:8001)   — validates your key, enforces rate limits
  |
  v
Cache engine (:8002)   — checks Redis for cached responses (x-cache: HIT)
  |
  v
LiteLLM proxy (:8003)  — routes to provider, injects provider API key
  |
  v
Provider (Anthropic / Google / GitHub / Ollama)
```

### Two endpoints

| Endpoint | URL | Use with |
|---|---|---|
| OpenAI-compatible | `http://localhost:8002/v1` | All models, all frameworks with OpenAI support |
| Anthropic-compatible | `http://localhost:8002/anthropic` | Claude models, Anthropic SDK, Claude Code CLI |

From inside a Docker Compose network replace `localhost` with `gateway`:
- `http://gateway:8002/v1`
- `http://gateway:8002/anthropic`

---

## 2. Choosing a model

| Model ID | Provider | Context | Cost tier | Best for |
|---|---|---|---|---|
| `claude-haiku-4-5` | Anthropic | 200k | Low | High-volume tasks, classification, quick responses, chat |
| `claude-sonnet-4-6` | Anthropic | 200k | Medium | **Recommended default.** Agents, code generation, RAG, tool calling |
| `claude-opus-4-7` | Anthropic | 200k | High | Complex reasoning, architecture decisions, research synthesis |
| `gemini-1.5-pro` | Google | 1M | Medium | Very long documents (entire codebases), multimodal inputs |
| `github-gpt-4o` | GitHub Models | 128k | Medium | OpenAI-native tool calling patterns, teams already using GPT-4o |
| `copilot-gpt-4o` | GitHub Copilot | 128k | Medium | GPT-4o via Copilot subscription; requires GitHub PAT with Copilot scope |
| `copilot-gpt-4o-mini` | GitHub Copilot | 128k | Low | Fast GPT-4o-mini via Copilot; good for batch jobs and high-volume use |
| `copilot-o3-mini` | GitHub Copilot | 128k | Medium | Reasoning tasks via Copilot; lower latency than full o3 |
| `copilot-claude-3.5-sonnet` | GitHub Copilot | 200k | Medium | Claude 3.5 Sonnet accessed through GitHub Copilot |
| `azure-gpt-4o` | Azure AI Foundry | 128k | Medium | GPT-4o hosted in your Azure subscription; data stays in your Azure region |
| `azure-gpt-4o-mini` | Azure AI Foundry | 128k | Low | Low-cost Azure-hosted GPT-4o-mini |
| `azure-o3-mini` | Azure AI Foundry | 128k | Medium | Azure-hosted o3-mini for reasoning workloads |
| `azure-gpt-4.1` | Azure AI Foundry | 1M | Medium | Latest GPT-4.1 on Azure; 1M-token context for large document tasks |
| `local` | Ollama (llama3.2) | varies | Free | Development and testing — data never leaves your machine |

### Decision guide

- **Just want something that works?** Use `claude-sonnet-4-6`. It balances speed, cost, and capability for the vast majority of tasks.
- **High-request-volume pipeline or batch job?** Use `claude-haiku-4-5` to keep costs low.
- **Need to reason over a 500-page PDF or an entire repo?** Use `gemini-1.5-pro` or `azure-gpt-4.1` for their 1M-token context windows.
- **Hardest reasoning problem, cost is secondary?** Use `claude-opus-4-7`.
- **Sensitive data or offline work?** Use `local` — no data leaves the machine.
- **Data must stay in your Azure region?** Use any `azure-*` model — traffic routes through your own Azure subscription.
- **Team has GitHub Copilot licences?** Use `copilot-*` models to stay within your existing Copilot spend.
- **Existing codebase uses OpenAI function-calling JSON schema?** `github-gpt-4o`, `copilot-gpt-4o`, or `azure-gpt-4o` all drop in with no schema changes.

**Note on fallbacks:** The gateway is configured to fall back from `claude-sonnet-4-6` to `gemini-1.5-pro` automatically if Anthropic is unavailable. Your code needs no changes to benefit from this.

---

## 3. Integration examples

All examples below use the recommended `claude-sonnet-4-6`. Swap in any model ID from the table above.

### curl

```bash
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-KEY-HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant for SimCorp engineers."},
      {"role": "user", "content": "Explain the difference between a mutex and a semaphore."}
    ],
    "max_tokens": 1024
  }'
```

GitHub Copilot models use the same syntax — just swap the model ID:

```bash
# GitHub Copilot via gateway
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-KEY-HERE" \
  -H "Content-Type: application/json" \
  -d '{"model": "copilot-gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}'
```

Azure AI Foundry models work the same way:

```bash
# Azure AI Foundry via gateway
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-KEY-HERE" \
  -H "Content-Type: application/json" \
  -d '{"model": "azure-gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}'
```

### Python — OpenAI SDK

Works with all models. Use this unless you need Anthropic-specific features.

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-YOUR-KEY-HERE",
    base_url="http://localhost:8002/v1",
)

response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a Python function that validates an ISIN."},
    ],
    max_tokens=2048,
)

print(response.choices[0].message.content)
```

Store the key in the environment rather than in source code:

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["SIMCORP_GATEWAY_KEY"],
    base_url="http://localhost:8002/v1",
)
```

### Python — Anthropic SDK

Point `base_url` at `/anthropic`, not `/v1`. The two endpoints use different wire protocols.

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-YOUR-KEY-HERE",
    base_url="http://localhost:8002/anthropic",
)

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system="You are a helpful assistant.",
    messages=[
        {"role": "user", "content": "Summarise this function and suggest improvements."}
    ],
)

print(message.content[0].text)
```

### Claude Code CLI

One-time shell setup:

```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Add to ~/.bashrc or ~/.zshrc
export ANTHROPIC_API_KEY=sk-YOUR-KEY-HERE
export ANTHROPIC_BASE_URL=http://localhost:8002/anthropic

# Verify
claude --version
claude "What model are you running on?"
```

Inline (no env var required):

```bash
ANTHROPIC_API_KEY=sk-YOUR-KEY-HERE \
ANTHROPIC_BASE_URL=http://localhost:8002/anthropic \
claude "Summarise the last 10 commits"
```

CI / GitHub Actions:

```yaml
# .github/workflows/ai-review.yml
- name: AI code review
  env:
    ANTHROPIC_API_KEY: ${{ secrets.SIMCORP_GATEWAY_KEY }}
    ANTHROPIC_BASE_URL: http://gateway:8002/anthropic
  run: |
    claude --output-format json \
      "Review the changes in this PR for security issues" \
      > review.json
```

Project-wide config — place a `CLAUDE.md` at your repo root and Claude Code reads it automatically:

```markdown
# CLAUDE.md

This project uses the SimCorp AI Gateway.
Set ANTHROPIC_BASE_URL=http://localhost:8002/anthropic in your environment.
API keys: http://localhost:3002/portal/keys
```

### LangChain

Minimum version: `langchain-openai>=0.1.0`

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="claude-sonnet-4-6",
    openai_api_key="sk-YOUR-KEY-HERE",
    openai_api_base="http://localhost:8002/v1",
    temperature=0.2,
)

response = llm.invoke("Summarise the changes in this pull request: ...")
print(response.content)
```

For Anthropic-specific features (extended thinking, native tool format):

```python
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    anthropic_api_key="sk-YOUR-KEY-HERE",
    anthropic_api_url="http://localhost:8002/anthropic",
    max_tokens=4096,
)
```

RAG pipeline:

```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.chains import RetrievalQA
from langchain_community.vectorstores import FAISS

llm = ChatOpenAI(
    model="claude-sonnet-4-6",
    openai_api_key="sk-YOUR-KEY-HERE",
    openai_api_base="http://localhost:8002/v1",
)
embeddings = OpenAIEmbeddings(
    openai_api_key="sk-YOUR-KEY-HERE",
    openai_api_base="http://localhost:8002/v1",
)
vectorstore = FAISS.load_local("my_index", embeddings)
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=vectorstore.as_retriever(search_kwargs={"k": 4}),
)
result = qa_chain.invoke({"query": "What is SimCorp's code review policy?"})
print(result["result"])
```

**LangChain pitfall:** Use `openai_api_base=`, not `base_url=`. The `base_url` parameter is silently ignored in older LangChain versions.

### LlamaIndex

Minimum version: `llama-index-llms-openai>=0.1.0`

```python
from llama_index.llms.openai import OpenAI
from llama_index.core import Settings

llm = OpenAI(
    model="claude-sonnet-4-6",
    api_key="sk-YOUR-KEY-HERE",
    api_base="http://localhost:8002/v1",
    temperature=0.1,
    max_tokens=4096,
)
Settings.llm = llm
```

RAG with embeddings through the gateway:

```python
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings

Settings.llm = OpenAI(
    model="claude-sonnet-4-6",
    api_key="sk-YOUR-KEY-HERE",
    api_base="http://localhost:8002/v1",
)
Settings.embed_model = OpenAIEmbedding(
    model="text-embedding-3-small",
    api_key="sk-YOUR-KEY-HERE",
    api_base="http://localhost:8002/v1",
)

documents = SimpleDirectoryReader("./docs").load_data()
index = VectorStoreIndex.from_documents(documents)
response = index.as_query_engine().query("What auth methods does the gateway support?")
print(response)
```

**LlamaIndex pitfall:** The parameter is `api_base=`, not `base_url=` or `openai_api_base=`. For LlamaIndex < 0.10 use `ServiceContext.from_defaults(llm=llm)` instead of `Settings.llm`.

### OpenAI Agents SDK

Minimum version: `openai-agents>=0.0.7`

Basic agent:

```python
from agents import Agent, Runner, OpenAIChatCompletionsModel
from openai import AsyncOpenAI

gateway_client = AsyncOpenAI(
    api_key="sk-YOUR-KEY-HERE",
    base_url="http://localhost:8002/v1",
)
model = OpenAIChatCompletionsModel(
    model="claude-sonnet-4-6",
    openai_client=gateway_client,
)
agent = Agent(
    name="CodeReviewer",
    instructions="You are a senior engineer performing code reviews.",
    model=model,
)
result = Runner.run_sync(agent, "Review this function for security issues: ...")
print(result.final_output)
```

Agent with tools:

```python
from agents import Agent, Runner, OpenAIChatCompletionsModel, function_tool
from openai import AsyncOpenAI

gateway_client = AsyncOpenAI(api_key="sk-YOUR-KEY-HERE", base_url="http://localhost:8002/v1")
model = OpenAIChatCompletionsModel(model="claude-sonnet-4-6", openai_client=gateway_client)

@function_tool
def search_codebase(query: str) -> str:
    """Search the codebase for relevant files and functions."""
    # Replace with your actual search implementation
    return f"Found: services/auth/app/validators/api_key.py matches '{query}'"

agent = Agent(
    name="Navigator",
    instructions="Find relevant code.",
    model=model,
    tools=[search_codebase],
)
result = Runner.run_sync(agent, "Where is API key validation implemented?")
print(result.final_output)
```

Multi-agent handoff — route cheap model to expensive model only when needed:

```python
from agents import Agent, Runner, OpenAIChatCompletionsModel, handoff
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key="sk-YOUR-KEY-HERE", base_url="http://localhost:8002/v1")

def make_model(m):
    return OpenAIChatCompletionsModel(model=m, openai_client=client)

triage = Agent(
    name="Triage",
    model=make_model("claude-haiku-4-5"),
    instructions="Classify the request as 'code', 'docs', or 'other'.",
)
coder = Agent(
    name="Coder",
    model=make_model("claude-sonnet-4-6"),
    instructions="Write production-quality code.",
)
triage.handoffs = [handoff(coder)]

result = Runner.run_sync(triage, "Write a Python email validator.")
print(result.final_output)
```

**OpenAI Agents SDK pitfall:** Pass `openai_client=` to `OpenAIChatCompletionsModel`, not to `Agent` or `Runner`. Also, the SDK sends traces to `api.openai.com` by default — disable with `Runner.run_sync(..., trace=False)` or configure a custom exporter, otherwise traces will silently fail.

---

## 4. Interactive sandbox (Claude Code via SSH)

The easiest way to experiment with the gateway is the Claude sandbox container — it has Claude Code CLI pre-installed and pre-configured to route through the gateway.

```bash
# Start the sandbox (runs until stopped)
make sandbox

# Connect via SSH
ssh claude@localhost -p 2222
# Password: gateway

# Inside the container — run the interactive setup wizard
go
```

The `go` script will:
1. Check the gateway is reachable
2. Ask for an API key (paste an existing one, create a new one via the admin API, or open the portal)
3. Optionally pick a model from the live model list
4. Launch `claude` with everything configured

The sandbox is connected to the internal Docker network, so it uses the full gateway stack (auth, cache, observability).

To stop: `make sandbox-stop`

---

## 5. Testing your integration

The repo includes a full pytest integration suite that runs against the live stack:

```bash
DEV_BYPASS_AUTH=true make test
```

This runs 50 tests covering auth, caching, proxy, admin API, and the developer portal — all via real HTTP against real containers. Useful to confirm your changes haven't broken anything.

For a quick smoke check only:

```bash
DEV_BYPASS_AUTH=true make test-smoke
```

---

## 5a. Session context headers and self-service stats

### Enriching your requests with session context

You can attach optional headers to any inference request to improve analytics attribution and enable richer reporting:

| Header | Description |
|---|---|
| `X-Session-Trace-Id` | Your own session identifier (UUID or opaque string). Groups related requests into a logical session. |
| `X-Repo` | Repository slug (e.g. `simcorp/investment-engine`). Enables per-repo cost and usage breakdowns. |
| `X-Session-Purpose` | Free-text description of what this session is doing (e.g. `PR review for #1234`). |

No prompt text is stored from these headers — they are used only for grouping and attribution in the analytics pipeline. Sessions are tracked per `X-Session-Trace-Id` and aggregated with a quality score (1–5) based on session signals.

```bash
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-KEY-HERE" \
  -H "X-Session-Trace-Id: my-session-abc123" \
  -H "X-Repo: simcorp/investment-engine" \
  -H "X-Session-Purpose: refactor auth module" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "..."}]}'
```

### Self-service stats

Developers can query their own usage and cost metrics without admin access:

```
GET http://localhost:8005/dev-auth/me/stats
Authorization: Bearer <portal-session-token>
```

The response includes:

| Field | Description |
|---|---|
| `cost_breakdown` | Spend by model and by repository |
| `cost_per_pr` | Estimated AI cost attributed to merged pull requests |
| `cost_per_commit` | Estimated AI cost attributed to commits |
| `session_quality_score` | Average session quality score (1–5) for the current period |
| `efficiency_percentile` | Your efficiency rank within your team (e.g. `72` means more efficient than 72% of teammates) |
| `budget_visibility` | Your team's remaining budget for the period |
| `optimization_hints` | Suggestions to reduce cost or improve efficiency (e.g. "Switch batch jobs to claude-haiku-4-5") |

---

## 6. Streaming

All models support streaming via both endpoints. Tokens are flushed as they are generated.

**Token tracking:** Streaming responses now capture token counts for observability. The gateway parses the final SSE chunk from LiteLLM to extract usage data and records it in cost_records. Streaming requests no longer appear with zero tokens in your usage stats or cost reports.

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-YOUR-KEY-HERE",
    base_url="http://localhost:8002/v1",
)

with client.chat.completions.stream(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Write a haiku about caching."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()  # newline after stream ends
```

With the Anthropic SDK:

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-YOUR-KEY-HERE",
    base_url="http://localhost:8002/anthropic",
)

with client.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Explain event-driven architecture."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
```

**Note:** Cached responses (`x-cache: HIT`) are still returned as a single response object even if you request streaming, because the full content is already in Redis. This is transparent — your streaming code works unchanged.

---

## 7. Understanding the cache

The gateway runs a semantic cache in front of every model call. This has two effects:

1. **Exact hits** — an identical prompt returns instantly from Redis at zero provider cost.
2. **Semantic hits** — a prompt that is very similar to a cached one (same meaning, different wording) also returns the cached response. This is why repeated CI jobs on unchanged code are fast and cheap.

### How to tell if a response was cached

Check the response headers:

```
x-cache: HIT    — served from cache, no provider call made
x-cache: MISS   — went to the provider, response now cached
x-cache: BYPASS — cache explicitly skipped via bypass header
```

### When caching helps

- Repeated CI jobs running the same code-review prompt on unchanged files.
- Multiple developers asking similar questions in quick succession.
- Batch jobs where many inputs are near-duplicates.

### When to bypass the cache

If you need a fresh response — for example, when the underlying data has changed but the prompt text has not — you can bypass the cache per request using either of two headers:

- `Cache-Control: no-cache` — standard HTTP cache bypass
- `x-cache: bypass` — gateway-specific shorthand; identical effect

The response will carry `x-cache: BYPASS` (instead of `MISS`) to confirm the bypass was applied.

```bash
# Option 1 — Cache-Control
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-KEY-HERE" \
  -H "Cache-Control: no-cache" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "What is today'\''s date?"}]}'

# Option 2 — x-cache: bypass
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-KEY-HERE" \
  -H "x-cache: bypass" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "What is today'\''s date?"}]}'
```

```python
from openai import OpenAI
import httpx

# Using x-cache: bypass
client = OpenAI(
    api_key="sk-YOUR-KEY-HERE",
    base_url="http://localhost:8002/v1",
    http_client=httpx.Client(headers={"x-cache": "bypass"}),
)
```

### Cache behaviour to be aware of

- Cache entries expire. Do not rely on a cache hit being available indefinitely.
- The cache key is derived from the full message array, model ID, and a subset of parameters. Changing `temperature` does not bypass the cache by itself — use `Cache-Control: no-cache` explicitly.
- Streaming responses are cached after the stream completes, so the second identical request returns instantly even though the first was streamed.

---

## 8. Rate limits

Rate limits are enforced per team. When you exceed your team's limit the gateway returns:

```
HTTP 429 Too Many Requests
Retry-After: 12
```

The `Retry-After` value is in seconds. Always read it rather than using a fixed sleep.

### Recommended retry pattern

```python
import time
import httpx
from openai import OpenAI, RateLimitError

client = OpenAI(
    api_key="sk-YOUR-KEY-HERE",
    base_url="http://localhost:8002/v1",
)

def call_with_backoff(messages, model="claude-sonnet-4-6", max_retries=5):
    delay = 1.0
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(model=model, messages=messages)
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            # Honour the Retry-After header when present
            retry_after = getattr(e, "response", None)
            if retry_after is not None:
                header_val = retry_after.headers.get("Retry-After")
                if header_val:
                    delay = float(header_val)
            print(f"Rate limited. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
            delay = min(delay * 2, 60)  # exponential backoff, cap at 60s
```

### Tips to avoid hitting rate limits

- Create one API key per application or pipeline, not one shared key for everything. Limits are tracked per key.
- For CI jobs that run in parallel, create a separate key per pipeline so they draw from separate buckets.
- Use `claude-haiku-4-5` for high-volume batch work — it has a higher RPM allocation than Sonnet.
- If your team genuinely needs a higher limit, contact Platform Engineering (see [Getting help](#10-getting-help)).

---

## 9. Common pitfalls

### 1. Wrong port or hostname

The gateway listens on port **8002**, not 8001, 8003, 8004, or 8005.

- From your host machine: `http://localhost:8002`
- From inside a Docker Compose network: `http://gateway:8002`
- WSL users: use `http://gateway:8002` inside Docker, `http://localhost:8002` on the Windows host.

### 2. Wrong base_url for the SDK

The two endpoints use different wire protocols. Using the wrong one gives 400 or 404 errors.

| SDK | Correct base_url |
|---|---|
| `openai` Python SDK | `http://localhost:8002/v1` |
| `anthropic` Python SDK | `http://localhost:8002/anthropic` |
| Claude Code CLI (`ANTHROPIC_BASE_URL`) | `http://localhost:8002/anthropic` |
| LangChain `ChatOpenAI` | `http://localhost:8002/v1` (via `openai_api_base=`) |
| LangChain `ChatAnthropic` | `http://localhost:8002/anthropic` (via `anthropic_api_url=`) |
| LlamaIndex `OpenAI` class | `http://localhost:8002/v1` (via `api_base=`) |
| OpenAI Agents SDK | `http://localhost:8002/v1` (via `base_url=` on `AsyncOpenAI`) |

Do not append `/v1` twice. `http://localhost:8002/v1/v1/chat/completions` is a 404.

### 3. Wrong model ID

Model IDs are exact strings. Common mistakes:

| Wrong | Correct |
|---|---|
| `haiku` | `claude-haiku-4-5` |
| `claude-haiku` | `claude-haiku-4-5` |
| `sonnet` | `claude-sonnet-4-6` |
| `gpt-4o` | `github-gpt-4o` (or `copilot-gpt-4o` / `azure-gpt-4o`) |
| `gemini-pro` | `gemini-1.5-pro` |
| `copilot-gpt4o` | `copilot-gpt-4o` (hyphen required) |
| `azure-gpt4o` | `azure-gpt-4o` (hyphen required) |

A `400 model not found` error always means the model ID string is wrong.

### 4. API key not in the `sk-` format

Gateway keys must start with `sk-` (lowercase). If you accidentally paste a raw Anthropic or OpenAI key, authentication will fail with `401`. Keys are created at http://localhost:3002/portal/keys.

### 5. Forgetting to bypass the cache when data changes

If your prompt text stays the same but the underlying data changes (e.g. you updated a document and are asking the model to summarise it again), you will get the stale cached response. Always pass `Cache-Control: no-cache` or `x-cache: bypass` when freshness matters.

---

## 10. Getting help

### Self-service

| Resource | URL |
|---|---|
| Developer portal (keys, usage, docs) | http://localhost:3002/portal |
| Admin portal (teams, guardrails, audit) | http://localhost:3001/admin/dashboard |
| Gateway health status | http://localhost:8002/health |
| Admin API health | http://localhost:8005/health |

### Quick health check

Run this before debugging any framework issue — it confirms your key and the gateway are both working:

```python
import httpx

resp = httpx.post(
    "http://localhost:8002/v1/chat/completions",
    headers={"Authorization": "Bearer sk-YOUR-KEY-HERE"},
    json={
        "model": "claude-haiku-4-5",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 10,
    },
    timeout=30.0,
)
if resp.status_code == 200:
    print("Gateway OK:", resp.json()["choices"][0]["message"]["content"])
elif resp.status_code == 401:
    print("Auth failed — check your key at http://localhost:3002/portal/keys")
elif resp.status_code == 429:
    print("Rate limited — Retry-After:", resp.headers.get("Retry-After"))
else:
    print(f"Unexpected {resp.status_code}:", resp.text)
```

### Platform Engineering

If you need a rate limit increase, have a question that the portal does not answer, or suspect a gateway bug, contact **Platform Engineering** via the internal Slack channel or raise a ticket in the SimCorp IT service desk.

When filing a ticket, include:
- Your API key ID (not the secret — just the identifier shown in the portal)
- The HTTP status code and full error response body
- The service and endpoint you were calling
- The model ID you requested
