import os
from pathlib import Path
from dotenv import load_dotenv

from openmower_cli.console import warn, error, info, success

# Environment / configuration file for the stack (now that dotenv is loaded)
ENV_PATH: str = os.environ.get("OPENMOWER_ENV_PATH", "/opt/stacks/openmower/.env")
try:
    info(f"Loading environment variables from {ENV_PATH} ...")
    if os.path.exists(ENV_PATH):
        # Do not override already-set environment variables
        load_dotenv(dotenv_path=ENV_PATH, override=False)
        success("Environment variables loaded from .env")
    else:
        warn(f"Environment file {ENV_PATH} not found. Using system environment variables.")
except Exception:
    # Never fail on dotenv issues when importing constants
    error("Failed to load environment variables from {ENV_PATH}.")
    pass



# Docker compose configuration
COMPOSE_FILE: str = os.environ.get("OPENMOWER_COMPOSE_FILE", "/opt/stacks/openmower/compose.yaml")
DOCKER_BIN: str = os.environ.get("OPENMOWER_DOCKER_BIN", "/usr/bin/docker")
STACK_NAME: str = os.environ.get("OPENMOWER_STACK_NAME", "openmower")
DEFAULT_SERVICE: str = os.environ.get("OPENMOWER_DEFAULT_SERVICE", "open_mower_ros")

# GitHub repo for self-update and update checks
DEFAULT_GH_REPO: str = os.environ.get("OPENMOWER_CLI_REPO", "ClemensElflein/openmower-cli")

# Firmware repo (can be overridden via env)
FW_REPO: str = os.environ.get("OPENMOWER_FW_REPO", "xtech/fw-openmower-v2")
FW_BIN_NAME: str | None = os.environ.get("OPENMOWER_FW_CUSTOM_BIN_NAME")

# Paths for internal state/cache files
LAST_CHECK_FILE: Path = Path(os.path.expanduser("~/.config/openmower-cli/last_update_check.json"))
