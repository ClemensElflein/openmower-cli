import hashlib
import os
import stat
import sys
import zipfile
from pathlib import Path
from typing import List, Optional

import typer

from openmower_cli.console import info, error, success, message
from openmower_cli.helpers import run, read_settings, write_settings

openmower_common_app = typer.Typer(help="OpenMower (Legacy) Commands", no_args_is_help=True)

from openmower_cli.constants import DEFAULT_GH_REPO, COMPOSE_FILE, DOCKER_BIN, DEFAULT_SERVICE, STACK_NAME, ENV_PATH, \
    MOWER_PARAMS_FILE


def _compose_base_args() -> List[str]:
    """Build the base docker compose command with -f compose file."""
    return [DOCKER_BIN, "compose", "-f", COMPOSE_FILE]


@openmower_common_app.command()
def pull():
    """Pull image(s) for the stack."""
    stop()
    info(f"Pulling compose stack images from {COMPOSE_FILE} ...")
    args = _compose_base_args() + ["pull"]
    run(args)
    # Remove unused images
    run([DOCKER_BIN, "system", "prune", "--force"])
    start()



@openmower_common_app.command()
def start():
    """Start the stack (docker compose up -d)."""
    info(f"Starting compose stack from {COMPOSE_FILE} ...")
    args = _compose_base_args() + ["up", "-d"]
    run(args)


@openmower_common_app.command()
def stop():
    """Stop the stack."""
    info(f"Stopping compose stack from {COMPOSE_FILE} ...")
    args = _compose_base_args() + ["down"]
    run(args)


@openmower_common_app.command()
def restart():
    """Restart the stack (down + up)."""
    stop()
    start()

@openmower_common_app.command("status")
def status_cmd():
    """Show stack status (docker compose ps)."""
    args = _compose_base_args() + ["ps"]
    # status in bash did not exec; we'll mirror by running and returning
    run(args)


@openmower_common_app.command("logs")
def logs_cmd(
        services: List[str] = typer.Argument(None, help="Optional service names to filter logs", show_default=False)):
    """Tail container logs. Defaults to -f --tail 100 when no service provided."""
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


@openmower_common_app.command("update-self")
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
