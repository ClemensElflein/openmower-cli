import signal
import subprocess
import os
from typing import Optional
from openmower_cli.helpers import which, run
import typer
from openmower_cli.console import info, warn, error, success

openmower_legacy_app = typer.Typer(help="OpenMower Commands (Legacy)", no_args_is_help=True)

# Map arguments to device paths
DEVICE_MAP = {
    "left": "/dev/ttyAMA4",
    "right": "/dev/ttyAMA2",
    "mower": "/dev/ttyAMA3",
}

DEFAULT_PORT = 1234

# Firmware update constants (mirror legacy bash script)
FW_URL_BASE = "https://github.com/ClemensElflein/OpenMower"
FW_URL = f"{FW_URL_BASE}/releases/download/latest/firmware"


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
            error(f"{e}")
            return 127
        except KeyboardInterrupt:
            # Our handler will flip running=False; continue to exit loop
            running = False

    return 0



@openmower_legacy_app.command("flash-pico")
def flash_pico(
    elf_path: str = typer.Argument(..., help="Path to the RP2040 firmware .elf file"),
):
    """Flash RP2040 firmware via openocd.
    - Sets RPi power GPIO 10 high using `pinctrl` if present; otherwise via sysfs; otherwise exits.
    - Calls openocd to program, verify, reset, and exit.
    """

    # Power GPIO 10 high
    if which("pinctrl"):
        info("Using pinctrl to set GPIO10 high (RPI power).")
        run(["pinctrl", "set", "10", "op", "dh"])
    elif os.path.exists("/sys/class/gpio/gpio10") or os.path.exists("/sys/class/gpio"):  # type: ignore
        try:
            if not os.path.exists("/sys/class/gpio/gpio10"):
                with open("/sys/class/gpio/export", "w") as f:
                    f.write("10")
            with open("/sys/class/gpio/gpio10/direction", "w") as f:
                f.write("out")
            with open("/sys/class/gpio/gpio10/value", "w") as f:
                f.write("1")
            info("GPIO10 set to high via sysfs.")
        except Exception as e:
            error(f"Failed to set GPIO10 via sysfs: {e}")
            raise typer.Exit(code=1)
    else:
        error("could not find a method to set RPI power gpio")
        raise typer.Exit(code=1)

    # Run openocd
    cmd = [
        "openocd",
        "-f",
        "interface/raspberrypi-swd.cfg",
        "-f",
        "target/rp2040.cfg",
        "-c",
        f"program {elf_path} verify reset exit",
    ]
    info("Starting openocd to flash firmware ...")
    run(cmd)
    success("Firmware flashed successfully.")

@openmower_legacy_app.command("openocd")
def openocd_cmd():
    """Starts openocd.
    - Sets RPi power GPIO 10 high using `pinctrl` if present; otherwise via sysfs; otherwise exits.
    - Starts openocd, so an IDE can connect to it.
    """

    # Power GPIO 10 high
    if which("pinctrl"):
        info("Using pinctrl to set GPIO10 high (RPI power).")
        run(["pinctrl", "set", "10", "op", "dh"])
    elif os.path.exists("/sys/class/gpio/gpio10") or os.path.exists("/sys/class/gpio"):  # type: ignore
        try:
            if not os.path.exists("/sys/class/gpio/gpio10"):
                with open("/sys/class/gpio/export", "w") as f:
                    f.write("10")
            with open("/sys/class/gpio/gpio10/direction", "w") as f:
                f.write("out")
            with open("/sys/class/gpio/gpio10/value", "w") as f:
                f.write("1")
            info("GPIO10 set to high via sysfs.")
        except Exception as e:
            error(f"Failed to set GPIO10 via sysfs: {e}")
            raise typer.Exit(code=1)
    else:
        error("could not find a method to set RPI power gpio")
        raise typer.Exit(code=1)

    # Run openocd
    cmd = [
        "openocd",
        "-f",
        "interface/raspberrypi-swd.cfg",
        "-f",
        "target/rp2040.cfg",
        "-c",
        "bindto 0.0.0.0",
    ]
    info("Starting openocd...")
    run(cmd)


@openmower_legacy_app.command("expose-xesc")
def serial_bridge(
    which: str = typer.Argument(..., help="Which device to bridge: left, right, mower"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help=f"TCP port to listen on (default: {DEFAULT_PORT})"),
):
    """Expose a serial device over TCP via socat (legacy behavior)."""
    device: Optional[str] = DEVICE_MAP.get(which)
    if device is None:
        valid = ", ".join(sorted(DEVICE_MAP))
        error(f"Error: Invalid argument. Valid values are: {valid}.")
        raise typer.Exit(code=2)

    code = _run_socat(port=port, device=device)
    raise typer.Exit(code=code)


@openmower_legacy_app.command("update-firmware")
def update_firmware():
    """Download the latest RP2040 firmware for the configured hardware and flash it using the system upload script.

    - Requires OM_HARDWARE_VERSION environment variable to be set (from /boot/openmower/mower_config.txt).
    - Uses a temporary directory and does not write into $HOME.
    - Downloads firmware.zip and verifies checksum against the latest release.
    - Extracts firmware/<OM_HARDWARE_VERSION>/firmware.elf into a temp file.
    - Uploads the extracted firmware.elf via openocd.
    """
    import tempfile
    import urllib.request
    import urllib.error

    import shutil
    tmp_dir = tempfile.mkdtemp(prefix="openmower-fw-")
    local_zip = os.path.join(tmp_dir, "firmware.zip")
    local_fw = os.path.join(tmp_dir, "firmware.elf")

    try:
        hw = os.getenv("OM_HARDWARE_VERSION", "").strip()
        if not hw:
            error("OM_HARDWARE_VERSION is not specified\nPlease configure it at /boot/openmower/mower_config.txt before running this command again!")
            raise typer.Exit(code=1)

        info(f"Downloading latest firmware.zip from \"{FW_URL_BASE}\"...")
        try:
            with urllib.request.urlopen(f"{FW_URL}.zip") as resp, open(local_zip, "wb") as out:
                # Stream download in chunks
                while True:
                    chunk = resp.read(1024 * 64)
                    if not chunk:
                        break
                    out.write(chunk)
        except urllib.error.URLError as e:
            error(f"Failed to download firmware.zip: {e}")
            raise typer.Exit(code=1)
        success("Firmware downloaded successfully.")

        # Extract the correct firmware.elf from the zip
        info(f"Extracting firmware for \"{hw}\"")
        import zipfile

        member_path = f"firmware/{hw}/firmware.elf"
        try:
            with zipfile.ZipFile(local_zip, "r") as zf:
                with zf.open(member_path) as src, open(local_fw, "wb") as dst:
                    dst.write(src.read())
        except KeyError:
            error(f"Firmware for hardware version '{hw}' not found in archive.")
            raise typer.Exit(code=2)
        success("Firmware extracted successfully.")

        info(f"Executing flash script with firmware \"{local_fw}\":")

        flash_pico(local_fw)

        success("Firmware updated successfully.")
    finally:
        # Always remove the temporary directory and its contents
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass
