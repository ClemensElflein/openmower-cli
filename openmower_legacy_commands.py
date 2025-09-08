import typer

openmower_legacy_app = typer.Typer(help="OpenMower Commands (Legacy)")

@openmower_legacy_app.command()
def update_firmware():
    typer.echo("Not implemented yet")