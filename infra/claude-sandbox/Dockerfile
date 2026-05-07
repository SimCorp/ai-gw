FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server \
        curl \
        git \
        python3 \
        python3-pip \
        jq \
        httpie \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code

# SSH setup
RUN mkdir /var/run/sshd
# Allow root login (sandbox only) and password auth
RUN sed -i \
    -e 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' \
    -e 's/#PasswordAuthentication yes/PasswordAuthentication yes/' \
    -e 's/PasswordAuthentication no/PasswordAuthentication yes/' \
    /etc/ssh/sshd_config
# Generate host keys
RUN ssh-keygen -A

# Create a non-root user "claude" with a known password
RUN useradd -m -s /bin/bash claude && echo "claude:gateway" | chpasswd
# Also set root password for convenience
RUN echo "root:gateway" | chpasswd

WORKDIR /home/claude/workspace
RUN chown claude:claude /home/claude/workspace

COPY entrypoint.sh /entrypoint.sh
COPY go /usr/local/bin/go
COPY CLAUDE.md /home/claude/workspace/CLAUDE.md
RUN chmod +x /entrypoint.sh /usr/local/bin/go \
    && chown claude:claude /home/claude/workspace/CLAUDE.md

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
