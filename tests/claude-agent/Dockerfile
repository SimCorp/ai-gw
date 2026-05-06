FROM node:20-slim

# curl is needed by bootstrap.sh for the gateway connectivity check
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /workspace

# Copy bootstrap script and the agent-local CLAUDE.md
COPY bootstrap.sh /bootstrap.sh
COPY CLAUDE.md /workspace/CLAUDE.md

RUN chmod +x /bootstrap.sh

ENTRYPOINT ["/bootstrap.sh"]
