import os
import time
import zipfile
import tempfile
from pathlib import Path
from typing import Optional

import typer
import requests

from openmower_cli.console import info, error, success, message
from openmower_cli.constants import FW_BIN_NAME, get_env, XCORE_CONFIG_FILE, BOOTLOADER_BIN_NAME
from openmower_cli.helpers import fetch_github_release_zip, run
from openmower_cli.constants import ESC_DEFAULT_PORT, GPS_DEFAULT_PORT, GPS_XCORE_PORT

openmower_app = typer.Typer(help="OpenMower Commands")

DEVICE_MAP = {
    "left": 65102,
    "mower": 65103,
    "right": 65104,
}

def _run_socat(port: int, target_ip: str, target_port: int) -> int:
    """Run socat bridging a serial device to a TCP port.

    Returns the final exit code (0 on normal completion).
    """

    info(f"Running socat for device: {target_ip}:{target_port} -> 0.0.0.0:{port} ...")
    cmd = [
        "socat",
        f"TCP-LISTEN:{port},fork",
        f"TCP:{target_ip}:{target_port}",
    ]
    run(cmd)
    return 0

@openmower_app.command()
def update_firmware(
    from_pr: Optional[int] = typer.Option(
        None,
        "--from-pr",
        help="Download firmware built for a specific pull request number.",
    ),
    from_branch: Optional[str] = typer.Option(
        None,
        "--from-branch",
        help="Download firmware built from the latest successful build on a branch.",
    ),
    firmware_file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Flash a local firmware .bin file instead of downloading one.",
    ),
    repo: Optional[str] = typer.Option(
        None,
        "--repo",
        "-r",
        help="GitHub repository in 'owner/name' form (defaults to OPENMOWER_FW_REPO env or 'xtech/fw-openmower-v2').",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        "-t",
        help="Release tag to install (e.g. 'v0.4.2'). Defaults to the latest release.",
    ),
):
    """Update mower firmware to the latest release from fw-openmower-v2.

    Steps:
    - Check FIRMWARE env variable is set (unless --file is given)
    - Download a firmware release zip from GitHub (default repo or --repo,
      latest or --tag), from the PR API when --from-pr is set, from a
      branch's latest build when --from-branch is set, or use a local .bin
      file when --file is given
    - Extract into a temp folder and locate FIRMWARE/firmware.bin (skipped when --file is given)
    - Upload via docker to the mower's xcore boot tool
    """
    if sum(x is not None for x in (firmware_file, from_pr, from_branch)) > 1:
        error("--file, --from-pr and --from-branch cannot be used together.")
        raise typer.Exit(code=2)

    if firmware_file is None and from_pr is None and from_branch is None and repo is None and tag is None:
        version = get_env("VERSION")
        if version and version != "latest":
            from_branch = "main" if version == "edge" else version
            info(f"VERSION is set to '{version}' (not 'latest') — installing firmware from branch '{from_branch}' instead of the latest release.")

    if firmware_file is not None:
        if not firmware_file.exists() or not firmware_file.is_file():
            error(f"Firmware file not found: {firmware_file}")
            raise typer.Exit(code=2)

        message(f"Using local firmware file: {firmware_file}")
        fw_dir = str(firmware_file.parent.resolve())
        fw_name = firmware_file.name

        from openmower_cli.constants import DOCKER_BIN
        message("Uploading firmware via docker ...")
        run([DOCKER_BIN, "pull", "ghcr.io/xtech/fw-xcore-boot:latest"])
        cmd = [
            DOCKER_BIN,
            "run",
            "--rm",
            "-it",
            "--network=host",
            f"-v{fw_dir}:/workdir",
            "ghcr.io/xtech/fw-xcore-boot:latest",
            "-i", "eth0", "upload", f"/workdir/{fw_name}",
        ]
        try:
            run(cmd)
        except typer.Exit:
            error("Error uploading firmware.")
            raise

        success(f"Firmware upload finished ({firmware_file}).")
        return

    firmware = get_env("FIRMWARE")
    if not firmware:
        error("Environment variable FIRMWARE is not set. Please set FIRMWARE to your firmware identifier and retry.")
        raise typer.Exit(code=2)

    if from_pr is not None and (repo is not None or tag is not None):
        error("--from-pr cannot be combined with --repo/--tag.")
        raise typer.Exit(code=2)

    from openmower_cli.constants import FW_REPO
    selected_repo = repo or FW_REPO

    # Decide source of firmware
    if from_pr is not None:
        url = f"https://api.openmower.de/v1/firmware/from-pr?pr={from_pr}"
        info(f"Fetching firmware from PR #{from_pr} ...")
        try:
            td = tempfile.TemporaryDirectory()
            tmpdir = Path(td.name)
            zip_path = tmpdir / "firmware.zip"
            with requests.get(url, stream=True, timeout=300) as resp:
                if resp.status_code != 200:
                    td.cleanup()
                    error(f"HTTP Error: {resp.status_code}")
                    raise typer.Exit(code=1)
                with open(zip_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
            resolved_tag = f"PR #{from_pr}"
            tmp_handle = td
        except Exception as e:
            error(f"Failed to fetch PR firmware")
            raise typer.Exit(code=1)
    elif from_branch is not None:
        url = f"https://api.openmower.de/v1/firmware/from-branch?branch={from_branch}"
        info(f"Fetching firmware from branch '{from_branch}' ...")
        try:
            td = tempfile.TemporaryDirectory()
            tmpdir = Path(td.name)
            zip_path = tmpdir / "firmware.zip"
            with requests.get(url, stream=True, timeout=300) as resp:
                if resp.status_code != 200:
                    td.cleanup()
                    error(f"HTTP Error: {resp.status_code}")
                    raise typer.Exit(code=1)
                with open(zip_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
            tag = f"branch '{from_branch}'"
            tmp_handle = td
        except Exception as e:
            error(f"Failed to fetch branch firmware")
            raise typer.Exit(code=1)
    else:
        info(f"Fetching firmware release {tag or 'latest'} from {selected_repo} ...")
        try:
            zip_path, resolved_tag, tmp_handle = fetch_github_release_zip(selected_repo, expected_asset_suffix=None, tag=tag)
        except Exception as e:
            error(f"Failed to fetch firmware release: {e}")
            raise typer.Exit(code=1)
        tmpdir = zip_path.parent

    # Proceed with extraction and upload
    try:
        message(f"Downloaded firmware archive: {zip_path}")
        message("Extracting firmware archive ...")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmpdir)
        except Exception as e:
            error(f"Failed to extract firmware archive: {e}")
            raise typer.Exit(code=1)
        fw_path = tmpdir / f"openmower-{firmware}.bin"
        if FW_BIN_NAME is not None:
            info(f"Using custom firmware binary file name: {FW_BIN_NAME}.")
            fw_path = tmpdir / FW_BIN_NAME

        if not fw_path.exists() or not fw_path.is_file():
            error(f"Firmware file not found at expected path: {fw_path}. Please ensure the release contains openmower-{firmware}.bin. Your FIRMWARE environment variable may be set incorrectly.")
            raise typer.Exit(code=1)

        # Run docker uploader
        message("Uploading firmware via docker ...")
        # Fetch the latest docker image
        from openmower_cli.constants import DOCKER_BIN
        run([DOCKER_BIN, "pull", "ghcr.io/xtech/fw-xcore-boot:latest"])
        # Ensure path is absolute
        fw_dir = str(fw_path.parent.resolve())
        cmd = [
            DOCKER_BIN,
            "run",
            "--rm",
            "-it",
            "--network=host",
            f"-v{fw_dir}:/workdir",
            "ghcr.io/xtech/fw-xcore-boot:latest",
            "-i", "eth0", "upload", f"/workdir/openmower-{firmware}.bin",
        ]
        try:
            run(cmd)
        except typer.Exit:
            # run already emitted messages; re-raise
            error("Error uploading firmware.")
            raise

        success(f"Firmware upload finished (release {resolved_tag or 'latest'}).")
    finally:
        # Ensure temporary download directory is removed
        try:
            tmp_handle.cleanup()
        except Exception:
            pass

@openmower_app.command("enable-bootloader-developer-mode")
def enable_bootloader_developer_mode(
    enable: bool = typer.Argument(..., help="Enable (true) or disable (false) bootloader developer mode."),
):
    """Enable or disable bootloader developer mode."""
    # Fetch the latest docker image
    from openmower_cli.constants import DOCKER_BIN
    run([DOCKER_BIN, "pull", "ghcr.io/xtech/fw-xcore-boot:latest"])

    cmd = [
        DOCKER_BIN,
        "run",
        "--rm",
        "-it",
        "--network=host",
        "ghcr.io/xtech/fw-xcore-boot:latest",
        "-i",
        "eth0",
        "set_dev_mode",
        "--enable" if enable else "--disable",
    ]
    try:
        run(cmd)
    except typer.Exit:
        # run already emitted messages; re-raise
        error("Error setting bootloader developer mode.")
        raise

    success(f"Bootloader developer mode set to {'enabled' if enable else 'disabled'}.")

def prepare_openocd_config():
    # Ensure xcore.cfg is downloaded and cached
    if not XCORE_CONFIG_FILE.exists():
        info("Downloading xcore.cfg from core.x-tech.online ...")
        try:
            XCORE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            response = requests.get("https://core.x-tech.online/downloads/openocd-xcore.cfg", timeout=30)
            response.raise_for_status()
            with open(XCORE_CONFIG_FILE, "wb") as f:
                f.write(response.content)
            success("xcore.cfg downloaded and cached successfully.")
        except requests.RequestException as e:
            error(f"Failed to download xcore.cfg: {e}")
            raise typer.Exit(code=1)
        except Exception as e:
            error(f"Failed to save xcore.cfg: {e}")
            raise typer.Exit(code=1)

@openmower_app.command()
def openocd():
    """Start openocd for xCore debugging.

    Downloads and caches xcore.cfg from core.x-tech.online if needed,
    then starts openocd listening on 0.0.0.0 so an IDE can connect to it.
    """
    prepare_openocd_config()

    # Run openocd
    cmd = [
        "openocd",
        "-f",
        str(XCORE_CONFIG_FILE),
        "-f",
        "target/stm32h7x.cfg",
        "-c",
        "bindto 0.0.0.0",
    ]
    info("Starting openocd for xCore ...")
    run(cmd)


@openmower_app.command()
def update_bootloader():
    """Update xcore bootloader to the latest release.
    """
    from openmower_cli.constants import BOOTLOADER_REPO
    repo = BOOTLOADER_REPO

    info("Fetching latest firmware release from GitHub ...")
    try:
        zip_path, tag, tmp_handle = fetch_github_release_zip(repo, expected_asset_suffix=None, tag=None)
    except Exception as e:
        error(f"Failed to fetch firmware release: {e}")
        raise typer.Exit(code=1)
    tmpdir = zip_path.parent

    # Proceed with extraction and upload
    try:
        message(f"Downloaded firmware archive: {zip_path}")
        message("Extracting firmware archive ...")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmpdir)
        except Exception as e:
            error(f"Failed to extract firmware archive: {e}")
            raise typer.Exit(code=1)
        fw_path = tmpdir / f"artifacts/bootloader/xcore-boot.elf"
        if BOOTLOADER_BIN_NAME is not None:
            info(f"Using custom firmware binary file name: {BOOTLOADER_BIN_NAME}.")
            fw_path = tmpdir / BOOTLOADER_BIN_NAME

        if not fw_path.exists() or not fw_path.is_file():
            error(f"Firmware file not found at expected path: {fw_path}. Please ensure the release contains artifacts/bootloader/xcore-boot.elf.")
            raise typer.Exit(code=1)


        prepare_openocd_config()
        # Run openocd upload
        message("Uploading firmware via openocd ...")
        # Run openocd
        cmd = [
            "openocd",
            "-f",
            str(XCORE_CONFIG_FILE),
            "-f",
            "target/stm32h7x.cfg",
            "-c",
            f"init; reset halt; stm32h7x mass_erase 0; program {fw_path.absolute()} verify reset; exit",
        ]

        try:
            run(cmd)
        except typer.Exit:
            # run already emitted messages; re-raise
            error("Error uploading firmware.")
            raise

        success(f"Firmware upload finished (release {tag or 'latest'}).")
    finally:
        # Ensure temporary download directory is removed
        try:
            tmp_handle.cleanup()
        except Exception:
            pass

