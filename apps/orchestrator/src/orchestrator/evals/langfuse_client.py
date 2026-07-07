"""Thin Langfuse Cloud wrapper for eval score logging (SPEC-101 AC2).

No-ops (with a one-time warning) when LANGFUSE_* env vars aren't set, so local dev and
tests never require real credentials — only CI (and anyone with real keys in `.env`)
actually logs to Langfuse. Targets Langfuse SDK v4 (OTel-based); `LANGFUSE_BASE_URL` is
that SDK's current documented env var name (`LANGFUSE_HOST` is its older/fallback name).
"""

import os
import warnings

from orchestrator.prompt_version import parse_prompt_version

__all__ = ["LangfuseClient", "parse_prompt_version"]


class LangfuseClient:
    def __init__(self) -> None:
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        base_url = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
        self._enabled = bool(public_key and secret_key and base_url)
        self._client: object | None = None
        if self._enabled:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=public_key, secret_key=secret_key, base_url=base_url
            )
        else:
            warnings.warn(
                "LANGFUSE_PUBLIC_KEY/SECRET_KEY/LANGFUSE_BASE_URL not set; eval scores "
                "will not be logged to Langfuse (SPEC-101 AC2 requires this in CI).",
                stacklevel=2,
            )

    def log_case_run(
        self,
        *,
        set_name: str,
        case_id: str,
        prompt_version: str,
        score: float,
        rationale: str,
    ) -> None:
        if self._client is None:
            return
        span = self._client.start_observation(  # type: ignore[attr-defined]
            name=f"eval:{set_name}:{case_id}",
            as_type="span",
            version=prompt_version,
            metadata={"case_id": case_id, "set": set_name},
        )
        span.score_trace(name="eval_score", value=score, comment=rationale)
        span.end()

    def flush(self) -> None:
        if self._client is not None:
            self._client.flush()  # type: ignore[attr-defined]
