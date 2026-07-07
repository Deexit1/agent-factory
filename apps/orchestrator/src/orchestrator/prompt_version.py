"""Shared prompt-version parsing (T-108). Used by cost tracking (agents/*.py, tagging
`agent_runs.prompt_version`) and by eval score logging (evals/langfuse_client.py) — a
neutral module so agents don't depend on evals/ for something both need."""

import re

_VERSION_HEADER_RE = re.compile(r"·\s*v([0-9]+\.[0-9]+)")


def parse_prompt_version(prompt_text: str) -> str:
    """Extracts 'X.Y' from a prompt file's `# ... · vX.Y` header (prompts/README.md)."""
    match = _VERSION_HEADER_RE.search(prompt_text.splitlines()[0] if prompt_text else "")
    return match.group(1) if match else "unknown"
