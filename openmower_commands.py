import typer

openmower_app = typer.Typer(help="OpenMower Commands")

@openmower_app.command()
def update_firmware():
    typer.echo("Not implemented yet")