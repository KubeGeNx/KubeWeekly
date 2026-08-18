#!/usr/bin/env python3
"""Regenerate deploy/k8s/secret.local.yaml from the example template, filling
in values from a local .env-style file (default: ~/.env). Never prints
secret values - only which keys were filled.

Usage: sync_secret.py [env_file] [template_file] [output_file]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KEY_MAP = {
    "anthropic-api-key": "ANTHROPIC_API_KEY",
    "deepseek-api-key": "DEEPSEEK_API_KEY",
    "github-token": "GITHUB_TOKEN",
    "nvd-api-key": "NVD_API_KEY",
}


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    env_vars = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env_vars[key.strip()] = value.strip()
    return env_vars


def main() -> None:
    env_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".env"
    template_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("deploy/k8s/secret.example.yaml")
    output_file = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("deploy/k8s/secret.local.yaml")

    env_vars = parse_env_file(env_file)
    if not env_vars:
        print(f"No values found in {env_file} - leaving {output_file} untouched.")
        return

    text = output_file.read_text() if output_file.exists() else template_file.read_text()

    filled = []
    for secret_key, env_key in KEY_MAP.items():
        value = env_vars.get(env_key, "")
        if not value:
            continue
        text = re.sub(
            rf'^(\s*{re.escape(secret_key)}:\s*).*$', rf'\1"{value}"', text, flags=re.MULTILINE
        )
        filled.append(secret_key)

    output_file.write_text(text)
    print(f"Synced {len(filled)}/{len(KEY_MAP)} keys from {env_file} into {output_file}: {', '.join(filled) or 'none'}")


if __name__ == "__main__":
    main()
