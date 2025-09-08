import os
import subprocess
from typing import List, Optional

import typer

TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}

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
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
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