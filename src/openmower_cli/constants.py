import os
from pathlib import Path

# Centralized constants and defaults for the CLI. Environment variables may override some defaults.

# Environment / configuration file for the stack
ENV_PATH: str = os.environ.get("OPENMOWER_ENV_PATH", "/opt/stacks/openmower/.env")

# Docker compose configuration
COMPOSE_FILE: str = os.environ.get("OPENMOWER_COMPOSE_FILE", "/opt/stacks/openmower/compose.yaml")
DOCKER_BIN: str = os.environ.get("OPENMOWER_DOCKER_BIN", "/usr/bin/docker")
STACK_NAME: str = os.environ.get("OPENMOWER_STACK_NAME", "openmower")
DEFAULT_SERVICE: str = os.environ.get("OPENMOWER_DEFAULT_SERVICE", "openmower")

# GitHub repo for self-update and update checks
DEFAULT_GH_REPO: str = os.environ.get("OPENMOWER_CLI_REPO", "ClemensElflein/openmower-cli")

# Firmware repo (can be overridden via env)
FW_REPO: str = os.environ.get("OPENMOWER_FW_REPO", "xtech/fw-openmower-v2")

# Paths for internal state/cache files
LAST_CHECK_FILE: Path = Path(os.path.expanduser("~/.config/openmower-cli/last_update_check.json"))
