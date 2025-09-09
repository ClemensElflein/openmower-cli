# OpenMower CLI

OpenMower CLI is a Python command line tool to manage and interact with the OpenMower software stack. It provides commands for day‑to‑day operations (pull, start, stop, restart, logs, shell/exec), legacy utilities, and a self‑update mechanism for the distributed zipapp binary.


## Features
- Manage OpenMower Docker Compose stack:
  - pull, start, stop, restart, status, logs
  - exec/shell into services
- Legacy commands for hardware/firmware workflows (subject to change)
- Self-update from GitHub Releases when using the zipapp distribution
- Rich, user-friendly console output

## Requirements
- Python 3.10+
- Docker with Docker Compose plugin (for stack management commands)
- Access to the OpenMower compose file (default: `/opt/stacks/openmower/compose.yaml`)

## Installation
Prebuilt zipapp artifacts may be published on GitHub Releases for convenient distribution. Download the `openmower` artifact from the repo releases page, make it executable and run it directly:
```bash
chmod +x ./openmower
./openmower --help
```
You can then keep it up to date via the built-in self-update command described below.

## Usage
Once installed, the main entry point is the `openmower` command.

```bash
openmower --help
openmower --version
```

The CLI selects command groups based on the environment variable `V2_HARDWARE`:
- If `V2_HARDWARE` is true-like (e.g., `1`, `true`, `yes`), commands under the newer `openmower` group are enabled.
- Otherwise, legacy commands are used. If the variable is not set, a warning is printed and legacy commands are used by default.

### Common stack commands
These commands manage the Docker Compose stack referenced by `/opt/stacks/openmower/compose.yaml`.

- Pull images:
  ```bash
  openmower pull
  ```
- Start services (detached):
  ```bash
  openmower start
  ```
- Stop services:
  ```bash
  openmower stop
  ```
- Restart services:
  ```bash
  openmower restart
  ```
- Status (compose ps):
  ```bash
  openmower status
  ```
- Logs (follow, last 100 lines by default):
  ```bash
  openmower logs
  # or specify services
  openmower logs openmower another-service
  ```
- Exec/Shell into a service (defaults to service `openmower` if none provided):
  ```bash
  # Interactive shell
  openmower shell

  # Shell into specific service
  openmower shell ros

  # Execute a command inside a service
  openmower exec ros bash -lc 'echo Hello && env | sort'
  ```

Notes:
- The CLI uses `/usr/bin/docker compose -f /opt/stacks/openmower/compose.yaml ...` under the hood.
- Ensure your user can run Docker commands (e.g., part of the `docker` group) or run with appropriate privileges.

### Self-update (zipapp distribution)
If you run the zipapp build (a single-file `openmower` executable), you can self-update from GitHub releases:
```bash
openmower self-update                  # update to latest release
openmower self-update -v v1.2.3        # update to specific tag
openmower self-update --repo owner/repo # override repo (defaults to ClemensElflein/openmower-cli)
openmower self-update --dry-run        # show what would be done
```
The command replaces the currently running zipapp with the downloaded version atomically.

## Development
Clone and install in editable mode:
```bash
git clone https://github.com/ClemensElflein/openmower-cli.git
cd openmower-cli
python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e .
```
Run the CLI from source:
```bash
openmower --help
```

Linting and formatting are managed via pre-commit hooks (a `pre-commit` helper script is present). You may install and run them locally if desired.

## Troubleshooting
- Docker not found: ensure `/usr/bin/docker` exists or adjust your environment to provide Docker with the compose plugin.
- Permission errors with Docker: add your user to the `docker` group or run with sufficient privileges.
- V2 hardware commands missing: set `V2_HARDWARE=1` to enable the new command group (currently minimal placeholder implementation).
- Self-update says executable is not a zipapp: the feature is only for the packaged zipapp artifact; when running from source or pip install, use your package manager to update instead.

## License
This project is licensed under the terms of the LICENSE file included in this repository.

## Acknowledgements
Built with:
- Typer for CLI composition
- Rich for styled console output
