import typer
import openmower_cli.openmower_commands
import openmower_cli.openmower_legacy_commands
import openmower_cli.openmower_common_commands
from openmower_cli.console import warn
from openmower_cli.helpers import env_bool
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

    is_v2_hardware = env_bool("V2_HARDWARE")
    if is_v2_hardware is None:
        warn("V2_HARDWARE environment variable not set. Using legacy commands.")
        is_v2_hardware = False

    if is_v2_hardware:
        app.add_typer(openmower_cli.openmower_commands.openmower_app)
    else:
        app.add_typer(openmower_cli.openmower_legacy_commands.openmower_legacy_app)
    app.add_typer(openmower_cli.openmower_common_commands.openmower_common_app)
    return app


def _print_version_and_exit():
    typer.echo(__version__)
    raise typer.Exit()

app = create_app()

def main() -> None:
    app()

if __name__ == "__main__":
    main()
