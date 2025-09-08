import typer
import openmower_commands
import openmower_legacy_commands
import openmower_common_commands
from console import warn
from helpers import env_bool

def create_app():
    app = typer.Typer(no_args_is_help=True, add_completion=False, help="OpenMower Command Line Interface")
    is_v2_hardware = env_bool("V2_HARDWARE")
    if is_v2_hardware is None:
        warn("V2_HARDWARE environment variable not set. Using legacy commands.")
        is_v2_hardware = False

    if is_v2_hardware:
        app.add_typer(openmower_commands.openmower_app)
    else:
        app.add_typer(openmower_legacy_commands.openmower_legacy_app)
    app.add_typer(openmower_common_commands.openmower_common_app)
    return app


app = create_app()

if __name__ == "__main__":
    app()
