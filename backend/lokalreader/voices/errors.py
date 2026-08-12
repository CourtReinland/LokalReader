"""Loud, specific voice-pipeline setup errors (never silent Samantha fallback)."""

from __future__ import annotations


class VoiceSetupError(RuntimeError):
    """Raised when Piper / RVC assets or subprocess are not ready."""

    def __init__(self, message: str, *, missing: list[str] | None = None) -> None:
        self.missing = missing or []
        hint = " Run `make setup-voices` then `make run`."
        if self.missing:
            detail = "; ".join(self.missing)
            super().__init__(f"{message} Missing: {detail}.{hint}")
        else:
            super().__init__(f"{message}{hint}")
