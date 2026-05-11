# echo-agent

Smallest possible workflow-designer agent. Reads `/run/inputs.json`, writes
`/run/outputs.json` with `{"echoed": <inputs>, "agent": "echo-agent"}`.

## Build

```bash
docker build agents/echo-agent -t ai-gateway-echo-agent:dev
```

## Register with the admin service

```bash
curl -X POST http://localhost:8005/agents \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d @agents/echo-agent/manifest.json
```

## Contract

| Path                | Purpose                                                       |
|---------------------|---------------------------------------------------------------|
| `/run/inputs.json`  | Workflow-worker writes JSON here before launch (read-only).  |
| `/run/outputs.json` | Agent writes JSON here on success. Worker reads after exit.  |
| `AIGW_RUN_ID`       | UUID of the parent workflow run.                              |
| `AIGW_NODE_ID`      | This node's id within the DAG.                                |
| `AIGW_BASE_URL`     | Gateway base URL (`http://cache:8002` in dev).                |
| `AIGW_API_KEY`      | Short-lived scoped key for LLM calls. **Empty in v0.1**       |
