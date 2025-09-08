import signal
import subprocess
from typing import Optional

import typer
from console import info, warn

openmower_legacy_app = typer.Typer(help="OpenMower Commands (Legacy)", no_args_is_help=True)

# Map arguments to device paths
DEVICE_MAP = {
    "left": "/dev/ttyAMA4",
    "right": "/dev/ttyAMA2",
    "mower": "/dev/ttyAMA3",
}

DEFAULT_PORT = 1234


def _run_socat(port: int, device: str) -> int:
    """Run socat in a loop like the bash script until interrupted.

    Returns the final exit code (0 for graceful Ctrl-C).
    """
    running = True

    def _handle_sigint(signum, frame):
        nonlocal running
        info("Interrupt received! Stopping...")
        running = False

    # Register SIGINT handler
    signal.signal(signal.SIGINT, _handle_sigint)

    info(f"Running socat for device: {device} on port: {port} ...")

    # Loop to restart socat similar to `while $running; do ... || true; done`
    while running:
        cmd = [
            "sudo",
            "socat",
            f"TCP-LISTEN:{port},reuseaddr,fork",
            f"FILE:{device},b115200,cs8,raw,echo=0",
        ]
        try:
            subprocess.run(cmd)
        except FileNotFoundError as e:
            typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
            return 127
        except KeyboardInterrupt:
            # Our handler will flip running=False; continue to exit loop
            running = False

    return 0


@openmower_legacy_app.command("expose-xesc")
def serial_bridge(
    which: str = typer.Argument(..., help="Which device to bridge: left, right, mower"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help=f"TCP port to listen on (default: {DEFAULT_PORT})"),
):
    """Expose a serial device over TCP via socat (legacy behavior)."""
    device: Optional[str] = DEVICE_MAP.get(which)
    if device is None:
        valid = ", ".join(sorted(DEVICE_MAP))
        typer.secho(
            f"Error: Invalid argument. Valid values are: {valid}.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    code = _run_socat(port=port, device=device)
    raise typer.Exit(code=code)