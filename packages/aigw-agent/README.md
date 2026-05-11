# aigw-agent

CLI to register a laptop-hosted agent with the AI Gateway relay.

## Install
pip install -e packages/aigw-agent

## Usage
# Serve a local agent script
aigw-agent serve agents/echo-agent/main.py --slug my-echo

# Check connected agents
aigw-agent status

# Use a custom relay URL (e.g. in CI)
aigw-agent serve ./my_agent.py --relay-url http://relay.internal:8007 --slug ci-agent
