from rich import print

def warn(message: str) -> None:
    """Print a warning message in a consistent format."""
    print(f"[bold yellow]:warning: Warning:[/bold yellow] {message}")

def info(message: str) -> None:
    """Print an info message in a consistent format."""
    print(f"[bold cyan]:information_source: Info:[/bold cyan] {message}")

def debug(message: str) -> None:
    """Print a debug message in a consistent format."""
    print(f"[bold grey]Debug:[/bold grey] {message}")

def error(message: str) -> None:
    """Print an error message in a consistent format."""
    print(f"[bold red]:cross_mark: Error:[/bold red] {message}")

def success(message: str) -> None:
    """Print a success message in a consistent format."""
    print(f"[bold green]:heavy_check_mark:[/bold green] {message}")