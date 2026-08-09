import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
import typer

from openmower_cli.console import info, warn, error, success, message
from openmower_cli.helpers import run, read_settings, write_settings, read_os_update_status, write_os_update_status

openmower_common_app = typer.Typer(help="OpenMower (Legacy) Commands", no_args_is_help=True)

from openmower_cli.constants import DEFAULT_GH_REPO, COMPOSE_FILE, DOCKER_BIN, DEFAULT_SERVICE, STACK_NAME, ENV_PATH, \
    MOWER_PARAMS_FILE, IS_NEW_OS, UPDATE_CHECK_DISABLE_FILE, get_env

ROS_SERVICE_UNIT = "openmower.service"


def _compose_base_args() -> List[str]:
    """Build the base docker compose command with -f compose file."""
    return [DOCKER_BIN, "compose", "-f", COMPOSE_FILE]


# --- ROS primitives (OSv3 only -- no-ops on the old OS, where open_mower_ros IS
# the compose service the _aux_* primitives below already manage) -------------------

def _ros_start() -> bool:
    """Start the OSv3 systemd unit and report whether it actually came up.
    No-op on the old OS, where open_mower_ros isn't a separate systemd service
    (reports success so callers don't block the compose stack below it)."""
    if not IS_NEW_OS:
        return True
    run(["systemctl", "start", ROS_SERVICE_UNIT])
    # Type=simple + ExecCondition=: `systemctl start` returns as soon as the unit is
    # forked -- or the job is skipped (exit 0, NOT a failure) if ExecCondition rejects
    # it, e.g. no mower_params.yaml yet. Check afterward rather than trusting the exit
    # code, and surface openmower-check-config's own (already correct, specific) error
    # instead of a generic "didn't start".
    if subprocess.run(["systemctl", "is-active", "--quiet", ROS_SERVICE_UNIT]).returncode != 0:
        warn(f"{ROS_SERVICE_UNIT} did not start:")
        subprocess.run(["/usr/bin/openmower-check-config"])
        return False
    success(f"{ROS_SERVICE_UNIT} started.")
    return True


def _ros_stop():
    if IS_NEW_OS:
        run(["systemctl", "stop", ROS_SERVICE_UNIT])


def _ros_status():
    if IS_NEW_OS:
        # Not helpers.run(): `systemctl status` on an inactive unit (the default --
        # openmower.service ships disabled, auto-start is deliberately off) returns
        # LSB exit code 3, and run() raises typer.Exit on any nonzero code, which
        # would abort before _aux_status() ever runs on the single most common
        # invocation (checking status before starting anything).
        subprocess.run(["systemctl", "status", ROS_SERVICE_UNIT])


# --- Aux stack primitives (both OSes -- Mosquitto/OpenMowerApp on OSv3,
# the whole stack including open_mower_ros on the old OS) ---------------------------

def _aux_start():
    info(f"Starting compose stack from {COMPOSE_FILE} ...")
    run(_compose_base_args() + ["up", "-d"])


def _aux_stop():
    info(f"Stopping compose stack from {COMPOSE_FILE} ...")
    run(_compose_base_args() + ["down"])


def _aux_status():
    run(_compose_base_args() + ["ps"])


@openmower_common_app.command()
def pull():
    """Pull image(s) for the stack."""
    # Aux images only, deliberately -- NOT _ros_start()/_ros_stop(). On OSv3
    # open_mower_ros isn't docker-pulled at all (vendored into the OS image, updated
    # via RAUC OTA instead), so restarting it here would just interrupt a live mow for
    # no reason. On the old OS this is exactly the previous stop()/pull/prune/start()
    # sequence (open_mower_ros IS one of the images _aux_stop()/_aux_start() manage).
    _aux_stop()
    info(f"Pulling compose stack images from {COMPOSE_FILE} ...")
    args = _compose_base_args() + ["pull"]
    run(args)
    # Remove unused images
    run([DOCKER_BIN, "system", "prune", "--force"])
    _aux_start()
    if IS_NEW_OS:
        info(f"Note: open_mower_ros itself updates via RAUC OTA (`update-os`), not `pull`.")



@openmower_common_app.command()
def start():
    """Start the stack (systemd service + docker compose up -d on OSv3; docker compose up -d only on the old OS)."""
    if not _ros_start():
        error(f"{ROS_SERVICE_UNIT} failed to start; not starting the docker compose stack.")
        raise typer.Exit(code=1)
    _aux_start()


