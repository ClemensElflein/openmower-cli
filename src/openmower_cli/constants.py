import os
from pathlib import Path
from dotenv import dotenv_values

from openmower_cli.console import warn, error, info, success, message


def _detect_new_os() -> bool:
    """True on the Buildroot-based OS (open_mower_ros runs via systemd/nspawn, not
    docker-compose), False on the old pi-gen-based OpenMowerOS and anything else.
    Defaults to False on any read failure -- this is the single switch that keeps
    old-OS behavior byte-for-byte unchanged, so it must fail safe toward "old"."""
    try:
        with open("/etc/os-release") as f:
            return any(line.strip() == "ID=openmower-os" for line in f)
    except Exception:
        return False


# Baked into /etc/os-release at build time on OSv3 (external/board/openmower-cm4/
# post-build.sh); the old OS never sets/overrides ID (stays raspbian/debian). A single
# atomic signal rather than per-feature capability probes (e.g. "does openmower-shell
# exist") avoids inconsistent branching within one invocation on a half-upgraded system,
# and reflects the running OS rather than this CLI's own version -- on the old OS it
# self-updates independently via `update-self`, so it can't assume its own build matches
# the OS it's on; on OSv3 the CLI is vendored into the image instead, and updates
# only via `update-os` (update-self is disabled there).
IS_NEW_OS: bool = _detect_new_os()

# Environment / configuration file path (do NOT load into os.environ)
# On OSv3, /opt/stacks/openmower/.env deliberately does NOT configure
# open_mower_ros (that runs via systemd/nspawn, not this compose stack) -- its own
# header comment says so. The real per-device config lives at
# /data/openmower/openmower.conf instead.
ENV_PATH: str = os.environ.get(
    "OPENMOWER_ENV_PATH",
    "/data/openmower/openmower.conf" if IS_NEW_OS else "/opt/stacks/openmower/.env",
)

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

# GitHub repo for self-update and update checks
DEFAULT_GH_REPO: str = get_env("OPENMOWER_CLI_REPO", "ClemensElflein/openmower-cli")

# Firmware repo (can be overridden via env)
FW_REPO: str = get_env("OPENMOWER_FW_REPO", "xtech/fw-openmower-v2")
FW_BIN_NAME: str | None = get_env("OPENMOWER_FW_CUSTOM_BIN_NAME")
BOOTLOADER_REPO: str = get_env("XCORE_BOOTLOADER_REPO", "xtech/fw-xcore-boot")
BOOTLOADER_BIN_NAME: str | None = get_env("XCORE_BOOTLOADER_CUSTOM_BIN_NAME")

# Host network interface fw-xcore-boot (run with --network=host) uses to reach the
# xCore board. OSv3 puts the CM4's ethernet under a bridge (br0); the old OS keeps
# the plain eth0 name.
XCORE_NETWORK_INTERFACE: str = "br0" if IS_NEW_OS else "eth0"

# Mower configuration file path. PARAMS_PATH fallback mirrors
# openmower-check-config's own PARAMS_PATH="${PARAMS_PATH:-/data/openmower/params}"
# on OSv3, so this stays in sync with the actual service if overridden.
MOWER_PARAMS_FILE: Path = (
    Path(get_env("PARAMS_PATH", "/data/openmower/params")) / "mower_params.yaml"
    if IS_NEW_OS
    else Path(os.path.expanduser("~/params/mower_params.yaml"))
)

# Paths for internal state/cache files. On OSv3 the root filesystem (and $HOME under
# it) is read-only -- only /data persists across boots -- so state lives there instead
# of the usual ~/.config on the old OS.
_STATE_DIR: Path = (
    Path("/data/openmower/cli")
    if IS_NEW_OS
    else Path(os.path.expanduser("~/.config/openmower-cli"))
)
LAST_CHECK_FILE: Path = _STATE_DIR / "last_update_check.json"
# Written daily by `openmower check-os-update` (openmower-check-update.timer,
# os repo) instead of a network call on every invocation -- read by
# warn_if_os_update_available() at CLI startup.
OS_UPDATE_STATUS_FILE: Path = _STATE_DIR / "os_update_status.json"
# Presence alone disables `check-os-update` (see its own docstring) -- an
# empty file is enough, no content is read. Also referenced directly (not
# via this constant) by openmower-check-update.service's own
# ConditionPathExists=! in the os repo, so the unit can skip the process
# entirely most days without needing the CLI to even start.
UPDATE_CHECK_DISABLE_FILE: Path = Path("/data/openmower/no-update-check")
SETTINGS_FILE: Path = _STATE_DIR / "settings.json"
XCORE_CONFIG_FILE: Path = _STATE_DIR / "xcore.cfg"


# Default ports for exposing xESC and IMU
ESC_DEFAULT_PORT = 65102
GPS_DEFAULT_PORT = 2000

# GPS raw-passthrough TCP port on the xCore (fw-openmower-v2: DebugTCPInterface, gps_service.hpp:50)
GPS_XCORE_PORT = 10000
