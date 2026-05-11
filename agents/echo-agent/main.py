"""echo-agent — copies /run/inputs.json to /run/outputs.json with an echoed wrapper.

The minimal workflow-designer agent contract:
  - read JSON from /run/inputs.json
  - process
  - write JSON to /run/outputs.json
  - exit 0 on success
"""
import json
import os
import sys

inputs_path = "/run/inputs.json"
outputs_path = "/run/outputs.json"

print(f"echo-agent starting; node={os.environ.get('AIGW_NODE_ID')} run={os.environ.get('AIGW_RUN_ID')}")

try:
    with open(inputs_path) as f:
        inputs = json.load(f)
except FileNotFoundError:
    print("no inputs.json — emitting empty wrapper")
    inputs = {}

outputs = {"echoed": inputs, "agent": "echo-agent"}

with open(outputs_path, "w") as f:
    json.dump(outputs, f)

print(f"wrote {len(json.dumps(outputs))} bytes to outputs.json")
sys.exit(0)
