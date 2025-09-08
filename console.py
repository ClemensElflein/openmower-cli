from rich import print

def warn(message: str) -> None:
    """Print a warning message in a consistent format."""
    print(f"[bold yellow]:warning: Warning:[/bold yellow] {message}")