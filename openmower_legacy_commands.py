import typer

openmower_legacy_app = typer.Typer(help="OpenMower (Legacy) Commands")

@openmower_legacy_app.command()
def ping():
    typer.echo("pong (openmower_legacy_app)")