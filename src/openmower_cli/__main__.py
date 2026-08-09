import os
import typer
import openmower_cli.openmower_commands
import openmower_cli.openmower_legacy_commands
import openmower_cli.openmower_common_commands
from openmower_cli.console import warn
from openmower_cli.constants import HARDWARE_PLATFORM, IS_NEW_OS
from openmower_cli import __version__

def create_app():
    app = typer.Typer(
        no_args_is_help=True,
        add_completion=True,
        help="OpenMower Command Line Interface",
    )

    # Add a global --version option
    @app.callback()
    def _version_callback(
        version: bool = typer.Option(
            None,
            "--version",
            help="Show the OpenMower CLI version and exit.",
            callback=lambda v: (_print_version_and_exit() if v else None),
            is_eager=True,
        )
    ):
        pass

    # Perform a lightweight update check at startup (at most once every 7 days)
    try:
        from openmower_cli.helpers import check_for_update_if_needed
        check_for_update_if_needed(__version__)
    except Exception:
        # Never block startup for update checks
        pass

    # Surface openmower-check-update.timer's daily OS-update result, if any
    # (os repo; only relevant/present on the Buildroot-based OS). Reads a
    # local flag file, no network call here.
    if IS_NEW_OS:
        try:
            from openmower_cli.helpers import warn_if_os_update_available
            warn_if_os_update_available()
        except Exception:
            pass

    if HARDWARE_PLATFORM is None:
        warn("HARDWARE_PLATFORM environment variable not set. Using legacy commands.")
        is_v2_hardware = False
    elif HARDWARE_PLATFORM not in ["1", "2"]:
        warn(f"Unknown hardware platform: {HARDWARE_PLATFORM}. Using legacy commands.")
        is_v2_hardware = False
    else:
        is_v2_hardware = HARDWARE_PLATFORM == "2"

    if is_v2_hardware:
        app.add_typer(openmower_cli.openmower_commands.openmower_app)
    else:
        app.add_typer(openmower_cli.openmower_legacy_commands.openmower_legacy_app)
    app.add_typer(openmower_cli.openmower_common_commands.openmower_common_app)

    # Provide `help` as an alias for `--help`
    @app.command("help")
    def _help_cmd(ctx: typer.Context):
        """Show this help message (alias for --help)."""
        parent = ctx.parent
        if parent is not None:
            typer.echo(parent.get_help())
        else:
            typer.echo(ctx.get_help())
        raise typer.Exit()

    return app


def _print_version_and_exit():
    typer.echo(__version__)
    raise typer.Exit()

app = create_app()

def main() -> None:
    # Keep --install-completion/--show-completion working, but drop them from
    # --help -- shell completion setup isn't something a normal user needs to see.
    import typer.main as typer_main
    command = typer_main.get_command(app)
    for param in command.params:
        if param.name in ("install_completion", "show_completion"):
            param.hidden = True
    command()

if __name__ == "__main__":
    main()
