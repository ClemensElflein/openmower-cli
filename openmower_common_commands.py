import subprocess
from typing import List
from console import info
from helpers import run
import typer

openmower_common_app = typer.Typer(help="OpenMower (Legacy) Commands", no_args_is_help=True)

# Constants matching the legacy bash script
COMPOSE_FILE = "/opt/stacks/openmower/compose.yaml"
DOCKER_BIN = "/usr/bin/docker"
DEFAULT_SERVICE = "openmower"
STACK_NAME = "openmower"


def _compose_base_args() -> List[str]:
    """Build the base docker compose command with -f compose file."""
    return [DOCKER_BIN, "compose", "-f", COMPOSE_FILE]



@openmower_common_app.command()
def pull():
    """Pull image(s) for the stack."""
    info(f"Pulling compose stack images from {COMPOSE_FILE} ...")
    args = _compose_base_args() + ["pull"]
    run(args)


@openmower_common_app.command()
def start():
    """Start the stack (docker compose up -d)."""
    args = _compose_base_args() + ["up", "-d"]
    run(args)


@openmower_common_app.command()
def stop():
    """Stop the stack."""
    args = _compose_base_args() + ["stop"]
    run(args)


@openmower_common_app.command()
def restart():
    """Restart the stack."""
    args = _compose_base_args() + ["restart"]
    run(args)


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
    args = _compose_base_args() + ["exec", "-it"] + env_args + [service, "bash", "-l"]

    # For interactive, we should set the subprocess to use the current stdin/stdout/stderr (default behavior)
    run(args)
