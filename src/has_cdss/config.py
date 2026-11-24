from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_local_environment() -> None:
    """Lê o .env local ignorado pelo Git; não imprime nem valida valores em logs."""
    if os.getenv("PULSO_PUBLIC_DEPLOY") == "1":
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class LLMSettings:
    api_key: str = field(repr=False)
    base_url: str = field(repr=False)
    model_name: str = field(repr=False)

    @property
    def ready(self) -> bool:
        return bool(self.api_key.strip() and self.base_url.strip() and self.model_name.strip())


def get_llm_settings(overrides: Mapping[str, str] | None = None) -> LLMSettings:
    load_local_environment()
    supplied = overrides or {}
    if os.getenv("PULSO_PUBLIC_DEPLOY") == "1":
        return LLMSettings(
            api_key=supplied.get("api_key", "").strip(),
            base_url=supplied.get("base_url", "").strip(),
            model_name=supplied.get("model_name", "").strip(),
        )
    return LLMSettings(
        api_key=(supplied.get("api_key") or os.getenv("LLM_API_KEY", "")).strip(),
        base_url=(supplied.get("base_url") or os.getenv("LLM_BASE_URL", "")).strip(),
        model_name=(supplied.get("model_name") or os.getenv("LLM_MODEL_NAME", "")).strip(),
    )
