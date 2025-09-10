import os
import zipfile

import typer

from openmower_cli.console import info, error, success
from openmower_cli.helpers import fetch_github_release_zip, run

openmower_app = typer.Typer(help="OpenMower Commands")


@openmower_app.command()
def update_firmware():
    """Update mower firmware to the latest release from fw-openmower-v2.

    Steps:
    - Check MOWER env variable is set
    - Download latest firmware release zip from GitHub
    - Extract into a temp folder and locate MOWER/firmware.bin
    - Upload via docker to the mower's xcore boot tool
    """
    mower = os.environ.get("MOWER")
    if not mower:
        error("Environment variable MOWER is not set. Please set MOWER to your mower identifier and retry.")
        raise typer.Exit(code=2)

    repo = "xtech/fw-openmower-v2"

    info("Fetching latest firmware release from GitHub ...")
    try:
        zip_path, tag, tmp_handle = fetch_github_release_zip(repo, expected_asset_suffix=None, tag=None)
    except Exception as e:
        error(f"Failed to fetch firmware release: {e}")
        raise typer.Exit(code=1)

    tmpdir = zip_path.parent
    try:
        info(f"Downloaded firmware archive: {zip_path}")
        info("Extracting firmware archive ...")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmpdir)
        except Exception as e:
            error(f"Failed to extract firmware archive: {e}")
            raise typer.Exit(code=1)

        fw_path = tmpdir / f"openmower-{mower}.bin"
        if not fw_path.exists() or not fw_path.is_file():
            error(f"Firmware file not found at expected path: {fw_path}. Please ensure the release contains openmower-{mower}.bin. Your MOWER environment variable may be set incorrectly.")
            raise typer.Exit(code=1)

        # Run docker uploader
        info("Uploading firmware to mower via docker ...")
        # Ensure path is absolute
        fw_dir = str(fw_path.parent.resolve())
        cmd = [
            "/usr/bin/docker",
            "run",
            "--rm",
            "-it",
            "--network=host",
            f"-v{fw_dir}:/workdir",
            "ghcr.io/xtech/fw-xcore-boot:main",
            "upload",
            "/workdir/firmware.bin",
        ]
        try:
            run(cmd)
        except typer.Exit:
            # run already emitted messages; re-raise
            raise

        success(f"Firmware upload finished (release {tag or 'latest'}).")
    finally:
        # Ensure temporary download directory is removed
        try:
            tmp_handle.cleanup()
        except Exception:
            pass