@openmower_common_app.command()
def stop():
    """Stop the stack."""
    _ros_stop()
    _aux_stop()


@openmower_common_app.command()
def restart():
    """Restart the stack (down + up)."""
    stop()
    start()

@openmower_common_app.command("status")
def status_cmd():
    """Show stack status (systemd + docker compose ps on OSv3; docker compose ps only on the old OS)."""
    _ros_status()
    _aux_status()


@openmower_common_app.command("logs")
def logs_cmd(
        services: List[str] = typer.Argument(None, help="Optional service names to filter logs", show_default=False)):
    """Tail container logs. Defaults to -f --tail 100 when no service provided."""
    if not services and IS_NEW_OS:
        # Bare invocation means "the ROS stack" (same convention as shell/exec's
        # DEFAULT_SERVICE) -- open_mower_ros isn't a compose service here, its logs
        # are in the journal instead. Named services (mosquitto/openmowerapp) are
        # still real compose services, unchanged below.
        run(["journalctl", "-u", ROS_SERVICE_UNIT, "-f", "-n", "100"])
        return
    args = _compose_base_args() + ["logs"]
    if not services:
        args += ["-f", "--tail", "100"]
    else:
        args += services
    run(args)


@openmower_common_app.command("shell", context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
                              help="Open an interactive shell inside the running container or execute a command.")
@openmower_common_app.command("exec", context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
                              help="Open an interactive shell inside the running container or execute a command.")
def shell_cmd(
        ctx: typer.Context
):
    """
    Open an interactive shell inside the running container or execute a command.

    Behavior mirrors the legacy bash:
    - Default service is 'openmower'.
    - If a command is provided, run it via `docker compose exec <svc> <cmd ...>`.
    - If no command is provided, run an interactive login shell with env hints.
    """
    service = DEFAULT_SERVICE if len(ctx.args) == 0 else ctx.args[0]
    cmd = ctx.args[1:] if len(ctx.args) > 1 else None

    # open_mower_ros isn't a compose service on OSv3 -- redirect both the
    # no-args default and someone explicitly naming it out of habit (DEFAULT_SERVICE
    # itself, or "ros") to openmower-shell, the host script that actually knows how to
    # get into the vendored ROS tree (systemd-nspawn with careful device detection --
    # not replicated here). Every other service name (mosquitto/openmowerapp) falls
    # through unchanged below; those remain real compose services on OSv3 too.
    if IS_NEW_OS and service in (DEFAULT_SERVICE, "ros"):
        if cmd:
            info(f"Running `{' '.join(cmd)}` in the ROS container")
        else:
            info("Starting Shell in the ROS container")
        run(["/usr/bin/openmower-shell"] + (cmd or []))
        return

    # If command provided, do simple exec
    if cmd:
        info(f"Running `{' '.join(cmd)}` in {service}")
        args = _compose_base_args() + ["exec", service] + cmd
        run(args)
        return

    info(f"Starting Shell in {service}")
    # No command provided: open interactive bash -l with env vars and TTY
    env_args = ["-e", "STACK_SHELL=1", "-e", f"STACK_NAME={STACK_NAME}"]
    args = _compose_base_args() + ["exec", "-it"] + env_args + [service, "bash", "-il"]

    # For interactive, we should set the subprocess to use the current stdin/stdout/stderr (default behavior)
    run(args)


