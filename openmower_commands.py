import typer

openmower_app = typer.Typer(help="OpenMower Commands")

@openmower_app.command()
def ping():
    typer.echo("pong (v2)")