@openmower_app.command("expose-xesc")
def serial_bridge(
    which: str = typer.Argument(..., help="Which device to bridge: left, right, mower"),
    port: int = typer.Option(ESC_DEFAULT_PORT, "--port", "-p", help=f"TCP port to listen on (default: {ESC_DEFAULT_PORT})"),
):
    """redirect TCP to the given ESC"""
    esc_port: Optional[int] = DEVICE_MAP.get(which)
    if esc_port is None:
        valid = ", ".join(sorted(DEVICE_MAP))
        error(f"Error: Invalid argument. Valid values are: {valid}.")
        raise typer.Exit(code=2)

    info(f"You can now run the VESC tool and connect to port {port}")
    code = _run_socat(target_ip="172.16.78.150", target_port=esc_port, port=port)
    raise typer.Exit(code=code)


@openmower_app.command("expose-gps")
def expose_gps(
    port: int = typer.Option(GPS_DEFAULT_PORT, "--port", "-p", help=f"TCP port to listen on (default: {GPS_DEFAULT_PORT})"),
):
    """Expose the xCore GPS raw-passthrough over TCP so u-center can connect."""
    info(f"You can now run u-center and connect to port {port}")
    code = _run_socat(target_ip="172.16.78.150", target_port=GPS_XCORE_PORT, port=port)
    raise typer.Exit(code=code)
