import os
from pathlib import Path
from dotenv import dotenv_values

from openmower_cli.console import warn, error, info, success, message

# Environment / configuration file path (do NOT load into os.environ)
ENV_PATH: str = os.environ.get("OPENMOWER_ENV_PATH", "/opt/stacks/openmower/.env")

# Cache of values parsed from .env (not injected into process environment)
try:
    if os.path.exists(ENV_PATH):
        _DOTENV_VALUES = dotenv_values(ENV_PATH) or {}
    else:
        _DOTENV_VALUES = {}
        warn(f"Environment file {ENV_PATH} not found. Using system environment variables only.")
except Exception:
    _DOTENV_VALUES = {}
    error(f"Failed to read environment file at {ENV_PATH}. Proceeding without .env values.")


def get_env(key: str, default: str | None = None) -> str | None:
    """Return value for key with precedence: .env first, then real environment."""
    if key in _DOTENV_VALUES and _DOTENV_VALUES.get(key) not in (None, ""):
        return _DOTENV_VALUES.get(key)
    return os.environ.get(key, default)


# Docker compose configuration
HARDWARE_PLATFORM: str | None = get_env("HARDWARE_PLATFORM")
COMPOSE_FILE: str = get_env("OPENMOWER_COMPOSE_FILE", "/opt/stacks/openmower/compose.yaml")
DOCKER_BIN: str = get_env("OPENMOWER_DOCKER_BIN", "/usr/bin/docker")
STACK_NAME: str = get_env("OPENMOWER_STACK_NAME", "openmower")
DEFAULT_SERVICE: str = get_env("OPENMOWER_DEFAULT_SERVICE", "open_mower_ros")
CONTAINER_WORKSPACE_PATH: str = get_env("OPENMOWER_CONTAINER_WORKSPACE_PATH", "/opt/open_mower_ros")
HOST_WORKSPACE_PATH: str = get_env("OPENMOWER_HOST_WORKSPACE_PATH", os.path.expanduser("~/open_mower_ros"))

# GitHub repo for self-update and update checks
DEFAULT_GH_REPO: str = get_env("OPENMOWER_CLI_REPO", "ClemensElflein/openmower-cli")

# Firmware repo (can be overridden via env)
FW_REPO: str = get_env("OPENMOWER_FW_REPO", "xtech/fw-openmower-v2")
FW_BIN_NAME: str | None = get_env("OPENMOWER_FW_CUSTOM_BIN_NAME")
BOOTLOADER_REPO: str = get_env("XCORE_BOOTLOADER_REPO", "xtech/fw-xcore-boot")
BOOTLOADER_BIN_NAME: str | None = get_env("XCORE_BOOTLOADER_CUSTOM_BIN_NAME")

# Mower configuration file path
MOWER_PARAMS_FILE: Path = Path(os.path.expanduser("~/params/mower_params.yaml"))

# Paths for internal state/cache files
LAST_CHECK_FILE: Path = Path(os.path.expanduser("~/.config/openmower-cli/last_update_check.json"))
SETTINGS_FILE: Path = Path(os.path.expanduser("~/.config/openmower-cli/settings.json"))
XCORE_CONFIG_FILE: Path = Path(os.path.expanduser("~/.config/openmower-cli/xcore.cfg"))


# Default ports for exposing xESC and IMU
ESC_DEFAULT_PORT = 65102
GPS_DEFAULT_PORT = 2000

# MQTT Configuration
MQTT_HOST: str = get_env("OPENMOWER_MQTT_HOST", "localhost")
MQTT_PORT: int = int(get_env("OPENMOWER_MQTT_PORT", "1883"))
MQTT_TOPIC_RPC_REQUEST: str = "rpc/request"
MQTT_TOPIC_RPC_RESPONSE: str = "rpc/response"
