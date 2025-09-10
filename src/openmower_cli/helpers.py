import os
import subprocess
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timedelta
import json
import requests
from openmower_cli.console import error, warn, info
import typer

TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}

LAST_CHECK_FILE = Path(os.path.expanduser("~/.config/openmower-cli/last_update_check.json"))
DEFAULT_GH_REPO = os.environ.get("OPENMOWER_CLI_REPO", "ClemensElflein/openmower-cli")


def env_bool(name: str) -> bool | None:
    val = os.getenv(name)
    if val is None:
        return None
    s = val.strip().lower()
    if s in TRUE_VALUES:
        return True
    if s in FALSE_VALUES:
        return False
    raise ValueError(f"Invalid boolean for {name!r}: {val!r}. "
                     f"Use one of {sorted(TRUE_VALUES | FALSE_VALUES)}")


def run(cmd: List[str]) -> None:
    """Run a command, streaming output, and exit with its return code if it fails."""
    try:
        # Use check=False so we can propagate return code cleanly
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            raise typer.Exit(code=proc.returncode)
    except FileNotFoundError as e:
        error(f"{e}")
        raise typer.Exit(code=127)


def which(cmd: str) -> Optional[str]:
    try:
        proc = subprocess.run(["which", cmd], capture_output=True, text=True)
        if proc.returncode == 0:
            path = proc.stdout.strip()
            return path or None
        return None
    except Exception:
        return None


def _read_last_check_ts() -> Optional[datetime]:
    try:
        if LAST_CHECK_FILE.exists():
            with open(LAST_CHECK_FILE, "r") as f:
                data = json.load(f)
            ts = data.get("last_check")
            if ts:
                return datetime.fromisoformat(ts)
    except Exception:
        # ignore file errors
        return None
    return None


def _write_last_check_ts(now: Optional[datetime] = None) -> None:
    try:
        ts = (now or datetime.now()).isoformat()
        LAST_CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LAST_CHECK_FILE, "w") as f:
            json.dump({"last_check": ts}, f)
    except Exception:
        pass


def _parse_version(v: str) -> List[int]:
    v = v.strip()
    if v.startswith("v"):
        v = v[1:]
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            # stop at first non-int (e.g., 1.2.3-beta)
            break
    return parts or [0]


def _is_newer(latest: str, current: str) -> bool:
    a = _parse_version(latest)
    b = _parse_version(current)
    # pad
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return a > b


def check_for_update_if_needed(current_version: str, repo: str = DEFAULT_GH_REPO, max_age_days: int = 7) -> None:
    """Check GitHub for a newer release and warn the user once in a while.

    - Only runs if last check is older than max_age_days.
    - Stores the last check timestamp regardless of success.
    - Never raises: logs a warning on newer version, otherwise silent.
    """
    try:
        last = _read_last_check_ts()
        now = datetime.now()
        if last and (now - last) < timedelta(days=max_age_days):
            return
        info("Checking for new version")
        # perform check
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        r = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=10)
        if r.status_code == 200:
            rel = r.json()
            tag = rel.get("tag_name") or ""
            if tag and _is_newer(tag, current_version):
                warn(f"A new version {tag} of openmower-cli is available. Run 'openmower self-update' to update.")
        # Regardless of outcome, update timestamp
        _write_last_check_ts(now)
    except Exception:
        # On any error, still write timestamp to avoid repeated attempts on every run
        _write_last_check_ts()
        return
