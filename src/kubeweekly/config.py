from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_SOURCES_PATH = os.environ.get("KUBEWEEKLY_SOURCES_PATH", "config/sources.yaml")
DEFAULT_DB_PATH = os.environ.get("KUBEWEEKLY_DB_PATH", "data/kubeweekly.db")
DEFAULT_OUTPUT_DIR = os.environ.get("KUBEWEEKLY_OUTPUT_DIR", "data/output")


@dataclass
class SourcesConfig:
    rss: list[dict] = field(default_factory=list)
    github: dict = field(default_factory=dict)
    artifacthub: dict = field(default_factory=dict)
    hackernews: dict = field(default_factory=dict)
    reddit: dict = field(default_factory=dict)
    cve: dict = field(default_factory=dict)
    cloud_providers: list[dict] = field(default_factory=list)
    mailing_lists: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_SOURCES_PATH) -> "SourcesConfig":
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Per-provider defaults. LLM_PROVIDER selects which one is actually used;
# this is deliberately a single selector rather than two independent
# enable/disable flags, since exactly one provider serves any given call —
# two flags would just add an ambiguous "both true" / "both false" state.
PROVIDER_DEFAULTS = {
    "claude": {
        "env_key": "ANTHROPIC_API_KEY",
        "classify_model": "claude-haiku-4-5",
        "summarize_model": "claude-sonnet-5",
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "classify_model": "deepseek-chat",
        "summarize_model": "deepseek-chat",
    },
}


@dataclass
class AppConfig:
    llm_provider: str
    llm_api_key: str
    github_token: str | None
    db_path: str
    output_dir: str
    sources_path: str
    classify_model: str
    summarize_model: str
    dry_run: bool = False
    max_sources: int | None = None  # cap connectors used, for --dry-run

    @classmethod
    def from_env(cls, dry_run: bool = False, max_sources: int | None = None) -> "AppConfig":
        provider = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
        if provider not in PROVIDER_DEFAULTS:
            raise RuntimeError(
                f"LLM_PROVIDER={provider!r} is not supported, expected 'claude' or 'deepseek'"
            )
        defaults = PROVIDER_DEFAULTS[provider]

        api_key = os.environ.get(defaults["env_key"], "")
        if not api_key:
            raise RuntimeError(
                f"{defaults['env_key']} is not set (required even for --dry-run, which still "
                f"makes a handful of real {provider} calls). Set LLM_PROVIDER to switch providers."
            )

        return cls(
            llm_provider=provider,
            llm_api_key=api_key,
            github_token=os.environ.get("GITHUB_TOKEN"),
            db_path=DEFAULT_DB_PATH,
            output_dir=DEFAULT_OUTPUT_DIR,
            sources_path=DEFAULT_SOURCES_PATH,
            classify_model=os.environ.get("CLASSIFY_MODEL", defaults["classify_model"]),
            summarize_model=os.environ.get("SUMMARIZE_MODEL", defaults["summarize_model"]),
            dry_run=dry_run,
            max_sources=max_sources,
        )