@openmower_common_app.command("configure", help="Edit OpenMower configuration files.")
@openmower_common_app.command("config", help="Edit OpenMower configuration files (Alias for configure).")
def configure(
    ctx: typer.Context,
    target: Optional[str] = typer.Argument(
        None,
        metavar="TARGET",
        help=(
            "What to configure.\n"
            " - 'env' -> edit the stack .env file used by Docker Compose\n"
            " - 'ros' -> edit ~/mower_params.yaml (ROS parameters)\n"
        ),
        show_default=False,
    ),
):
    """Configure OpenMower settings by editing one of the configuration files.

    Examples:
      - openmower configure env
      - openmower configure ros
      - openmower config env   (alias)

    After you save and exit the editor, if changes are detected the Docker stack
    will be restarted automatically so the new configuration takes effect.
    """
    # If no target is provided, show help for this command
    if not target:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    # Normalize and determine which file to edit
    if str(target).strip().lower() == "ros":
        file_path = MOWER_PARAMS_FILE
    else:
        file_path = Path(ENV_PATH)

    # Ensure parent dir exists; create empty file if missing
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    before_hash = None
    if file_path.exists():
        try:
            before_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except Exception:
            before_hash = None
    else:
        # Create empty file so nano can open it
        try:
            file_path.touch()
        except Exception:
            # If touch fails, still try to open nano; it may allow writing
            pass

    # Determine preferred editor from settings or prompt
    settings = read_settings()
    editor_bin = settings.get("editor")

    # If not set, prompt the user
    if not editor_bin:
        info("Select your preferred editor for configuring")
        info("We suggest 'nano' for Linux/macOS and 'mcedit' for Windows.")
        # Offer simple choices
        default_idx = 0
        prompt = f"Choose editor [1] nano, [2] mcedit: "
        try:
            ans = typer.prompt(prompt, default=str(default_idx + 1))
        except Exception:
            ans = str(default_idx + 1)
        ans = str(ans).strip()
        editor_bin = "nano" if ans in ("1", "nano") else ("mcedit" if ans in ("2", "mcedit") else "nano")
        settings["editor"] = editor_bin
        write_settings(settings)
        success(f"Saved preferred editor: {editor_bin}")

    message(f"Opening {file_path} in {editor_bin} ...")
    try:
        run([editor_bin, str(file_path)])
    except typer.Exit:
        # Propagate return code
        raise

    after_hash = None
    if file_path.exists():
        try:
            after_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except Exception:
            after_hash = None

    if before_hash != after_hash:
        info("Detected changes. Restarting Stack ...")
        restart()
        success("Stack restarted with updated environment.")
    else:
        info(f"No changes detected. Stack not restarted.")


def _read_machine_id() -> str:
    """Stable per-device id for OS update fleet tracking. Persisted across OS
    updates by openmower-persist-machine-id/openmower-machine-id.service
    (external/board/openmower-cm4/rootfs-overlay in the os repo), unlike a
    freshly-generated systemd default that would reset on reflash."""
    try:
        return Path("/etc/machine-id").read_text().strip() or "unknown"
    except Exception:
        return "unknown"


def _read_os_version() -> str:
    """Currently booted OS build version, straight from the source of truth.
    VERSION_ID is baked into /etc/os-release at image build time (os repo:
    external/board/openmower-cm4/post-build.sh) and always matches whichever
    slot is actually running -- unlike any value the CLI could cache itself,
    it's correct even after a reflash, a manual bundle install, or a rollback
    to the other slot."""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("VERSION_ID="):
                    return line.partition("=")[2].strip().strip('"') or "unknown"
    except Exception:
        pass
    return "unknown"


def _print_os_update_lookup_error(r: "requests.Response") -> None:
    """Render an /os-update error response.

    The server already picks a fitting HTTP status and a human-readable message
    for each case (see OsUpdateLookupException in the api repo: 404 no build
    triggered yet, 409 build still running, 410 build failed) - just show it, no
    client-side table mapping a reason code back to wording. 409 is the one
    transient/retryable case, so it gets a warning instead of an error.
    """
    try:
        detail = r.json().get("message")
    except Exception:
        detail = None
    detail = detail or f"HTTP Error looking up update: {r.status_code}"

    if r.status_code == 409:
        warn(detail)
    else:
        error(detail)


def _tryboot_reboot() -> None:
    """Reboot into the newly-installed RAUC slot via the Pi's tryboot mechanism
    (falls back to the previous slot automatically if the new one doesn't come up)."""
    info("Rebooting into new slot (tryboot) ...")
    try:
        os.makedirs("/run/systemd", exist_ok=True)
        with open("/run/systemd/reboot-param", "w") as f:
            f.write("0 tryboot")
    except PermissionError:
        error("Failed to set tryboot reboot param. Rerun with sudo!")
        raise typer.Exit(code=1)
    run(["systemctl", "reboot"])


def _version_env_branch() -> Optional[str]:
    """Map the VERSION env var (also used on the old OS as the open_mower_ros
    docker tag) to a branch name for OS-update lookups: 'edge' -> 'main', any
    other non-'latest' value is used as-is (a branch name). None if VERSION is
    unset or 'latest', meaning "use the latest release" (no override)."""
    version = get_env("VERSION")
    if not version or version == "latest":
        return None
    return "main" if version == "edge" else version


