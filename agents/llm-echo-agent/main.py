"""llm-echo-agent — reads inputs, asks the gateway LLM to summarise them,
writes the reply + inputs to /run/outputs.json.

Uses AIGW_API_KEY and AIGW_BASE_URL (injected by workflow-worker) to call
the OpenAI-compatible chat completions endpoint through cache:8002.
The cost record that appears in the observability service verifies the
cost-attribution acceptance criterion.
"""
import json
import os
import sys

import httpx

inputs_path = "/run/inputs.json"
outputs_path = "/run/outputs.json"

api_key = os.environ.get("AIGW_API_KEY", "")
base_url = os.environ.get("AIGW_BASE_URL", "http://cache:8002")
run_id = os.environ.get("AIGW_RUN_ID", "unknown")
node_id = os.environ.get("AIGW_NODE_ID", "unknown")

print(f"llm-echo-agent starting; node={node_id} run={run_id}")

try:
    with open(inputs_path) as f:
        inputs = json.load(f)
except FileNotFoundError:
    inputs = {}

if not api_key:
    print("AIGW_API_KEY not set — skipping LLM call, returning inputs only")
    with open(outputs_path, "w") as f:
        json.dump({"agent": "llm-echo-agent", "reply": None, "inputs": inputs, "llm_called": False}, f)
    sys.exit(0)

prompt = f"Summarise this in one sentence: {json.dumps(inputs)}"
payload = {
    "model": "claude-haiku-4-5",
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": 64,
}

try:
    resp = httpx.post(
        f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    reply = resp.json()["choices"][0]["message"]["content"]
    print(f"LLM reply: {reply[:100]}")
    outputs = {"agent": "llm-echo-agent", "reply": reply, "inputs": inputs, "llm_called": True}
except Exception as exc:
    print(f"LLM call failed: {exc}", file=sys.stderr)
    outputs = {"agent": "llm-echo-agent", "reply": None, "inputs": inputs, "error": str(exc), "llm_called": False}

with open(outputs_path, "w") as f:
    json.dump(outputs, f)

print(f"wrote outputs.json ({len(json.dumps(outputs))} bytes)")
sys.exit(0)
