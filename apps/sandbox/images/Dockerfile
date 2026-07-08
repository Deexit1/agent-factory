# Base sandbox image: Python + Node toolchains, non-root, no docker CLI/socket.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# T-204: lets the orchestrator's SandboxClaudeCodeRunner exec the real dev-agent CLI
# inside this container (docker_runtime.exec_stream) instead of on the bare host.
RUN npm install -g @anthropic-ai/claude-code

# System-wide (not /home/sandbox, which is tmpfs and wiped at container start):
# bind-mounted paths won't be owned by the sandbox user, which git otherwise
# refuses to operate on ("dubious ownership"). Safe here: single-tenant, ephemeral,
# torn down after the ticket closes — the scenario safe.directory guards against
# (a shared, persistent machine) doesn't apply.
RUN git config --system --add safe.directory '*'

RUN useradd --create-home --uid 10001 sandbox
USER sandbox
WORKDIR /workspace

CMD ["sleep", "infinity"]