@openmower_common_app.command("update-os")
def update_os(
    from_pr: Optional[int] = typer.Option(
        None,
        "--from-pr",
        help="Install the RAUC bundle built for a specific pull request number.",
    ),
    from_branch: Optional[str] = typer.Option(
        None,
        "--from-branch",
        help="Install the RAUC bundle from the latest successful build on a branch.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        "-t",
        help="Release tag to install (e.g. 'v1.3.0'). Defaults to the latest release.",
    ),
    from_file: Optional[Path] = typer.Option(
        None,
        "--from-file",
        help="Install a local RAUC bundle (.raucb) instead of downloading one, then tryboot into it.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    from_url: Optional[str] = typer.Option(
        None,
        "--from-url",
        help="Download a RAUC bundle (.raucb) from an arbitrary URL and install it, bypassing api.openmower.de.",
    ),
    reboot: bool = typer.Option(
        False,
        "--reboot",
        help="Reboot into the new slot (tryboot) immediately after a successful install. Implied by --from-file.",
    ),
):
    """Install an OS update (RAUC bundle carrying open_mower_ros) via api.openmower.de,
    a local bundle via --from-file, or an arbitrary URL via --from-url.

    Steps:
    - Ask api.openmower.de for the bundle location: a PR's latest build (--from-pr),
      a branch's latest build (--from-branch), or a tagged release (--tag, defaults
      to the latest release) -- or skip the lookup entirely with --from-file/--from-url
    - Download the bundle (PR/branch builds come wrapped in a GitHub Actions artifact
      zip and must be unzipped first; release bundles and --from-url downloads are
      the raw .raucb already)
    - Install via `rauc install`

    Refuses to contact api.openmower.de (exits with an error) if
    UPDATE_CHECK_DISABLE_FILE exists; --from-file/--from-url are unaffected since
    they never hit the API.
    """
    if not IS_NEW_OS:
        error("update-os is only available on the Buildroot-based OpenMower OS.")
        raise typer.Exit(code=1)

    if from_file is not None and from_url is not None:
        error("--from-file and --from-url cannot be used together.")
        raise typer.Exit(code=2)

    if from_file is not None:
        if any(x is not None for x in (from_pr, from_branch, tag)):
            error("--from-file cannot be combined with --from-pr/--from-branch/--tag.")
            raise typer.Exit(code=2)

        message(f"Installing bundle: {from_file} ...")
        try:
            run(["rauc", "install", str(from_file)])
        except typer.Exit:
            error("rauc install failed.")
            raise
        success(f"OS update installed from {from_file}.")
        _tryboot_reboot()
        return

    if from_url is not None:
        if any(x is not None for x in (from_pr, from_branch, tag)):
            error("--from-url cannot be combined with --from-pr/--from-branch/--tag.")
            raise typer.Exit(code=2)

        info(f"Downloading bundle from {from_url} ...")
        td = tempfile.TemporaryDirectory()
        try:
            tmpdir = Path(td.name)
            bundle_path = tmpdir / "bundle.raucb"
            try:
                with requests.get(from_url, stream=True, timeout=600) as resp:
                    if resp.status_code != 200:
                        error(f"HTTP Error downloading bundle: {resp.status_code}")
                        raise typer.Exit(code=1)
                    with open(bundle_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                f.write(chunk)
            except typer.Exit:
                raise
            except Exception as e:
                error(f"Failed to download bundle: {e}")
                raise typer.Exit(code=1)

            message(f"Installing bundle: {bundle_path} ...")
            try:
                run(["rauc", "install", str(bundle_path)])
            except typer.Exit:
                error("rauc install failed.")
                raise
            success(f"OS update installed from {from_url}.")

            if reboot:
                _tryboot_reboot()
            else:
                info("Reboot to switch into the new slot: `systemctl reboot` (or pass --reboot next time).")
        finally:
            try:
                td.cleanup()
            except OSError:
                pass
        return

    if UPDATE_CHECK_DISABLE_FILE.exists():
        error(f"Update checks are disabled ({UPDATE_CHECK_DISABLE_FILE} exists), so update-os won't contact "
              "api.openmower.de. Remove that file to re-enable, or use --from-file to install a local bundle.")
        raise typer.Exit(code=1)

    if sum(x is not None for x in (from_pr, from_branch)) > 1:
        error("--from-pr and --from-branch cannot be used together.")
        raise typer.Exit(code=2)
    if tag is not None and (from_pr is not None or from_branch is not None):
        error("--tag cannot be combined with --from-pr/--from-branch.")
        raise typer.Exit(code=2)

    if from_pr is None and from_branch is None and tag is None:
        version_branch = _version_env_branch()
        if version_branch is not None:
            from_branch = version_branch
            info(f"VERSION is set to '{get_env('VERSION')}' (not 'latest') — checking branch "
                 f"'{from_branch}' instead of the latest release.")

    if from_pr is not None:
        desc = f"PR #{from_pr}"
    elif from_branch is not None:
        desc = f"branch '{from_branch}'"
    else:
        desc = f"release {tag or 'latest'}"

    request_body = {
        "machine-id": _read_machine_id(),
        "current-version": _read_os_version(),
    }
    if from_pr is not None:
        request_body["pr"] = from_pr
    elif from_branch is not None:
        request_body["branch"] = from_branch
    elif tag is not None:
        request_body["tag"] = tag

    info(f"Looking up OS update for {desc} ...")
    try:
        r = requests.post("https://api.openmower.de/v1/os-update", json=request_body, timeout=30)
        if r.status_code != 200:
            _print_os_update_lookup_error(r)
            raise typer.Exit(code=1)
        payload = r.json()
    except typer.Exit:
        raise
    except Exception as e:
        error(f"Failed to look up OS update: {e}")
        raise typer.Exit(code=1)

    version = payload.get("version")
    download_url = payload.get("download-url")
    proxied = payload.get("proxied")
    if not download_url:
        error("Update lookup response did not include a download-url.")
        raise typer.Exit(code=1)

    info(f"Found version {version}. Downloading ...")
    td = tempfile.TemporaryDirectory()
    try:
        tmpdir = Path(td.name)
        dl_path = tmpdir / "bundle.download"
        try:
            with requests.get(download_url, stream=True, timeout=600) as resp:
                if resp.status_code != 200:
                    error(f"HTTP Error downloading bundle: {resp.status_code}")
                    raise typer.Exit(code=1)
                with open(dl_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
        except typer.Exit:
            raise
        except Exception as e:
            error(f"Failed to download bundle: {e}")
            raise typer.Exit(code=1)

        if proxied:
            # PR/branch builds: a GitHub Actions artifact, always a zip wrapper
            # around the .raucb (and the signed URL we just used is short-lived,
            # already spent by the download above).
            message("Extracting bundle from artifact zip ...")
            try:
                with zipfile.ZipFile(dl_path) as zf:
                    zf.extractall(tmpdir)
            except Exception as e:
                error(f"Failed to extract bundle archive: {e}")
                raise typer.Exit(code=1)
            candidates = sorted(tmpdir.glob("openmower-*.raucb"))
            if not candidates:
                error("No .raucb bundle found inside the downloaded artifact.")
                raise typer.Exit(code=1)
            bundle_path = candidates[0]
        else:
            bundle_path = dl_path

        message(f"Installing bundle: {bundle_path} ...")
        try:
            run(["rauc", "install", str(bundle_path)])
        except typer.Exit:
            error("rauc install failed.")
            raise
        success(f"OS update to version {version} installed.")

        if reboot:
            _tryboot_reboot()
        else:
            info("Reboot to switch into the new slot: `systemctl reboot` (or pass --reboot next time).")
    finally:
        try:
            td.cleanup()
        except Exception:
            pass


@openmower_common_app.command("check-os-update", hidden=True)
def check_os_update():
    """Check api.openmower.de for a newer OS release and record the result to
    OS_UPDATE_STATUS_FILE for `warn_if_os_update_available()` (CLI startup) to
    pick up -- no download, no install, no output on a normal run. Meant to be
    run once a day by openmower-check-update.timer (os repo), not by hand.

    Compares by string equality against the latest published release tag, not
    a semver/newer-than check: current-version can be a real release tag or a
    dev-build timestamp (see os repo's post-build.sh), and the two aren't
    comparable on the same scale. Not being on the exact latest tag is enough
    to flag "update available" either way.

    Respects VERSION (see _version_env_branch()): if set to something other
    than 'latest', checks against that branch's latest build instead of the
    latest release, same as `update-os` does.

    Never raises: a systemd timer running this unattended shouldn't show up
    as a failed unit over a transient network hiccup, same reasoning as
    check_for_update_if_needed's self-update check. On failure, leaves any
    previously recorded latest_version/update_available untouched.

    Opt-out: skips entirely (leaves OS_UPDATE_STATUS_FILE untouched) if
    UPDATE_CHECK_DISABLE_FILE exists. The timer unit already has its own
    ConditionPathExists=! for the same file so it usually won't even get
    this far, but this makes a direct `openmower check-os-update` respect
    it too.
    """
    if not IS_NEW_OS or UPDATE_CHECK_DISABLE_FILE.exists():
        return

    current_version = _read_os_version()
    status = {"current_version": current_version, "checked_at": datetime.now().isoformat()}
    previous = read_os_update_status()
    status["latest_version"] = previous.get("latest_version")
    status["update_available"] = previous.get("update_available", False)

    try:
        request_body = {"machine-id": _read_machine_id(), "current-version": current_version}
        version_branch = _version_env_branch()
        if version_branch is not None:
            request_body["branch"] = version_branch
        r = requests.post("https://api.openmower.de/v1/os-update", json=request_body, timeout=30)
        if r.status_code == 200:
            latest_version = r.json().get("version")
            status["latest_version"] = latest_version
            status["update_available"] = bool(latest_version) and latest_version != current_version
    except Exception:
        pass

    write_os_update_status(status)


@openmower_common_app.command("update-self", hidden=IS_NEW_OS)
def self_update(
        version: Optional[str] = typer.Option(None, "--version", "-v",
                                              help="Update to a specific tag (e.g., v1.2.3). Defaults to the latest release."),
        repo: str = typer.Option(DEFAULT_GH_REPO, "--repo",
                                 help="GitHub repo slug 'owner/name' to fetch releases from."),
        dry_run: bool = typer.Option(False, "--dry-run",
                                     help="Only check and print what would be done; do not modify files."),
):
    """Self-update the openmower zipapp from GitHub Releases.

    This command downloads the latest (or specified) release artifact and replaces the currently running
    zipapp executable with the new version.
    """
    if IS_NEW_OS:
        error("update-self is not available on the Buildroot-based OpenMower OS: the CLI ships as part of "
              "the OS image and updates together with it via `update-os`.")
        raise typer.Exit(code=1)

    exe_path = Path(sys.argv[0]).resolve()
    if not exe_path.exists():
        error(f"Cannot resolve current executable path: {exe_path}")
        raise typer.Exit(code=1)

    # Basic heuristic: shiv-built artifact is a zipapp. This should be True for our distribution.
    try:
        is_zip = zipfile.is_zipfile(exe_path)
    except Exception:
        is_zip = False
    if not is_zip:
        error(f"Current executable does not look like a zipapp: {exe_path}. Exiting.")
        raise typer.Exit(code=1)

    from openmower_cli.helpers import fetch_github_release_zip

    info("Fetching release artifact from GitHub ...")
    try:
        # We expect asset name to end with .zip; our helper will pick first zip if multiple
        zip_path, tag_name, tmp_handle = fetch_github_release_zip(repo, expected_asset_suffix=None, tag=version)
    except Exception as e:
        error(str(e))
        raise typer.Exit(code=1)
    message(f"Downloaded release zip: {zip_path}")

    try:
        if dry_run:
            info("Dry-run: would extract and replace current executable")
            return

        # Extract and locate the shiv executable (likely named 'openmower')
        td = zip_path.parent
        message("Extracting artifact ...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(td)

        new_bin = td / "openmower"
        if not new_bin.exists() or not new_bin.is_file():
            error("Failed to locate 'openmower' executable inside the downloaded ZIP.")
            raise typer.Exit(code=1)

        # Ensure executable permissions
        st = os.stat(new_bin)
        os.chmod(new_bin, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # Replace current executable atomically
        message(f"Updating {exe_path} ...")
        try:
            # Write to a temp path in the same directory for atomic replace
            target_dir = exe_path.parent
            tmp_target = target_dir / (exe_path.name + ".tmp")
            # Copy contents
            with open(new_bin, 'rb') as src, open(tmp_target, 'wb') as dst:
                while True:
                    chunk = src.read(1024 * 256)
                    if not chunk:
                        break
                    dst.write(chunk)
            # Preserve executable bits
            st = os.stat(tmp_target)
            os.chmod(tmp_target, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            os.replace(tmp_target, exe_path)
        except PermissionError as e:
            error(f"Failed to update executable. Rerun with sudo!")
            raise typer.Exit(code=1)
        success(f"Updated successfully to {tag_name or 'latest'}. Please re-run the command.")
    finally:
        # Always cleanup temporary download directory
        try:
            tmp_handle.cleanup()
        except Exception:
            pass
