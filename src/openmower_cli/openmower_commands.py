import os
import time
import zipfile
import tempfile
from pathlib import Path
from typing import Optional

import typer
import requests

from openmower_cli.console import info, error, success, message
from openmower_cli.constants import FW_BIN_NAME, get_env, XCORE_CONFIG_FILE
from openmower_cli.helpers import fetch_github_release_zip, run

openmower_app = typer.Typer(help="OpenMower Commands")


@openmower_app.command()
def update_firmware(
    from_pr: Optional[int] = typer.Option(
        None,
        "--from-pr",
        help="Download firmware built for a specific pull request number.",
    )
):
    """Update mower firmware to the latest release from fw-openmower-v2.

    Steps:
    - Check FIRMWARE env variable is set
    - Download latest firmware release zip from GitHub (default) or from PR API when --from-pr is set
    - Extract into a temp folder and locate FIRMWARE/firmware.bin
    - Upload via docker to the mower's xcore boot tool
    """
    firmware = get_env("FIRMWARE")
    if not firmware:
        error("Environment variable FIRMWARE is not set. Please set FIRMWARE to your firmware identifier and retry.")
        raise typer.Exit(code=2)

    from openmower_cli.constants import FW_REPO
    repo = FW_REPO

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
            tag = f"PR #{from_pr}"
            tmp_handle = td
        except Exception as e:
            error(f"Failed to fetch PR firmware")
            raise typer.Exit(code=1)
    else:
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

        success(f"Firmware upload finished (release {tag or 'latest'}).")
    finally:
        # Ensure temporary download directory is removed
        try:
            tmp_handle.cleanup()
        except Exception:
            pass


@openmower_app.command()
def openocd():
    """Start openocd for xCore debugging.

    Downloads and caches xcore.cfg from core.x-tech.online if needed,
    then starts openocd listening on 0.0.0.0 so an IDE can connect to it.
    """
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
