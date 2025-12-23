import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import requests
import typer

from openmower_cli.console import error, warn, info
from openmower_cli.constants import LAST_CHECK_FILE, DEFAULT_GH_REPO, SETTINGS_FILE


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


def read_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f) or {}
    except Exception:
        return {}
    return {}


def write_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


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
                warn(f"A new version {tag} of openmower-cli is available. Run 'openmower update-self' to update.")
        # Regardless of outcome, update timestamp
        _write_last_check_ts(now)
    except Exception:
        # On any error, still write timestamp to avoid repeated attempts on every run
        _write_last_check_ts()
        return


def fetch_github_release(repo: str, tag: str | None = None) -> dict:
    """Fetch GitHub release JSON for latest or a specific tag."""
    session = requests.Session()
    session.headers.update({"Accept": "application/vnd.github+json"})
    if tag:
        rel_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    else:
        rel_url = f"https://api.github.com/repos/{repo}/releases/latest"
    r = session.get(rel_url, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to fetch release metadata from GitHub (HTTP {r.status_code})")
    return r.json()


def fetch_github_release_zip(repo: str, expected_asset_suffix: str | None = None, tag: str | None = None) -> tuple[
    Path, str, tempfile.TemporaryDirectory]:
    """Download a release asset (.zip) from GitHub to a temporary directory and return (zip_path, tag, tmpdir_handle).
    - repo: 'owner/name'
    - expected_asset_suffix: e.g., '.zip' or a specific name to match; if None, picks first .zip
    - tag: tag name to fetch; if None, fetches latest
    - The returned TemporaryDirectory handle must be kept alive until you're done with files in it,
      and should be explicitly cleaned up; callers should use try/finally to call tmpdir_handle.cleanup().
    """
    rel = fetch_github_release(repo, tag)
    tag_name = rel.get("tag_name") or tag or ""

    # pick asset
    asset = None
    assets = rel.get("assets", [])
    for a in assets:
        name = a.get("name", "")
        if expected_asset_suffix:
            if name == expected_asset_suffix or name.endswith(expected_asset_suffix):
                asset = a
                break
        else:
            if name.endswith('.zip'):
                asset = a
                break
    if not asset:
        raise RuntimeError("No matching .zip asset found in the release.")

    asset_name = asset.get("name")
    download_url = asset.get("browser_download_url")

    td = tempfile.TemporaryDirectory()
    tmpdir = Path(td.name)
    zip_path = tmpdir / asset_name

    session = requests.Session()
    session.headers.update({"Accept": "application/octet-stream"})
    with session.get(download_url, stream=True, timeout=300) as resp:
        if resp.status_code != 200:
            # ensure temp dir gets removed even if download fails
            td.cleanup()
            raise RuntimeError(f"Failed to download asset (HTTP {resp.status_code})")
        with open(zip_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
    # Do not cleanup here; caller will cleanup after using the files
    return zip_path, tag_name, td

def fetch_file_locally(path: str):
    base_path = Path(path)
    if not base_path.exists():
        raise FileNotFoundError(path)
    with open(base_path, 'r') as f:
        return f.read() 

def fetch_folder_locally(path: str):
    base_path = Path(path)
    if not base_path.exists():
        raise FileNotFoundError(path)
    for root, _, files in os.walk(path):
        for file in files:
            full_path = Path(root) / file
            rel_path = str(full_path.relative_to(base_path))
            try:
                with open(full_path, 'r') as f:
                    content = f.read()
                    yield rel_path, content
            except Exception:
                # Skip files that can't be read (e.g. binary or permissions)
                continue
